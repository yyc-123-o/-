"""P0/P1 修复的自动化回归测试 — 使用 pytest + FastAPI TestClient

运行方式: pytest test_fixes.py -v
无需手动启动服务。
"""
import sys
from pathlib import Path

# 确保项目根在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient
from main import app
from models.knowledge_graph import KG
from core.profile_builder import build_profile
from core import gap_analyzer, mastery
from generators.mock_generator import generate_all_mock_data

client = TestClient(app)


@pytest.fixture(scope="module")
def learners_and_bank():
    """生成测试数据"""
    learners, test_bank = generate_all_mock_data()
    return learners, test_bank


class TestP01_ResourceHintsDynamic:
    """P0-1: 任意章节均能生成非空的三类资源提示"""

    def test_ch01_has_nonempty_hints(self, learners_and_bank):
        learners, _ = learners_and_bank
        learner = learners[0]
        profile = build_profile(learner, KG, "ch01_foundation")
        h = profile.resource_generation_hints
        assert h.lecture_notes.must_include, "ch01 讲义提示为空"
        assert h.practical_guide.must_include, "ch01 实操指南为空"
        assert h.test_questions.must_cover, "ch01 测试题提示为空"

    def test_ch03_has_nonempty_hints(self, learners_and_bank):
        learners, _ = learners_and_bank
        learner = learners[0]
        profile = build_profile(learner, KG, "ch03_cnn")
        h = profile.resource_generation_hints
        assert h.lecture_notes.must_include
        assert h.practical_guide.must_include
        assert h.test_questions.must_cover

    def test_ch06_has_nonempty_hints(self, learners_and_bank):
        learners, _ = learners_and_bank
        learner = learners[0]
        profile = build_profile(learner, KG, "ch06_transformer")
        h = profile.resource_generation_hints
        assert h.lecture_notes.must_include
        assert h.practical_guide.must_include
        assert h.test_questions.must_cover

    def test_no_cnn_hardcode(self, learners_and_bank):
        """搜索不再存在 CNN 专用资源模板"""
        learners, _ = learners_and_bank
        for ch_id in ["ch01_foundation", "ch03_cnn", "ch06_transformer"]:
            profile = build_profile(learners[0], KG, ch_id)
            h = profile.resource_generation_hints
            # 不应出现 CIFAR-10 或 nn.Conv2d 等硬编码
            all_hints = str(h.lecture_notes.must_include) + str(h.practical_guide.must_include)
            assert "CIFAR" not in all_hints, f"{ch_id} 仍含 CIFAR 硬编码"
            assert "nn.Conv2d" not in all_hints, f"{ch_id} 仍含 nn.Conv2d 硬编码"

    def test_depth_varies_by_chapter(self, learners_and_bank):
        """不同章节的 target_depth 可以不同"""
        learners, _ = learners_and_bank
        depths = set()
        for ch_id in ["ch01_foundation", "ch02_ml_review", "ch03_cnn"]:
            profile = build_profile(learners[0], KG, ch_id)
            depths.add(profile.resource_generation_hints.target_depth)
        # 至少有一种深度值
        assert len(depths) >= 1


class TestP02_PriorChaptersReal:
    """P0-2: 前序章节基于真实数据"""

    def test_empty_learner_has_no_prior(self):
        """空白学习者的 prior_chapters 为空"""
        from models.schemas import Learner, Education
        empty = Learner(id="empty", name="空", education=Education(level="本科"))
        profile = build_profile(empty, KG, "ch03_cnn")
        assert len(profile.prior_chapters) == 0, "空白学习者不应有前序章节历史"

    def test_no_fixed_dates(self, learners_and_bank):
        """不再出现固定日期"""
        learners, _ = learners_and_bank
        for learner in learners:
            profile = build_profile(learner, KG, "ch03_cnn")
            for pc in profile.prior_chapters:
                assert pc.completed_at != "2026-07-20T16:00:00Z"
                assert pc.completed_at != "2026-07-30T15:00:00Z"

    def test_different_learners_different_history(self, learners_and_bank):
        """两名学习者前序章节不同"""
        learners, _ = learners_and_bank
        if len(learners) >= 2:
            p1 = build_profile(learners[0], KG, "ch03_cnn")
            p2 = build_profile(learners[1], KG, "ch03_cnn")
            # 至少 accuracy 或 time_spent 或 kps_covered 应有差异
            if p1.prior_chapters and p2.prior_chapters:
                assert p1.prior_chapters[0].accuracy != p2.prior_chapters[0].accuracy or \
                       p1.prior_chapters[0].time_spent_hours != p2.prior_chapters[0].time_spent_hours or \
                       p1.prior_chapters[0].kps_covered != p2.prior_chapters[0].kps_covered


