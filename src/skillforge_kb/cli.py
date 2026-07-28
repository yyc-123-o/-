from pathlib import Path
from typing import Annotated

import typer
from neo4j import GraphDatabase

from skillforge_kb.config import Settings
from skillforge_kb.fusion.runner import run_dry_run
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.coverage import analyze_candidate_coverage, write_coverage_report
from skillforge_kb.ontology.neo4j import Neo4jConceptGraph
from skillforge_kb.ontology.validation import validate_catalog

app = typer.Typer(no_args_is_help=True)


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
    catalog = OntologyCatalog.load(course_file, relations_file)
    validate_catalog(catalog)
    return catalog


@app.command("graph-validate")
def graph_validate(
    course_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    relations_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    catalog = _load_validated_catalog(course_file, relations_file)
    typer.echo(
        f"Validated {len(catalog.chapters())} chapters, "
        f"{len(catalog.course_document.sections)} sections, "
        f"{len(catalog.concepts())} concepts"
    )


@app.command("graph-coverage")
def graph_coverage(
    course_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    relations_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    pilot_jsonl: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output_file: Annotated[Path, typer.Option()],
) -> None:
    catalog = _load_validated_catalog(course_file, relations_file)
    output_path = output_file.resolve()
    input_path = pilot_jsonl.resolve()
    if output_path == input_path or input_path in output_path.parents:
        raise typer.BadParameter("output_file must be outside the pilot JSONL directory")
    report = analyze_candidate_coverage(catalog, pilot_jsonl)
    write_coverage_report(report, output_file)
    typer.echo(f"Wrote coverage report to {output_file.resolve()}")


@app.command("graph-publish")
def graph_publish(
    course_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    relations_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    catalog = _load_validated_catalog(course_file, relations_file)
    settings = Settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        Neo4jConceptGraph(driver).publish(catalog)
    finally:
        driver.close()
    typer.echo(f"Published graph version {catalog.course_document.version}")


if __name__ == "__main__":
    app()
