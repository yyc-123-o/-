"""Export a candidate learning package into a review-friendly demonstration directory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .controlled_evaluation import ResourceEvaluationReport
from .controlled_generation import CandidateLearningPackage, ResourceGenerationBrief
from .demo_evidence import EvidenceBundleManifest, write_review_checklist
from .notebook_runner import NotebookExecutionReport


def export_candidate_demo(
    *,
    package: CandidateLearningPackage,
    brief: ResourceGenerationBrief,
    notebook_report: NotebookExecutionReport,
    evidence_bundle: EvidenceBundleManifest,
    output_root: Path = Path("reports/generated"),
    evaluation: ResourceEvaluationReport | None = None,
) -> Path:
    """Write a self-contained, explicitly non-released review package."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = output_root / f"resource_demo_{timestamp}"
    destination.mkdir(parents=True, exist_ok=False)
    _write_overview(destination / "00_demo_overview.md", package, brief, notebook_report)
    if package.draft is not None:
        _write_materials(destination, package)
    _write_notebook(destination / "05_pytorch_practical_notebook.ipynb")
    _write_json(destination / "05_notebook_execution_report.json", notebook_report)
    _write_json(destination / "06_generation_trace.json", package.trace)
    if package.audit_report is not None:
        _write_json(destination / "07_audit_report.json", package.audit_report)
        _write_json(
            destination / "08_claim_evidence_ledger.json",
            {"claim_evidence_ledger": package.audit_report.claim_evidence_ledger},
        )
    _write_json(destination / "09_personalization_coverage.json", evaluation or {})
    if evaluation is not None:
        _write_json(destination / "10_three_profile_evaluation.json", evaluation)
        _write_comparison(destination / "11_comparison_report.md", evaluation)
    else:
        (destination / "10_three_profile_evaluation.json").write_text(
            json.dumps({"status": "not_run"}, indent=2) + "\n", encoding="utf-8"
        )
        (destination / "11_comparison_report.md").write_text(
            "# Three-profile comparison\n\nNot run for this single-profile package.\n",
            encoding="utf-8",
        )
    _write_json(destination / "12_evidence_bundle.json", evidence_bundle)
    write_review_checklist(evidence_bundle, destination / "12_evidence_review_checklist.md")
    return destination


def _write_overview(
    path: Path,
    package: CandidateLearningPackage,
    brief: ResourceGenerationBrief,
    notebook: NotebookExecutionReport,
) -> None:
    blockers = [
        "`dl.vision.image-tensor` prerequisite is unresolved.",
        "Referenced release evidence has not reached `approved` status.",
    ]
    body = [
        "# CNN Candidate Learning Package",
        "",
        "> **RESOURCE STATUS: candidate_draft**",
        ">",
        f"> Generation: `{package.generation_status.value}`",
        f"> Audit: `{package.audit_status.value}`",
        f"> Publication: `{package.publication_status.value}`",
        "",
        "## Release blockers",
        *[f"- {blocker}" for blocker in blockers],
        "",
        "This package is for demonstration and review only; it is not an officially released "
        "course resource.",
        "",
        "## Immutable execution boundary",
        f"- Policy: `{brief.policy.policy_id}`",
        f"- Concept: `{brief.policy.concept_id}`",
        f"- Depth: `{brief.policy.delivery_depth}`",
        f"- Notebook: `{notebook.status}`; isolation: `{notebook.network_isolation}`",
    ]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def _write_materials(destination: Path, package: CandidateLearningPackage) -> None:
    assert package.draft is not None
    lecture = package.draft.lecture
    practical = package.draft.practical_guide
    quiz = package.draft.student_quiz
    teacher = package.draft.teacher_guide
    (destination / "01_lecture.md").write_text(
        f"# {lecture.title}\n\n" + "\n\n".join(lecture.sections) + "\n",
        encoding="utf-8",
    )
    def exercise_section(title: str, exercise: object | None) -> str:
        if exercise is None:
            return ""
        return (
            f"\n\n## {title}\n\n{exercise.task}\n\n"
            "```python\n"
            f"{exercise.starter_code}\n"
            "```\n\n"
            f"Expected output: {exercise.expected_output}\n\n"
            + "Checks:\n"
            + "\n".join(f"- {check}" for check in exercise.checks)
        )

    (destination / "02_pytorch_practical_guide.md").write_text(
        f"# {practical.title}\n\n## Steps\n"
        + "\n".join(f"- {step}" for step in practical.learning_steps)
        + "\n\n## Notebook tasks\n"
        + "\n".join(f"- {task}" for task in practical.notebook_tasks)
        + "\n\n## Experiment protocol\n"
        + "\n".join(f"{index}. {step}" for index, step in enumerate(practical.experiment_protocol, start=1))
        + exercise_section("基础教学代码", practical.exercise)
        + exercise_section("项目式复杂代码", practical.project_exercise)
        + "\n",
        encoding="utf-8",
    )
    (destination / "03_student_quiz.md").write_text(
        "# Student Quiz\n\n"
        + quiz.instructions
        + "\n\n"
        + "\n\n".join(
            f"## {item.question_id} · {item.kind.value} · difficulty {item.difficulty}\n\n"
            f"{item.prompt}\n"
            for item in quiz.items
        ),
        encoding="utf-8",
    )
    (destination / "04_teacher_guide.md").write_text(
        "# Teacher Answers and Diagnostics\n\n"
        + "\n\n".join(
            f"## {item.question_id}\n\nAnswer: {item.answer}\n\n"
            f"Scoring: {'; '.join(item.scoring_points)}\n\n"
            f"Diagnosis: {item.error_diagnosis}\n\nAction: {item.teaching_action}"
            for item in teacher.items
        )
        + "\n",
        encoding="utf-8",
    )


def _write_notebook(path: Path) -> None:
    core = [
        "import torch\n",
        "from torch import nn\n",
        "x = torch.zeros((2, 3, 32, 32))\n",
        "layer = nn.Conv2d(3, 8, kernel_size=3, stride=2, padding=1)\n",
        "y = layer(x)\n",
        "expected_height = ((32 + 2 * 1 - 3) // 2) + 1\n",
        "assert tuple(x.shape) == (2, 3, 32, 32)\n",
        "assert tuple(y.shape) == (2, 8, expected_height, expected_height)\n",
    ]
    notebook = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# System-owned CNN core\n"]},
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": core,
            },
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_comparison(path: Path, report: ResourceEvaluationReport) -> None:
    metrics = (
        "review_section_count",
        "starter_code_ratio",
        "mean_quiz_difficulty",
        "debug_hint_depth",
        "review_task_count",
        "explanation_order",
        "feedback_strategy",
    )
    profiles = list(report.comparison_matrix)
    lines = ["# Three-profile control-variable comparison", ""]
    lines.append("| Metric | " + " | ".join(profiles) + " |")
    lines.append("|---|" + "|".join("---" for _ in profiles) + "|")
    for metric in metrics:
        values = [str(report.comparison_matrix[profile].get(metric, "")) for profile in profiles]
        lines.append("| " + metric + " | " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, value: object) -> None:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
