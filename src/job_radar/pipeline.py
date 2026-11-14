import asyncio
import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from .db import CompanyRow, JobRow, RunRow
from .models import Company, Job
from .sources import ashby, greenhouse, lever

SOURCES = {"greenhouse": greenhouse, "lever": lever, "lever-eu": lever, "ashby": ashby}
# ponytail: one global cap; add a per-host delay if an ATS starts answering 429.
CONCURRENCY = 5
# A fingerprint match older than this is a reopened role, not a duplicate.
DEDUP_WINDOW = timedelta(days=30)


def load_companies(path: Path) -> list[Company]:
    with open(path, newline="", encoding="utf-8-sig") as file:
        return [Company(**{k: v for k, v in row.items() if v}) for row in csv.DictReader(file)]


async def fetch_all(
    companies: list[Company], transport: httpx.AsyncBaseTransport | None = None
) -> list[list[Job] | BaseException]:
    """Jobs per company, or the exception that broke that company. One failure never stops the rest."""
    limit = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(transport=transport, timeout=30) as client:

        async def one(company: Company) -> list[Job]:
            async with limit:
                source = SOURCES[company.ats]
                return [source.normalize(raw, company) for raw in await source.fetch(client, company)]

        return await asyncio.gather(*(one(c) for c in companies), return_exceptions=True)


def store(session: Session, company: Company, jobs: list[Job], now: datetime) -> int:
    """Insert unseen postings, refresh last_seen_at on known ones. Returns how many are new and not duplicates."""
    company_row = session.scalar(
        select(CompanyRow).where(CompanyRow.ats == company.ats, CompanyRow.slug == company.slug)
    ) or CompanyRow(ats=company.ats, slug=company.slug)
    company_row.name, company_row.domain, company_row.sector = company.name, company.domain, company.sector
    session.add(company_row)

    ids = [job.external_id for job in jobs]
    known = {
        (row.source, row.external_id): row
        for row in session.scalars(select(JobRow).where(JobRow.external_id.in_(ids)))
    }
    new = 0
    for job in jobs:
        key = (job.source, job.external_id)
        if key in known:
            known[key].last_seen_at = now
            continue
        original = session.scalar(
            select(JobRow.id)
            .where(JobRow.fingerprint == job.fingerprint, JobRow.last_seen_at >= now - DEDUP_WINDOW)
            .order_by(JobRow.id)
            .limit(1)
        )
        known[key] = JobRow(
            company=company_row,
            **job.model_dump(exclude={"company"}),
            fingerprint=job.fingerprint,
            first_seen_at=now,
            last_seen_at=now,
            duplicate_of_id=original,
        )
        session.add(known[key])
        new += original is None
    return new


def run(
    companies_path: Path, engine: Engine, transport: httpx.AsyncBaseTransport | None = None
) -> tuple[list[RunRow], list[str]]:
    """One full pass over the seed list. Returns one run row per source and the per-company failures."""
    companies = load_companies(companies_path)
    now = datetime.now(UTC).replace(tzinfo=None)
    results = asyncio.run(fetch_all(companies, transport))

    runs: dict[str, RunRow] = {}
    failures: list[str] = []
    with Session(engine, expire_on_commit=False) as session:
        for company, result in zip(companies, results):
            run_row = runs.setdefault(
                company.ats, RunRow(source=company.ats, started_at=now, fetched=0, new=0, errors=0)
            )
            if isinstance(result, BaseException):
                run_row.errors += 1
                failures.append(f"{company.name} ({company.ats}/{company.slug}): {type(result).__name__}: {result}")
            else:
                run_row.fetched += len(result)
                run_row.new += store(session, company, result, now)
        session.add_all(runs.values())
        session.commit()
    return list(runs.values()), failures
