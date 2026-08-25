"""学情诊断 Agent — FastAPI 入口 (v2.1)

启动: uvicorn main:app --reload --port 8000

新增 (v2.1):
  - POST /api/learner/upload          上传自定义学习者数据
  - POST /api/adaptive-test/start      启动自适应测试会话
  - POST /api/adaptive-test/answer     提交答案，获取下一题
  - GET  /api/adaptive-test/session    查看会话状态
  - POST /api/learner/{id}/diagnose    支持 ?chapter_id= 参数
  - GET  /api/chapters                 章节列表
"""

from __future__ import annotations
import os, sys, uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.schemas import (
    Learner, LearnerProfile, DiagnosisResult,
    Education, SelfAssessment, TestRecord, InteractionRecord,
    CourseSelfAssessment, DomainAssessment, ProjectExperience,
)
from models.knowledge_graph import KG
from core.profile_builder import build_profile
from core import adaptive_test
from generators.mock_generator import generate_all_mock_data, save_mock_data

app = FastAPI(
    title="学情诊断 Agent v2.1",
    description="基于IRT项目反应理论的学习者画像构建 · 自适应测试 · 知识盲区诊断 · 章节级资源生成提示",
    version="2.1.0",
)

app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")

_learners: Dict[str, Learner] = {}
_profiles: Dict[tuple[str, str], LearnerProfile] = {}
_test_bank: list = []
_applied_sessions: Dict[str, dict] = {}
_EDUCATION_LEVELS = {"\u4e13\u79d1", "\u672c\u79d1", "\u7855\u58eb", "\u535a\u58eb"}
_INTERACTION_TYPES = {"view", "quiz", "practice", "discussion"}
_SELF_ASSESSMENT_LEVELS = {"未学过", "入门", "基础", "熟练", "精通"}


def _profile_key(learner_id: str, chapter_id: str | None) -> tuple[str, str]:
    return learner_id, chapter_id or "ch03_cnn"


def _invalidate_profiles(learner_id: str) -> None:
    for key in tuple(_profiles):
        if key[0] == learner_id:
            _profiles.pop(key, None)


@app.on_event("startup")
async def startup():
    global _test_bank
    learners, _test_bank = generate_all_mock_data()
    for l in learners:
        _learners[l.id] = l
    print(f"[启动] {len(_learners)} 组模拟学习者, {len(_test_bank)} 道测试题, {len(KG.chapters)} 个章节")


# ============================================================
# 知识图谱 & 题库 & 章节
# ============================================================

@app.get("/api/knowledge-graph")
async def get_knowledge_graph():
    return {"domains": KG.domains(), "knowledge_points": KG.to_dict_list(), "total": len(KG.points)}

@app.get("/api/chapters")
async def get_chapters():
    """获取章节列表 — 供前端章节选择器"""
    return {"chapters": KG.chapters_to_dict()}

@app.get("/api/test-bank")
async def get_test_bank():
    return {
        "questions": [adaptive_test.public_question(question) for question in _test_bank],
        "total": len(_test_bank),
    }


# ============================================================
# 学习者管理
# ============================================================

@app.get("/api/learners")
async def list_learners():
    return {
        "learners": [
            {
                "id": l.id, "name": l.name,
                "education_level": l.education.level, "major": l.education.major,
                "test_count": len(l.test_records), "interaction_count": len(l.interaction_records),
            }
            for l in _learners.values()
        ]
    }

@app.get("/api/learner/{learner_id}")
async def get_learner(learner_id: str):
    learner = _learners.get(learner_id)
    if not learner:
        raise HTTPException(status_code=404, detail="学习者不存在")
    return learner.model_dump(mode="json")


# ============================================================
# ★ 上传自定义学习者数据 (NEW)
# ============================================================

