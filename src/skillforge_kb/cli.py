import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
import uvicorn
import yaml
from langgraph.checkpoint.sqlite import SqliteSaver
from neo4j import GraphDatabase
from pydantic import ValidationError

from skillforge_kb.agents.runtime import (
    StandaloneAgentPaths,
    load_planning_event,
    run_standalone_event,
    validate_standalone_agent_paths,
)
from skillforge_kb.api.app import create_app
from skillforge_kb.config import Settings
from skillforge_kb.evaluation import (
    DEFAULT_SYNTHETIC_CASE_COUNT,
    DEFAULT_SYNTHETIC_SEED,
    evaluate_course_paths,
    generate_synthetic_dataset,
    load_synthetic_dataset,
    search_planner_policies,
    write_path_evaluation_report,
    write_planner_policy_calibration_report,
    write_synthetic_dataset,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.neo4j import Neo4jConceptGraph
from skillforge_kb.platform.runtime import (
    build_default_platform_service,
    build_default_profile_agent_adapter,
)
from skillforge_kb.resources.controlled_evaluation import (
    EvaluationProfile,
    evaluate_profiles,
)
from skillforge_kb.resources.controlled_generation import (
    ControlledResourceGenerationService,
    LLMClaimSupportVerifier,
    OpenAICompatibleLLMAdapter,
    ResourceAuditor,
    ResourceGenerationBrief,
    check_model_capabilities,
)
from skillforge_kb.resources.controlled_input import (
    attach_frozen_evidence,
    build_brief_from_handoffs,
)
from skillforge_kb.resources.demo_evidence import EvidenceBundleManifest, freeze_cnn_demo_bundle
from skillforge_kb.resources.demo_export import export_candidate_demo
from skillforge_kb.resources.notebook_runner import run_fixed_cnn_notebook

if TYPE_CHECKING:
    from skillforge_kb.ontology.catalog import OntologyCatalog

app = typer.Typer(no_args_is_help=True)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COURSE_FILE = PROJECT_ROOT / "resources" / "ontology" / "ai_course_v1.yaml"
DEFAULT_RELATIONS_FILE = PROJECT_ROOT / "resources" / "ontology" / "ai_relations_v1.yaml"
DEFAULT_ATTRIBUTES_FILE = PROJECT_ROOT / "resources" / "ontology" / "concept_attributes_v1.yaml"
DEFAULT_KNOWLEDGE_FILE = PROJECT_ROOT / "data" / "index_chunks.jsonl"


@app.callback()
def main() -> None:
    """Operate the SkillForge knowledge base."""


@app.command("platform-serve")
def platform_serve(
    project_root: Annotated[
        Path | None,
        typer.Option(exists=True, file_okay=False),
    ] = None,
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
) -> None:
    try:
        root = project_root or Path.cwd()
        service = build_default_platform_service(root)
        profile_adapter = build_default_profile_agent_adapter(root)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        raise typer.BadParameter(f"platform configuration failed: {exc}") from exc
    uvicorn.run(create_app(service, profile_adapter=profile_adapter), host=host, port=port)


@app.command("fusion-dry-run")
def fusion_dry_run(
    knowledge_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    legacy_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    pilot_jsonl: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    legacy_jsonl: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    workspace_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output_dir: Annotated[Path, typer.Option()],
) -> None:
    from skillforge_kb.fusion.runner import run_dry_run

    summary = run_dry_run(
        knowledge_root=knowledge_root,
        legacy_root=legacy_root,
        pilot_jsonl=pilot_jsonl,
        legacy_jsonl=legacy_jsonl,
        workspace_root=workspace_root,
        output_dir=output_dir,
    )
    typer.echo(f"Processed {summary.input_rows} rows into {output_dir.resolve()}")


def _load_validated_catalog(course_file: Path, relations_file: Path) -> "OntologyCatalog":
    import yaml
    from pydantic import ValidationError

    from skillforge_kb.ontology.catalog import OntologyCatalog
    from skillforge_kb.ontology.validation import validate_catalog

    try:
        catalog = OntologyCatalog.load(course_file, relations_file)
        validate_catalog(catalog)
        return catalog
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        raise typer.BadParameter(f"invalid course graph: {exc}") from exc


def _output_path_outside_inputs(output_path: Path, *input_paths: Path) -> Path:
    resolved_output = output_path.resolve()
    if any(resolved_output == input_path.resolve() for input_path in input_paths):
        raise typer.BadParameter("output must not overwrite a graph input")
    return resolved_output


def _write_json_atomically(path: Path, payload: str) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=resolved.parent,
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, resolved)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


