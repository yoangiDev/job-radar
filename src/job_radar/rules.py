"""Stage 1 filter: free rules on title and location. Tune the word lists here."""

import re

TITLE_INCLUDE = (
    "backend", "python", "fastapi", "flutter", "kotlin", "android", "mobile", "ai", "automation",
    "junior", "graduate", "trainee", "intern", "internship", "associate",
)  # fmt: skip
TITLE_EXCLUDE = ("senior", "sr", "staff", "principal", "lead", "manager", "head", "director")
# On-site or hybrid is only acceptable here.
LOCAL = ("murcia", "alicante")
# A remote job must name one of these, or name no region at all.
REMOTE_REGIONS = ("spain", "españa", "eu", "emea", "europe", "european", "worldwide", "global", "anywhere")


def _any_word(words: tuple[str, ...]) -> re.Pattern[str]:
    # Whole words only: "ai" must not match "maintainer", nor "intern" match "internal".
    return re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b", re.IGNORECASE)


_INCLUDE = _any_word(TITLE_INCLUDE)
_EXCLUDE = _any_word(TITLE_EXCLUDE)
_LOCAL = _any_word(LOCAL)
_REGION = re.compile(r"\(ES\)|" + _any_word(REMOTE_REGIONS).pattern, re.IGNORECASE)


def check(job) -> tuple[bool, str]:
    """Return (passes, note) for anything with title, location and remote.

    The note explains a rejection, or flags a pass that needs a human look.
    """
    if match := _EXCLUDE.search(job.title):
        return False, f"title excludes '{match[0].lower()}'"
    if not _INCLUDE.search(job.title):
        return False, "title has no target keyword"
    if _LOCAL.search(job.location):
        return True, ""
    if not (job.remote or "remote" in job.location.lower()):
        return False, "not remote"
    if _REGION.search(job.location):
        return True, ""
    if not re.sub(r"remote|[\W_]", "", job.location, flags=re.IGNORECASE):
        return True, "remote, region not stated"
    return False, "remote outside Spain/EU"
