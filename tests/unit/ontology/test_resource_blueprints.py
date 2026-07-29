from pathlib import Path

from skillforge_kb.ontology.concept_attributes import (
    concept_attributes,
    load_concept_attributes,
)
from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.ontology.resource_blueprints import (
    load_resource_blueprints,
    resource_blueprint,
)


def test_every_required_concept_depth_has_a_resource_blueprint(catalog) -> None:
    blueprints = load_resource_blueprints(
        catalog,
        Path(__file__).parents[3] / "resources" / "ontology" / "resource_blueprints_v1.yaml",
    )

    for concept in catalog.concepts():
        if not concept.required:
            continue
        for depth in DepthLevel:
            blueprint = resource_blueprint(blueprints, concept.id, depth)
            assert blueprint.learning_outcomes
            assert blueprint.resource_types
            assert blueprint.assessment_kinds


def test_resource_blueprint_preserves_concept_level_outcomes(catalog) -> None:
    blueprints = load_resource_blueprints(
        catalog,
        Path(__file__).parents[3] / "resources" / "ontology" / "resource_blueprints_v1.yaml",
    )
    blueprint = resource_blueprint(blueprints, "math.linear-algebra.scalar", DepthLevel.INTRO)
    level = catalog.get_concept("math.linear-algebra.scalar").levels[0]

    assert blueprint.learning_outcomes == tuple(level.learning_outcomes)
    assert blueprint.assessment_kinds == tuple(level.assessment_kinds)


def test_every_concept_has_normalized_ability_demand(catalog) -> None:
    attributes = load_concept_attributes(
        catalog,
        Path(__file__).parents[3] / "resources" / "ontology" / "concept_attributes_v1.yaml",
    )

    for concept in catalog.concepts():
        demand = concept_attributes(attributes, concept.id).ability_demand
        assert sum(demand.values()) == 1.0


def test_chapter_defaults_distinguish_math_and_applied_nodes(catalog) -> None:
    attributes = load_concept_attributes(
        catalog,
        Path(__file__).parents[3] / "resources" / "ontology" / "concept_attributes_v1.yaml",
    )
    math = concept_attributes(attributes, "math.linear-algebra.scalar").ability_demand
    applied = concept_attributes(attributes, "ml.supervised.learning").ability_demand

    assert math.mathematical_foundation > math.coding_ability
    assert applied.coding_ability > math.coding_ability