@app.post("/api/learner/upload")
async def upload_learner(payload: dict = Body(...)):
    """上传学习者 JSON 数据 — 支持自填问卷 + 答题记录 + 交互记录

    请求体示例:
    {
      "name": "张三",
      "education": {"level": "本科", "major": "计算机", "institution": "某大学"},
      "self_assessment": {"ml_level": "入门", "dl_level": "零基础", ...},
      "test_records": [{"knowledge_point_id": "kp_001", "difficulty": -1.0, "discrimination": 1.0, "is_correct": true, ...}, ...],
      "interaction_records": [{"knowledge_point_id": "kp_001", "type": "view", "duration": 120, ...}, ...]
    }
    """
    import uuid as _uuid
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="学习者数据必须是 JSON 对象")
    lid = payload.get("id", f"uploaded_{_uuid.uuid4().hex[:8]}")

    # 解析 education
    edu_data = payload.get("education", {})
    if not isinstance(edu_data, dict):
        raise HTTPException(status_code=422, detail="education 必须是对象")
    if edu_data.get("level", "本科") not in _EDUCATION_LEVELS:
        raise HTTPException(status_code=422, detail="education.level 不是受支持的学历层次")
    education = Education(
        level=edu_data.get("level", "本科"),
        major=edu_data.get("major", ""),
        institution=edu_data.get("institution", ""),
        graduation_year=edu_data.get("graduation_year", 2025),
        gpa=edu_data.get("gpa"),
        relevant_courses=edu_data.get("relevant_courses", []),
    )

    # 解析 self_assessment
    sa_data = payload.get("self_assessment", {})
    if not isinstance(sa_data, dict):
        raise HTTPException(status_code=422, detail="self_assessment 必须是对象")
    domain_assessments = [
        DomainAssessment(
            domain=item.get("domain", ""),
            courses=[CourseSelfAssessment(**course) for course in item.get("courses", [])],
            note=item.get("note", ""),
        )
        for item in sa_data.get("domain_assessments", [])
    ]
    courses = [CourseSelfAssessment(**course) for course in sa_data.get("courses", [])]
    for assessment in domain_assessments:
        courses.extend(assessment.courses)
    self_assessment = SelfAssessment(
        ml_level=sa_data.get("ml_level", ""),
        dl_level=sa_data.get("dl_level", ""),
        math_level=sa_data.get("math_level", ""),
        programming_level=sa_data.get("programming_level", ""),
        learning_goal=sa_data.get("learning_goal", ""),
        weekly_hours=sa_data.get("weekly_hours", 5),
        position=sa_data.get("position", ""),
        strengths=sa_data.get("strengths", ""),
        weaknesses=sa_data.get("weaknesses", ""),
        courses=courses,
        domain_assessments=domain_assessments,
        projects=[ProjectExperience(**p) for p in sa_data.get("projects", [])],
    )

    # 解析 test_records
    test_records = []
    for t in payload.get("test_records", []):
        if t.get("knowledge_point_id") not in set(KG.all_ids()):
            raise HTTPException(status_code=422, detail=f"未知知识点: {t.get('knowledge_point_id')}")
        if not isinstance(t.get("is_correct"), bool):
            raise HTTPException(status_code=422, detail="test_records.is_correct 必须是布尔值")
        if t.get("time_spent", 60) < 0 or t.get("discrimination", 1.0) <= 0:
            raise HTTPException(status_code=422, detail="测试时间必须非负且区分度必须为正数")
        test_records.append(TestRecord(
            knowledge_point_id=t["knowledge_point_id"],
            question_id=t.get("question_id", ""),
            difficulty=t.get("difficulty", 0.0),
            discrimination=t.get("discrimination", 1.0),
            is_correct=t["is_correct"],
            time_spent=t.get("time_spent", 60),
            hint_used=t.get("hint_used", False),
            error_pattern=t.get("error_pattern"),
        ))

    # 解析 interaction_records
    interaction_records = []
    for i in payload.get("interaction_records", []):
        if i.get("knowledge_point_id") not in set(KG.all_ids()):
            raise HTTPException(status_code=422, detail=f"未知知识点: {i.get('knowledge_point_id')}")
        if i.get("type", "view") not in _INTERACTION_TYPES or i.get("duration", 60) < 0:
            raise HTTPException(status_code=422, detail="交互类型或持续时间无效")
        interaction_records.append(InteractionRecord(
            knowledge_point_id=i["knowledge_point_id"],
            type=i.get("type", "view"),
            duration=i.get("duration", 60),
            detail=i.get("detail", ""),
        ))

    learner = Learner(
        id=lid,
        name=payload.get("name", "未命名"),
        education=education,
        self_assessment=self_assessment,
        test_records=test_records,
        interaction_records=interaction_records,
    )

    _learners[lid] = learner
    _invalidate_profiles(lid)
    return {
        "message": f"学习者 {learner.name} 已上传",
        "learner_id": lid,
        "test_count": len(test_records),
        "interaction_count": len(interaction_records),
    }


