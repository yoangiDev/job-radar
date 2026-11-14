import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, ForeignKey, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DEFAULT_URL = "sqlite:///data/radar.db"


class Base(DeclarativeBase):
    pass


class CompanyRow(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("ats", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    domain: Mapped[str]
    ats: Mapped[str]
    slug: Mapped[str]
    sector: Mapped[str]


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    company: Mapped[CompanyRow] = relationship()
    source: Mapped[str]
    external_id: Mapped[str]
    title: Mapped[str]
    location: Mapped[str]
    remote: Mapped[bool | None]
    url: Mapped[str]
    description: Mapped[str]
    published_at: Mapped[datetime | None]  # what the ATS claims
    first_seen_at: Mapped[datetime]  # when the radar first saw it: the real novelty signal
    last_seen_at: Mapped[datetime]
    fingerprint: Mapped[str] = mapped_column(index=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    started_at: Mapped[datetime]
    fetched: Mapped[int]
    new: Mapped[int]
    errors: Mapped[int]


def get_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("RADAR_DB_URL", DEFAULT_URL)
    if url == DEFAULT_URL:
        Path("data").mkdir(exist_ok=True)
    engine = create_engine(url)
    # ponytail: no migrations; add Alembic when a schema change has to keep existing data.
    Base.metadata.create_all(engine)
    return engine
