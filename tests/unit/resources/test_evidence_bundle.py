import pytest

from skillforge_kb.resources.evidence_bundle import build_evidence_bundle

from .test_briefs import _builder, _profile


def test_bundle_uses_filtered_published_evidence_in_stable_order(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    brief = builder.build(decision, profile, node.concept_id)

    first = build_evidence_bundle(brief, builder.evidence_index)
    second = build_evidence_bundle(brief, builder.evidence_index)

    assert first == second
    assert first.bundle_id == second.bundle_id
    assert [record.evidence_id for record in first.records] == sorted(
        record.evidence_id for record in first.records
    )
    assert all(record.concept_id == brief.concept_id for record in first.records)
    assert all(record.depth is brief.delivery_depth for record in first.records)
    assert {record.content_kind for record in first.records} == set(
        brief.evidence_filters.content_kinds
    )


def test_bundle_rejects_missing_required_evidence(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    brief = builder.build(decision, profile, node.concept_id)
    empty = builder.evidence_index.model_copy(update={"records": ()})

    with pytest.raises(ValueError, match="missing published evidence"):
        build_evidence_bundle(brief, empty)


def test_bundle_rejects_cross_version_index(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    brief = builder.build(decision, profile, node.concept_id)
    other_version = builder.evidence_index.model_copy(update={"graph_version": "v2"})

    with pytest.raises(ValueError, match="graph version"):
        build_evidence_bundle(brief, other_version)
