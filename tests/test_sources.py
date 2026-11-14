"""Sources against recorded ATS responses (trimmed to a few postings, long text truncated).

No test touches the network: every request is answered by httpx.MockTransport.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from job_radar import sources
from job_radar.models import Company
from job_radar.sources import ashby, greenhouse, lever

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def fetch(source, company: Company, handler) -> list[dict]:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await source.fetch(client, company)

    return asyncio.run(go())


def test_greenhouse():
    company = Company(name="GitLab", ats="greenhouse", slug="gitlab")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=fixture("greenhouse"))

    jobs = [greenhouse.normalize(raw, company) for raw in fetch(greenhouse, company, handler)]

    assert seen == ["https://boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=true"]
    assert len(jobs) == 7
    job = jobs[0]
    assert job.source == "greenhouse"
    assert job.external_id == "8704363002"
    assert job.company == "GitLab"
    assert job.title == "Backend Engineer (Python),AI Engineering: Agent Foundations"
    assert job.location == "Remote, Canada; Remote, Poland; Remote, United Kingdom"
    assert job.remote is None
    assert job.url.startswith("https://")
    assert job.published_at == datetime(2026, 8, 19, 13, 38, 27)  # first_published, as naive UTC
    assert job.description and "<" not in job.description and "&lt;" not in job.description
    assert jobs[6].title == "Senior Backend Engineer, AI Engineering: Chat"  # whitespace stripped


def test_lever_paginates(monkeypatch):
    monkeypatch.setattr(lever, "PAGE_SIZE", 2)
    company = Company(name="Spotify", ats="lever", slug="spotify")
    postings, skips = fixture("lever"), []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.lever.co"
        assert request.url.path == "/v0/postings/spotify"
        skip, limit = int(request.url.params["skip"]), int(request.url.params["limit"])
        skips.append(skip)
        return httpx.Response(200, json=postings[skip : skip + limit])

    jobs = [lever.normalize(raw, company) for raw in fetch(lever, company, handler)]

    assert skips == [0, 2, 4]
    assert len(jobs) == 5
    job = jobs[3]
    assert job.source == "lever"
    assert job.external_id == "9899871a-4307-4367-9f74-039569d7a650"
    assert job.title == "Full Stack Engineer - Music"
    assert job.location == "New York, NY (US)"
    assert job.remote is True
    assert job.url == "https://jobs.lever.co/spotify/9899871a-4307-4367-9f74-039569d7a650"
    assert job.published_at == datetime(2026, 10, 2, 17, 43, 5, 85000)  # createdAt 1790962985085 ms
    assert "Who You Are" in job.description and "<" not in job.description
    assert jobs[1].location == "Stockholm; London (SE)"
    assert jobs[1].remote is False  # hybrid
    assert jobs[1].fingerprint == jobs[2].fingerprint  # same job posted twice


def test_lever_eu_host():
    company = Company(name="Acme", ats="lever-eu", slug="acme")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.eu.lever.co"
        return httpx.Response(200, json=[])

    assert fetch(lever, company, handler) == []


def test_ashby():
    company = Company(name="Supabase", ats="ashby", slug="supabase")
    board = fixture("ashby")
    board["jobs"][3]["isListed"] = False  # unlisted postings must be dropped

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.ashbyhq.com/posting-api/job-board/supabase"
        return httpx.Response(200, json=board)

    jobs = [ashby.normalize(raw, company) for raw in fetch(ashby, company, handler)]

    assert len(jobs) == 5
    assert "Engineering Manager - Pipelines" not in [job.title for job in jobs]
    job = jobs[0]
    assert job.source == "ashby"
    assert job.external_id == "3b5d54ca-741b-45ac-bd3f-31605a0d3541"
    assert job.title == "AI Platform Engineer"
    assert job.location == "Remote, Global"
    assert job.remote is None  # isRemote and workplaceType are both null in this posting
    assert job.url.startswith("https://jobs.ashbyhq.com/")
    assert job.published_at == datetime(2026, 7, 31, 18, 56, 39, 246000)
    assert job.description
    assert jobs[2].title == "Developer Relations Engineer"
    assert jobs[2].location == "Remote, San Francisco, CA, US (United States)"
    assert jobs[2].remote is True
    assert jobs[4].location == "Remote, Bay Area, CA, US; Remote, San Francisco, CA, US; Remote, AMER"


def test_get_json_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(sources, "BACKOFF", 0)
    statuses = iter([503, 429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), json={"ok": True})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await sources.get_json(client, "https://example.test/x")

    assert asyncio.run(go()) == {"ok": True}


def test_get_json_gives_up(monkeypatch):
    monkeypatch.setattr(sources, "BACKOFF", 0)

    async def go():
        transport = httpx.MockTransport(lambda request: httpx.Response(404))
        async with httpx.AsyncClient(transport=transport) as client:
            return await sources.get_json(client, "https://example.test/x")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(go())
