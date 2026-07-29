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
    records = {record.evidence_id: record for record in bundle.records}
    for artifact in first.artifacts:
        for item in artifact.items:
            for citation in item.citations:
                record = records[citation.evidence_id]
                assert citation.source_id == record.source_id
                assert citation.chunk_id == record.chunk_id
                assert citation.locator == record.locator
                assert citation.normalized_hash == record.normalized_hash


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

    uncited_item = first_item.model_copy(update={"citations": ()})
    uncited = generated[0].model_copy(update={"items": (uncited_item,)})
    with pytest.raises(ValueError, match="citation"):
        ResourceGenerationTool().validate(brief, bundle, (uncited, *generated[1:]))

    unknown_citation = first_item.citations[0].model_copy(
        update={"evidence_id": "evidence_" + "f" * 64}
    )
    unknown_item = first_item.model_copy(update={"citations": (unknown_citation,)})
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
    exercise_citation = next(
        artifact.items[0].citations[0]
        for artifact in generated
        if artifact.resource_type.value == "assessment"
    )
    lecture_item = generated[0].items[0].model_copy(
        update={"citations": (exercise_citation,)}
    )
    invalid_lecture = generated[0].model_copy(update={"items": (lecture_item,)})

    with pytest.raises(ValueError, match="resource evidence kind"):
        ResourceGenerationTool().validate(
            brief,
            bundle,
            (invalid_lecture, *generated[1:]),
        )


def test_tool_rejects_citation_metadata_mutation(resource_case) -> None:
    brief, bundle = resource_case
    generated = FakeResourceGenerator().generate(brief, bundle)
    item = generated[0].items[0]
    invalid_citation = item.citations[0].model_copy(update={"locator": "wrong"})
    invalid_item = item.model_copy(update={"citations": (invalid_citation,)})
    invalid_artifact = generated[0].model_copy(update={"items": (invalid_item,)})

    with pytest.raises(ValueError, match="citation metadata"):
        ResourceGenerationTool().validate(
            brief,
            bundle,
            (invalid_artifact, *generated[1:]),
        )
