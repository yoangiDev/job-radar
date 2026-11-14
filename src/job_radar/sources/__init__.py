"""One module per ATS, all with the same interface:

    async fetch(client, company) -> list[dict]   raw postings of one company
    normalize(raw, company) -> Job               raw posting to the common model
"""

import asyncio
import html
import re

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 3
BACKOFF = 1.0  # seconds, doubled after each failed attempt


async def get_json(client: httpx.AsyncClient, url: str, **params):
    for attempt in range(ATTEMPTS):
        last = attempt == ATTEMPTS - 1
        try:
            response = await client.get(url, params=params)
        except httpx.TransportError:
            if last:
                raise
        else:
            if last or response.status_code not in RETRY_STATUS:
                response.raise_for_status()
                return response.json()
        await asyncio.sleep(BACKOFF * 2**attempt)


def html_to_text(markup: str) -> str:
    # ponytail: regex tag strip, good enough to feed rules and an LLM;
    # switch to html.parser if block structure ever matters.
    text = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(markup)))
    return re.sub(r"\s+", " ", text).strip()
