"""Render the recorded experimental evidence as an auxiliary PDF and editable HTML.

No model is fitted, no result is inferred, and the source JSON is never modified.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether,
)
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/technical_evidence_tables.json"
OUT = ROOT / "output/pdf"
PDF = OUT / "ENU_Experimental_materials_KZ.pdf"
HTML = OUT / "ENU_Experimental_materials_KZ.html"
WIDTH = 170 * mm
FONT = Path("C:/Windows/Fonts")
for name, file in [("TNR", "times.ttf"), ("TNR-Bold", "timesbd.ttf"),
                   ("TNR-Italic", "timesi.ttf"), ("TNR-BoldItalic", "timesbi.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONT / file)))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic", boldItalic="TNR-BoldItalic")

STYLES = {
    "body": ParagraphStyle("body", fontName="TNR", fontSize=14, leading=16.2, spaceAfter=8),
    "title": ParagraphStyle("title", fontName="TNR-Bold", fontSize=18, leading=23, spaceAfter=15),
    "heading": ParagraphStyle("heading", fontName="TNR-Bold", fontSize=14, leading=18, spaceAfter=9, keepWithNext=True),
    "sub": ParagraphStyle("sub", fontName="TNR-Bold", fontSize=14, leading=16.2, spaceBefore=9, spaceAfter=6, keepWithNext=True),
    "cell": ParagraphStyle("cell", fontName="TNR", fontSize=10.5, leading=12.8, wordWrap="CJK"),
    "head": ParagraphStyle("head", fontName="TNR-Bold", fontSize=10.5, leading=12.8, wordWrap="CJK"),
    "compact_cell": ParagraphStyle("compact_cell", fontName="TNR", fontSize=10, leading=12, wordWrap="CJK"),
    "meta": ParagraphStyle("meta", fontName="TNR", fontSize=14, leading=16.2, spaceAfter=6, wordWrap="CJK"),
    "note": ParagraphStyle("note", fontName="TNR-Italic", fontSize=14, leading=16.2, spaceAfter=6),
}

LABELS = {
    "file": "Файл", "bytes": "Көлемі, байт", "sha256": "SHA-256",
    "dataset": "Деректер", "raw_rows": "Бастапқы жолдар", "raw_columns": "Бастапқы бағандар",
    "unknown_target_removed": "Нысанасы белгісіз: шығарылған", "retained": "Сақталған жолдар",
    "MICHD_mismatches": "_MICHD сәйкессіздігі", "duplicate_state_PSU": "Штат + PSU қайталануы",
    "identical_predictor_rows_retained": "Белгілері бірдей сақталған жолдар", "predictors": "Белгілер саны",
    "part": "Бөлік", "n": "n", "positive": "Оң сынып", "negative": "Теріс сынып",
    "positive_fraction": "Оң сынып үлесі", "name": "Атауы", "label": "Белгі атауы",
    "kind": "Түрі", "options": "Мүмкін мәндер", "min": "Ең аз", "max": "Ең көп", "step": "Қадам",
    "source": "Бастапқы белгі", "group": "Тобы", "missing_dev": "Бос мән, әзірлеу",
    "missing_cleveland": "Бос мән, Cleveland", "center": "Орталық", "missing_fraction": "Бос ұяшықтар үлесі",
    "base_ap": "Базалық CV AP", "tuned_ap": "Таңдалған CV AP", "best_params": "Таңдалған параметрлер",
    "model": "Модель", "trial_number": "№", "params": "Параметрлер",
    "mean_test_score": "Ішкі CV AP, орташа", "std_test_score": "Ішкі CV AP, SD",
    "mean_fit_time": "Fit, орташа с", "mean_train_score": "Train AP, орташа",
    "roc_auc": "ROC-AUC", "average_precision": "AP", "accuracy": "Accuracy",
    "precision": "Precision", "recall": "Recall", "specificity": "Specificity", "f1": "F1", "brier": "Brier",
    "confusion": "Қате матрицасы", "probability_version": "Ықтималдық нұсқасы",
    "extra_sigmoid_selected": "Қосымша сигмоида таңдалған", "variant": "Нұсқа",
    "threshold": "Шек", "extra_calibration": "Қосымша калибрлеу", "survey_weighted": "Сауалнама салмағы",
    "features": "Белгілер", "training_n": "Оқыту n", "metric": "Метрика", "lower": "Төменгі шек",
    "upper": "Жоғарғы шек", "feature": "Белгі", "value": "Мән", "ci": "Интервал",
    "recall_interval_degenerate": "Recall интервалы нөлге қысқарған", "mean": "Орташа", "std": "SD",
    "sample_sd": "Іріктемелік SD", "outer_best_params": "Сыртқы fold параметрлері", "fold": "Fold",
    "chosen_params": "Таңдалған параметрлер", "summary_kind": "Жинақтау түрі", "details": "Егжей-тегжей",
    "experiment": "Тәжірибе", "train_n": "Оқыту n", "test_n": "Бағалау n",
    "procedure_seconds": "Рәсім уақыты, с", "procedure": "Өлшенген рәсім",
    "test_predict_seconds": "Болжау уақыты, с", "mean_probability": "Орташа ықтималдық",
    "note": "Ескертпе", "category": "Тексеру", "record": "Сақталған жазба",
    "scope": "Қамту", "seed": "Seed", "weighted": "Салмақталған",
    "missingness_scope": "Бос мәндерді есептеу бөлігі", "feature_count": "Белгілер саны",
    "training_center": "Оқыту орталығы", "folds": "Fold саны", "trials_per_non_dummy": "Әр негізгі модельге сынақ",
    "primary_metric": "Негізгі метрика", "fit_n": "Fit n", "calibration_n": "Калибрлеу n",
    "validation_n": "Валидация n", "deployed_model": "Қосымша моделі", "C": "C",
    "extra_sigmoid": "Қосымша сигмоида", "evaluation_weighted": "Бағалау салмақталған",
    "resamples": "Қайта іріктеу саны", "unit": "Бірлік", "fixed_model": "Бекітілген модель",
    "complex_survey_design": "Күрделі сауалнама дизайны", "type": "Түрі",
    "bootstrap_resamples_per_group": "Топқа bootstrap саны", "permutations_per_feature": "Белгіге алмастыру саны",
    "score": "Бағалау көрсеткіші", "outer": "Сыртқы цикл", "inner": "Ішкі цикл",
    "outer_train_n": "Сыртқы оқыту n", "outer_test_n": "Сыртқы бағалау n",
    "outer_search_trials": "Сыртқы fold ішіндегі сынақ", "final_search_trials": "Соңғы іздеу сынағы",
    "final_training_n": "Соңғы оқыту n", "hardware": "Орындау ортасы",
    "timing_repetitions": "Уақыт өлшеу қайталануы", "automated_test_count": "Автотест саны",
    "tests": "Тесттер", "failures": "Сәтсіздіктер", "errors": "Қателер", "skipped": "Өткізілген",
}
VALUES = {
    "fit": "Оқыту (fit)", "calibration": "Калибрлеу", "validation": "Валидация", "test": "Тест",
    "benchmark_train": "Салыстыру: оқыту", "benchmark_test": "Салыстыру: тест",
    "category": "Санат", "number": "Сан", "raw": "Базалық", "calibrated": "Калибрленген",
    "sigmoid": "Сигмоидалық", "selected_threshold": "Таңдалған шек", "threshold_05": "0.5 шегі",
    "false_positive": "Жалған оң", "false_negative": "Жалған теріс",
    "mean_two_OOF_predictions_per_patient": "Әр пациенттің екі OOF бағасының орташа мәні",
    "final_training_search": "Барлық деректе соңғы оқыту іздеуі",
}


def normalize(text):
    return str(text).replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-")


def scalar(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "Иә" if value else "Жоқ"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        if value.is_integer() and abs(value) >= 1:
            return f"{int(value):,}".replace(",", " ")
        return f"{value:.6f}".rstrip("0").rstrip(".") if value else "0"
    return normalize(VALUES.get(str(value), value))


def celltext(value):
    if isinstance(value, dict):
        if not value:
            return "{} (параметр жоқ)"
        return "\n".join(f"{LABELS.get(k, k)}: {celltext(v)}" for k, v in value.items())
    if isinstance(value, (tuple, list)):
        if not value:
            return "[] (жазба жоқ)"
        if all(isinstance(x, dict) and set(x) == {"value", "label"} for x in value):
            return "\n".join(f"{scalar(x['value'])}: {scalar(x['label'])}" for x in value)
        if all(not isinstance(x, (dict, list, tuple)) for x in value):
            return "; ".join(scalar(x) for x in value)
        return "\n".join(f"{i}. {celltext(x)}" for i, x in enumerate(value, 1))
    return scalar(value)


def esc(value):
    return html.escape(normalize(value), quote=False).replace("\n", "<br/>")


class Builder:
    def __init__(self):
        self.story = []
        self.html = []
        self.coverage = {}

    def paragraph(self, text, style="body"):
        self.story.append(Paragraph(esc(text), STYLES[style]))
        tag = "h1" if style == "title" else "h2" if style == "heading" else "h3" if style == "sub" else "p"
        self.html.append(f'<{tag} class="{style}">{esc(text)}</{tag}>')

    def table(self, columns, rows, widths=None, labels=None, compact=False):
        if not rows:
            return
        labels = labels or [LABELS.get(c, c) for c in columns]
        values = [[r.get(c, "-") for c in columns] if isinstance(r, dict) else r for r in rows]
        widths = widths or [1] * len(columns)
        colwidths = [WIDTH * w / sum(widths) for w in widths]
        data = [[Paragraph(esc(label), STYLES["head"]) for label in labels]]
        for row in values:
            data.append([Paragraph(esc(celltext(v)), STYLES["compact_cell" if compact else "cell"]) for v in row])
        tab = Table(data, colWidths=colwidths, repeatRows=1, hAlign="LEFT", splitByRow=1)
        tab.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7edf3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.65, colors.HexColor("#4c6073")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#b8c1c9")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4 if compact else 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if compact else 5),
        ]))
        if len(values) <= 3:
            prefix = []
            for _ in range(2):
                if self.story and isinstance(self.story[-1], Paragraph) and self.story[-1].style.name in {"sub", "heading", "meta"}:
                    prefix.insert(0, self.story.pop())
                else:
                    break
            self.story.extend([KeepTogether(prefix + [tab]), Spacer(1, 6)])
        else:
            self.story.extend([tab, Spacer(1, 6)])
        self.html.append('<table><thead><tr>' + ''.join(f'<th>{esc(x)}</th>' for x in labels) + '</tr></thead><tbody>')
        for row in values:
            self.html.append('<tr>' + ''.join(f'<td>{esc(celltext(v))}</td>' for v in row) + '</tr>')
        self.html.append('</tbody></table>')

    def properties(self, value):
        self.table(["key", "value"], [[LABELS.get(k, k), v] for k, v in value.items()], [1, 2.8], ["Өріс", "Сақталған мән"])

    def newpage(self):
        self.story.append(PageBreak())
        self.html.append('<div class="pagebreak"></div>')

    def metrics(self, rows, context_keys=None):
        metric_names = {"roc_auc", "average_precision", "brier", "accuracy", "precision", "recall", "specificity", "f1", "confusion", "ci"}
        context_keys = context_keys or list(dict.fromkeys(k for r in rows for k in r if k not in metric_names))
        numbered = [{"row": str(i), **r} for i, r in enumerate(rows, 1)]
        self.paragraph("Жолдардың сәйкестендіруі мен шарттары", "sub")
        if "feature" in context_keys and "ci" in rows[0]:
            self.table(["row", "group", "n", "positive", "recall_interval_degenerate"], [
                {"row": r["row"], "group": f"{r['feature']} = {scalar(r['value'])}\n{r['label']}", "n": r["n"], "positive": r["positive"], "recall_interval_degenerate": r["recall_interval_degenerate"]} for r in numbered
            ], [0.3, 1.7, 0.65, 0.65, 1.1], ["№", "Топ / бастапқы код", "n", "Оң сынып", "Recall интервалы нөлге қысқарған"])
        elif len(context_keys) <= 4:
            widths = [0.3] + [1.6 if k in {"model", "name", "summary_kind", "chosen_params"} else 1 for k in context_keys]
            self.table(["row"] + context_keys, numbered, widths, ["№"] + [LABELS.get(k, k) for k in context_keys])
        elif set(context_keys) == {"model", "variant", "threshold", "extra_calibration", "survey_weighted"}:
            self.table(["row", "model_variant", "threshold", "extra_calibration", "survey_weighted"], [{"row": r["row"], "model_variant": f"{r['model']}\n{r['variant']}", **{k: r[k] for k in ["threshold", "extra_calibration", "survey_weighted"]}} for r in numbered], [0.3, 1.8, 0.8, 0.9, 0.9], ["№", "Модель / нұсқа", "Шек", "Қосымша калибрлеу", "Сауалнама салмағы"])
        else:
            self.table(["row", "context"], [{"row": r["row"], "context": {k: r[k] for k in context_keys if k in r}} for r in numbered], [0.32, 4], ["№", "Жол сипаттамасы"])
        self.paragraph("Ықтималдық сапасы", "sub")
        self.table(["row", "roc_auc", "average_precision", "brier"], numbered, [0.4, 1, 1, 1], ["№", "ROC-AUC", "Average Precision", "Brier score"])
        self.paragraph("Белгіленген шектегі жіктеу", "sub")
        self.table(["row", "accuracy", "precision", "recall", "specificity", "f1"], numbered, [0.4, 1, 1, 1, 1, 1], ["№", "Accuracy", "Precision", "Recall", "Specificity", "F1"])
        matrices = []
        for r in numbered:
            if "confusion" in r:
                m = r["confusion"]
                matrices.append([r["row"], m[0][0], m[0][1], m[1][0], m[1][1]])
        if matrices:
            self.paragraph("Қате матрицалары: жол = нақты сынып; баған = болжанған сынып", "sub")
            self.table(["row", "TN", "FP", "FN", "TP"], matrices, [0.4, 1, 1, 1, 1], ["№", "TN", "FP", "FN", "TP"])
        if any("ci" in r for r in numbered):
            self.paragraph("Сақталған bootstrap интервалдары: төменгі; жоғарғы шек", "sub")
            self.table(["row", "roc_auc", "average_precision", "recall", "brier"], [{"row": r["row"], **r.get("ci", {})} for r in numbered], [0.35, 1.2, 1.2, 1.2, 1.2], ["№", "ROC-AUC", "AP", "Recall", "Brier"])


def render_rows(b, table):
    rows, tid = table["rows"], table["id"]
    if tid == "sources":
        b.table(["file", "bytes", "sha256"], rows, [1.2, 0.6, 2.4])
    elif tid == "data_flow":
        fields = list(dict.fromkeys(k for r in rows for k in r if k != "dataset"))
        b.table(["field"] + [r["dataset"] for r in rows], [[LABELS.get(k, k)] + [r.get(k, "Жазылмаған") for r in rows] for k in fields], [2.2, 1, 1], ["Көрсеткіш"] + [r["dataset"] for r in rows])
    elif tid in {"brfss_schema", "uci_schema"}:
        formatted = []
        for r in rows:
            kind = f"{r['source']}\nТүрі: {scalar(r['kind'])}\nТобы: {r['group']}"
            allowed = celltext(r["options"]) if "options" in r else f"min: {scalar(r['min'])}\nmax: {scalar(r['max'])}\nstep: {scalar(r['step'])}"
            missing = r.get("missing_dev", r.get("missing_cleveland"))
            formatted.append([f"{r['name']}\n{r['label']}", kind, allowed, missing])
        b.table(["feature", "source", "allowed", "missing"], formatted, [1.25, 1.35, 1.65, 0.42], ["Белгі және атауы", "Дерек, түрі, тобы", "Барлық санаттар / шектер", "Бос\nмән"])
        b.paragraph("Кодтар мен диапазондар - сақталған схема мәндері. Интерфейс мәтіні орысша болған жағдайда түпнұсқа белгі атауы сақталды; бұл медициналық қалып диапазоны емес.", "note")
    elif tid == "benchmark_search":
        b.table(["name", "base_ap", "tuned_ap", "best_params"], rows, [1.05, 1.15, 0.65, 1.9])
    elif tid == "search_trials":
        for model in dict.fromkeys(r["model"] for r in rows):
            b.paragraph(model, "sub")
            b.table(["trial_number", "params", "mean_test_score", "std_test_score", "mean_train_score", "mean_fit_time"], [r for r in rows if r["model"] == model], [0.3, 2.2, 0.75, 0.75, 0.75, 0.75])
    elif tid in {"benchmark_test", "calibration_validation", "full_test", "ablations", "subgroups"}:
        b.metrics(rows)
    elif tid == "uci_nested_cv":
        for metrics, label in [(["roc_auc", "average_precision", "brier"], "Ықтималдық көрсеткіштері: орташа; іріктемелік SD"), (["accuracy", "precision", "recall", "specificity", "f1"], "Шектегі жіктеу: орташа; іріктемелік SD")]:
            b.paragraph(label, "sub")
            formatted = [{"model": r["model"], **{k: [r["mean"][k], r["sample_sd"][k]] for k in metrics}} for r in rows]
            b.table(["model"] + metrics, formatted, [1.2] + [1] * len(metrics))
        b.paragraph("Әр сыртқы fold ішінде таңдалған параметрлер", "sub")
        for r in rows:
            if not r["outer_best_params"]:
                b.paragraph(f"{r['model']}: outer_best_params = [] (сақталған параметр жазбасы жоқ).", "meta")
            else:
                b.paragraph(r["model"], "sub")
                b.table(["fold", "chosen_params"], [[i, params] for i, params in enumerate(r["outer_best_params"], 1)], [0.35, 4])
    elif tid == "uci_rf_detail":
        metrics = [{**{k: v for k, v in r.items() if k != "metrics"}, **r["metrics"]} for r in rows if "metrics" in r]
        b.metrics(metrics)
        for r in rows:
            if "details" not in r:
                continue
            b.paragraph(celltext(r["summary_kind"]), "sub")
            detail = r["details"]
            b.properties({k: v for k, v in detail.items() if k != "trials"})
            trials = [{"trial_number": i, **v} for i, v in enumerate(detail.get("trials", []), 1)]
            b.table(["trial_number", "params", "mean_test_score", "std_test_score", "mean_train_score", "mean_fit_time"], trials, [0.3, 2.2, 0.75, 0.75, 0.75, 0.75])
    elif tid == "timings":
        groups = dict.fromkeys((r["dataset"], r["experiment"], r["procedure"]) for r in rows)
        for dataset, experiment, procedure in groups:
            b.paragraph(f"{dataset}: {experiment}", "sub")
            b.paragraph("Өлшенген рәсім: " + procedure, "meta")
            subset = [r for r in rows if (r["dataset"], r["experiment"], r["procedure"]) == (dataset, experiment, procedure)]
            b.table(["model", "train_n", "test_n", "procedure_seconds", "test_predict_seconds"], subset, [1.6, 0.8, 0.8, 1, 1])
    elif tid == "verification":
        b.table(["category", "record"], rows, [1.2, 3], compact=True)
    elif tid == "errors":
        b.table(["kind", "n", "mean_probability"], rows, [1.2, 0.6, 1])
        for i, r in enumerate(rows, 1):
            if r.get("note"):
                b.paragraph(f"{i}-жол ескертпесі: {r['note']}", "note")
    else:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        b.table(keys, rows, [1.6] + [1] * (len(keys) - 1))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("TNR", 10)
    canvas.setFillColor(colors.HexColor("#444444"))
    canvas.drawCentredString(A4[0] / 2, 13 * mm, str(doc.page))
    canvas.setFont("TNR", 8.5)
    canvas.drawString(30 * mm, A4[1] - 13 * mm, "Қосалқы техникалық материал | Студент тексеруі күтіледі")
    canvas.restoreState()


def main():
    payload = SOURCE.read_bytes()
    data = json.loads(payload.decode("utf-8-sig"))
    assert data["table_count"] == len(data["tables"]) == 20
    assert next(t for t in data["tables"] if t["id"] == "search_trials")["rows"].__len__() == 21
    assert sum(len(t["rows"]) for t in data["tables"] if t["id"] in {"brfss_schema", "uci_schema"}) == 24
    OUT.mkdir(parents=True, exist_ok=True)
    b = Builder()
    b.paragraph("ТӘЖІРИБЕЛІК МАТЕРИАЛДАР", "title")
    b.paragraph("Сақталған нәтижелердің тексеруге арналған техникалық жинағы", "heading")
    b.paragraph("Бұл құжат Codex жасанды интеллект құралының көмегімен бастапқы есептерден техникалық түрде құрастырылды. Студенттің тексеруі күтіледі. Бұл аяқталған диплом, студенттің авторлық тарауы немесе ғылыми қорытынды емес.")
    b.paragraph(data["status"])
    b.paragraph(data["regulation_note"])
    b.paragraph(f"Дерек күні: {data['generated_date']}. Негіз: reports/technical_evidence_tables.json.", "meta")
    b.paragraph("Бастапқы JSON SHA-256: " + hashlib.sha256(payload).hexdigest(), "meta")
    b.paragraph("Қамту: 20 логикалық кесте; BRFSS іздеуінің 21 конфигурациясы; екі схеманың барлық 24 белгісі. Кең кестелер жол нөмірі сақталған бірнеше блокқа бөлінді.")
    b.paragraph("Оқу белгілеулері", "heading")
    b.paragraph("AP - Average Precision; SD - стандартты ауытқу; CV - кросс-валидация; OOF - бақылау оқытуға кірмеген бөлікте алынған болжам. TN/FP/FN/TP - қате матрицасының ұяшықтары. Ықтималдықтар мен үлестер пайызға айналдырылмаған.")
    b.paragraph("Сандар ең көбі 6 ондық таңбаға дөңгелектелді; бастапқы толық дәлдік JSON-да сақталады. null - бастапқы файлдағы null мәні; сандық нөл емес. '-' - осы жолда өріс жоқ. Параметр ішіндегі null мәнінің мағынасы алгоритмге тәуелді.")
    b.paragraph("Бұл жинақ жаңа оқыту, қосымша тест, клиникалық валидация немесе студенттің интерпретациясын жүргізбейді. Әр кестеде оның есеп файлы, шарттары және ескертпелері берілген.")
    b.newpage()
    b.paragraph("Кестелер тізімі", "title")
    b.table(["no", "title", "rows"], [[i, t["title"], len(t["rows"])] for i, t in enumerate(data["tables"], 1)], [0.35, 4, 0.4], ["№", "Атауы", "Жол"])
    for i, table in enumerate(data["tables"], 1):
        b.newpage()
        b.paragraph(f"{i}-кесте. {table['title']}", "heading")
        b.paragraph("Дереккөз: " + "; ".join(table["sources"]), "meta")
        b.paragraph(f"Сақталған жолдар: {len(table['rows'])}. Кесте идентификаторы: {table['id']}.", "meta")
        if table["conditions"]:
            b.paragraph("Бағалау / құрастыру шарттары", "sub")
            b.properties(table["conditions"])
        if table["notes"]:
            b.paragraph("Міндетті ескертпелер", "sub")
            for note in table["notes"]:
                b.paragraph(note, "note")
        render_rows(b, table)
    doc = BaseDocTemplate(str(PDF), pagesize=A4, leftMargin=30 * mm, rightMargin=10 * mm,
                            topMargin=20 * mm, bottomMargin=25 * mm, title="Тәжірибелік материалдар - тексеруге арналған жинақ",
                            author="Codex - AI-assisted technical extraction; student review pending")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="evidence", frames=frame, onPage=footer))
    doc.build(b.story)
    css = """@page{size:A4;margin:20mm 10mm 25mm 30mm}*{box-sizing:border-box}body{font-family:'Times New Roman',serif;font-size:14pt;line-height:1.3;max-width:170mm;margin:25px auto;color:#161b22}h1{font-size:18pt}h2,h3{font-size:14pt}p{margin:0 0 9pt}table{border-collapse:collapse;width:100%;table-layout:auto;margin:5pt 0 12pt;font-size:10.5pt}th,td{border:0.4pt solid #b8c1c9;text-align:left;vertical-align:top;padding:5pt;overflow-wrap:anywhere}th{background:#e7edf3}tbody tr:nth-child(even){background:#f6f8fa}thead{display:table-header-group}tr{break-inside:avoid}.meta,.note{font-size:14pt}.note{font-style:italic}.pagebreak{break-before:page;margin-top:30pt}h2,h3{break-after:avoid}header{padding:10px;background:#e7edf3;margin-bottom:20pt;font-size:11pt}@media print{body{margin:0;max-width:none}header{display:none}}"""
    save_js = "function saveCopy(){const b=new Blob(['<!doctype html>'+document.documentElement.outerHTML],{type:'text/html;charset=utf-8'});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download='ENU_Experimental_materials_KZ_edited.html';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}"
    css += 'p{line-height:1.1572}'
    HTML.write_text('<!doctype html><html lang="kk"><meta charset="utf-8"><title>Тәжірибелік материалдар</title><style>' + css + '</style><body><header>Өңдеуге болатын нұсқа: мәтінді басып өзгертуге болады. Өзгертілген көшірмені сақтау: <button onclick="saveCopy()">HTML көшірмесін сақтау</button></header><main contenteditable="true">' + "\n".join(b.html) + '</main><script>' + save_js + '</script></body></html>', encoding="utf-8")
    reader = PdfReader(str(PDF))
    extracted = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert "ТӘЖІРИБЕЛІК МАТЕРИАЛДАР" in extracted
    for index in range(1, 21):
        assert f"{index}-кесте." in extracted, index
    compact = lambda text: re.sub(r"\s+", "", normalize(text)).replace("\u00ad", "")
    complete_text = compact(extracted)
    for table in data["tables"]:
        for note in table["notes"]:
            assert compact(note) in complete_text, (table["id"], "missing note", note)
        for path in table["sources"]:
            assert compact(path) in complete_text, (table["id"], "missing source", path)
    print(json.dumps({"pdf": str(PDF), "html": str(HTML), "pages": len(reader.pages), "logical_tables": 20, "search_trials": 21, "schema_features": 24, "source_sha256": hashlib.sha256(payload).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
