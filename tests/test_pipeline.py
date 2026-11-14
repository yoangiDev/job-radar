"""End to end: seed CSV -> recorded ATS responses -> SQLite. No network."""

import copy

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from job_radar import pipeline
from job_radar.cli import app
from job_radar.db import CompanyRow, JobRow, RunRow, get_engine
from test_sources import fixture

SEED = """name,domain,ats,slug,sector
GitLab,gitlab.com,greenhouse,gitlab,devtools
Spotify,spotify.com,lever,spotify,
Supabase,supabase.com,ashby,supabase,devtools
Broken,,greenhouse,broken,
"""


@pytest.fixture
def boards():
    """Mutable copies of the recorded boards, so a test can publish a new posting between runs."""
    return {name: copy.deepcopy(fixture(name)) for name in ("greenhouse", "lever", "ashby")}


@pytest.fixture
def transport(boards):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/broken/" in request.url.path:
            return httpx.Response(404)
        if request.url.host == "boards-api.greenhouse.io":
            return httpx.Response(200, json=boards["greenhouse"])
        if request.url.host == "api.lever.co":
            skip, limit = int(request.url.params["skip"]), int(request.url.params["limit"])
            return httpx.Response(200, json=boards["lever"][skip : skip + limit])
        if request.url.host == "api.ashbyhq.com":
            return httpx.Response(200, json=boards["ashby"])
        raise AssertionError(f"unexpected request: {request.url}")

    return httpx.MockTransport(handler)


@pytest.fixture
def seed(tmp_path):
    path = tmp_path / "companies.csv"
    path.write_text(SEED, encoding="utf-8")
    return path


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'radar.db').as_posix()}"


def summary(runs):
    return {row.source: (row.fetched, row.new, row.errors) for row in runs}


def test_first_run_stores_everything_and_flags_duplicates(seed, db_url, transport):
    engine = get_engine(db_url)

    runs, failures = pipeline.run(seed, engine, transport)

    # Lever serves the same Spotify job under two ids: 5 fetched, 4 new.
    assert summary(runs) == {"greenhouse": (7, 7, 1), "lever": (5, 4, 0), "ashby": (6, 6, 0)}
    assert len(failures) == 1 and failures[0].startswith("Broken (greenhouse/broken): HTTPStatusError")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(JobRow)) == 18
        assert session.scalar(select(func.count()).select_from(CompanyRow)) == 3
        (duplicate,) = session.scalars(select(JobRow).where(JobRow.duplicate_of_id.is_not(None)))
        original = session.get(JobRow, duplicate.duplicate_of_id)
        assert duplicate.title == original.title == "Backend Engineer - Data Platform"
        assert duplicate.external_id != original.external_id
        assert original.company.name == "Spotify"


def test_second_run_only_reports_what_is_new(seed, db_url, transport, boards):
    engine = get_engine(db_url)
    pipeline.run(seed, engine, transport)

    fresh = copy.deepcopy(boards["greenhouse"]["jobs"][0])
    fresh.update(id=1, title="Junior Backend Engineer", absolute_url="https://example.test/1")
    boards["greenhouse"]["jobs"].append(fresh)
    runs, _ = pipeline.run(seed, engine, transport)

    assert summary(runs) == {"greenhouse": (8, 1, 1), "lever": (5, 0, 0), "ashby": (6, 0, 0)}
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(JobRow)) == 19
        assert session.scalar(select(func.count()).select_from(RunRow)) == 6
        old = session.scalar(select(JobRow).where(JobRow.external_id == "8704363002"))
        new = session.scalar(select(JobRow).where(JobRow.external_id == "1"))
        assert old.last_seen_at == new.first_seen_at > old.first_seen_at


def test_cli_run(seed, db_url, transport, monkeypatch):
    real_fetch_all = pipeline.fetch_all
    monkeypatch.setattr(pipeline, "fetch_all", lambda companies, _=None: real_fetch_all(companies, transport))
    monkeypatch.setenv("RADAR_DB_URL", db_url)

    result = CliRunner().invoke(app, ["run", "--companies", str(seed)])

    assert result.exit_code == 0, result.output
    assert "lever: 5 fetched, 4 new, 0 errors" in result.output
    assert "ERROR Broken (greenhouse/broken)" in result.output


def test_cli_today(seed, db_url, transport, boards, monkeypatch, tmp_path):
    unclear = copy.deepcopy(boards["greenhouse"]["jobs"][0])
    unclear.update(id=1, title="Junior Backend Engineer", absolute_url="https://example.test/1")
    unclear["location"]["name"] = "Remote"
    boards["greenhouse"]["jobs"].append(unclear)
    pipeline.run(seed, get_engine(db_url), transport)
    monkeypatch.setenv("RADAR_DB_URL", db_url)
    runner = CliRunner()

    result = runner.invoke(app, ["today"])

    # 19 stored, 1 duplicate hidden; only two survive the title and location rules.
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "# Radar: 2 matching jobs out of 18 new postings (last 24 h)"
    assert sorted(lines[2:]) == [
        "- [AI Platform Engineer](https://jobs.ashbyhq.com/supabase/3b5d54ca-741b-45ac-bd3f-31605a0d3541)"
        " | Supabase | Remote, Global | published 2026-07-31",
        "- [Junior Backend Engineer](https://example.test/1) | GitLab | Remote (?) | published 2026-08-19",
    ]
    assert lines[2].startswith("- [Junior")  # freshest publication first

    assert "0 matching jobs out of 0 new postings" in runner.invoke(app, ["today", "--hours", "0"]).output

    digest = tmp_path / "today.md"
    assert runner.invoke(app, ["today", "--out", str(digest)]).exit_code == 0
    assert digest.read_text(encoding="utf-8") == result.output
