from pathlib import Path

import typer

from . import pipeline
from .db import get_engine

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Radar of fresh job postings from public ATS boards."""


@app.command()
def run(
    companies: Path = typer.Option(
        Path("data/companies.csv"), exists=True, dir_okay=False, help="Seed list CSV."
    ),
) -> None:
    """Fetch every company board and store the postings not seen before."""
    runs, failures = pipeline.run(companies, get_engine())
    for row in runs:
        typer.echo(f"{row.source}: {row.fetched} fetched, {row.new} new, {row.errors} errors")
        if row.fetched == 0:
            typer.echo(f"WARNING {row.source} returned no postings: the source may be broken", err=True)
    for failure in failures:
        typer.echo(f"ERROR {failure}", err=True)
