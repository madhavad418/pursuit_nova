"""Region-wise native currency on the dashboard, and the silent-zero bug it replaces.

An opportunity's currency is free text. Before the fix, anything that was not an exact uppercase
match for a row in `fx_rates` converted to None, and every dashboard call site turned that into 0 —
so a real opportunity read as zero value and looked like it had vanished from the dashboard.
"""
import pytest

from app.main import norm_currency, region_currency_breakdown, to_corporate

RATES = {"USD": 1.0, "INR": 0.012, "GBP": 1.27, "EUR": 1.09}


# --------------------------------------------------------------------------- the bug, at the unit

@pytest.mark.parametrize("stored", ["INR", "inr", "INR ", " INR", " inr  ", "Inr"])
def test_currency_spelling_variants_all_convert(stored):
    """The exact spelling stored against the opportunity must not change its value."""
    assert to_corporate(50000, stored, RATES) == pytest.approx(600.0)


def test_blank_currency_falls_back_to_corporate_not_to_zero(client):
    # Needs the app fixture: a blank currency resolves against the stored corporate currency.
    from app.main import corporate_currency
    expected = 50000 * RATES[norm_currency(corporate_currency())]
    for blank in (None, "", "   "):
        assert to_corporate(50000, blank, RATES) == pytest.approx(expected)


def test_genuinely_unknown_currency_reports_none_rather_than_zero():
    """None is the signal callers need in order to warn. 0 is indistinguishable from a real zero."""
    assert to_corporate(50000, "ZZZ", RATES) is None


def test_norm_currency_is_idempotent():
    for raw in (" inr ", "INR", "inr"):
        assert norm_currency(norm_currency(raw)) == norm_currency(raw) == "INR"


# ------------------------------------------------------------------- region-wise native currency

def _leads():
    return [{"id": 1, "region": "India"}, {"id": 2, "region": "North America"}, {"id": 3, "region": "  "}]


def _opp(oid, lead_id, amount, currency, status="Qualified", final=None):
    return {"id": oid, "lead_id": lead_id, "amount": amount, "currency": currency,
            "status": status, "final_amount": final}


def test_amounts_stay_in_their_own_currency():
    """The whole point of the feature: no blending, no conversion."""
    out = region_currency_breakdown(_leads(), [
        _opp(1, 1, 5_000_000, "INR"),
        _opp(2, 2, 650_000, "USD"),
    ], RATES)
    india = next(r for r in out if r["region"] == "India")
    assert india["currencies"] == [
        {"currency": "INR", "pipeline": 5_000_000.0, "won": 0.0, "opportunities": 1, "convertible": True}]
    # Reported in INR, not the 60,000 USD it converts to.
    assert india["pipeline_corporate"] == pytest.approx(60_000.0)


def test_one_region_holding_several_currencies_lists_each_separately():
    out = region_currency_breakdown(_leads(), [
        _opp(1, 1, 5_000_000, "INR"),
        _opp(2, 1, 10_000, "USD"),
        _opp(3, 1, 2_000_000, "inr"),  # variant spelling folds into the same leg
    ], RATES)
    india = next(r for r in out if r["region"] == "India")
    assert india["opportunities"] == 3
    legs = {c["currency"]: c for c in india["currencies"]}
    assert set(legs) == {"INR", "USD"}
    assert legs["INR"]["pipeline"] == pytest.approx(7_000_000.0)
    assert legs["INR"]["opportunities"] == 2
    assert legs["USD"]["pipeline"] == pytest.approx(10_000.0)


def test_unconvertible_opportunity_keeps_its_real_amount_and_is_flagged():
    """The vanished-record bug: this used to read as 0 with no indication anything was wrong."""
    out = region_currency_breakdown(_leads(), [_opp(1, 1, 50_000, "ZZZ")], RATES)
    india = next(r for r in out if r["region"] == "India")
    leg = india["currencies"][0]
    assert leg["pipeline"] == pytest.approx(50_000.0), "the amount must survive"
    assert leg["convertible"] is False
    assert india["unconvertible"] == ["ZZZ"]
    assert india["pipeline_corporate"] is None, "a partial total must not pose as a whole one"


