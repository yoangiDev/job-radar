import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import pipeline, rules
from .db import JobRow, get_engine

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


@app.command()
def today(
    hours: int = typer.Option(24, help="How far back 'new' reaches, by first detection."),
    out: Path | None = typer.Option(None, help="Write the digest to this file as UTF-8 instead of printing it."),
) -> None:
    """Markdown digest of the new postings that pass the rules, freshest first."""
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)
    lines = []
    with Session(get_engine()) as session:
        rows = session.scalars(
            select(JobRow)
            .where(JobRow.first_seen_at >= since, JobRow.duplicate_of_id.is_(None))
            .order_by(JobRow.published_at.desc())
        ).all()
        for row in rows:
            passes, note = rules.check(row)
            if passes:
                location = (row.location or "location not stated") + (" (?)" if note else "")
                published = f"published {row.published_at:%Y-%m-%d}" if row.published_at else "no publish date"
                lines.append(f"- [{row.title}]({row.url}) | {row.company.name} | {location} | {published}")
    header = f"# Radar: {len(lines)} matching jobs out of {len(rows)} new postings (last {hours} h)"
    digest = "\n".join([header, "", *lines]) + "\n"
    if out:
        out.write_text(digest, encoding="utf-8")
        typer.echo(f"Wrote {out}")
    else:
        sys.stdout.reconfigure(errors="replace")  # a title outside the console code page must not crash a pipe
        typer.echo(digest, nl=False)
