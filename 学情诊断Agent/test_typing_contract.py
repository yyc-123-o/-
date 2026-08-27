"""Ensure public helpers expose resolvable type annotations."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import get_type_hints

PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.profile_builder import _build_evidence, _build_knowledge_mastery
from generators.mock_generator import generate_learner, generate_test_bank


def test_profile_builder_annotations_are_resolvable() -> None:
    assert "kp_priors" in get_type_hints(_build_knowledge_mastery)
    assert "kp_priors" in get_type_hints(_build_evidence)


def test_mock_generator_annotations_are_resolvable() -> None:
    assert "kg" in get_type_hints(generate_test_bank)
    assert "kg" in get_type_hints(generate_learner)
