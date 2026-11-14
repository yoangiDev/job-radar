import re
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class Company(BaseModel):
    """One row of the seed list."""

    name: str
    domain: str = ""
    ats: str  # greenhouse | lever | lever-eu | ashby
    slug: str
    sector: str = ""


class Job(BaseModel):
    """A posting normalized from any source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source: str
    external_id: str
    company: str
    title: str
    location: str = ""
    remote: bool | None = None  # None: the ATS does not say
    url: str
    description: str = ""
    published_at: datetime | None = None

    @field_validator("published_at")
    @classmethod
    def _naive_utc(cls, value: datetime | None) -> datetime | None:
        # Every datetime in the system is naive UTC: SQLite drops tzinfo anyway.
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    @property
    def fingerprint(self) -> str:
        """Same company + title + location is the same job, whatever its id or source."""
        return "|".join(_squash(part) for part in (self.company, self.title, self.location))


def _squash(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.lower()).strip()
