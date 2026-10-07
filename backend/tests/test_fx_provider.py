"""Live FX rates from exchangerate-api.com.

The provider quotes base->target (1 USD = 96.467 INR). `fx_rates.rate_to_corporate` holds the
inverse — what one unit of a currency is worth in the corporate currency — so every quote is
reciprocated on the way in. These tests never touch the network.
"""
import httpx
import pytest

from app import main
from app.main import FX_PROVIDER, currencies_in_use, norm_currency, refresh_fx_rates, to_corporate

API_KEY = "test-key-must-never-appear-in-an-error"

# Trimmed copy of a real v6 response.
PAYLOAD = {
    "result": "success",
    "base_code": "USD",
    "time_last_update_utc": "Wed, 07 Oct 2026 00:00:02 +0000",
    "conversion_rates": {"USD": 1, "INR": 96.467, "GBP": 0.754, "EUR": 0.8887, "AED": 3.6725},
}


class _Response:
    def __init__(self, payload, status=200):
        self.status_code, self._payload = status, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            # The real exception carries the request URL, which carries the key.
            raise httpx.HTTPStatusError(f"500 for https://v6.exchangerate-api.com/v6/{API_KEY}/latest/USD",
                                        request=httpx.Request("GET", "https://x"), response=None)

    def json(self):
        if self._payload is None: raise ValueError("not json")
        return self._payload


def _fake_provider(monkeypatch, payload, status=200, calls=None, boom=None):
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url):
            if calls is not None: calls.append(url)
            if boom: raise boom
            return _Response(payload, status)
    monkeypatch.setattr(main, "EXCHANGERATE_API_KEY", API_KEY)
    monkeypatch.setattr(main.httpx, "Client", _Client)


# ----------------------------------------------------------------------------- the rate maths

def test_quotes_are_reciprocated_into_rate_to_corporate(client, login, monkeypatch):
    calls = []
    _fake_provider(monkeypatch, PAYLOAD, calls=calls)
    result = refresh_fx_rates()

    assert result["provider"] == FX_PROVIDER
    assert result["as_of"] == "2026-10-07", "the provider's own timestamp is recorded, not today"
    assert calls[0].endswith(f"/{API_KEY}/latest/USD")

    rates = main.fx_map()
    assert rates["USD"] == 1.0, "the corporate currency is always exactly 1"
    assert rates["INR"] == pytest.approx(1 / 96.467), "96.467 INR per USD -> 0.010366 USD per INR"
    assert rates["GBP"] == pytest.approx(1 / 0.754), "GBP is worth more than a dollar"
    assert rates["GBP"] > 1 > rates["INR"]

    # And the figure a dashboard would actually show.
    assert to_corporate(5_000_000, "INR", rates) == pytest.approx(5_000_000 / 96.467)


def test_refresh_records_provenance(client, login, monkeypatch):
    _fake_provider(monkeypatch, PAYLOAD)
    refresh_fx_rates()
    stored = {r["currency"]: r for r in main.rows(main.select(main.fx_rates))}
    assert stored["INR"]["source"] == FX_PROVIDER
    assert stored["INR"]["as_of"] == "2026-10-07"


def test_a_currency_the_provider_does_not_quote_is_reported_not_guessed(client, login, monkeypatch):
    thin = {**PAYLOAD, "conversion_rates": {"USD": 1, "INR": 96.467}}
    _fake_provider(monkeypatch, thin)
    before = main.fx_map().get("GBP")
    result = refresh_fx_rates()
    assert "GBP" in result["unsupported"]
    assert "INR" in result["updated"]
    assert main.fx_map().get("GBP") == before, "an unquoted currency keeps whatever it had"


def test_a_zero_quote_is_refused_rather_than_dividing_by_zero(client, login, monkeypatch):
    _fake_provider(monkeypatch, {**PAYLOAD, "conversion_rates": {"USD": 1, "INR": 0}})
    result = refresh_fx_rates()
    assert "INR" in result["unsupported"]


# ------------------------------------------------------------------- the key must never leak

