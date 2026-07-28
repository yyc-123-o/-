import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from neo4j import GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError
from pydantic import ValidationError

from skillforge_kb.config import Settings
from skillforge_kb.fusion.runner import run_dry_run
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.coverage import analyze_candidate_coverage, write_coverage_report
from skillforge_kb.ontology.neo4j import Neo4jConceptGraph
from skillforge_kb.ontology.validation import validate_catalog

app = typer.Typer(no_args_is_help=True)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COURSE_FILE = PROJECT_ROOT / "resources" / "ontology" / "ai_course_v1.yaml"
DEFAULT_RELATIONS_FILE = PROJECT_ROOT / "resources" / "ontology" / "ai_relations_v1.yaml"


@app.callback()
def main() -> None:
    """Operate the SkillForge knowledge base."""


@app.command("fusion-dry-run")
def fusion_dry_run(
    knowledge_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    legacy_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    pilot_jsonl: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    legacy_jsonl: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    workspace_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output_dir: Annotated[Path, typer.Option()],
) -> None:
    summary = run_dry_run(
        knowledge_root=knowledge_root,
        legacy_root=legacy_root,
        pilot_jsonl=pilot_jsonl,
        legacy_jsonl=legacy_jsonl,
        workspace_root=workspace_root,
        output_dir=output_dir,
    )
    typer.echo(f"Processed {summary.input_rows} rows into {output_dir.resolve()}")


def _load_validated_catalog(course_file: Path, relations_file: Path) -> OntologyCatalog:
    try:
        catalog = OntologyCatalog.load(course_file, relations_file)
        validate_catalog(catalog)
        return catalog
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        raise typer.BadParameter(f"invalid course graph: {exc}") from exc


@app.command("graph-validate")
def graph_validate(
    course_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
    output: Annotated[Path | None, typer.Option()] = None,
) -> None:
    catalog = _load_validated_catalog(course_file, relations_file)
    report = validate_catalog(catalog)
    if output is not None:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
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
    course_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
) -> None:
    catalog = _load_validated_catalog(course_file, relations_file)
    output_path = output_file.resolve()
    input_path = pilot_jsonl.resolve()
    input_directory = input_path.parent
    if output_path.is_relative_to(input_directory):
        raise typer.BadParameter("output_file must be outside the pilot JSONL directory")
    try:
        report = analyze_candidate_coverage(catalog, pilot_jsonl)
        write_coverage_report(report, output_file)
    except OSError as exc:
        raise typer.BadParameter(f"could not write coverage report: {exc}") from exc
    typer.echo(f"Wrote coverage report to {output_file.resolve()}")


@app.command("graph-publish")
def graph_publish(
    course_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_COURSE_FILE,
    relations_file: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_RELATIONS_FILE,
) -> None:
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


if __name__ == "__main__":
    app()
