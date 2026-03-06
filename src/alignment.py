from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

LEVEL_2_HEADERS = [
    "Patient History",
    "Major Events",
    "Status Changes",
    "Neurological",
    "Cardiovascular",
    "Respiratory",
    "Gastrointestinal",
    "Other Systems",
    "Laboratory Tests",
    "Imaging Results",
    "Medications",
    "Procedures",
    "Immediate Action Plan",
    "Long-term Action Plan",
]

LEVEL_1_HEADERS = [
    "Situation",
    "Assessments by Systems",
    "Investigation",
    "Treatments",
    "Next steps",
]

HEADER_ALIASES = {
    "Imaing Results": "Imaging Results",
}

LEVEL_2_TO_LEVEL_1 = {
    "Patient History": "Situation",
    "Major Events": "Situation",
    "Status Changes": "Situation",
    "Neurological": "Assessments by Systems",
    "Cardiovascular": "Assessments by Systems",
    "Respiratory": "Assessments by Systems",
    "Gastrointestinal": "Assessments by Systems",
    "Other Systems": "Assessments by Systems",
    "Laboratory Tests": "Investigation",
    "Imaging Results": "Investigation",
    "Medications": "Treatments",
    "Procedures": "Treatments",
    "Immediate Action Plan": "Next steps",
    "Long-term Action Plan": "Next steps",
}


def normalize_text(text: str | None) -> str:
    if not text or (isinstance(text, float) and pd.isna(text)):
        return ""
    text = str(text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def load_gold_standard(xlsx_path: str | Path) -> dict[str, pd.DataFrame]:
    xlsx_path = Path(xlsx_path)
    xls = pd.ExcelFile(xlsx_path)
    patient_sheets: dict[str, pd.DataFrame] = {}
    for sheet in xls.sheet_names:
        if not re.match(r"^P\d+$", sheet):
            continue
        df = pd.read_excel(xls, sheet_name=sheet)
        expected_cols = ["Level 1", "Level 2", "Level 3"]
        if list(df.columns[:3]) != expected_cols:
            df.columns = expected_cols + list(df.columns[3:])
        df["Level 1"] = df["Level 1"].ffill()
        df["Level 2"] = df["Level 2"].apply(
            lambda x: HEADER_ALIASES.get(str(x).strip(), str(x).strip()) if pd.notna(x) else x
        )
        patient_sheets[sheet] = df
    return patient_sheets


def load_predictions(pred_dir: str | Path) -> dict[str, str]:
    pred_dir = Path(pred_dir)
    predictions: dict[str, str] = {}
    for txt_file in sorted(pred_dir.glob("P* summary.txt")):
        match = re.match(r"^P(\d+)\s+summary\.txt$", txt_file.name)
        if match:
            pid = f"P{match.group(1)}"
            predictions[pid] = txt_file.read_text(encoding="utf-8")
    return predictions


def parse_txt_sections(text: str) -> dict[str, str]:
    lines = text.split("\n")
    sections: dict[str, str] = {}
    current_header: str | None = None
    content_lines: list[str] = []
    l2_set = set(LEVEL_2_HEADERS)
    l1_set = set(LEVEL_1_HEADERS)
    for line in lines:
        stripped = line.strip()
        if stripped in l2_set:
            if current_header is not None:
                sections[current_header] = "\n".join(content_lines).strip()
            current_header = stripped
            content_lines = []
        elif stripped in l1_set:
            continue
        elif current_header is not None:
            content_lines.append(line)
    if current_header is not None:
        sections[current_header] = "\n".join(content_lines).strip()
    return sections


def build_pairs(
    gold_xlsx_path: str | Path,
    pred_dir: str | Path,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    gold_sheets = load_gold_standard(gold_xlsx_path)
    predictions = load_predictions(pred_dir)
    gold_ids = set(gold_sheets.keys())
    pred_ids = set(predictions.keys())
    matched_ids = sorted(gold_ids & pred_ids, key=lambda x: int(x[1:]))
    unmatched_gold = sorted(gold_ids - pred_ids, key=lambda x: int(x[1:]))
    unmatched_pred = sorted(pred_ids - gold_ids, key=lambda x: int(x[1:]))
    rows: list[dict] = []
    for pid in matched_ids:
        gold_df = gold_sheets[pid]
        pred_sections = parse_txt_sections(predictions[pid])
        for idx, row in gold_df.iterrows():
            level_1 = str(row["Level 1"]).strip() if pd.notna(row["Level 1"]) else ""
            level_2 = str(row["Level 2"]).strip() if pd.notna(row["Level 2"]) else ""
            gold_text = str(row["Level 3"]) if pd.notna(row["Level 3"]) else ""
            canonical_l2 = HEADER_ALIASES.get(level_2, level_2)
            pred_text = pred_sections.get(canonical_l2, "")
            if canonical_l2 in pred_sections:
                method = "exact"
                confidence = 1.0
            else:
                method = "unmatched"
                confidence = 0.0
            rows.append({
                "sheet_name": pid,
                "gold_row_index": idx,
                "level_1": level_1,
                "level_2": canonical_l2,
                "gold_text": gold_text,
                "gold_text_norm": normalize_text(gold_text),
                "pred_file": f"{pid} summary.txt",
                "pred_text": pred_text,
                "pred_text_norm": normalize_text(pred_text),
                "alignment_method": method,
                "alignment_confidence": confidence,
            })
    pairs_df = pd.DataFrame(rows)
    return pairs_df, unmatched_gold, unmatched_pred