@pytest.mark.parametrize("kwargs, expect", [
    ({"payload": {"result": "error", "error-type": "invalid-key"}}, "invalid-key"),
    ({"payload": {}, "status": 403}, "rejected the API key"),
    ({"payload": {}, "status": 429}, "quota is exhausted"),
    ({"payload": None}, "malformed"),
    ({"payload": {"result": "success", "conversion_rates": {}}}, "no rates"),
    ({"payload": {}, "boom": httpx.ConnectError("dns failure")}, "unreachable"),
    ({"payload": {}, "status": 500}, "unreachable"),
])
def test_provider_failures_surface_without_the_api_key(client, login, monkeypatch, kwargs, expect):
    _fake_provider(monkeypatch, **kwargs)
    with pytest.raises(main.HTTPException) as e:
        refresh_fx_rates()
    assert expect in e.value.detail
    assert API_KEY not in e.value.detail, "the key is in the request path and must never be echoed"


def test_refresh_without_a_key_is_a_clear_409(client, login, monkeypatch):
    monkeypatch.setattr(main, "EXCHANGERATE_API_KEY", "")
    with pytest.raises(main.HTTPException) as e:
        refresh_fx_rates()
    assert e.value.status_code == 409
    assert "EXCHANGERATE_API_KEY" in e.value.detail


# --------------------------------------------------------------------------- what gets refreshed

def test_refresh_covers_currencies_the_data_actually_uses(client, login, csrf_headers, monkeypatch):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    lead_id = next(l["id"] for l in client.get('/api/leads').json() if (l.get("region") or "").strip())
    client.post(f'/api/leads/{lead_id}/opportunities',
                json={"data": {"name": "Dirham deal", "amount": 1000, "currency": "AED"}},
                headers=csrf_headers(client))

    assert "AED" in currencies_in_use(), "a currency in the data is picked up even with no rate row yet"
    _fake_provider(monkeypatch, PAYLOAD)
    result = refresh_fx_rates()
    assert "AED" in result["updated"]
    assert main.fx_map()["AED"] == pytest.approx(1 / 3.6725)


def test_auto_refresh_never_raises(client, login, monkeypatch):
    """It runs on a boot thread, so a provider outage must not surface at all."""
    _fake_provider(monkeypatch, {}, boom=httpx.ConnectError("down"))
    monkeypatch.setattr(main, "FX_AUTO_REFRESH", True)
    main.auto_refresh_fx_rates()  # must not raise


def test_auto_refresh_is_skipped_when_rates_are_already_current(client, login, monkeypatch):
    # Current *and* already off the seeded placeholders — both conditions must hold to skip.
    main.execute(main.update(main.fx_rates).values(as_of="2026-10-07", source=FX_PROVIDER))
    calls = []
    _fake_provider(monkeypatch, PAYLOAD, calls=calls)
    monkeypatch.setattr(main, "FX_AUTO_REFRESH", True)
    monkeypatch.setattr(main, "today_str", lambda: "2020-01-01")  # every stored rate is "in the future"
    main.auto_refresh_fx_rates()
    assert calls == [], "no provider call when the stored rates are not stale"


# ------------------------------------------------------------------------------- over the API

def test_refresh_endpoint_requires_forecast_admin(client, login, csrf_headers, monkeypatch):
    _fake_provider(monkeypatch, PAYLOAD)
    client.cookies.clear()
    login(client, email='bd.exec1@jsan.local')
    r = client.post('/api/admin/currency/refresh', headers=csrf_headers(client))
    assert r.status_code == 403


