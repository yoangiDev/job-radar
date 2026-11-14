from types import SimpleNamespace

import pytest

from job_radar.rules import check

CASES = [
    # title, location, remote, passes, note
    ("Junior Backend Engineer", "Remote, Spain", None, True, ""),
    ("AI Platform Engineer", "Remote, Global", None, True, ""),
    ("Flutter Developer", "Remote (European Union)", True, True, ""),
    ("Python Engineer", "Remote (US | EU)", True, True, ""),
    ("Support Engineer, Python", "Remote, EMEA", None, True, ""),
    ("Kotlin Developer", "Madrid (ES)", True, True, ""),
    ("Android Intern", "Murcia, Spain", False, True, ""),  # local, on-site is fine
    ("Python Developer", "Remote", True, True, "remote, region not stated"),
    ("Python Developer", "", True, True, "remote, region not stated"),
    ("Senior Backend Engineer, AI Engineering: Chat", "Remote, EMEA", None, False, "title excludes 'senior'"),
    ("Team Lead, Python", "Remote, Spain", None, False, "title excludes 'lead'"),
    ("Sr. Backend Engineer", "Remote, Spain", None, False, "title excludes 'sr'"),
    ("Support Engineer (EMEA)", "Remote, EMEA", None, False, "title has no target keyword"),
    ("Internal Tools Engineer", "Remote, EMEA", None, False, "title has no target keyword"),
    ("Maintainer Relations", "Remote, EMEA", None, False, "title has no target keyword"),
    ("Backend Engineer - Data Platform", "Stockholm; London (SE)", False, False, "not remote"),
    ("Kotlin Developer", "Madrid, Spain", False, False, "not remote"),
    ("Kotlin Developer", "Madrid, Spain", None, False, "not remote"),
    ("Python Developer", "New York, NY (US)", True, False, "remote outside Spain/EU"),
    ("Backend Engineer (Python)", "Remote, Canada; Remote, Poland", None, False, "remote outside Spain/EU"),
]


@pytest.mark.parametrize("title, location, remote, passes, note", CASES)
def test_check(title, location, remote, passes, note):
    job = SimpleNamespace(title=title, location=location, remote=remote)
    assert check(job) == (passes, note)
