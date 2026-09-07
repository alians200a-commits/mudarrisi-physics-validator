#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = {
    "mcq_option_count": 4,
    "tf_options": ["صح", "خطأ"],
    "batch_size": 30,
    "require_question_id": True,
    "require_explanations": True,
    "require_source_evidence_for_pass": True,
    "require_semantic_review_for_pass": True,
    "forbidden_reference_phrases": [
        "في الجدول", "وفق الجدول", "في الشكل", "وفق الشكل",
        "في الصورة", "وفق الصورة", "في المصدر", "وفق المصدر",
        "في الكتاب", "وفق الكتاب", "في الملزمة", "وفق الملزمة",
        "كما موضح", "كما هو موضح",
    ],
}

@dataclass
class Finding:
    severity: str
    code: str
    question_id: str | None = None
    field: str | None = None
    detail: str | None = None


def _load(path: Path | None) -> Any:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    text = re.sub(r"[\u064B-\u065F\u0670]", "", str(text))
    text = text.replace("ـ", "")
    return re.sub(r"\s+", " ", text).strip()


def _questions(bank: Any) -> list[dict[str, Any]]:
    if isinstance(bank, list):
        qs = bank
    elif isinstance(bank, dict) and isinstance(bank.get("questions"), list):
        qs = bank["questions"]
    else:
        raise ValueError("bank must be an array or an object containing questions[]")
    if not all(isinstance(q, dict) for q in qs):
        raise ValueError("every question must be a JSON object")
    return qs


def _qid(q: dict[str, Any], index: int) -> str:
    v = q.get("id")
    return v if isinstance(v, str) and v.strip() else f"#INDEX-{index}"


def _stem(q: dict[str, Any]) -> str:
    return str(q.get("question") or q.get("statement") or "")


def _text_fields(q: dict[str, Any]):
    if isinstance(q.get("question"), str):
        yield "question", q["question"]
    if isinstance(q.get("statement"), str):
        yield "statement", q["statement"]
    for key in ("options", "explanations"):
        value = q.get(key)
        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str):
                    yield f"{key}[{i}]", item


def validate_structure(bank: Any, cfg: dict[str, Any]) -> list[Finding]:
    qs = _questions(bank)
    findings: list[Finding] = []
    seen_ids: set[str] = set()
    seen_stems: dict[str, str] = {}
    forbidden = [_norm(x) for x in cfg["forbidden_reference_phrases"]]

    for i, q in enumerate(qs, 1):
        qid = _qid(q, i)
        raw_id = q.get("id")
        if cfg.get("require_question_id") and not (isinstance(raw_id, str) and raw_id.strip()):
            findings.append(Finding("ERROR", "MISSING_QUESTION_ID", qid, "id"))
        elif isinstance(raw_id, str):
            if raw_id in seen_ids:
                findings.append(Finding("ERROR", "DUPLICATE_QUESTION_ID", raw_id, "id"))
            seen_ids.add(raw_id)

        stem = _norm(_stem(q))
        if not stem:
            findings.append(Finding("ERROR", "EMPTY_QUESTION_TEXT", qid, "question"))
        elif stem in seen_stems:
            findings.append(Finding("ERROR", "DUPLICATE_QUESTION_TEXT", qid, "question", f"same as {seen_stems[stem]}"))
        else:
            seen_stems[stem] = qid

        for field, text in _text_fields(q):
            ntext = _norm(text)
            for phrase in forbidden:
                if phrase and phrase in ntext:
                    findings.append(Finding("ERROR", "FORBIDDEN_SOURCE_REFERENCE", qid, field, phrase))

        qtype = q.get("type")
        options = q.get("options")
        correct = q.get("correctAnswer")
        explanations = q.get("explanations")

        if qtype == "mcq":
            n = int(cfg.get("mcq_option_count", 4))
            if not isinstance(options, list) or len(options) != n:
                findings.append(Finding("ERROR", "MCQ_OPTION_COUNT", qid, "options", f"expected {n}"))
                options = options if isinstance(options, list) else []
            if options and len({_norm(x) for x in options}) != len(options):
                findings.append(Finding("ERROR", "DUPLICATE_OPTIONS", qid, "options"))
            if not isinstance(correct, int) or isinstance(correct, bool) or not 0 <= correct < n:
                findings.append(Finding("ERROR", "INVALID_CORRECT_ANSWER_INDEX", qid, "correctAnswer"))
            if cfg.get("require_explanations"):
                if not isinstance(explanations, list) or len(explanations) != n:
                    findings.append(Finding("ERROR", "EXPLANATION_COUNT", qid, "explanations", f"expected {n}"))
                elif any(not isinstance(x, str) or not x.strip() for x in explanations):
                    findings.append(Finding("ERROR", "EMPTY_EXPLANATION", qid, "explanations"))

        elif qtype == "true_false":
            expected = cfg.get("tf_options", ["صح", "خطأ"])
            if options != expected:
                findings.append(Finding("ERROR", "TF_OPTIONS_MISMATCH", qid, "options", f"expected {expected}"))
            if not isinstance(correct, int) or isinstance(correct, bool) or correct not in (0, 1):
                findings.append(Finding("ERROR", "INVALID_CORRECT_ANSWER_INDEX", qid, "correctAnswer"))
            if cfg.get("require_explanations"):
                if not isinstance(explanations, list) or len(explanations) != 2:
                    findings.append(Finding("ERROR", "EXPLANATION_COUNT", qid, "explanations", "expected 2"))
                elif any(not isinstance(x, str) or not x.strip() for x in explanations):
                    findings.append(Finding("ERROR", "EMPTY_EXPLANATION", qid, "explanations"))
        else:
            findings.append(Finding("ERROR", "UNSUPPORTED_QUESTION_TYPE", qid, "type", str(qtype)))

    if isinstance(bank, dict) and isinstance(bank.get("batch"), dict):
        meta = bank["batch"]
        size = int(cfg.get("batch_size", 30))
        if meta.get("is_final") is False and len(qs) != size:
            findings.append(Finding("ERROR", "NON_FINAL_BATCH_SIZE", detail=f"expected {size}, got {len(qs)}"))
        if meta.get("is_final") is True and len(qs) > size:
            findings.append(Finding("ERROR", "FINAL_BATCH_TOO_LARGE", detail=f"max {size}, got {len(qs)}"))

    return findings


