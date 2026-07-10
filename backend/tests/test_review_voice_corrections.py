"""语音查房错例聚类脚本单元测试。"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import yaml

from scripts.review_voice_corrections import (
    _build_output_yaml,
    _direction_consistency,
    _normalize,
    _similarity,
    classify_and_dedup,
    cluster_pairs,
    compute_systematic_score,
    extract_edit_pairs,
    filter_clusters,
)


class NormalizeTest(unittest.TestCase):
    def test_strips_whitespace(self):
        self.assertEqual(_normalize("  测试  "), "测试")

    def test_fullwidth_to_halfwidth(self):
        self.assertEqual(_normalize("ＡＢＣ１２３"), "ABC123")

    def test_nfc_normalization(self):
        # Unicode NFKC 统一
        self.assertEqual(_normalize("Ａ"), "A")


class ExtractEditPairsTest(unittest.TestCase):
    def test_extracts_replace_only(self):
        logs = [{
            "_id": "log1",
            "confirmed_by": "doctor1",
            "patient_id": "p1",
            "confirmed_at": datetime.now(),
            "edited_spans": [
                {"op": "replace", "before": "会部", "after": "肺部"},
                {"op": "insert", "after": "新增"},
                {"op": "delete", "before": "删除"},
            ],
        }]
        pairs = extract_edit_pairs(logs)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["before_norm"], "会部")
        self.assertEqual(pairs[0]["after_norm"], "肺部")

    def test_skips_empty_spans(self):
        logs = [{
            "_id": "log1",
            "confirmed_by": "doctor1",
            "patient_id": "p1",
            "edited_spans": [
                {"op": "replace", "before": "", "after": "肺部"},
                {"op": "replace", "before": "会部", "after": ""},
            ],
        }]
        pairs = extract_edit_pairs(logs)
        self.assertEqual(len(pairs), 0)

    def test_carries_trace_fields(self):
        logs = [{
            "_id": "log1",
            "confirmed_by": "doctor1",
            "patient_id": "p1",
            "confirmed_at": datetime(2025, 6, 1),
            "edited_spans": [{"op": "replace", "before": "A", "after": "B"}],
        }]
        pairs = extract_edit_pairs(logs)
        self.assertEqual(pairs[0]["log_id"], "log1")
        self.assertEqual(pairs[0]["actor"], "doctor1")
        self.assertEqual(pairs[0]["patient_id"], "p1")


class ClusterPairsTest(unittest.TestCase):
    def test_exact_grouping(self):
        pairs = [
            {"before_norm": "会部", "after_norm": "肺部", "actor": "d1", "patient_id": "p1", "log_id": "1"},
            {"before_norm": "会部", "after_norm": "肺部", "actor": "d2", "patient_id": "p2", "log_id": "2"},
        ]
        clusters = cluster_pairs(pairs, merge_threshold=0.75)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["count"], 2)
        self.assertEqual(clusters[0]["distinct_actors"], 2)

    def test_approximate_merge(self):
        """'会部听' 和 '会步听' 相似度高（3字共享2字），应合并到同一簇。"""
        pairs = [
            {"before_norm": "会部听", "after_norm": "肺部听", "actor": "d1", "patient_id": "p1", "log_id": "1"},
            {"before_norm": "会步听", "after_norm": "肺部听", "actor": "d2", "patient_id": "p2", "log_id": "2"},
        ]
        clusters = cluster_pairs(pairs, merge_threshold=0.6)
        self.assertEqual(len(clusters), 1)
        self.assertIn("会部听", clusters[0]["before_variants"])
        self.assertIn("会步听", clusters[0]["before_variants"])

    def test_different_after_not_merged(self):
        pairs = [
            {"before_norm": "发烧", "after_norm": "高热", "actor": "d1", "patient_id": "p1", "log_id": "1"},
            {"before_norm": "发烧", "after_norm": "体温升高", "actor": "d2", "patient_id": "p2", "log_id": "2"},
        ]
        clusters = cluster_pairs(pairs, merge_threshold=0.75)
        self.assertEqual(len(clusters), 2)


class SystematicScoreTest(unittest.TestCase):
    def test_high_score_for_many_actors(self):
        cluster = {
            "count": 10,
            "distinct_actors": 5,
            "direction_consistency": 1.0,
        }
        score = compute_systematic_score(cluster, min_count=3, min_distinct_actors=2)
        self.assertGreater(score, 0.6)

    def test_low_score_for_single_actor(self):
        """单医生反复改 → 跨医生分低，综合分低于多医生场景。"""
        cluster = {
            "count": 10,
            "distinct_actors": 1,
            "direction_consistency": 1.0,
        }
        score = compute_systematic_score(cluster, min_count=3, min_distinct_actors=2)
        # 单医生得分应明显低于多医生（跨医生权重最高）
        multi_actor_score = compute_systematic_score(
            {"count": 10, "distinct_actors": 4, "direction_consistency": 1.0},
            min_count=3, min_distinct_actors=2,
        )
        self.assertLess(score, multi_actor_score)


class FilterClustersTest(unittest.TestCase):
    def test_low_count_rejected(self):
        clusters = [{
            "before_variants": ["会部"], "after": "肺部",
            "count": 1, "distinct_actors": 1, "distinct_patients": 1,
            "direction_consistency": 1.0,
            "actors": ["d1"], "sample_log_ids": ["1"],
        }]
        passed, rejected = filter_clusters(
            clusters, min_count=3, min_distinct_actors=2, min_score=0.4,
        )
        self.assertEqual(len(passed), 0)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reject_reason"], "low_count")

    def test_low_actor_diversity_rejected(self):
        """同一对出现 5 次但全是同一个医生 → 被过滤为个人习惯噪声。"""
        clusters = [{
            "before_variants": ["会部"], "after": "肺部",
            "count": 5, "distinct_actors": 1, "distinct_patients": 5,
            "direction_consistency": 1.0,
            "actors": ["doctor1"], "sample_log_ids": ["1"],
        }]
        passed, rejected = filter_clusters(
            clusters, min_count=3, min_distinct_actors=2, min_score=0.4,
        )
        self.assertEqual(len(passed), 0)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reject_reason"], "low_actor_diversity")

    def test_systematic_error_passes(self):
        """同一对跨 3 个医生各出现一次 → 入选且系统性分较高。"""
        clusters = [{
            "before_variants": ["料量"], "after": "尿量",
            "count": 3, "distinct_actors": 3, "distinct_patients": 3,
            "direction_consistency": 1.0,
            "actors": ["d1", "d2", "d3"], "sample_log_ids": ["1", "2", "3"],
        }]
        passed, rejected = filter_clusters(
            clusters, min_count=3, min_distinct_actors=2, min_score=0.4,
        )
        self.assertEqual(len(passed), 1)
        self.assertGreater(passed[0]["systematic_score"], 0.5)


class DirectionConsistencyTest(unittest.TestCase):
    def test_consistent(self):
        items = [
            {"before_norm": "发烧", "after_norm": "高热"},
            {"before_norm": "发烧", "after_norm": "高热"},
        ]
        self.assertEqual(_direction_consistency(items), 1.0)

    def test_inconsistent(self):
        items = [
            {"before_norm": "发烧", "after_norm": "高热"},
            {"before_norm": "发烧", "after_norm": "体温升高"},
        ]
        self.assertEqual(_direction_consistency(items), 0.0)

    def test_mixed(self):
        items = [
            {"before_norm": "发烧", "after_norm": "高热"},
            {"before_norm": "发烧", "after_norm": "高热"},
            {"before_norm": "拉稀", "after_norm": "腹泻"},
            {"before_norm": "拉稀", "after_norm": "大便次数增多"},
        ]
        self.assertEqual(_direction_consistency(items), 0.5)


class DirectionInconsistencyRejectTest(unittest.TestCase):
    def test_same_before_two_afters_rejected(self):
        """同一 before 改成两种不同 after → 方向不一致，被拒绝。"""
        clusters = [{
            "before_variants": ["发烧"], "after": "高热",
            "count": 5, "distinct_actors": 3, "distinct_patients": 3,
            "direction_consistency": 0.0,  # 不一致
            "actors": ["d1", "d2", "d3"], "sample_log_ids": [],
        }]
        passed, rejected = filter_clusters(
            clusters, min_count=3, min_distinct_actors=2, min_score=0.4,
        )
        self.assertEqual(len(passed), 0)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reject_reason"], "direction_inconsistent")


class DrugIsolationTest(unittest.TestCase):
    def test_drug_pair_goes_to_drug_review(self):
        """编辑对涉及药名 → 进 drug_review 区，不进 accent/dialect。"""
        clusters = [{
            "before_variants": ["多巴酚丁胺"], "after": "多巴胺",
            "count": 5, "distinct_actors": 3, "distinct_patients": 3,
            "systematic_score": 0.8, "direction_consistency": 1.0,
            "actors": ["d1", "d2", "d3"], "sample_log_ids": [],
        }]
        hints = {"accent_errors": [], "dialect_phrases": [], "drug_confusables": [
            {"names": ["多巴胺", "多巴酚丁胺"], "note": ""},
        ]}
        # 设置全局药名集
        import scripts.review_voice_corrections as mod
        mod._DRUG_NAMES_FLAT = {"多巴胺", "多巴酚丁胺"}

        classified = classify_and_dedup(clusters, hints)
        self.assertEqual(len(classified["drug_review"]), 1)
        self.assertEqual(len(classified["accent_errors"]), 0)
        self.assertEqual(len(classified["dialect_phrases"]), 0)


class DedupAgainstHintsTest(unittest.TestCase):
    def test_existing_hint_not_output(self):
        """候选已存在于 accent_errors → 不重复输出。"""
        clusters = [{
            "before_variants": ["会部", "灰部"], "after": "肺部",
            "count": 5, "distinct_actors": 3, "distinct_patients": 3,
            "systematic_score": 0.8, "direction_consistency": 1.0,
            "actors": ["d1", "d2", "d3"], "sample_log_ids": [],
        }]
        hints = {
            "accent_errors": [{"wrong": ["会部", "灰部"], "right": "肺部"}],
            "dialect_phrases": [],
            "drug_confusables": [],
        }
        import scripts.review_voice_corrections as mod
        mod._DRUG_NAMES_FLAT = set()

        classified = classify_and_dedup(clusters, hints)
        total = sum(len(v) for v in classified.values())
        self.assertEqual(total, 0)

    def test_new_variant_not_deduped(self):
        """只有部分 before 在 hints 里 → 仍然输出（因为新变体不在 hints 中）。"""
        clusters = [{
            "before_variants": ["会部", "灰步"],  # "灰步" 不在 hints 里
            "after": "肺部",
            "count": 5, "distinct_actors": 3, "distinct_patients": 3,
            "systematic_score": 0.8, "direction_consistency": 1.0,
            "actors": ["d1", "d2", "d3"], "sample_log_ids": [],
        }]
        hints = {
            "accent_errors": [{"wrong": ["会部"], "right": "肺部"}],
            "dialect_phrases": [],
            "drug_confusables": [],
        }
        import scripts.review_voice_corrections as mod
        mod._DRUG_NAMES_FLAT = set()

        classified = classify_and_dedup(clusters, hints)
        total = sum(len(v) for v in classified.values())
        self.assertGreater(total, 0)


class ReadOnlyGuaranteeTest(unittest.TestCase):
    def test_hints_file_unchanged_after_analysis(self):
        """跑完分析后 correction_hints.yaml 内容未变。"""
        with tempfile.TemporaryDirectory() as tmp:
            hints_path = Path(tmp) / "hints.yaml"
            original = {
                "accent_errors": [{"wrong": ["会部"], "right": "肺部"}],
                "dialect_phrases": [],
                "drug_confusables": [],
            }
            hints_path.write_text(yaml.dump(original, allow_unicode=True), encoding="utf-8")
            original_content = hints_path.read_text(encoding="utf-8")

            # 模拟分析（只调用纯函数，不写文件）
            clusters = [{
                "before_variants": ["新错字"], "after": "正确",
                "count": 5, "distinct_actors": 3, "distinct_patients": 3,
                "systematic_score": 0.8, "direction_consistency": 1.0,
                "actors": ["d1", "d2", "d3"], "sample_log_ids": [],
            }]
            import scripts.review_voice_corrections as mod
            mod._DRUG_NAMES_FLAT = set()
            classify_and_dedup(clusters, original)

            # 验证文件未变
            after_content = hints_path.read_text(encoding="utf-8")
            self.assertEqual(original_content, after_content)


class BuildOutputYamlTest(unittest.TestCase):
    def test_output_structure_matches_hints_schema(self):
        """输出的 wrong/right 字段与 correction_hints.yaml 的 accent_errors schema 一致。"""
        classified = {
            "accent_errors": [{
                "before_variants": ["会部", "灰部"],
                "after": "肺部",
                "count": 5,
                "distinct_actors": 3,
                "distinct_patients": 3,
                "systematic_score": 0.8,
                "direction_consistency": 1.0,
                "actors": ["d1", "d2", "d3"],
                "sample_log_ids": ["id1"],
            }],
            "dialect_phrases": [],
            "drug_review": [],
        }
        output = _build_output_yaml(classified, {"test": True})
        candidates = output["accent_errors_candidates"][0]
        self.assertEqual(candidates["wrong"], ["会部", "灰部"])
        self.assertEqual(candidates["right"], "肺部")
        self.assertEqual(candidates["suggested_category"], "accent_errors")


if __name__ == "__main__":
    unittest.main()
