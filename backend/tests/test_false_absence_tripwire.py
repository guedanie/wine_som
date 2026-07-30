import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from api.routers.recommend import _false_absence_suspects
from recommendation.availability import (PRESENT_NOT_SHORTLISTED, NOT_IN_CATALOG,
                                         PRESENT_SHORTLISTED)


def test_fires_when_absence_language_contradicts_present_fact():
    facts = [{"label": "Barolo", "state": PRESENT_NOT_SHORTLISTED}]
    hits = _false_absence_suspects("There are no Barolos nearby, sorry.", facts)
    assert hits


def test_silent_when_fact_is_not_in_catalog():
    facts = [{"label": "Muscadet", "state": NOT_IN_CATALOG}]
    assert not _false_absence_suspects("There are no Muscadets nearby.", facts)


def test_silent_without_absence_language():
    facts = [{"label": "Barolo", "state": PRESENT_SHORTLISTED}]
    assert not _false_absence_suspects("The Barolo is a lovely choice tonight.", facts)


def test_silent_with_no_facts():
    assert not _false_absence_suspects("There is nothing here.", [])
