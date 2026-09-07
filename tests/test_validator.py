import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import validator


def load(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(validator.DEFAULT_CONFIG)
        self.bank = load("bank.valid.json")
        self.manifest = load("manifest.valid.json")
        self.semantic = load("semantic_review.valid.json")

    def test_known_good_passes(self):
        self.assertEqual(validator.run(self.bank, self.cfg, self.manifest, self.semantic)["status"], "PASS")

    def test_missing_semantic_review_never_passes(self):
        self.assertEqual(validator.run(self.bank, self.cfg, self.manifest, None)["status"], "UNVERIFIED")

    def test_missing_source_evidence_never_passes(self):
        self.assertEqual(validator.run(self.bank, self.cfg, None, self.semantic)["status"], "UNVERIFIED")

    def test_bad_mcq_option_count_fails(self):
        bank = copy.deepcopy(self.bank)
        bank["questions"][0]["options"] = ["أ", "ب", "ج"]
        result = validator.run(bank, self.cfg, self.manifest, self.semantic)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("MCQ_OPTION_COUNT", [x["code"] for x in result["findings"]])

    def test_forbidden_reference_fails(self):
        bank = copy.deepcopy(self.bank)
        bank["questions"][0]["question"] = "وفق الصورة، ما الخاصية الفيزيائية للمادة؟"
        result = validator.run(bank, self.cfg, self.manifest, self.semantic)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("FORBIDDEN_SOURCE_REFERENCE", [x["code"] for x in result["findings"]])

    def test_duplicate_stem_fails(self):
        bank = copy.deepcopy(self.bank)
        q = copy.deepcopy(bank["questions"][0])
        q["id"] = "Q-03"
        bank["questions"].append(q)
        self.assertEqual(validator.run(bank, self.cfg, self.manifest, self.semantic)["status"], "FAIL")

    def test_literal_mismatch_fails(self):
        bank = copy.deepcopy(self.bank)
        bank["questions"][0]["question"] = "عرّف الخاصية الفيزيائية للمادة."
        result = validator.run(bank, self.cfg, self.manifest, self.semantic)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("ORIGINAL_VERBATIM_MISMATCH", [x["code"] for x in result["findings"]])

    def test_nonfinal_batch_must_be_30(self):
        bank = copy.deepcopy(self.bank)
        bank["batch"]["is_final"] = False
        result = validator.run(bank, self.cfg, self.manifest, self.semantic)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("NON_FINAL_BATCH_SIZE", [x["code"] for x in result["findings"]])

if __name__ == "__main__":
    unittest.main()