def test_corporate_total_survives_a_zero_valued_unconvertible_leg():
    """Only a currency actually carrying value can make a total incomplete."""
    out = region_currency_breakdown(_leads(), [
        _opp(1, 1, 100_000, "USD"),
        _opp(2, 1, 0, "ZZZ"),
    ], RATES)
    india = next(r for r in out if r["region"] == "India")
    assert india["unconvertible"] == ["ZZZ"]
    assert india["pipeline_corporate"] == pytest.approx(100_000.0)


def test_won_uses_final_amount_and_is_split_from_pipeline():
    out = region_currency_breakdown(_leads(), [
        _opp(1, 2, 500_000, "USD", status="Closed Won", final=430_000),
        _opp(2, 2, 200_000, "USD"),
        _opp(3, 2, 900_000, "USD", status="Closed Lost"),
        _opp(4, 2, 700_000, "USD", status="Closed Hold"),
    ], RATES)
    na = next(r for r in out if r["region"] == "North America")
    leg = na["currencies"][0]
    assert leg["won"] == pytest.approx(430_000.0)
    assert leg["pipeline"] == pytest.approx(200_000.0), "closed rows never count as open pipeline"
    assert na["opportunities"] == 4, "every opportunity is still counted"


def test_blank_and_unknown_regions_collapse_into_unassigned():
    out = region_currency_breakdown(_leads(), [
        _opp(1, 3, 1_000, "USD"),     # lead with a whitespace-only region
        _opp(2, 999, 2_000, "USD"),   # lead outside the caller's visible scope
    ], RATES)
    assert [r["region"] for r in out] == ["Unassigned"]
    assert out[0]["currencies"][0]["pipeline"] == pytest.approx(3_000.0)


def test_rows_are_ordered_and_stable():
    out = region_currency_breakdown(_leads(), [
        _opp(1, 1, 10, "USD"), _opp(2, 1, 10, "USD"), _opp(3, 2, 10, "USD"),
    ], RATES)
    assert [r["region"] for r in out] == ["India", "North America"], "busiest region first"
    assert region_currency_breakdown(_leads(), [_opp(1, 1, 10, "USD")], RATES) == \
           region_currency_breakdown(_leads(), [_opp(1, 1, 10, "USD")], RATES)


def test_empty_input_is_an_empty_list():
    assert region_currency_breakdown(_leads(), [], RATES) == []


# ------------------------------------------------------------------------------ over the live API

