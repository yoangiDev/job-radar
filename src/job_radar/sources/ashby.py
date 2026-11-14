"""Ashby public job posting API: https://developers.ashbyhq.com/docs/public-job-posting-api"""

import httpx

from ..models import Company, Job
from . import get_json

URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


async def fetch(client: httpx.AsyncClient, company: Company) -> list[dict]:
    data = await get_json(client, URL.format(slug=company.slug))
    return [job for job in data["jobs"] if job.get("isListed", True)]


def normalize(raw: dict, company: Company) -> Job:
    places = [raw.get("location")] + [s.get("location") for s in raw.get("secondaryLocations") or []]
    location = "; ".join(dict.fromkeys(p for p in places if p))
    country = ((raw.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
    if country and country not in location:
        location = f"{location} ({country})"
    remote = raw.get("isRemote")
    if remote is None and raw.get("workplaceType"):
        remote = raw["workplaceType"] == "Remote"
    return Job(
        source="ashby",
        external_id=raw["id"],
        company=company.name,
        title=raw["title"],
        location=location,
        remote=remote,
        url=raw["jobUrl"],
        description=raw.get("descriptionPlain") or "",
        # Last publication, not first: a republished job looks fresh. Novelty uses first_seen_at.
        published_at=raw.get("publishedAt"),
    )
