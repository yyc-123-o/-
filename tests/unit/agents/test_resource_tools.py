import pytest

from skillforge_kb.agents.resource_tools import (
    FakeResourceGenerator,
    ResourceGenerationTool,
)


def test_fake_resource_tool_is_deterministic_and_complete(resource_case) -> None:
    brief, bundle = resource_case
    tool = ResourceGenerationTool()
    generator = FakeResourceGenerator()

    first = tool.invoke(brief, bundle, generator)
    second = tool.invoke(brief, bundle, generator)

    assert first == second
    assert first.result_id == second.result_id
    assert {artifact.resource_type for artifact in first.artifacts} == set(
        brief.required_resource_types
    )
    assert all(artifact.path_id == brief.path_id for artifact in first.artifacts)


def test_tool_rejects_path_mutation(resource_case) -> None:
    brief, bundle = resource_case
    generated = FakeResourceGenerator().generate(brief, bundle)
    invalid = generated[0].model_copy(update={"path_id": "path_" + "0" * 64})

    with pytest.raises(ValueError, match="path contract"):
        ResourceGenerationTool().validate(brief, bundle, (invalid, *generated[1:]))


def test_tool_rejects_uncited_and_unknown_evidence(resource_case) -> None:
    brief, bundle = resource_case
    generated = FakeResourceGenerator().generate(brief, bundle)
    first_item = generated[0].items[0]

    uncited_item = first_item.model_copy(update={"evidence_ids": ()})
    uncited = generated[0].model_copy(update={"items": (uncited_item,)})
    with pytest.raises(ValueError, match="citation"):
        ResourceGenerationTool().validate(brief, bundle, (uncited, *generated[1:]))

    unknown_item = first_item.model_copy(
        update={"evidence_ids": ("evidence_" + "f" * 64,)}
    )
    unknown = generated[0].model_copy(update={"items": (unknown_item,)})
    with pytest.raises(ValueError, match="unknown evidence"):
        ResourceGenerationTool().validate(brief, bundle, (unknown, *generated[1:]))


def test_tool_rejects_missing_required_resource_type(resource_case) -> None:
    brief, bundle = resource_case
    generated = FakeResourceGenerator().generate(brief, bundle)

    with pytest.raises(ValueError, match="required resource types"):
        ResourceGenerationTool().validate(brief, bundle, generated[:-1])


def test_tool_rejects_bundle_scope_mutation(resource_case) -> None:
    brief, bundle = resource_case
    generated = FakeResourceGenerator().generate(brief, bundle)
    invalid_bundle = bundle.model_copy(update={"concept_id": "unknown.concept"})

    with pytest.raises(ValueError, match="bundle scope"):
        ResourceGenerationTool().validate(brief, invalid_bundle, generated)


def test_tool_rejects_resource_irrelevant_citations(resource_case) -> None:
    brief, bundle = resource_case
    generated = FakeResourceGenerator().generate(brief, bundle)
    exercise_id = next(
        record.evidence_id
        for record in bundle.records
        if record.content_kind.value == "exercise"
    )
    lecture_item = generated[0].items[0].model_copy(
        update={"evidence_ids": (exercise_id,)}
    )
    invalid_lecture = generated[0].model_copy(update={"items": (lecture_item,)})

    with pytest.raises(ValueError, match="resource evidence kind"):
        ResourceGenerationTool().validate(
            brief,
            bundle,
            (invalid_lecture, *generated[1:]),
        )
