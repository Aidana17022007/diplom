"""Release packaging ships current source and verified data, without local state."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


SPEC = importlib.util.spec_from_file_location("package_release", Path(__file__).resolve().parents[1] / "scripts/package_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def project(root):
    """A tiny valid project; no real records, model loading or training."""
    for folder in release.FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)
    for name in release.REQUIRED:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    (root / "frontend/dist/index.html").write_text('<script type="module" src="/assets/main.js"></script>')
    (root / "frontend/dist/assets").mkdir()
    (root / "frontend/dist/assets/main.js").write_text("/* built fixture */")
    (root / "deployment/cardio-site/client/src").mkdir(parents=True)
    (root / "deployment/cardio-site/client/src/main.tsx").write_bytes(b"fixture")
    for name in ("data/thesis-topic.json", "reports/thesis-topic.json", "deployment/cardio-site/data/thesis-topic.json"):
        (root / name).write_text(json.dumps({"title": "fixture"}))
    (root / "reports/sources.json").write_text(json.dumps([{"file": "LLCP2023XPT.zip", "sha256": digest(b"original")}]))
    record = {"frozen_files_unchanged": True, "datasets": {
        "uci": {"n": 303, "processed_sha256": digest(b"fixture"), "source_sha256": digest(b"fixture"), "oof_row_ids_and_targets_match": True},
        "brfss": {"n": 428738, "processed_sha256": digest(b"fixture"), "source_sha256": digest(b"original"),
                  "source_matches_archived_fingerprint": True, "split_row_ids_match": True,
                  "test_targets_and_weights_match": True, "train_n": 342990, "test_n": 85748,
                  "max_frozen_probability_delta": 1e-16}}}
    (root / "data/processed/recovery-manifest.json").write_text(json.dumps(record))
    return root


def test_current_application_zip_excludes_runtime_state_and_preserves_existing_release(tmp_path):
    root = project(tmp_path / "project")
    excluded = ["frontend/.env.production", "frontend/node_modules/untrusted.js", "reports/experiments.sqlite",
                "scripts/__pycache__/pack.pyc", "deployment/cardio-site/dist/server/index.js",
                "deployment/cardio-site/public/index.html", "deployment/cardio-site/.openai/credentials.json",
                "deployment/cardio-site/client/dist/index.html", "output/thesis.pdf", "scripts/previous.zip"]
    for name in excluded:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"private-or-generated-fixture")
    destination = tmp_path / "release.zip"
    result = release.package_release(root, destination)
    assert result["sha256"] == release.sha256(destination)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {release.PREFIX + name for name in release.REQUIRED} <= names
        assert not names.intersection(release.PREFIX + name for name in excluded)
        assert archive.read("CardioResearch/data/processed/brfss.pkl") == b"fixture"
        assert archive.read("CardioResearch/frontend/dist/assets/main.js") == b"/* built fixture */"
        manifest = json.loads(archive.read("CardioResearch/RELEASE_CONTENTS.json"))
        for entry in manifest["files"]:
            assert digest(archive.read(release.PREFIX + entry["path"])) == entry["sha256"]
    before = destination.read_bytes()
    with pytest.raises(FileExistsError, match="preserved"):
        release.package_release(root, destination)
    assert destination.read_bytes() == before


def test_changed_processed_data_and_missing_browser_assets_block_packaging(tmp_path):
    root = project(tmp_path / "project")
    destination = tmp_path / "release.zip"
    (root / "data/processed/uci.pkl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="recovery fingerprint"):
        release.package_release(root, destination)
    assert not destination.exists()
    (root / "data/processed/uci.pkl").write_bytes(b"fixture")
    (root / "frontend/dist/assets/main.js").unlink()
    with pytest.raises(ValueError, match="missing asset"):
        release.package_release(root, destination)
    assert not destination.exists()


def test_out_of_sync_frontend_and_topic_are_rejected(tmp_path):
    root = project(tmp_path / "project")
    (root / "deployment/cardio-site/client/src/main.tsx").write_bytes(b"stale")
    with pytest.raises(ValueError, match="frontend sources differ"):
        release.verify_sources(root, release.collect(root))
    (root / "deployment/cardio-site/client/src/main.tsx").write_bytes(b"fixture")
    (root / "data/thesis-topic.json").write_text('{}')
    with pytest.raises(ValueError, match="topic is out of sync"):
        release.verify_sources(root, release.collect(root))
