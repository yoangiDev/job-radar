"""Greenhouse Job Board API: https://docs.greenhouse.io/job-board.html"""

import httpx

from ..models import Company, Job
from . import get_json, html_to_text

URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


async def fetch(client: httpx.AsyncClient, company: Company) -> list[dict]:
    data = await get_json(client, URL.format(slug=company.slug), content="true")
    return data["jobs"]


def normalize(raw: dict, company: Company) -> Job:
    return Job(
        source="greenhouse",
        external_id=str(raw["id"]),
        company=company.name,
        title=raw["title"],
        location=(raw.get("location") or {}).get("name") or "",
        url=raw["absolute_url"],
        description=html_to_text(raw.get("content") or ""),
        published_at=raw.get("first_published") or raw.get("updated_at"),
    )