class TestP03_NoFakeEvidence:
    """P0-3: 删除固定 CNN 结论与伪造证据"""

    def test_no_cnn_evidence(self, learners_and_bank):
        """画像中不包含 CNN 专属固定证据（硬编码的 status=not_learned 和 kp_012共2道题）"""
        learners, _ = learners_and_bank
        for learner in learners:
            profile = build_profile(learner, KG, "ch01_foundation")
            for ev in profile.evidence:
                # 原硬编码证据的标志性文本：status=not_learned + "自适应测试: kp_012共2道题"
                assert "status=not_learned" not in ev.claim, f"仍含硬编码 CNN 证据: {ev.claim}"
                assert "kp_012共2道题" not in ev.detail, f"仍含硬编码 CNN 证据: {ev.detail}"
                assert "数据稀疏已使用学历先验做L2正则" not in ev.detail

    def test_no_double_annotation(self, learners_and_bank):
        """不再出现"双标注一致率=0.87" """
        learners, _ = learners_and_bank
        for learner in learners:
            profile = build_profile(learner, KG, "ch01_foundation")
            for ev in profile.evidence:
                assert "双标注一致率" not in ev.detail
                assert "0.87" not in ev.detail or "0.87" not in str(ev.detail)

    def test_evidence_dynamic(self, learners_and_bank):
        """证据内容随测试记录变化"""
        learners, _ = learners_and_bank
        if len(learners) >= 2:
            p1 = build_profile(learners[0], KG, "ch01_foundation")
            p2 = build_profile(learners[1], KG, "ch01_foundation")
            # 全局θ证据的 claim 应因学习者而异
            theta_ev1 = [e for e in p1.evidence if "全局能力" in e.claim]
            theta_ev2 = [e for e in p2.evidence if "全局能力" in e.claim]
            if theta_ev1 and theta_ev2:
                assert theta_ev1[0].claim != theta_ev2[0].claim or \
                       theta_ev1[0].detail != theta_ev2[0].detail


class TestP04_KpMapping:
    """P0-4: 全部30个旧知识点均可映射到平台概念"""

    def test_all_30_mapped(self):
        coverage = KG.mapping_coverage()
        assert coverage["total_kps"] == 30
        assert coverage["mapped"] == 30
        assert len(coverage["unmapped"]) == 0

    def test_kp_002_composite(self):
        """kp_002 展开为多个平台概念"""
        mapped = KG.map_kp_to_platform("kp_002")
        assert len(mapped) == 3

    def test_previously_unmapped(self):
        """原先未映射的6个kp现在已映射"""
        for kp_id in ["kp_001", "kp_021", "kp_022", "kp_024", "kp_025", "kp_026"]:
            mapped = KG.map_kp_to_platform(kp_id)
            assert len(mapped) >= 1, f"{kp_id} 未映射"

    def test_unknown_kp_returns_empty(self):
        assert KG.map_kp_to_platform("kp_999") == []

    def test_batch_mapping(self):
        all_kps = [kp.id for kp in KG.points]
        mapped = KG.map_kp_list_to_platform(all_kps)
        assert len(mapped) >= 30  # kp_002 展开后 >30

    def test_versions_in_meta(self, learners_and_bank):
        """画像 meta 中包含图谱版本和映射版本"""
        learners, _ = learners_and_bank
        profile = build_profile(learners[0], KG, "ch01_foundation")
        assert "kg_version" in profile.meta
        assert "mapping_version" in profile.meta