@app.command("agent-run")
def agent_run(
    event_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    thread_id: Annotated[str, typer.Option()],
    state_db: Annotated[Path | None, typer.Option()] = None,
    output_file: Annotated[Path | None, typer.Option()] = None,
    course_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
    attributes_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_ATTRIBUTES_FILE,
    knowledge_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_KNOWLEDGE_FILE,
) -> None:
    paths = StandaloneAgentPaths(
        course_file=course_file,
        relations_file=relations_file,
        attributes_file=attributes_file,
        knowledge_file=knowledge_file,
    )
    input_paths = (
        event_file,
        paths.course_file,
        paths.relations_file,
        paths.attributes_file,
        paths.knowledge_file,
    )
    try:
        event = load_planning_event(event_file)
        validate_standalone_agent_paths(paths)
        if state_db is not None:
            state_db = _output_path_outside_inputs(state_db, *input_paths)
        if output_file is not None:
            output_file = _output_path_outside_inputs(output_file, *input_paths)
            if state_db is not None and output_file == state_db:
                raise typer.BadParameter("output_file must not overwrite state_db")
        if state_db is None:
            result = run_standalone_event(paths, event, thread_id)
        else:
            state_db.parent.mkdir(parents=True, exist_ok=True)
            with SqliteSaver.from_conn_string(str(state_db)) as checkpointer:
                result = run_standalone_event(
                    paths,
                    event,
                    thread_id,
                    checkpointer=checkpointer,
                )
    except typer.BadParameter:
        raise
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise typer.BadParameter(f"agent-run configuration failed: {exc}") from exc

    payload = json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"
    typer.echo(payload, nl=False)
    if output_file is not None:
        try:
            _write_json_atomically(output_file, payload)
        except OSError as exc:
            raise typer.BadParameter(f"could not write output file: {exc}") from exc
    if result.status.value == "failed":
        raise typer.Exit(code=3)


