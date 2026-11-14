# job-radar

A personal radar for fresh job postings. It polls the public job boards of a list of
companies (Greenhouse, Lever and Ashby), stores every posting in SQLite, and prints a
daily digest of the new ones that pass a set of title and location rules.

The public ATS endpoints publish a posting the moment the company opens it, so reading
them directly surfaces a job hours before it reaches an aggregator or an email alert.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Create your seed list from the example and edit it:

```bash
mkdir data
```

```bash
cp companies.example.csv data/companies.csv
```

| Column   | Meaning                                                        |
| -------- | -------------------------------------------------------------- |
| `name`   | Company name shown in the digest                               |
| `domain` | Company website (optional)                                     |
| `ats`    | `greenhouse`, `lever`, `lever-eu` (Lever's EU host) or `ashby` |
| `slug`   | Board name: the `x` in `boards.greenhouse.io/x`, `jobs.lever.co/x` or `jobs.ashbyhq.com/x` |
| `sector` | Free label (optional)                                          |

`data/` is git-ignored: your seed list and your database never leave your machine.

## Usage

Run both commands from the repository root.

```bash
uv run radar run
```

Fetches every board, stores the postings not seen before and prints one line per source:

```
greenhouse: 277 fetched, 274 new, 0 errors
lever: 87 fetched, 86 new, 0 errors
ashby: 87 fetched, 87 new, 0 errors
```

A company that fails is reported and does not stop the others. A source that returns
nothing prints a warning, since that usually means it broke.

```bash
uv run radar today
```

Prints a Markdown digest of the postings first seen in the last 24 hours that pass the
rules, freshest first. `--hours 72` widens the window; `--out today.md` writes the digest
to a file as UTF-8.

```
# Radar: 2 matching jobs out of 447 new postings (last 24 h)

- [SDK Engineer - Python](https://jobs.ashbyhq.com/...) | Supabase | Remote, Global | published 2026-10-16
- [Junior Backend Engineer](https://...) | Acme | Remote (?) | published 2026-11-13
```

`(?)` marks a remote job whose region is not stated: it passes, but check it by hand.

On the first run every open posting counts as new, so the first digest is long.

## How it works

- **Novelty.** A posting is new when its id was not in the database. `first_seen_at` is
  what the digest window uses. The date the ATS reports is stored as `published_at` and
  only used for ordering, because some boards reset it when a job is republished.
- **Deduplication.** Company, title and location are normalized into a fingerprint. A
  posting whose fingerprint matches one seen in the last 30 days is stored but flagged as
  a duplicate and left out of the digest.
- **Rules.** The title must contain a target keyword and no excluded one, matched as whole
  words. The location must be remote and open to Spain, the EU, EMEA or worldwide, or be
  on-site in a listed city. The word lists are constants in
  [`src/job_radar/rules.py`](src/job_radar/rules.py); rules run when the digest is built,
  so a change applies to postings already stored.
- **Runs.** Every pass writes one row per source to the `runs` table with postings
  fetched, new postings and failed companies.

The database is `data/radar.db`. Set `RADAR_DB_URL` to any SQLAlchemy URL to move it.

## Adding a source

A source is one module in [`src/job_radar/sources/`](src/job_radar/sources/) with two functions:

```python
async def fetch(client, company) -> list[dict]: ...   # raw postings of one company
def normalize(raw, company) -> Job: ...               # raw posting to the common model
```

Register it in `SOURCES` in [`src/job_radar/pipeline.py`](src/job_radar/pipeline.py) and
add a recorded response under `tests/fixtures/`.

## Tests

```bash
uv run pytest
```

Tests replay recorded responses from each ATS, trimmed to a few postings. No test touches
the network.
