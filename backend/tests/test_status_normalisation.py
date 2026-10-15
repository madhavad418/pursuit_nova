"""Opportunity stage is canonicalised on the way in, and anything odd is reported, not hidden.

Every dashboard figure is decided by comparing `opportunities.status` to an exact string. A stage
stored as "Closed Won " matched `startswith("Closed ")` but not `== "Closed Won"`, so it counted as
neither won nor open: the opportunity was still in the table and worth nothing on every panel. Same
silent-zero shape as the free-text currency bug. These tests pin both halves of the fix - the write
is canonicalised, and a status that still cannot be recognised is named on the dashboard.
"""
import pytest

from app.main import OPPORTUNITY_STAGES, norm_status, uncounted_opportunities


@pytest.fixture(autouse=True)
def _schema(client):
    """`uncounted_opportunities` resolves a blank currency against the stored corporate currency."""


def _opp(oid, status, name="A deal", currency="USD", amount=1000):
    return {"id": oid, "name": name, "company_name": "Acme", "status": status,
            "currency": currency, "amount": amount}


# ------------------------------------------------------------------ canonicalising the stage

@pytest.mark.parametrize("stored", ["Closed Won", "closed won", "CLOSED WON", "Closed Won ",
                                    " closed  won ", "ClosedWon", "closedwon"])
def test_every_spelling_of_a_stage_resolves_to_the_one_the_dashboard_compares_against(stored):
    assert norm_status(stored) == "Closed Won"


@pytest.mark.parametrize("stage", OPPORTUNITY_STAGES)
def test_each_real_stage_survives_untouched(stage):
    assert norm_status(stage) == stage
    assert norm_status(stage.lower()) == stage
    assert norm_status(f"  {stage}  ") == stage


def test_the_awkward_stage_with_punctuation_and_spacing_still_resolves():
    for spelling in ("Presales / Solutioning", "presales / solutioning", "Presales /Solutioning",
                     "presales/solutioning", "  PRESALES  /  SOLUTIONING  "):
        assert norm_status(spelling) == "Presales / Solutioning"


def test_norm_status_is_idempotent():
    for raw in (" closed won ", "CLOSED WON", "Closed Won"):
        assert norm_status(norm_status(raw)) == norm_status(raw) == "Closed Won"


def test_an_unknown_stage_is_passed_through_rather_than_rejected():
    """Statuses predate this guard and an integration may legitimately carry one. Breaking a working
    caller with a 400 would be a worse failure than reporting the value on the dashboard."""
    assert norm_status("Parked pending legal") == "Parked pending legal"
    assert norm_status("   ") == ""


# ----------------------------------------------------- the write paths that used to store anything

def test_creating_an_opportunity_canonicalises_a_sloppy_stage(client, login, csrf_headers):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    lead_id = client.get('/api/leads').json()[0]["id"]
    created = client.post(f'/api/leads/{lead_id}/opportunities',
                          json={"data": {"name": "Sloppy stage deal", "amount": 50_000,
                                         "currency": "USD", "status": "  qualified "}},
                          headers=csrf_headers(client))
    assert created.status_code == 200, created.text
    assert created.json()["opportunity"]["status"] == "Qualified"


def test_updating_an_opportunity_canonicalises_the_stage_it_is_moved_to(client, login, csrf_headers):
    """The reported shape: a deal marked won, stored with a trailing space, gone from every figure."""
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    lead_id = client.get('/api/leads').json()[0]["id"]
    opp = client.post(f'/api/leads/{lead_id}/opportunities',
                      json={"data": {"name": "Trailing space win", "amount": 90_000, "currency": "USD"}},
                      headers=csrf_headers(client)).json()["opportunity"]

    updated = client.put(f'/api/opportunities/{opp["id"]}',
                         json={"data": {"status": "Closed Won ", "final_amount": 88_000}},
                         headers=csrf_headers(client))
    assert updated.status_code == 200, updated.text
    assert updated.json()["opportunity"]["status"] == "Closed Won"

    # And because it is canonical, it actually lands in the won figure.
    totals = client.get('/api/dashboard/analytics').json()["currency_totals"]
    usd = next(r for r in totals if r["currency"] == "USD")
    assert usd["won"] >= 88_000
    assert not any(o["id"] == opp["id"] for o in
                   client.get('/api/dashboard/analytics').json()["uncounted"]["unrecognised"])


# --------------------------------------------------------------- reporting what is still not counted

def test_an_unrecognised_stage_is_named_rather_than_silently_absent():
    out = uncounted_opportunities([
        _opp(1, "Qualified"),
        _opp(2, "Parked pending legal", name="Limbo deal"),
        _opp(3, ""),
    ])
    named = {o["id"]: o for o in out["unrecognised"]}
    assert set(named) == {2, 3}, "only stages outside the app's own list"
    assert named[2]["name"] == "Limbo deal" and named[2]["status"] == "Parked pending legal"
    assert named[3]["status"] == "", "a blank stage is reported too, not skipped"


def test_hold_and_lost_are_counted_not_listed():
    """Deliberate exclusions, not faults - enough to account for the record, without listing
    closed business the page was asked not to show."""
    out = uncounted_opportunities([
        _opp(1, "Closed Hold"), _opp(2, "Closed Hold"), _opp(3, "Closed Lost"), _opp(4, "Qualified"),
    ])
    assert out["on_hold"] == 2 and out["lost"] == 1
    assert out["unrecognised"] == [], "a real stage is never reported as unrecognised"


def test_a_counted_opportunity_is_never_reported_as_uncounted():
    out = uncounted_opportunities([_opp(1, s) for s in ("Qualified", "Negotiation", "Closed Won")])
    assert out["unrecognised"] == [] and out["on_hold"] == 0 and out["lost"] == 0


def test_no_visible_opportunity_is_silently_absent(client, login):
    """The page's promise. Every opportunity in scope is either in a figure, tallied as hold/lost,
    or named as unrecognised - never simply missing.

    Not a partition: a stage like "closed won" is counted (as pipeline, wrongly) AND named, which is
    the point - being in a figure is no guarantee of being in the right one.
    """
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    a = client.get('/api/dashboard/analytics').json()
    named = {o["id"] for o in a["uncounted"]["unrecognised"]}

    counted = hold = lost = 0
    for o in client.get('/api/opportunities').json():
        status = str(o.get("status") or "")
        if status == "Closed Won" or not status.startswith("Closed "):
            counted += 1
        elif status == "Closed Hold":
            hold += 1
        elif status == "Closed Lost":
            lost += 1
        else:
            assert o["id"] in named, f"opportunity {o['id']} ({status!r}) is in no figure and unnamed"

    totals = sum(r["won_count"] + r["pipeline_count"] for r in a["currency_totals"])
    assert totals == counted, "the figures count exactly the opportunities a stage puts in them"
    assert a["uncounted"]["on_hold"] == hold and a["uncounted"]["lost"] == lost


def test_uncounted_follows_record_scope(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    everyone = client.get('/api/dashboard/analytics').json()["uncounted"]
    client.cookies.clear()
    login(client, email='bd.exec1@jsan.local')
    mine = client.get('/api/dashboard/analytics').json()["uncounted"]
    assert mine["lost"] <= everyone["lost"] and mine["on_hold"] <= everyone["on_hold"]
    assert len(mine["unrecognised"]) <= len(everyone["unrecognised"])
