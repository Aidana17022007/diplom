"""Package the current runnable application without rewriting old releases.

Includes source, frozen model artifacts, verified processed public datasets,
research reports and the built local frontend. No manuscript output, credentials,
environment, runtime database or duplicate generated hosted bundle is included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "CardioResearch/"
FOLDERS = ("cardio", "frontend", "models", "reports", "assets", "tests", "scripts",
           "deployment/cardio-site", "data/processed")
FILES = ("README.md", "requirements.txt", "requirements-tested.txt", "run.ps1",
         "runtime.ps1", "setup.ps1", "START.cmd", "CHECK.cmd", "REPRODUCE.cmd",
         "Dockerfile", "compose.yaml", ".dockerignore", ".gitignore",
         "OPEN_SITE.url", "open_site.ps1", "data/thesis-topic.json",
         "data/raw/codebook.html", "data/raw/uci_description.txt")
SKIP_DIRS = frozenset({"node_modules", ".git", ".hg", ".svn", ".venv", "venv", "env",
                       "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                       ".cache", ".sites-runtime", ".wrangler", ".codex", ".agents",
                       ".aws", ".ssh", ".vscode", ".idea", "tmp", "temp", "logs"})
SKIP_TREES = ("deployment/cardio-site/dist", "deployment/cardio-site/client/dist",
              "deployment/cardio-site/src/generated", "deployment/cardio-site/public",
              "reports/experiment_lab_runs")
SKIP_SUFFIXES = (".pyc", ".pyo", ".tsbuildinfo", ".log", ".sqlite", ".sqlite3",
                 ".sqlite-wal", ".sqlite-shm", ".db", ".db-wal", ".db-shm",
                 ".zip", ".tar", ".tar.gz", ".tgz", ".7z", ".rar",
                 ".pem", ".key", ".pfx", ".p12")
PRIVATE_NAMES = frozenset({".npmrc", ".pypirc", ".netrc", "credentials", "credentials.json",
                           "secrets.json", "token.json", "tokens.json", "id_rsa", "id_ed25519"})
REQUIRED = frozenset({"cardio/api.py", "frontend/dist/index.html", "frontend/src/main.tsx",
                     "frontend/package.json", "frontend/package-lock.json", "models/brfss.joblib",
                     "models/uci.joblib", "models/brfss_background.joblib", "models/uci_background.joblib",
                     "data/processed/brfss.pkl", "data/processed/uci.pkl",
                     "data/processed/recovery-manifest.json", "data/processed/uci_centers_audit.csv",
                     "data/thesis-topic.json", "reports/thesis-topic.json", "reports/sources.json",
                     "reports/evaluation.json", "reports/brfss_results.json", "reports/uci_results.json",
                     "deployment/cardio-site/data/thesis-topic.json", "deployment/cardio-site/package.json",
                     "deployment/cardio-site/.openai/hosting.json", "deployment/cardio-site/src/worker.js",
                     "setup.ps1", "runtime.ps1", "START.cmd", "README.md"})


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def is_reparse(path: Path) -> bool:
    """Do not traverse Windows junctions or Unix symbolic links."""
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) &
                                     getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def contains_reparse(path: Path, root: Path) -> bool:
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if is_reparse(current):
            return True
    return False


def excluded(relative: str) -> bool:
    parts = Path(relative).parts
    lower = relative.replace("\\", "/").lower()
    name = parts[-1].lower()
    return (any(part.lower() in SKIP_DIRS for part in parts)
            or any(lower == tree or lower.startswith(tree + "/") for tree in SKIP_TREES)
            or name.startswith(".env") or name in PRIVATE_NAMES
            or name.endswith(SKIP_SUFFIXES)
            or ("credential" in name and name.endswith(".json"))
            or ".secrets." in name
            or (".openai" in (part.lower() for part in parts)
                and lower not in {"deployment/cardio-site/.openai", "deployment/cardio-site/.openai/hosting.json"}))


def collect(root: Path) -> list[Path]:
    paths = set()
    for folder in FOLDERS:
        start = root / folder
        if not start.is_dir() or contains_reparse(start, root):
            raise ValueError(f"Required real source directory is missing or linked: {folder}")
        for directory, children, names in os.walk(start, followlinks=False):
            base = Path(directory)
            children[:] = sorted(name for name in children
                                 if not is_reparse(base / name)
                                 and not excluded((base / name).relative_to(root).as_posix()))
            for name in names:
                path = base / name
                relative = path.relative_to(root).as_posix()
                if not is_reparse(path) and not excluded(relative):
                    paths.add(path)
    for name in FILES:
        path = root / name
        if path.is_file() and not contains_reparse(path, root):
            paths.add(path)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def verify_sources(root: Path, paths: list[Path]) -> dict:
    names = {path.relative_to(root).as_posix() for path in paths}
    missing = REQUIRED - names
    if missing:
        raise ValueError(f"Release is incomplete; missing: {', '.join(sorted(missing))}")
    recovery = json.loads((root / "data/processed/recovery-manifest.json").read_text(encoding="utf-8-sig"))
    if recovery.get("frozen_files_unchanged") is not True:
        raise ValueError("Processed data do not have a verified frozen-input recovery record")
    for dataset, rows in (("uci", 303), ("brfss", 428738)):
        item = recovery["datasets"][dataset]
        if item["n"] != rows or sha256(root / f"data/processed/{dataset}.pkl") != item["processed_sha256"]:
            raise ValueError(f"{dataset} table does not match its verified recovery fingerprint")
    uci, brfss = recovery["datasets"]["uci"], recovery["datasets"]["brfss"]
    sources = json.loads((root / "reports/sources.json").read_text(encoding="utf-8-sig"))
    brfss_source = next(item for item in sources if item["file"] == "LLCP2023XPT.zip")
    if not uci.get("oof_row_ids_and_targets_match") or uci["source_sha256"] != sha256(root / "data/processed/uci_centers_audit.csv"):
        raise ValueError("UCI source/OOF provenance check failed")
    if (brfss["source_sha256"] != brfss_source["sha256"] or
            not all(brfss.get(key) is True for key in ("source_matches_archived_fingerprint", "split_row_ids_match", "test_targets_and_weights_match")) or
            brfss["train_n"] != 342990 or brfss["test_n"] != 85748 or
            not 0 <= brfss["max_frozen_probability_delta"] <= 1e-12):
        raise ValueError("BRFSS source/frozen-prediction parity check failed")
    canonical_topic = json.loads((root / "reports/thesis-topic.json").read_text(encoding="utf-8-sig"))
    for name in ("data/thesis-topic.json", "deployment/cardio-site/data/thesis-topic.json"):
        if json.loads((root / name).read_text(encoding="utf-8-sig")) != canonical_topic:
            raise ValueError(f"Canonical project topic is out of sync: {name}")
    for name in sorted(names):
        if name.startswith("frontend/src/"):
            other = root / "deployment/cardio-site/client/src" / name.removeprefix("frontend/src/")
            if not other.is_file() or sha256(root / name) != sha256(other):
                raise ValueError(f"Local and hosted frontend sources differ: {name}")
        elif name.startswith("deployment/cardio-site/client/src/"):
            other = "frontend/src/" + name.removeprefix("deployment/cardio-site/client/src/")
            if other not in names:
                raise ValueError(f"Hosted-only frontend source is not synchronized: {name}")
    # Check the built document's local script/style dependencies before shipping it.
    from html.parser import HTMLParser
    class Assets(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attr = dict(attrs)
            reference = attr.get("src") if tag == "script" else attr.get("href") if tag == "link" else None
            if reference and not reference.startswith(("http:", "https:", "data:", "//")):
                asset = reference.split("?", 1)[0].split("#", 1)[0].lstrip("/")
                if asset and f"frontend/dist/{asset}" not in names:
                    raise ValueError(f"Built frontend references a missing asset: {reference}")
    Assets().feed((root / "frontend/dist/index.html").read_text(encoding="utf-8-sig"))
    return recovery


def package_release(root: Path, destination: Path) -> dict:
    if not destination.is_absolute():
        raise ValueError("--output must be an absolute ZIP path")
    root = root.resolve()
    destination = destination.resolve()
    if destination.suffix.lower() != ".zip":
        raise ValueError("--output must end in .zip")
    if destination.exists():
        raise FileExistsError(f"Existing release is preserved: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {destination.parent}")
    paths = collect(root)
    recovery = verify_sources(root, paths)
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                "sha256": sha256(path)} for path in paths]
    manifest = {"schema_version": 1, "project": "CardioResearch", "kind": "runnable-application",
                "processed_data_verified": True, "manuscript_output_included": False,
                "files": entries,
                "excluded": {"directories": sorted(SKIP_DIRS), "trees": list(SKIP_TREES),
                             "suffixes": list(SKIP_SUFFIXES),
                             "other": ["symbolic links and Windows reparse points", "output/ (manuscript artifacts)",
                                       "unlisted root files and raw archives", ".env* and credential/key files",
                                       ".openai files except public hosting.json"]}}
    # Build beside the destination, then publish only after CRC/hash verification.
    fd, temporary_name = tempfile.mkstemp(prefix=".cardio-release-", suffix=".zip", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, item in zip(paths, entries):
                archive.write(path, PREFIX + item["path"])
            archive.writestr(PREFIX + "RELEASE_CONTENTS.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        with zipfile.ZipFile(temporary) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"ZIP CRC verification failed: {bad}")
            names = archive.namelist()
            if len(names) != len(set(names)) or not {PREFIX + name for name in REQUIRED}.issubset(names):
                raise ValueError("Release has duplicate or missing required entries")
            for item in entries:
                with archive.open(PREFIX + item["path"]) as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != item["sha256"]:
                    raise ValueError(f"Source changed while packaging: {item['path']}")
            for dataset in ("uci", "brfss"):
                digest = next(item["sha256"] for item in entries if item["path"] == f"data/processed/{dataset}.pkl")
                if digest != recovery["datasets"][dataset]["processed_sha256"]:
                    raise ValueError(f"Processed dataset changed while packaging: {dataset}")
        # Exclusive creation works on Windows without hard-link privileges and
        # refuses an existing destination, including a concurrent new release.
        import shutil
        created = False
        try:
            with temporary.open("rb") as source, destination.open("xb") as output:
                created = True
                shutil.copyfileobj(source, output)
            if sha256(destination) != sha256(temporary):
                raise ValueError("Release copy did not retain the verified ZIP hash")
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise
        return {"archive": str(destination), "bytes": destination.stat().st_size,
                "sha256": sha256(destination), "entries": len(entries) + 1,
                "verified": ["required contents", "ZIP CRC", "all entry SHA-256", "processed-data provenance", "frontend source parity", "built entrypoint dependencies"],
                "manuscript_output_included": False}
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New absolute ZIP path; existing archives are never overwritten")
    args = parser.parse_args()
    result = package_release(ROOT, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
