"""热词生成脚本单元测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.gen_hotwords import (
    SEED_TERMS_ABBR,
    SEED_TERMS_HIGH,
    _is_valid_term,
    merge_seeds,
    write_hotwords,
)


class IsValidTermTest(unittest.TestCase):
    def test_valid_chinese(self):
        self.assertTrue(_is_valid_term("去甲肾上腺素"))

    def test_valid_english(self):
        self.assertTrue(_is_valid_term("CRRT"))

    def test_too_short(self):
        self.assertFalse(_is_valid_term("A"))

    def test_empty(self):
        self.assertFalse(_is_valid_term(""))

    def test_pure_numbers(self):
        self.assertFalse(_is_valid_term("12345"))

    def test_pure_punctuation(self):
        self.assertFalse(_is_valid_term("，。、"))

    def test_mixed_valid(self):
        self.assertTrue(_is_valid_term("P/F比值"))

    def test_whitespace_stripped(self):
        self.assertTrue(_is_valid_term("  CRRT  "))


class MergeSeedsTest(unittest.TestCase):
    def test_seeds_added_to_empty(self):
        terms = merge_seeds({})
        self.assertEqual(terms["去甲肾上腺素"], 20)
        self.assertEqual(terms["CRRT"], 25)

    def test_seeds_do_not_override_higher(self):
        terms = {"CRRT": 30}
        result = merge_seeds(terms)
        self.assertEqual(result["CRRT"], 30)  # 不被种子覆盖

    def test_seeds_fill_missing(self):
        terms = {"自定义术语": 10}
        result = merge_seeds(terms)
        self.assertEqual(result["自定义术语"], 10)
        self.assertEqual(result["ECMO"], 25)


class WriteHotwordsTest(unittest.TestCase):
    def test_write_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "hotwords.txt")
            n = write_hotwords({"CRRT": 25, "万古霉素": 20, "体温": 15}, out)
            self.assertEqual(n, 3)
            content = Path(out).read_text(encoding="utf-8")
            self.assertIn("CRRT 25", content)
            self.assertIn("万古霉素 20", content)
            self.assertIn("体温 15", content)

    def test_write_sorted_by_weight_desc(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "hotwords.txt")
            write_hotwords({"低权重": 10, "高权重": 30, "中权重": 20}, out)
            lines = Path(out).read_text(encoding="utf-8").strip().split("\n")
            weights = [int(line.split(" ")[-1]) for line in lines]
            self.assertEqual(weights, sorted(weights, reverse=True))

    def test_write_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "sub" / "dir" / "hotwords.txt")
            write_hotwords({"测试": 15}, out)
            self.assertTrue(Path(out).exists())


class SeedTermsTest(unittest.TestCase):
    def test_seed_high_not_empty(self):
        self.assertGreater(len(SEED_TERMS_HIGH), 10)

    def test_seed_abbr_not_empty(self):
        self.assertGreater(len(SEED_TERMS_ABBR), 10)

    def test_no_duplicates_between_seeds(self):
        overlap = set(SEED_TERMS_HIGH) & set(SEED_TERMS_ABBR)
        self.assertEqual(overlap, set(), f"种子术语重复: {overlap}")


if __name__ == "__main__":
    unittest.main()
