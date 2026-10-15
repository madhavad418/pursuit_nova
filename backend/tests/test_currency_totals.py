"""The dashboard's by-currency view: projects won and projects in pipeline, per booking currency.

The page reports each currency at the amount its deals were actually booked in. These tests pin the
two things that make that view trustworthy: a closed-lost deal never counts as pipeline or as a win,
and a currency with no exchange rate reports its real amount and is flagged rather than converting
to None and reading as zero.
"""
import pytest

from app.main import currency_breakdown, norm_currency

RATES = {"USD": 1.0, "INR": 0.012, "GBP": 1.27, "EUR": 1.09}

# A real code that neither the seed nor any test fixture supplies a rate for. Deliberately not the
# KWD that test_region_currency uses: these suites share one database, and that one asserts the
# exact amount sitting under its own code.
UNRATED = "BHD"


@pytest.fixture(autouse=True)
def _schema(client):
    """`currency_breakdown` resolves a blank currency against the stored corporate currency, so
    even the unit tests below need the app's schema in place."""


def _opp(amount, currency, status="Qualified", final=None):
    return {"amount": amount, "currency": currency, "status": status, "final_amount": final}


def _by_code(out):
    return {r["currency"]: r for r in out}


# ------------------------------------------------------------------ won and pipeline, per currency

def test_each_currency_reports_its_own_amount_unconverted():
    """The whole point of the view: no blending. 5,000,000 INR is reported as 5,000,000 INR."""
    out = _by_code(currency_breakdown([_opp(5_000_000, "INR"), _opp(650_000, "USD")], RATES))
    assert out["INR"]["pipeline"] == pytest.approx(5_000_000.0)
    assert out["USD"]["pipeline"] == pytest.approx(650_000.0)
    # The corporate equivalent rides alongside it, it does not replace it.
    assert out["INR"]["pipeline_corporate"] == pytest.approx(60_000.0)


def test_won_and_pipeline_are_separate_figures_with_separate_counts():
    out = _by_code(currency_breakdown([
        _opp(500_000, "USD", status="Closed Won", final=430_000),
        _opp(120_000, "USD", status="Closed Won"),      # no final amount recorded
        _opp(200_000, "USD"),
        _opp(300_000, "USD", status="Presales / Solutioning"),
    ], RATES))["USD"]
    assert out["won"] == pytest.approx(550_000.0), "final amount when recorded, else the amount"
    assert out["won_count"] == 2
    assert out["pipeline"] == pytest.approx(500_000.0)
    assert out["pipeline_count"] == 2


@pytest.mark.parametrize("closed", ["Closed Lost", "Closed Hold"])
def test_a_closed_deal_that_is_not_a_win_is_neither_won_nor_pipeline(closed):
    """It is not in play and it was not won, so it belongs to neither figure on this page."""
    out = _by_code(currency_breakdown([_opp(400_000, "USD"), _opp(900_000, "USD", status=closed)], RATES))["USD"]
    assert out["pipeline"] == pytest.approx(400_000.0)
    assert out["won"] == 0.0
    assert out["pipeline_count"] == 1 and out["won_count"] == 0


def test_a_currency_with_nothing_won_and_nothing_open_is_left_out_entirely():
    """A row of zeroes is not an answer to "what have we won and what is in play"."""
    out = currency_breakdown([_opp(900_000, "EUR", status="Closed Lost"), _opp(10_000, "USD")], RATES)
    assert [r["currency"] for r in out] == ["USD"]


def test_a_deal_genuinely_won_at_zero_still_counts_as_a_win():
    """Zero value, but it happened — the count must not quietly drop it."""
    out = currency_breakdown([_opp(50_000, "USD", status="Closed Won", final=0)], RATES)
    assert out[0]["won_count"] == 1 and out[0]["won"] == 0.0


@pytest.mark.parametrize("stored", ["INR", "inr", "INR ", " INR", " inr  ", "Inr"])
def test_spelling_variants_fold_into_one_leg(stored):
    """`opportunities.currency` is free text; the spelling must not split a currency in two."""
    out = currency_breakdown([_opp(1_000_000, "INR"), _opp(2_000_000, stored)], RATES)
    assert len(out) == 1
    assert out[0]["currency"] == "INR"
    assert out[0]["pipeline"] == pytest.approx(3_000_000.0)


def test_blank_currency_falls_back_to_corporate():
    """A currency left blank resolves against the stored corporate currency, not to a dropped row."""
    from app.main import corporate_currency
    corp = norm_currency(corporate_currency())
    out = _by_code(currency_breakdown([_opp(1_000, None), _opp(1_000, "   ")], RATES))
    assert out[corp]["pipeline"] == pytest.approx(2_000.0)


# -------------------------------------------------------------------- the unconvertible currency

