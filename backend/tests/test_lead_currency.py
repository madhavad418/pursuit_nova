"""Every prospect carries a default deal currency.

Set from the region when not given, editable, shown on the Prospects table, and inherited by new
opportunities on that prospect — so a deal for an Indian prospect defaults to INR without anyone
picking it.
"""
import pytest

from app import main
from app.db import REGION_CURRENCY, region_currency


def _login(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')


def _create(client, csrf_headers, **lead):
    body = {"data": {"company": {"name": lead.pop("company", f"Co {main.secrets.token_hex(4)}"), "vertical": "Data & AI"},
                     "lead": {"temperature": "Warm", "source": "LinkedIn", **lead}, "contacts": []}}
    r = client.post('/api/leads/full', json=body, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    j = r.json()
    return j if "lead" in j else {"lead": j}


@pytest.mark.parametrize("region, code", [("India", "INR"), ("UK", "GBP"), ("Europe", "EUR"), ("UAE", "AED"), ("North America", "USD"), ("india, uk", "INR"), ("Atlantis", "USD"), (None, "USD"), ("", "USD")])
def test_region_default_mapping(region, code):
    assert region_currency(region, "USD") == code


def test_every_mapped_code_is_a_three_letter_iso_code():
    assert all(len(c) == 3 and c.isupper() for c in REGION_CURRENCY.values())


def test_new_prospect_gets_its_regions_currency(client, login, csrf_headers):
    _login(client, login)
    lead = _create(client, csrf_headers, region="India")["lead"]
    assert lead["currency"] == "INR"
    assert next(l for l in client.get('/api/leads').json() if l["id"] == lead["id"])["currency"] == "INR", "exposed on the Prospects list"


def test_explicit_currency_wins_and_is_normalised(client, login, csrf_headers):
    _login(client, login)
    lead = _create(client, csrf_headers, region="India", currency=" gbp ")["lead"]
    assert lead["currency"] == "GBP"


def test_prospect_currency_is_editable_and_blank_restores_the_region_default(client, login, csrf_headers):
    _login(client, login)
    lead = _create(client, csrf_headers, region="UK")["lead"]
    r = client.put(f'/api/leads/{lead["id"]}', json={"data": {"currency": "$"}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    assert r.json()["lead"]["currency"] == "USD", "'$' resolves through the alias table"
    r = client.put(f'/api/leads/{lead["id"]}', json={"data": {"currency": ""}}, headers=csrf_headers(client))
    assert r.json()["lead"]["currency"] == "GBP", "blank means 'back to the region default'"


def test_new_opportunity_inherits_the_prospect_currency(client, login, csrf_headers):
    _login(client, login)
    lead = _create(client, csrf_headers, region="India")["lead"]
    opp = client.post(f'/api/leads/{lead["id"]}/opportunities',
                      json={"data": {"name": "Inherits INR", "amount": 100}}, headers=csrf_headers(client)).json()["opportunity"]
    assert opp["currency"] == "INR", "an untouched form stores the prospect's currency, not the corporate one"
    chosen = client.post(f'/api/leads/{lead["id"]}/opportunities',
                         json={"data": {"name": "Chose EUR", "amount": 100, "currency": "EUR"}}, headers=csrf_headers(client)).json()["opportunity"]
    assert chosen["currency"] == "EUR", "an explicit choice still wins"


def test_backfill_leaves_no_prospect_without_a_currency(client, login):
    main.execute(main.update(main.leads).values(currency=None))
    from app.db import backfill_lead_currency
    backfill_lead_currency()
    rows = main.rows(main.select(main.leads.c.region, main.leads.c.currency))
    assert rows and all(r["currency"] for r in rows)
    assert all(r["currency"] == region_currency(r["region"], main.norm_currency(main.corporate_currency())) for r in rows)


def test_prospect_currencies_count_as_in_use(client, login, csrf_headers):
    _login(client, login)
    _create(client, csrf_headers, region="Singapore")
    assert "SGD" in main.currencies_in_use(), "the next provider refresh will fetch a rate for it"