def test_refresh_endpoint_returns_the_updated_table(client, login, csrf_headers, monkeypatch):
    _fake_provider(monkeypatch, PAYLOAD)
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    r = client.post('/api/admin/currency/refresh', headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refresh"]["provider"] == FX_PROVIDER
    assert body["provider"]["configured"] is True
    inr = next(x for x in body["rates"] if norm_currency(x["currency"]) == "INR")
    assert inr["rate_to_corporate"] == pytest.approx(1 / 96.467)
    assert body["stale_rates"] == [], "nothing is left on a seeded placeholder after a refresh"
    assert API_KEY not in r.text


def test_auto_refresh_replaces_seeded_placeholders_even_when_dated_today(client, login, monkeypatch):
    """The seed stamps its placeholder rates with today's date, so freshness alone would never
    replace them — a fresh deploy would run all day on the wrong INR rate."""
    main.execute(main.update(main.fx_rates).values(as_of=main.today_str(), source="DEFAULT"))
    calls = []
    _fake_provider(monkeypatch, PAYLOAD, calls=calls)
    monkeypatch.setattr(main, "FX_AUTO_REFRESH", True)
    main.auto_refresh_fx_rates()
    assert calls, "a placeholder rate must trigger the refresh regardless of its date"
    stored = {norm_currency(r["currency"]): r["source"] for r in main.rows(main.select(main.fx_rates))}
    assert all(stored[c] == FX_PROVIDER for c in ("INR", "GBP", "EUR"))
    assert stored["USD"] == "CORPORATE-BASE", "the base row is marked as such, not as a provider quote"


# ------------------------------------------------------- display-side conversion ("view in")

def test_rates_endpoint_is_readable_by_any_signed_in_user(client, login):
    """The picker on the money pages needs rates without admin permissions."""
    client.cookies.clear()
    login(client, email='bd.exec1@jsan.local')
    r = client.get('/api/currency/rates')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["corporate_currency"] == norm_currency(body["corporate_currency"])
    assert body["rates"][body["corporate_currency"]] == 1.0
    assert set(body["rates"]) == set(main.fx_map()), "exactly the table the server converts with"
    assert body["as_of"] and isinstance(body["sources"], list) and isinstance(body["live"], bool)
    assert API_KEY not in r.text


def test_rates_endpoint_requires_a_session(client):
    client.cookies.clear()
    assert client.get('/api/currency/rates').status_code == 401


def test_rates_endpoint_live_flag_tracks_provenance(client, login, monkeypatch):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    main.execute(main.update(main.fx_rates).values(source="DEFAULT"))
    assert client.get('/api/currency/rates').json()["live"] is False
    _fake_provider(monkeypatch, PAYLOAD)
    refresh_fx_rates()
    assert client.get('/api/currency/rates').json()["live"] is True



# ------------------------------------------------------- review findings, pinned by tests

def test_a_hand_entered_rate_survives_a_provider_refresh(client, login, monkeypatch):
    """Treasury-approved rates are not overwritten by the feed unless explicitly overridden."""
    main.execute(main.update(main.fx_rates).where(main.fx_rates.c.currency == "GBP").values(rate_to_corporate=1.25, source="MANUAL"))
    _fake_provider(monkeypatch, PAYLOAD)
    result = refresh_fx_rates()
    assert "GBP" in result["kept_manual"] and "GBP" not in result["updated"]
    assert main.fx_map()["GBP"] == pytest.approx(1.25)
    forced = refresh_fx_rates(override_manual=True)
    assert "GBP" in forced["updated"]
    assert main.fx_map()["GBP"] == pytest.approx(1 / 0.754)


@pytest.mark.parametrize("raw, code", [("Rs", "INR"), (" rupees ", "INR"), ("$", "USD"), ("US$", "USD"), ("euro", "EUR"), ("Dhs", "AED"), ("inr ", "INR")])
def test_common_aliases_resolve_to_iso_codes(raw, code):
    assert norm_currency(raw) == code


@pytest.mark.parametrize("bad, msg", [("1e999", "finite"), ("nan", "finite"), ("-5", "negative"), ("50k$", "number")])
def test_non_finite_or_malformed_amounts_are_a_400_not_a_500(client, login, csrf_headers, bad, msg):
    """One stored `inf` used to make every dashboard endpoint 500 for everyone in scope."""
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    lead_id = next(l["id"] for l in client.get('/api/leads').json() if (l.get("region") or "").strip())
    r = client.post(f'/api/leads/{lead_id}/opportunities', json={"data": {"name": "bad", "amount": bad}}, headers=csrf_headers(client))
    assert r.status_code == 400, r.text
    assert msg in r.json()["detail"]
    assert client.get('/api/dashboard/summary').status_code == 200


def test_rate_put_validates_everything_before_writing(client, login, csrf_headers):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    before = main.fx_map(); corp_before = main.corporate_currency()
    r = client.put('/api/admin/currency', json={"data": {"rates": [{"currency": "gbp ", "rate_to_corporate": 1.3}, {"currency": "INR", "rate_to_corporate": -1}]}}, headers=csrf_headers(client))
    assert r.status_code == 400
    assert main.fx_map() == before, "a rejected request must change nothing"
    assert main.corporate_currency() == corp_before
    for bad in ("inf", "nan", "abc"):
        assert client.put('/api/admin/currency', json={"data": {"rates": [{"currency": "INR", "rate_to_corporate": bad}]}}, headers=csrf_headers(client)).status_code == 400
    assert client.put('/api/admin/currency', json={"data": {"rates": [{"currency": "INR", "rate_to_corporate": 0.01, "as_of": "today"}]}}, headers=csrf_headers(client)).status_code == 400
    # A padded code is stored canonically, never as a stray " GBP " row.
    r = client.put('/api/admin/currency', json={"data": {"rates": [{"currency": " gbp ", "rate_to_corporate": 1.3}]}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    assert [x["currency"] for x in r.json()["rates"] if "GBP" in x["currency"].upper()] == ["GBP"]
    assert main.fx_map()["GBP"] == pytest.approx(1.3)
    assert "GBP" in r.json()["manual_rates"]


def test_changing_corporate_currency_rebases_from_the_provider(client, login, csrf_headers, monkeypatch):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    inr_base = {**PAYLOAD, "base_code": "INR", "conversion_rates": {"INR": 1, "USD": 0.01036624, "GBP": 0.00781, "EUR": 0.00921, "AED": 0.0381}}
    calls = []
    _fake_provider(monkeypatch, inr_base, calls=calls)
    r = client.put('/api/admin/currency', json={"data": {"corporate_currency": "inr"}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    assert calls and calls[-1].endswith('/latest/INR'), "quotes are pulled for the NEW base"
    rates = main.fx_map()
    assert main.norm_currency(main.corporate_currency()) == "INR" and rates["INR"] == 1.0
    assert rates["USD"] == pytest.approx(1 / 0.01036624), "one USD is now worth ~96 INR"
    assert r.json()["rebase"]["base"] == "INR"
    # And back - the provider answers for USD again.
    _fake_provider(monkeypatch, PAYLOAD)
    assert client.put('/api/admin/currency', json={"data": {"corporate_currency": "USD"}}, headers=csrf_headers(client)).status_code == 200
    assert main.fx_map()["INR"] == pytest.approx(1 / 96.467)


def test_a_failed_rebase_changes_nothing(client, login, csrf_headers, monkeypatch):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    before = main.fx_map(); corp = main.norm_currency(main.corporate_currency())
    _fake_provider(monkeypatch, {}, boom=httpx.ConnectError("down"))
    r = client.put('/api/admin/currency', json={"data": {"corporate_currency": "EUR"}}, headers=csrf_headers(client))
    assert r.status_code == 502
    assert main.norm_currency(main.corporate_currency()) == corp and main.fx_map() == before


def test_rebase_without_a_provider_needs_a_full_manual_set(client, login, csrf_headers, monkeypatch):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    monkeypatch.setattr(main, "EXCHANGERATE_API_KEY", "")
    corp = main.norm_currency(main.corporate_currency())
    r = client.put('/api/admin/currency', json={"data": {"corporate_currency": "EUR", "rates": [{"currency": "USD", "rate_to_corporate": 0.9}]}}, headers=csrf_headers(client))
    assert r.status_code == 409 and "missing:" in r.json()["detail"]
    assert main.norm_currency(main.corporate_currency()) == corp


def test_pipeline_query_reports_per_stage_converted_totals(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    body = client.get('/api/query/opportunities?page_size=1').json()
    assert "missing_fx_rates" in body and isinstance(body["missing_fx_rates"], list)
    by = body["summary"]["by_status"]
    assert by and all({"count", "value", "unrated"} <= set(v) for v in by.values())
    assert sum(v["count"] for v in by.values()) == body["total"], "stage totals cover the whole filtered set, not the page"


def test_dashboard_summary_reports_missing_rates(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    assert isinstance(client.get('/api/dashboard/summary').json()["missing_fx_rates"], list)


def test_top_opportunities_are_ranked_by_converted_value(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    values = [o["value"] for o in client.get('/api/dashboard/analytics').json()["top_opportunities"]]
    assert values == sorted(values, reverse=True)


def test_rates_endpoint_flags_staleness_separately_from_provenance(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    main.execute(main.update(main.fx_rates).values(as_of="2020-01-01", source=FX_PROVIDER))
    body = client.get('/api/currency/rates').json()
    assert body["live"] is True and body["stale"] is True, "a month of failed refreshes must not read as fresh"
    main.execute(main.update(main.fx_rates).values(as_of=main.today_str()))
    assert client.get('/api/currency/rates').json()["stale"] is False


def test_closed_won_at_zero_reports_zero_not_the_pre_close_amount():
    assert main.won_amount({"amount": 500_000, "final_amount": 0}) == 0
    assert main.won_amount({"amount": 500_000, "final_amount": None}) == 500_000