# ============================================================
# 学情诊断 (v2.1: 支持章节参数)
# ============================================================

@app.post("/api/learner/{learner_id}/diagnose")
async def diagnose_learner(
    learner_id: str,
    chapter_id: Optional[str] = Query(None, description="目标章节ID, 如 ch03_cnn"),
):
    """执行学情诊断 — 可选指定章节以生成对应 resource_hints"""
    learner = _learners.get(learner_id)
    if not learner:
        raise HTTPException(status_code=404, detail="学习者不存在")

    ch_id = chapter_id or "ch03_cnn"
    if not KG.get_chapter(ch_id):
        raise HTTPException(status_code=400, detail=f"章节 {ch_id} 不存在, 可用: {[c.chapter_id for c in KG.chapters]}")

    profile = build_profile(learner, KG, current_chapter_id=ch_id)
    _profiles[_profile_key(learner_id, ch_id)] = profile

    return DiagnosisResult(
        success=True,
        profile=profile,
        message=f"诊断完成 (章节: {ch_id}): {profile.meta.get('total_test_count', 0)}条测试记录, {len(profile.knowledge_gaps)}个知识盲区",
    )


@app.get("/api/learner/{learner_id}/profile")
async def get_profile(learner_id: str, chapter_id: Optional[str] = Query(None)):
    key = _profile_key(learner_id, chapter_id)
    profile = _profiles.get(key)
    if not profile:
        learner = _learners.get(learner_id)
        if not learner:
            raise HTTPException(status_code=404, detail="学习者不存在")
        profile = build_profile(learner, KG, current_chapter_id=chapter_id or "ch03_cnn")
        _profiles[key] = profile
    return profile.model_dump(mode="json")


@app.get("/api/learner/{learner_id}/gaps")
async def get_gaps(learner_id: str):
    key = _profile_key(learner_id, None)
    profile = _profiles.get(key)
    if not profile:
        learner = _learners.get(learner_id)
        if not learner:
            raise HTTPException(status_code=404, detail="学习者不存在")
        profile = build_profile(learner, KG)
        _profiles[key] = profile
    return {"gaps": [g.model_dump(mode="json") for g in profile.knowledge_gaps]}


@app.get("/api/learner/{learner_id}/mastery-detail")
async def get_mastery_detail(learner_id: str):
    key = _profile_key(learner_id, None)
    profile = _profiles.get(key)
    if not profile:
        learner = _learners.get(learner_id)
        if not learner:
            raise HTTPException(status_code=404, detail="学习者不存在")
        profile = build_profile(learner, KG)
        _profiles[key] = profile

    domain_data = {}
    for kp in KG.points:
        domain = kp.domain
        if domain not in domain_data:
            domain_data[domain] = []
        pt = profile.knowledge_mastery.points.get(kp.id)
        domain_data[domain].append({
            "kp_id": kp.id, "kp_name": kp.name,
            "difficulty": kp.difficulty,
            "mastery": pt.mastery if pt else 0.0,
            "prerequisites": kp.prerequisites,
        })
    return {"domain_data": domain_data}


# ============================================================
# ★ 自适应测试 (NEW)
# ============================================================

@app.post("/api/adaptive-test/start/{learner_id}")
async def start_adaptive_test(learner_id: str, payload: Optional[dict] = Body(default=None)):
    """启动自适应测试 — 返回第一道题

    可选 JSON body (分类测试 + 难度梯度 + 结束条件):
    {
      "domains": ["数学基础"],                      // 按领域过滤
      "knowledge_point_ids": ["kp_012", "kp_014"],  // 按知识点过滤
      "difficulty_stages": [{"label":"易","low":-3,"high":-0.2,"promote_accuracy":0.7,"min_questions":2}, ...],
      "max_questions": 30, "min_questions": 8,
      "consecutive_wrong_stop": 3, "convergence_threshold": 0.15
    }
    """
    learner = _learners.get(learner_id)
    if not learner:
        raise HTTPException(status_code=404, detail="学习者不存在")
    prior_theta = 0.0
    if learner.education:
        from core.irt import education_prior_theta
        prior_theta = education_prior_theta(learner.education.level)
    try:
        config = adaptive_test.build_config(payload) if payload else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = adaptive_test.start_session(learner_id, prior_theta, _test_bank, config=config)
    if result.get("bank_size", 0) == 0:
        raise HTTPException(status_code=422, detail="筛选条件没有匹配的测试题")
    return result