def test_analytics_exposes_region_currency_and_an_fx_account(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    a = client.get('/api/dashboard/analytics').json()

    assert "region_currency" in a and "fx" in a
    assert a["fx"]["corporate_currency"] == a["currency"]
    assert isinstance(a["fx"]["missing_rates"], list)

    # Every opportunity the caller can see is represented exactly once.
    pipeline_rows = client.get('/api/dashboard/pipeline').json()
    assert sum(r["opportunities"] for r in a["region_currency"]) == sum(g["count"] for g in pipeline_rows)

    for r in a["region_currency"]:
        assert r["region"], "a region label is never blank"
        assert r["currencies"], "a region row always carries at least one currency leg"
        for leg in r["currencies"]:
            assert leg["currency"] == norm_currency(leg["currency"])
            assert leg["pipeline"] >= 0 and leg["won"] >= 0
        # The flagged set and the per-leg flags agree.
        assert r["unconvertible"] == [c["currency"] for c in r["currencies"] if not c["convertible"]]


def test_region_currency_follows_record_scope(client, login):
    """A BD Executive sees only their own opportunities here, same as everywhere else."""
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    everyone = sum(r["opportunities"] for r in client.get('/api/dashboard/analytics').json()["region_currency"])
    client.cookies.clear()
    login(client, email='bd.exec1@jsan.local')
    mine = sum(r["opportunities"] for r in client.get('/api/dashboard/analytics').json()["region_currency"])
    visible = len(client.get('/api/opportunities').json())
    assert mine == visible, "exactly the opportunities this user can open - no more, no fewer"
    assert mine < everyone, "a BD Executive must not see the whole business"


# ------------------------------------------------- the reported bug, reproduced through the API

def _first_lead_id(client):
    """A lead that carries a region, so the region assertions below mean something."""
    leads = client.get('/api/leads').json()
    return next(l["id"] for l in leads if (l.get("region") or "").strip())


def _stored_rate(client, code):
    """Read the rate the app is actually holding. Rates move (a provider refresh rewrites them),
    so these tests assert against live state rather than a hardcoded number."""
    rates = client.get('/api/admin/currency').json()["rates"]
    return next(float(r["rate_to_corporate"]) for r in rates if norm_currency(r["currency"]) == code)


# A real code that neither the seed nor any test fixture supplies a rate for.
UNRATED = "KWD"


def test_opportunity_entered_with_a_padded_currency_still_carries_value(client, login, csrf_headers):
    """The reported symptom: an opportunity that was showing, then read as zero the next day.

    A currency stored as "INR " (or any other spelling) used to miss the rate table and be folded
    into the dashboard as 0 — the record was still there, but worth nothing on every panel.
    """
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    lead_id = _first_lead_id(client)
    before = client.get('/api/dashboard/summary').json()["pipeline_value"]

    created = client.post(f'/api/leads/{lead_id}/opportunities',
                          json={"data": {"name": "Padded currency deal", "amount": 5_000_000,
                                         "currency": " inr ", "status": "Qualified"}},
                          headers=csrf_headers(client))
    assert created.status_code == 200, created.text
    opp = created.json()["opportunity"]

    # Stored canonically, so it can never miss the rate table again.
    assert opp["currency"] == "INR"

    after = client.get('/api/dashboard/summary').json()["pipeline_value"]
    assert after == pytest.approx(before + 5_000_000 * _stored_rate(client, "INR")), "the deal must move the needle"
    assert after > before, "it is worth something, not zero"

    # And it is visible in its own currency, under its own region.
    a = client.get('/api/dashboard/analytics').json()
    legs = [leg for r in a["region_currency"] for leg in r["currencies"] if leg["currency"] == "INR"]
    assert legs, "an INR deal must appear as an INR leg"
    assert sum(leg["pipeline"] for leg in legs) >= 5_000_000, "reported in INR, not converted"


def test_opportunity_in_an_unrated_currency_is_surfaced_not_silently_zeroed(client, login, csrf_headers):
    """No rate exists for this code, so it cannot be converted — but it must not disappear."""
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    lead_id = _first_lead_id(client)

    created = client.post(f'/api/leads/{lead_id}/opportunities',
                          json={"data": {"name": "Unrated currency deal", "amount": 75_000,
                                         "currency": UNRATED, "status": "Qualified"}},
                          headers=csrf_headers(client))
    assert created.status_code == 200, created.text

    a = client.get('/api/dashboard/analytics').json()
    assert UNRATED in a["fx"]["missing_rates"], "the dashboard must say which rates are missing"
    assert a["fx"]["unconvertible_opportunities"] >= 1

    leg = next(leg for r in a["region_currency"] for leg in r["currencies"] if leg["currency"] == UNRATED)
    assert leg["pipeline"] == pytest.approx(75_000.0), "the real amount survives"
    assert leg["convertible"] is False

    region = next(r for r in a["region_currency"] if any(c["currency"] == UNRATED for c in r["currencies"]))
    assert region["pipeline_corporate"] is None, "an incomplete total is withheld, not guessed"


def test_changing_currency_through_the_update_endpoint_is_also_normalized(client, login, csrf_headers):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    lead_id = _first_lead_id(client)
    opp = client.post(f'/api/leads/{lead_id}/opportunities',
                      json={"data": {"name": "Currency edit deal", "amount": 1_000, "currency": "USD"}},
                      headers=csrf_headers(client)).json()["opportunity"]

    updated = client.put(f'/api/opportunities/{opp["id"]}',
                         json={"data": {"currency": "  gbp "}}, headers=csrf_headers(client))
    assert updated.status_code == 200, updated.text
    assert updated.json()["opportunity"]["currency"] == "GBP"