@app.command("graph-validate")
def graph_validate(
    course_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
    output: Annotated[Path | None, typer.Option()] = None,
) -> None:
    from skillforge_kb.ontology.validation import validate_catalog

    catalog = _load_validated_catalog(course_file, relations_file)
    report = validate_catalog(catalog)
    if output is not None:
        output_path = _output_path_outside_inputs(output, course_file, relations_file)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(
                    report.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise typer.BadParameter(f"could not write validation report: {exc}") from exc
    typer.echo(
        f"Validated {len(catalog.chapters())} chapters, "
        f"{len(catalog.course_document.sections)} sections, "
        f"{len(catalog.concepts())} concepts"
    )


@app.command("graph-coverage")
def graph_coverage(
    pilot_jsonl: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_file: Annotated[Path, typer.Option()],
    course_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
) -> None:
    from skillforge_kb.ontology.coverage import analyze_candidate_coverage, write_coverage_report

    catalog = _load_validated_catalog(course_file, relations_file)
    input_path = pilot_jsonl.resolve()
    output_path = _output_path_outside_inputs(
        output_file,
        course_file,
        relations_file,
        pilot_jsonl,
    )
    input_directory = input_path.parent
    if output_path.is_relative_to(input_directory):
        raise typer.BadParameter("output_file must be outside the pilot JSONL directory")
    try:
        report = analyze_candidate_coverage(catalog, pilot_jsonl)
        write_coverage_report(report, output_path)
    except OSError as exc:
        raise typer.BadParameter(f"could not write coverage report: {exc}") from exc
    typer.echo(f"Wrote coverage report to {output_file.resolve()}")


@app.command("graph-publish")
def graph_publish(
    course_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
) -> None:
    from neo4j.exceptions import DriverError, Neo4jError

    catalog = _load_validated_catalog(course_file, relations_file)
    try:
        settings = Settings()
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            Neo4jConceptGraph(driver).publish(catalog)
        finally:
            driver.close()
    except (DriverError, Neo4jError, OSError, ValidationError) as exc:
        raise typer.BadParameter(f"Neo4j publish failed: {exc}") from exc
    typer.echo(f"Published graph version {catalog.course_document.version}")


@app.command("planning-generate-synthetic")
def planning_generate_synthetic(
    output_file: Annotated[Path, typer.Option()],
    case_count: Annotated[int, typer.Option(min=8)] = DEFAULT_SYNTHETIC_CASE_COUNT,
    seed: Annotated[int, typer.Option()] = DEFAULT_SYNTHETIC_SEED,
    course_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
) -> None:
    catalog = _load_validated_catalog(course_file, relations_file)
    output_path = _output_path_outside_inputs(
        output_file,
        course_file,
        relations_file,
    )
    try:
        dataset = generate_synthetic_dataset(
            catalog,
            case_count=case_count,
            seed=seed,
        )
        write_synthetic_dataset(dataset, output_path)
    except (OSError, ValueError, ValidationError) as exc:
        raise typer.BadParameter(f"could not generate synthetic dataset: {exc}") from exc
    typer.echo(
        f"Wrote {len(dataset.cases)} synthetic planning cases to {output_path}"
    )


@app.command("planning-evaluate")
def planning_evaluate(
    dataset_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_file: Annotated[Path, typer.Option()],
    course_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
) -> None:
    catalog = _load_validated_catalog(course_file, relations_file)
    output_path = _output_path_outside_inputs(
        output_file,
        course_file,
        relations_file,
        dataset_file,
    )
    try:
        dataset = load_synthetic_dataset(dataset_file)
        report = evaluate_course_paths(catalog, dataset)
        write_path_evaluation_report(report, output_path)
    except (OSError, ValueError, ValidationError) as exc:
        raise typer.BadParameter(f"invalid synthetic dataset: {exc}") from exc
    typer.echo(
        f"Evaluated {len(report.case_results)} synthetic planning cases into {output_path}"
    )


@app.command("planning-calibrate-policy")
def planning_calibrate_policy(
    dataset_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_file: Annotated[Path, typer.Option()],
    course_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
) -> None:
    catalog = _load_validated_catalog(course_file, relations_file)
    output_path = _output_path_outside_inputs(
        output_file,
        course_file,
        relations_file,
        dataset_file,
    )
    try:
        dataset = load_synthetic_dataset(dataset_file)
        report = search_planner_policies(catalog, dataset)
        write_planner_policy_calibration_report(report, output_path)
    except (OSError, ValueError, ValidationError) as exc:
        raise typer.BadParameter(f"planner policy calibration failed: {exc}") from exc
    typer.echo(
        f"Evaluated {len(report.ranked_candidates)} planner policy candidates "
        f"over {report.baseline.metrics.case_count} synthetic cases into {output_path}"
    )
@app.command("resource-generate")
def resource_generate(
    brief_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_file: Annotated[Path, typer.Option()],
    evidence_bundle_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    demo_output_root: Annotated[Path, typer.Option()] = Path("reports/generated"),
) -> None:
    """Generate an auditable candidate package from an immutable generation brief."""
    settings = Settings()
    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        raise typer.BadParameter(
            "set SKILLFORGE_LLM_BASE_URL, SKILLFORGE_LLM_API_KEY and SKILLFORGE_LLM_MODEL"
        )
    try:
        brief = ResourceGenerationBrief.model_validate_json(brief_file.read_text(encoding="utf-8"))
        bundle = EvidenceBundleManifest.model_validate_json(
            evidence_bundle_file.read_text(encoding="utf-8")
        )
        brief = attach_frozen_evidence(brief, bundle)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"invalid generation input: {exc}") from exc
    notebook = run_fixed_cnn_notebook(timeout_seconds=settings.notebook_timeout_seconds)
    adapter = OpenAICompatibleLLMAdapter(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model_name=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    verifier_adapter = OpenAICompatibleLLMAdapter(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model_name=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    package = ControlledResourceGenerationService(
        adapter,
        auditor=ResourceAuditor(LLMClaimSupportVerifier(verifier_adapter)),
    ).generate(
        brief, notebook_passed=notebook.status == "passed"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    demo_directory = export_candidate_demo(
        package=package,
        brief=brief,
        notebook_report=notebook,
        evidence_bundle=bundle,
        output_root=demo_output_root,
    )
    typer.echo(
        f"generation={package.generation_status.value} "
        f"audit={package.audit_status.value} "
        f"publication={package.publication_status.value}"
    )
    typer.echo(f"demo={demo_directory.resolve()}")


@app.command("resource-model-check")
def resource_model_check(
    output_file: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Check a configured compatible API without displaying its secret."""
    settings = Settings()
    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        raise typer.BadParameter(
            "set SKILLFORGE_LLM_BASE_URL, SKILLFORGE_LLM_API_KEY and SKILLFORGE_LLM_MODEL"
        )
    report = check_model_capabilities(
        OpenAICompatibleLLMAdapter(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model_name=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    )
    if output_file is not None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(report.model_dump_json(indent=2))


@app.command("resource-freeze-cnn-evidence")
def resource_freeze_cnn_evidence(
    output_file: Annotated[Path, typer.Option()],
    reviewer: Annotated[str | None, typer.Option()] = None,
    license_confirmed: Annotated[bool, typer.Option()] = False,
) -> None:
    """Freeze the selected official CNN documentation spans for human review."""
    try:
        bundle = freeze_cnn_demo_bundle(
            reviewer=reviewer,
            license_confirmed=license_confirmed,
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(f"could not freeze CNN evidence: {exc}") from exc
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Wrote frozen CNN evidence {bundle.bundle_id} to {output_file.resolve()}")


@app.command("resource-build-brief")
def resource_build_brief(
    profile_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    handoff_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    retrieval_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_file: Annotated[Path, typer.Option()],
    evidence_bundle_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
) -> None:
    """Convert three upstream handoffs into a signed immutable generation brief."""
    try:
        profile = json.loads(profile_file.read_text(encoding="utf-8"))
        handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
        retrieval = json.loads(retrieval_file.read_text(encoding="utf-8"))
        brief = build_brief_from_handoffs(profile=profile, handoff=handoff, retrieval=retrieval)
        if evidence_bundle_file is not None:
            brief = attach_frozen_evidence(
                brief,
                EvidenceBundleManifest.model_validate_json(
                    evidence_bundle_file.read_text(encoding="utf-8")
                ),
            )
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"invalid upstream handoff: {exc}") from exc
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(brief.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Wrote immutable policy {brief.policy.policy_id} to {output_file.resolve()}")


@app.command("resource-evaluate")
def resource_evaluate(
    evaluation_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    notebook_validation_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_file: Annotated[Path, typer.Option()],
) -> None:
    """Run a three-profile controlled-variable evaluation with one shared policy."""
    settings = Settings()
    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        raise typer.BadParameter(
            "set SKILLFORGE_LLM_BASE_URL, SKILLFORGE_LLM_API_KEY and SKILLFORGE_LLM_MODEL"
        )
    try:
        payload = json.loads(evaluation_file.read_text(encoding="utf-8"))
        base_policy = ResourceGenerationBrief.model_validate(payload["baseline_brief"]).policy
        profiles = tuple(EvaluationProfile(**item) for item in payload["profiles"])
        notebook = json.loads(notebook_validation_file.read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"invalid evaluation input: {exc}") from exc
    adapter = OpenAICompatibleLLMAdapter(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model_name=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    report = evaluate_profiles(
        base_policy=base_policy,
        profiles=profiles,
        service_factory=lambda: ControlledResourceGenerationService(
            adapter,
            auditor=ResourceAuditor(LLMClaimSupportVerifier(adapter)),
        ),
        notebook_passed=notebook.get("status") == "passed",
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Wrote three-profile evaluation to {output_file.resolve()}")


if __name__ == "__main__":
    app()