def test_an_unrated_currency_keeps_its_real_amount_and_is_flagged():
    """The silent-zero bug: this used to convert to None and be folded in as 0."""
    leg = currency_breakdown([_opp(75_000, UNRATED)], RATES)[0]
    assert leg["pipeline"] == pytest.approx(75_000.0), "the amount must survive"
    assert leg["convertible"] is False
    assert leg["pipeline_corporate"] is None, "an amount that cannot be converted is withheld, not guessed"
    assert leg["won_corporate"] is None


def test_an_unrated_currency_sorts_last_rather_than_by_its_native_number():
    """75,000 KWD and 5,000,000 INR are not comparable numbers, so the unrated one does not
    claim a position in a ranking by worth."""
    out = currency_breakdown([_opp(75_000, UNRATED), _opp(5_000_000, "INR"), _opp(650_000, "USD")], RATES)
    assert [r["currency"] for r in out] == ["USD", "INR", UNRATED]


def test_order_is_by_corporate_worth_not_by_the_size_of_the_native_number():
    out = currency_breakdown([_opp(5_000_000, "INR"), _opp(650_000, "USD")], RATES)
    assert [r["currency"] for r in out] == ["USD", "INR"], "650,000 USD outweighs 5,000,000 INR"


def test_output_is_stable_and_empty_input_is_an_empty_list():
    assert currency_breakdown([], RATES) == []
    deals = [_opp(10, "USD"), _opp(10, "INR")]
    assert currency_breakdown(deals, RATES) == currency_breakdown(deals, RATES)


# ------------------------------------------------------------------------------ over the live API

def test_analytics_exposes_currency_totals(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    a = client.get('/api/dashboard/analytics').json()

    assert "currency_totals" in a
    for r in a["currency_totals"]:
        assert r["currency"] == norm_currency(r["currency"]), "codes are canonical"
        assert r["pipeline"] >= 0 and r["won"] >= 0
        assert r["pipeline_count"] >= 0 and r["won_count"] >= 0
        assert r["pipeline_count"] or r["won_count"], "a currency with nothing to report is not listed"
        if r["convertible"]:
            assert r["pipeline_corporate"] is not None and r["won_corporate"] is not None
        else:
            assert r["pipeline_corporate"] is None and r["won_corporate"] is None
            assert r["currency"] in a["fx"]["missing_rates"]


def test_currency_totals_reconcile_with_the_region_breakdown(client, login):
    """Two views of the same opportunities: rolled up by currency, and by region then currency.
    They are computed independently, so they are a check on each other."""
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    a = client.get('/api/dashboard/analytics').json()

    from collections import defaultdict
    expected = defaultdict(lambda: {"pipeline": 0.0, "won": 0.0})
    for region in a["region_currency"]:
        for leg in region["currencies"]:
            expected[leg["currency"]]["pipeline"] += leg["pipeline"]
            expected[leg["currency"]]["won"] += leg["won"]

    for r in a["currency_totals"]:
        assert r["pipeline"] == pytest.approx(expected[r["currency"]]["pipeline"])
        assert r["won"] == pytest.approx(expected[r["currency"]]["won"])


def test_currency_totals_follow_record_scope(client, login):
    """A BD Executive sees only their own opportunities here, same as everywhere else."""
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    everyone = sum(r["pipeline_count"] + r["won_count"] for r in client.get('/api/dashboard/analytics').json()["currency_totals"])
    client.cookies.clear()
    login(client, email='bd.exec1@jsan.local')
    a = client.get('/api/dashboard/analytics').json()
    mine = sum(r["pipeline_count"] + r["won_count"] for r in a["currency_totals"])

    visible = client.get('/api/opportunities').json()
    counted = len([o for o in visible if o["status"] == "Closed Won" or not o["status"].startswith("Closed ")])
    assert mine == counted, "exactly the open and won opportunities this user can open"
    assert mine < everyone, "a BD Executive must not see the whole business"


def test_a_deal_in_an_unrated_currency_shows_up_in_the_by_currency_view(client, login, csrf_headers):
    """End to end: the record the dashboard used to swallow is now one of the cards on the page."""
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    lead_id = next(l["id"] for l in client.get('/api/leads').json() if (l.get("region") or "").strip())

    created = client.post(f'/api/leads/{lead_id}/opportunities',
                          json={"data": {"name": "Unrated currency deal", "amount": 75_000,
                                         "currency": UNRATED, "status": "Qualified"}},
                          headers=csrf_headers(client))
    assert created.status_code == 200, created.text

    totals = client.get('/api/dashboard/analytics').json()["currency_totals"]
    leg = next(r for r in totals if r["currency"] == UNRATED)
    assert leg["pipeline"] >= 75_000.0, "reported at its real amount"
    assert leg["convertible"] is False
    # Unrated codes have no comparable worth, so they sit after every convertible one rather than
    # claiming a rank. Asserted as an invariant: other suites add unrated deals to this same database.
    rated = [r["convertible"] for r in totals]
    assert rated == sorted(rated, reverse=True), "every unrated currency sorts after every rated one"