@app.get("/api/adaptive-test/config")
async def get_adaptive_config():
    """返回默认配置 + 可用领域/知识点 — 供前端渲染配置表单"""
    return {
        "default": adaptive_test.default_config_payload(),
        "domains": KG.domains(),
        "knowledge_points": KG.to_dict_list(),
    }


@app.post("/api/adaptive-test/answer")
async def answer_adaptive_test(payload: dict = Body(...)):
    """提交答案 — 返回下一题或停止信号

    请求体: {"session_id": "...", "question_id": "...", "selected_answer": 1, "time_spent": 45}
    """
    if "is_correct" in payload:
        raise HTTPException(status_code=422, detail="禁止提交 is_correct，请提交 selected_answer")
    if "selected_answer" not in payload:
        raise HTTPException(status_code=422, detail="缺少 selected_answer")
    result = adaptive_test.submit_answer(
        session_id=payload["session_id"],
        question_id=payload["question_id"],
        selected_answer=payload["selected_answer"],
        time_spent=payload.get("time_spent", 60),
        test_bank=_test_bank,
    )
    return result


@app.get("/api/adaptive-test/session/{session_id}")
async def get_adaptive_session(session_id: str):
    """查看自适应测试会话状态"""
    s = adaptive_test.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    return s


@app.post("/api/adaptive-test/apply/{learner_id}")
async def apply_adaptive_test(learner_id: str, session_id: str = Query(...)):
    """将自适应测试会话的答题记录转移到学习者 — 必须在诊断前调用"""
    learner = _learners.get(learner_id)
    if not learner:
        raise HTTPException(status_code=404, detail="学习者不存在")

    s = adaptive_test.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not s.get("finished"):
        raise HTTPException(status_code=400, detail="测试尚未完成，请先结束测试")
    if s.get("learner_id") != learner_id:
        raise HTTPException(status_code=403, detail="测试会话不属于当前学习者")
    if session_id in _applied_sessions:
        return _applied_sessions[session_id]

    answers = s.get("answers", [])
    if not answers:
        raise HTTPException(status_code=400, detail="无答题记录")

    # 将每条答题记录转为 TestRecord 并追加到 learner
    from models.schemas import TestRecord as TR
    new_records = []
    for a in answers:
        q = next((q for q in _test_bank if q["question_id"] == a["question_id"]), None)
        new_records.append(TR(
            knowledge_point_id=a.get("kp_id", q["knowledge_point_id"] if q else ""),
            question_id=a["question_id"],
            difficulty=a.get("difficulty", q["difficulty"] if q else 0.0),
            discrimination=a.get("discrimination", q["discrimination"] if q else 1.0),
            is_correct=a["is_correct"],
            time_spent=a.get("time_spent", 60),
        ))

    learner.test_records.extend(new_records)
    _invalidate_profiles(learner_id)

    result = {
        "message": f"已转移 {len(new_records)} 条答题记录到学习者 {learner.name}",
        "learner_id": learner_id,
        "added_count": len(new_records),
        "total_test_count": len(learner.test_records),
    }
    _applied_sessions[session_id] = result
    return result


# ============================================================
# 模拟数据管理
# ============================================================

@app.post("/api/demo/generate")
async def generate_mock_data():
    global _test_bank, _learners, _profiles, _applied_sessions
    learners, _test_bank = generate_all_mock_data()
    _learners.clear(); _profiles.clear(); _applied_sessions.clear()
    for l in learners:
        _learners[l.id] = l
    save_mock_data(str(PROJECT_ROOT / "data"))
    return {
        "message": "模拟数据已重新生成",
        "learners": [{"id": l.id, "name": l.name, "level": l.education.level} for l in learners],
    }


# ============================================================
# 前端
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = PROJECT_ROOT / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
