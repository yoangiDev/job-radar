"""Lever Postings API: https://github.com/lever/postings-api"""

import httpx

from ..models import Company, Job
from . import get_json, html_to_text

HOSTS = {"lever": "https://api.lever.co", "lever-eu": "https://api.eu.lever.co"}
PAGE_SIZE = 100
REMOTE = {"remote": True, "hybrid": False, "onsite": False, "on-site": False}


async def fetch(client: httpx.AsyncClient, company: Company) -> list[dict]:
    url = f"{HOSTS[company.ats]}/v0/postings/{company.slug}"
    postings: list[dict] = []
    while True:
        page = await get_json(client, url, mode="json", skip=len(postings), limit=PAGE_SIZE)
        postings += page
        if len(page) < PAGE_SIZE:
            return postings


def normalize(raw: dict, company: Company) -> Job:
    categories = raw.get("categories") or {}
    places = categories.get("allLocations") or [categories.get("location") or ""]
    location = "; ".join(places)
    if country := raw.get("country"):
        location = f"{location} ({country})"
    sections = [raw.get("descriptionPlain") or ""]
    sections += [f"{item['text']}: {html_to_text(item['content'])}" for item in raw.get("lists") or []]
    sections.append(raw.get("additionalPlain") or "")
    return Job(
        source="lever",
        external_id=raw["id"],
        company=company.name,
        title=raw["text"],
        location=location,
        remote=REMOTE.get(raw.get("workplaceType")),
        url=raw["hostedUrl"],
        description="\n\n".join(s.strip() for s in sections if s.strip()),
        published_at=raw.get("createdAt"),  # epoch milliseconds, parsed by Pydantic
    )