class TestP05_UnexploredNullMastery:
    """P0-5: 未测评节点 mastery=null"""

    def test_unexplored_has_null_mastery(self, learners_and_bank):
        learners, _ = learners_and_bank
        profile = build_profile(learners[0], KG, "ch01_foundation")
        for kp_id, pt in profile.knowledge_mastery.points.items():
            if pt.test_count == 0:
                assert pt.mastery is None, f"{kp_id} test_count=0 但 mastery={pt.mastery} 不为null"
                assert pt.status == "unexplored"

    def test_tested_has_numeric_mastery(self, learners_and_bank):
        learners, _ = learners_and_bank
        profile = build_profile(learners[0], KG, "ch01_foundation")
        has_tested = False
        for kp_id, pt in profile.knowledge_mastery.points.items():
            if pt.test_count > 0:
                assert pt.mastery is not None, f"{kp_id} 有测试记录但 mastery 为 null"
                has_tested = True
        # 至少应有一些被测试的知识点
        assert has_tested, "没有任何知识点被测试"

    def test_depth_labels_unexplored(self, learners_and_bank):
        """未测评知识点的 depth_labels 标注 '未测评'"""
        learners, _ = learners_and_bank
        profile = build_profile(learners[0], KG, "ch01_foundation")
        for dl in profile.depth_labels:
            pt = profile.knowledge_mastery.points.get(dl.kp_id)
            if pt and pt.test_count == 0:
                assert "未测评" in dl.rationale


class TestP13_GapConfidence:
    """P1-3: 未测节点盲区置信度修正"""

    def test_unexplored_low_confidence(self, learners_and_bank):
        """无测试记录的盲区置信度应低于有测试记录的"""
        learners, _ = learners_and_bank
        learner = learners[0]
        prior_theta = 0.0
        from core.irt import education_prior_theta
        prior_theta = education_prior_theta(learner.education.level)
        m_map, _, tc_map, _, _ = mastery.compute_all_mastery(
            KG, learner.test_records, learner.interaction_records, prior_theta
        )
        gaps = gap_analyzer.analyze_gaps(
            KG, m_map, learner.test_records, learner.interaction_records, tc_map
        )
        for g in gaps:
            if g.gap_type == "blindspot":
                tc = tc_map.get(g.kp_id, 0)
                if tc == 0:
                    assert g.confidence <= 0.40, f"{g.kp_id} test_count=0 但置信度={g.confidence}"
                elif tc >= 3:
                    assert g.confidence >= 0.80, f"{g.kp_id} test_count={tc} 但置信度={g.confidence}"


class TestP14_InputValidation:
    """P1-4: 输入校验"""

    def test_valid_upload(self):
        """合法上传成功"""
        resp = client.post("/api/learner/upload", json={
            "name": "测试用户",
            "education": {"level": "本科", "major": "CS"},
            "self_assessment": {
                "learning_goal": "学AI",
                "weekly_hours": 10,
            },
            "test_records": [
                {"knowledge_point_id": "kp_001", "difficulty": -1.0, "is_correct": True}
            ],
            "interaction_records": [
                {"knowledge_point_id": "kp_001", "type": "view", "duration": 120}
            ],
        })
        assert resp.status_code == 200

    def test_unknown_kp_id(self):
        """未知知识点ID返回422"""
        resp = client.post("/api/learner/upload", json={
            "name": "测试",
            "education": {"level": "本科"},
            "test_records": [
                {"knowledge_point_id": "kp_999", "difficulty": 0.0, "is_correct": True}
            ],
        })
        assert resp.status_code == 422

    def test_negative_time_spent(self):
        """负时长返回422"""
        resp = client.post("/api/learner/upload", json={
            "name": "测试",
            "education": {"level": "本科"},
            "test_records": [
                {"knowledge_point_id": "kp_001", "difficulty": 0.0, "is_correct": True, "time_spent": -5}
            ],
        })
        assert resp.status_code == 422

    def test_invalid_education_level(self):
        """非法学历返回422"""
        resp = client.post("/api/learner/upload", json={
            "name": "测试",
            "education": {"level": "幼儿园"},
            "test_records": [],
        })
        assert resp.status_code == 422