def validate_manifest(bank: Any, manifest: Any) -> list[Finding]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("originals"), list):
        return [Finding("UNVERIFIED", "SOURCE_MANIFEST_MISSING_OR_INVALID")]

    qs = _questions(bank)
    by_id = {q.get("id"): q for q in qs if isinstance(q.get("id"), str)}
    findings: list[Finding] = []

    for original in manifest["originals"]:
        if not isinstance(original, dict):
            findings.append(Finding("ERROR", "INVALID_ORIGINAL_RECORD"))
            continue
        oid = str(original.get("id") or "")
        if original.get("status", "active") == "deferred":
            continue
        reps = original.get("representation_question_ids")
        if not isinstance(reps, list) or not reps:
            findings.append(Finding("ERROR", "ORIGINAL_REPRESENTATION_MISSING", oid))
            continue
        missing = [str(x) for x in reps if str(x) not in by_id]
        if missing:
            findings.append(Finding("ERROR", "ORIGINAL_REPRESENTATION_MISSING", oid, detail=",".join(missing)))
            continue

        if original.get("literal_required") is True:
            source_stem = original.get("stem")
            if not isinstance(source_stem, str) or not source_stem.strip():
                findings.append(Finding("UNVERIFIED", "ORIGINAL_STEM_EVIDENCE_MISSING", oid))
                continue
            if not any(_norm(_stem(by_id[str(qid)])) == _norm(source_stem) for qid in reps if str(qid) in by_id):
                findings.append(Finding("ERROR", "ORIGINAL_VERBATIM_MISMATCH", oid))
    return findings


def validate_semantic_review(bank: Any, review: Any) -> list[Finding]:
    if not isinstance(review, dict) or not isinstance(review.get("questions"), list):
        return [Finding("UNVERIFIED", "SEMANTIC_REVIEW_MISSING_OR_INVALID")]
    records = {r.get("id"): r for r in review["questions"] if isinstance(r, dict) and isinstance(r.get("id"), str)}
    required = ("single_defensible_answer", "distractors_same_genus", "explanations_specific", "scientifically_valid")
    findings: list[Finding] = []
    for i, q in enumerate(_questions(bank), 1):
        qid = _qid(q, i)
        rec = records.get(qid)
        if not rec:
            findings.append(Finding("UNVERIFIED", "SEMANTIC_REVIEW_QUESTION_MISSING", qid))
            continue
        if rec.get("status") == "FAIL":
            findings.append(Finding("ERROR", "SEMANTIC_REVIEW_FAIL", qid, detail=str(rec.get("reason") or "")))
            continue
        for key in required:
            if rec.get(key) is not True:
                findings.append(Finding("UNVERIFIED", "SEMANTIC_CHECK_UNVERIFIED", qid, key))
    return findings


def run(bank: Any, cfg: dict[str, Any], manifest: Any, semantic_review: Any) -> dict[str, Any]:
    findings = validate_structure(bank, cfg)
    if manifest is None and cfg.get("require_source_evidence_for_pass"):
        findings.append(Finding("UNVERIFIED", "SOURCE_EVIDENCE_NOT_PROVIDED"))
    elif manifest is not None:
        findings.extend(validate_manifest(bank, manifest))

    if semantic_review is None and cfg.get("require_semantic_review_for_pass"):
        findings.append(Finding("UNVERIFIED", "SEMANTIC_REVIEW_NOT_PROVIDED"))
    elif semantic_review is not None:
        findings.extend(validate_semantic_review(bank, semantic_review))

    errors = sum(x.severity == "ERROR" for x in findings)
    unverified = sum(x.severity == "UNVERIFIED" for x in findings)
    status = "FAIL" if errors else ("UNVERIFIED" if unverified else "PASS")
    return {
        "status": status,
        "question_count": len(_questions(bank)),
        "counts": {"errors": errors, "unverified": unverified, "findings": len(findings)},
        "findings": [asdict(x) for x in findings],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True, type=Path)
    ap.add_argument("--config", type=Path)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--semantic-review", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        cfg = dict(DEFAULT_CONFIG)
        user_cfg = _load(args.config)
        if isinstance(user_cfg, dict):
            cfg.update(user_cfg)
        result = run(_load(args.bank), cfg, _load(args.manifest), _load(args.semantic_review))
    except Exception as exc:
        result = {
            "status": "FAIL",
            "question_count": 0,
            "counts": {"errors": 1, "unverified": 0, "findings": 1},
            "findings": [asdict(Finding("ERROR", "VALIDATOR_RUNTIME_ERROR", detail=str(exc)))],
        }
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if result["status"] == "PASS" else 2

if __name__ == "__main__":
    sys.exit(main())
