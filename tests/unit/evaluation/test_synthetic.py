from collections import Counter

import pytest
from pydantic import ValidationError

from skillforge_kb.evaluation import (
    ScenarioCohort,
    SyntheticPlanningDataset,
    generate_synthetic_dataset,
)


def test_default_generation_is_deterministic_and_stratified(catalog) -> None:
    first = generate_synthetic_dataset(catalog)
    second = generate_synthetic_dataset(catalog)

    assert first == second
    assert len(first.cases) == 60
    assert {case.cohort for case in first.cases} == set(ScenarioCohort)
    counts = Counter(case.cohort for case in first.cases)
    assert max(counts.values()) - min(counts.values()) <= 1
    assert first.data_kind == "synthetic"


def test_generation_changes_values_but_not_allocation_when_seed_changes(catalog) -> None:
    first = generate_synthetic_dataset(catalog, seed=1)
    second = generate_synthetic_dataset(catalog, seed=2)

    assert tuple(case.cohort for case in first.cases) == tuple(
        case.cohort for case in second.cases
    )
    assert first.dataset_digest != second.dataset_digest


def test_generation_rejects_too_few_cases(catalog) -> None:
    with pytest.raises(ValueError, match="at least eight"):
        generate_synthetic_dataset(catalog, case_count=7)


def test_generated_cases_cover_each_required_concept_once(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    required_ids = {concept.id for concept in catalog.concepts() if concept.required}

    for case in dataset.cases:
        expected_ids = [node.concept_id for node in case.expected_nodes]
        assert set(expected_ids) == required_ids
        assert len(expected_ids) == len(set(expected_ids))
        assert all(
            (node.delivery_depth is None) == node.should_skip
            for node in case.expected_nodes
        )


def test_dataset_rejects_duplicate_case_ids(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    payload = dataset.model_dump()
    payload["cases"] = [payload["cases"][0], *payload["cases"][:-1]]

    with pytest.raises(ValidationError, match="case IDs"):
        SyntheticPlanningDataset.model_validate(payload)


def test_dataset_digest_rejects_content_mutation(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    payload = dataset.model_dump()
    payload["seed"] = dataset.seed + 1

    with pytest.raises(ValidationError, match="digest"):
        SyntheticPlanningDataset.model_validate(payload)


def test_dataset_models_are_frozen(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)

    with pytest.raises(ValidationError, match="frozen"):
        dataset.seed = 7
