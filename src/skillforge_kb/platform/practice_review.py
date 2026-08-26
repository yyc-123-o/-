"""Safe, source-only feedback for the learning workbench code exercises."""

from __future__ import annotations

import json
import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from skillforge_kb.resources.controlled_generation import PracticeExercise


class PracticeReviewIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str


class PracticeReviewResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str
    accepted: bool
    execution_performed: bool = False
    issues: tuple[PracticeReviewIssue, ...] = ()
    missing_tokens: tuple[str, ...] = ()
    feedback: str
    next_step: str


class PracticeReviewLLM(Protocol):
    def complete(self, prompt: str, *, repair: str | None = None) -> str: ...


_MAX_SOURCE_LENGTH = 12_000
_FORBIDDEN_PATTERNS = {
    "subprocess": r"\b(?:import\s+subprocess|subprocess\.)",
    "filesystem": r"\b(?:open\s*\(|pathlib\.|os\.|shutil\.)",
    "network": r"\b(?:socket\.|requests\.|httpx\.|urllib\.)",
    "dynamic_execution": r"\b(?:eval\s*\(|exec\s*\(|__import__\s*\()",
}
_ALLOWED_IMPORTS = {"math", "numpy"}


def review_practice_submission(
    *,
    concept_id: str,
    source: str,
    exercise: PracticeExercise,
    llm: PracticeReviewLLM | None = None,
) -> PracticeReviewResult:
    """Review source text without compiling, importing, or executing it."""
    source = source.strip()
    issues: list[PracticeReviewIssue] = []
    if not source:
        issues.append(PracticeReviewIssue(code="empty_source", message="请先在编辑器中写入代码。"))
    if len(source) > _MAX_SOURCE_LENGTH:
        issues.append(
            PracticeReviewIssue(
                code="source_too_long",
                message=f"代码超过 {_MAX_SOURCE_LENGTH} 个字符，无法安全检查。",
            )
        )
    for code, pattern in _FORBIDDEN_PATTERNS.items():
        if re.search(pattern, source):
            issues.append(
                PracticeReviewIssue(
                    code=f"forbidden_{code}",
                    message=f"检测到不允许的 {code} 调用；本练习只接受纯 Python/NumPy 计算代码。",
                )
            )
    for imported in re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", source, re.MULTILINE):
        root = imported.split(".", 1)[0]
        if root not in _ALLOWED_IMPORTS:
            issues.append(
                PracticeReviewIssue(
                    code="forbidden_import",
                    message=f"不允许导入 {root}；本练习仅允许 math 或 numpy。",
                )
            )
    if "TODO" in source:
        issues.append(
            PracticeReviewIssue(code="unfinished", message="请先完成代码中的 TODO，再提交检查。")
        )
    identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", source))
    missing = tuple(token for token in exercise.required_tokens if token not in identifiers)
    if missing:
        issues.append(
            PracticeReviewIssue(
                code="missing_learning_tokens",
                message="尚未出现本题关键对象：" + "、".join(missing) + "。",
            )
        )

    if issues:
        return PracticeReviewResult(
            concept_id=concept_id,
            accepted=False,
            issues=tuple(issues),
            missing_tokens=missing,
            feedback="代码尚未满足本练习的静态检查条件。请根据问题列表完成最小修改后再次提交。",
            next_step=exercise.checks[0],
        )

    feedback = (
        "静态检查已通过：关键变量和输出语句齐全。请对照预期结果逐行解释，"
        "确认你理解的是计算过程，而不是只得到一个结果。"
    )
    next_step = exercise.checks[-1]
    if llm is not None:
        feedback, next_step = _llm_feedback(llm, concept_id, exercise, source, feedback, next_step)
    return PracticeReviewResult(
        concept_id=concept_id,
        accepted=True,
        feedback=feedback,
        next_step=next_step,
    )


def _llm_feedback(
    llm: PracticeReviewLLM,
    concept_id: str,
    exercise: PracticeExercise,
    source: str,
    fallback_feedback: str,
    fallback_next_step: str,
) -> tuple[str, str]:
    prompt = (
        "You are a programming tutor. Review source text only; never execute, import, "
        "or claim to run it. Return JSON with feedback and next_step. "
        "Give one concrete correction or confirmation, then one next step. "
        f"Concept: {concept_id}\nTask: {exercise.task}\n"
        f"Expected output: {exercise.expected_output}\n"
        f"Checks: {list(exercise.checks)}\nStudent source:\n```python\n{source}\n```"
    )
    try:
        payload = json.loads(llm.complete(prompt))
        feedback = payload.get("feedback")
        next_step = payload.get("next_step")
        if isinstance(feedback, str) and isinstance(next_step, str):
            return feedback[:2_000], next_step[:500]
    except (ValueError, TypeError, json.JSONDecodeError):
        pass
    return fallback_feedback, fallback_next_step
