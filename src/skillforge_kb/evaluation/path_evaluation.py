from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import DepthLevel, RelationKind
from skillforge_kb.planning.models import PathStatus, PlannerPolicy
from skillforge_kb.planning.ordering import stable_required_concept_ids
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.planning.serialization import build_policy_digest

from .models import (
    SYNTHETIC_DISCLAIMER,
    PathEvaluationCaseResult,
    PathEvaluationReport,
    ScenarioCohort,
    SyntheticPlanningDataset,
    build_path_evaluation_report_digest,
    reconstruct_path_evaluation_metrics,
)


def evaluate_course_paths(
    catalog: OntologyCatalog,
    dataset: SyntheticPlanningDataset,
    policy: PlannerPolicy | None = None,
) -> PathEvaluationReport:
    dataset = SyntheticPlanningDataset.model_validate(dataset.model_dump())
    active_policy = PlannerPolicy.model_validate((policy or PlannerPolicy()).model_dump())
    policy_digest = build_policy_digest(active_policy)
    if dataset.graph_version != catalog.course_document.version:
        raise ValueError("synthetic dataset graph version does not match catalog")
    if (
        dataset.policy_version != active_policy.version
        or dataset.policy_digest != policy_digest
    ):
        raise ValueError("synthetic dataset policy does not match evaluator policy")

    required_ids = stable_required_concept_ids(catalog)
    required_set = set(required_ids)
    hard_pairs = tuple(
        (relation.source, relation.target)
        for relation in catalog.relations(RelationKind.HARD_PREREQUISITE)
        if relation.source in required_set and relation.target in required_set
    )
    planner = CoursePlanner(catalog, active_policy)
    results: list[PathEvaluationCaseResult] = []
    for case in dataset.cases:
        decision = planner.plan(case.profile)
        actual_nodes = {node.concept_id: node for node in decision.nodes}
        actual_ids = tuple(node.concept_id for node in decision.nodes)
        actual_set = set(actual_ids)
        position = {concept_id: index for index, concept_id in enumerate(actual_ids)}
        expected_nodes = {item.concept_id: item for item in case.expected_nodes}
        missing_ids = tuple(sorted(required_set - actual_set))
        unexpected_ids = tuple(sorted(actual_set - required_set))
        evaluated_pairs = tuple(
            pair for pair in hard_pairs if pair[0] in position and pair[1] in position
        )
        violation_pairs = tuple(
            sorted(
                pair
                for pair in evaluated_pairs
                if position[pair[0]] >= position[pair[1]]
            )
        )
        skip_mismatches = tuple(
            concept_id
            for concept_id in required_ids
            if concept_id not in actual_nodes
            or (
                actual_nodes[concept_id].status is PathStatus.SKIPPED
            )
            is not expected_nodes[concept_id].should_skip
        )
        depth_evaluable_ids = tuple(
            concept_id
            for concept_id in required_ids
            if not expected_nodes[concept_id].should_skip
        )
        depth_mismatches = tuple(
            concept_id
            for concept_id in depth_evaluable_ids
            if concept_id not in actual_nodes
            or actual_nodes[concept_id].status is PathStatus.SKIPPED
            or actual_nodes[concept_id].delivery_depth
            is not expected_nodes[concept_id].delivery_depth
        )
        skipped_count = sum(
            node.status is PathStatus.SKIPPED for node in decision.nodes
        )
        conservative: bool | None = None
        if case.cohort is ScenarioCohort.LOW_CONFIDENCE:
            conservative = skipped_count == 0 and all(
                node.delivery_depth is DepthLevel.INTRO for node in decision.nodes
            )
        results.append(
            PathEvaluationCaseResult(
                case_id=case.case_id,
                cohort=case.cohort,
                tags=case.tags,
                path_id=decision.path_id,
                required_concept_count=len(required_ids),
                returned_concept_count=len(decision.nodes),
                covered_concept_count=len(required_set & actual_set),
                learning_node_count=len(decision.nodes) - skipped_count,
                skipped_node_count=skipped_count,
                hard_prerequisite_edge_count=len(evaluated_pairs),
                hard_prerequisite_violation_count=len(violation_pairs),
                skip_evaluable_count=len(required_ids),
                skip_match_count=len(required_ids) - len(skip_mismatches),
                depth_evaluable_count=len(depth_evaluable_ids),
                depth_match_count=len(depth_evaluable_ids) - len(depth_mismatches),
                order_stable=actual_ids == tuple(required_ids),
                low_confidence_conservative=conservative,
                missing_concept_ids=missing_ids,
                unexpected_concept_ids=unexpected_ids,
                prerequisite_violation_pairs=violation_pairs,
                skip_mismatch_ids=skip_mismatches,
                depth_mismatch_ids=depth_mismatches,
            )
        )

    case_results = tuple(results)
    metrics = reconstruct_path_evaluation_metrics(case_results)
    payload = {
        "schema_version": "path-evaluation-report.v1",
        "data_kind": "synthetic",
        "disclaimer": SYNTHETIC_DISCLAIMER,
        "data_version": dataset.data_version,
        "dataset_digest": dataset.dataset_digest,
        "graph_version": dataset.graph_version,
        "policy_version": active_policy.version,
        "policy_digest": policy_digest,
        "seed": dataset.seed,
        "generated_at": dataset.generated_at,
        "case_results": case_results,
        "metrics": metrics,
    }
    return PathEvaluationReport(
        data_version=dataset.data_version,
        dataset_digest=dataset.dataset_digest,
        graph_version=dataset.graph_version,
        policy_version=active_policy.version,
        policy_digest=policy_digest,
        seed=dataset.seed,
        generated_at=dataset.generated_at,
        case_results=case_results,
        metrics=metrics,
        report_digest=build_path_evaluation_report_digest(payload),
    )
