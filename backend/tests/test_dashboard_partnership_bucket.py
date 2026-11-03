"""The dashboard's by-currency panel must report the partnership bucket, not just prospects.

Partnership opportunities live in `partner_opportunities`, a separate table with its own visibility
rules, while every other figure on the dashboard is built from `opportunity_rows`. The by-currency
panel claims to answer "what have we won and what is still in play" for the whole visible business,
so it has to cover both. It did not: a deal entered under a partnership appeared nowhere on the
page, which to whoever entered it looks exactly like the tool losing their work.

These tests are deliberately self-contained — they create the partnership deal they assert on rather
than relying on one an earlier suite happened to leave behind. `test_currency_totals.py` runs before
`test_partnerships.py` alphabetically, so its reconcile and scope assertions were passing against an
empty partnership bucket and could not have caught this.
"""
import pytest

from app import main

SUPER, EXEC1, EXEC2 = 'superadmin@jsan.local', 'bd.exec1@jsan.local', 'bd.exec2@jsan.local'

# A real code the seed supplies no rate for, and which the other currency suites do not assert exact
# amounts under (they use BHD and KWD).
UNRATED = 'OMR'


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _partnership(client, login, csrf_headers, email, company):
    """A partnership owned by `email`, returning (partnership_id, csrf headers)."""
    me = _as(client, login, email)
    h = csrf_headers(client)
    r = client.post('/api/partnerships/full', json={'data': {
        'company': {'name': company, 'vertical': 'Systems Integration'},
        'lead': {'owner_id': me['id'], 'region': 'UK'},
        'contacts': [],
    }}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()['lead']['id'], h


def _add_opp(client, h, pid, **data):
    r = client.post(f'/api/partnerships/{pid}/opportunities', json={'data': data}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _leg(totals, code):
    return next((r for r in totals if r['currency'] == code), None)


# --------------------------------------------------------------- the reported bug, end to end

def test_a_partnership_opportunity_reaches_the_by_currency_panel(client, login, csrf_headers):
    """The bug as reported: add an opportunity under a partnership, and the dashboard ignores it."""
    pid, h = _partnership(client, login, csrf_headers, SUPER, 'Dashboard Bucket Partner A')

    before = client.get('/api/dashboard/analytics').json()['currency_totals']
    was = (_leg(before, 'USD') or {}).get('pipeline', 0.0)
    was_count = (_leg(before, 'USD') or {}).get('pipeline_count', 0)

    _add_opp(client, h, pid, name='Partner co-sell', amount=250_000, currency='USD', status='Qualified')

    after = _leg(client.get('/api/dashboard/analytics').json()['currency_totals'], 'USD')
    assert after is not None, 'the USD leg must exist once a USD partnership deal is in play'
    assert after['pipeline'] == pytest.approx(was + 250_000), 'the partnership deal is in the figure'
    assert after['pipeline_count'] == was_count + 1, 'and in the project count beside it'


def test_a_won_partnership_deal_counts_as_won_not_as_pipeline(client, login, csrf_headers):
    pid, h = _partnership(client, login, csrf_headers, SUPER, 'Dashboard Bucket Partner B')
    before = _leg(client.get('/api/dashboard/analytics').json()['currency_totals'], 'USD') or {}
    won_was, count_was = before.get('won', 0.0), before.get('won_count', 0)

    _add_opp(client, h, pid, name='Partner win', amount=400_000, currency='USD',
             status='Closed Won', final_amount=360_000)

    leg = _leg(client.get('/api/dashboard/analytics').json()['currency_totals'], 'USD')
    assert leg['won'] == pytest.approx(won_was + 360_000), 'the final amount, as on the prospect side'
    assert leg['won_count'] == count_was + 1


@pytest.mark.parametrize('closed', ['Closed Lost', 'Closed Hold'])
def test_a_closed_partnership_deal_that_is_not_a_win_joins_neither_figure(client, login, csrf_headers, closed):
    pid, h = _partnership(client, login, csrf_headers, SUPER, f'Dashboard Bucket Partner {closed[-4:]}')
    before = _leg(client.get('/api/dashboard/analytics').json()['currency_totals'], 'USD') or {}

    extra = {'lost_reason': 'Lost to incumbent'} if closed == 'Closed Lost' else {'hold_reason': 'Budget', 'hold_review_date': '2027-01-10'}
    _add_opp(client, h, pid, name=f'Partner {closed}', amount=900_000, currency='USD', status=closed, **extra)

    leg = _leg(client.get('/api/dashboard/analytics').json()['currency_totals'], 'USD')
    assert leg['pipeline'] == pytest.approx(before.get('pipeline', 0.0)), 'not in play'
    assert leg['won'] == pytest.approx(before.get('won', 0.0)), 'and not a win'


# ------------------------------------------------------- the partnership share, and reconciliation

def test_partner_currency_totals_isolate_the_partnership_contribution(client, login, csrf_headers):
    pid, h = _partnership(client, login, csrf_headers, SUPER, 'Dashboard Bucket Partner C')
    _add_opp(client, h, pid, name='Partner share', amount=123_000, currency='EUR', status='Discussion')

    a = client.get('/api/dashboard/analytics').json()
    partner_eur = _leg(a['partner_currency_totals'], 'EUR')
    assert partner_eur is not None and partner_eur['pipeline'] >= 123_000
    # Every partnership leg must be within the combined figure for the same currency.
    for leg in a['partner_currency_totals']:
        combined = _leg(a['currency_totals'], leg['currency'])
        assert combined is not None, f"{leg['currency']} is in the partnership split but not the combined panel"
        assert combined['pipeline'] >= leg['pipeline'] - 1e-6
        assert combined['won'] >= leg['won'] - 1e-6
        assert combined['pipeline_count'] >= leg['pipeline_count']
        assert combined['won_count'] >= leg['won_count']


def test_the_combined_panel_is_exactly_prospects_plus_partnerships(client, login, csrf_headers):
    """The cross-check that replaces the old region-only reconcile.

    The region view is prospect-only by construction (region lives on the lead), so region legs plus
    the partnership split must account for exactly what the combined panel reports — no more, and
    nothing dropped. Computed independently of `currency_breakdown`, so it is a real check on it.
    """
    pid, h = _partnership(client, login, csrf_headers, SUPER, 'Dashboard Bucket Partner D')
    _add_opp(client, h, pid, name='Reconcile me', amount=88_000, currency='INR', status='Negotiation')

    a = client.get('/api/dashboard/analytics').json()

    from collections import defaultdict
    expected = defaultdict(lambda: {'pipeline': 0.0, 'won': 0.0})
    for region in a['region_currency']:
        for leg in region['currencies']:
            expected[leg['currency']]['pipeline'] += leg['pipeline']
            expected[leg['currency']]['won'] += leg['won']
    for leg in a['partner_currency_totals']:
        expected[leg['currency']]['pipeline'] += leg['pipeline']
        expected[leg['currency']]['won'] += leg['won']

    for r in a['currency_totals']:
        assert r['pipeline'] == pytest.approx(expected[r['currency']]['pipeline']), r['currency']
        assert r['won'] == pytest.approx(expected[r['currency']]['won']), r['currency']


# ------------------------------------------------------------------------------ scope and rates

def test_a_partnership_deal_follows_record_scope(client, login, csrf_headers):
    """A BD Executive must not pick up another executive's partnership deal through the dashboard."""
    pid, h = _partnership(client, login, csrf_headers, EXEC2, 'Dashboard Bucket Partner E')
    _add_opp(client, h, pid, name='Exec2 only partner deal', amount=777_000, currency='USD', status='Qualified')

    _as(client, login, EXEC2)
    owner_totals = client.get('/api/dashboard/analytics').json()
    assert any(r['pipeline'] >= 777_000 for r in owner_totals['partner_currency_totals'] if r['currency'] == 'USD'), \
        'the owner sees their own partnership deal'

    _as(client, login, EXEC1)
    other = client.get('/api/dashboard/analytics').json()
    other_usd = _leg(other['partner_currency_totals'], 'USD')
    assert other_usd is None or other_usd['pipeline'] < 777_000, \
        "another executive's partnership deal must not appear"

    _as(client, login, SUPER)
    everyone = _leg(client.get('/api/dashboard/analytics').json()['partner_currency_totals'], 'USD')
    assert everyone is not None and everyone['pipeline'] >= 777_000, 'all-business scope sees it'


def test_a_partnership_deal_in_an_unrated_currency_is_flagged_not_swallowed(client, login, csrf_headers):
    """It must reach the panel at its real amount, and name itself in `fx.missing_rates` — or the
    page's "combined total unavailable" message renders with a blank currency list."""
    pid, h = _partnership(client, login, csrf_headers, SUPER, 'Dashboard Bucket Partner F')
    _add_opp(client, h, pid, name='Unrated partner deal', amount=64_000, currency=UNRATED, status='Qualified')

    a = client.get('/api/dashboard/analytics').json()
    leg = _leg(a['currency_totals'], UNRATED)
    assert leg is not None and leg['pipeline'] >= 64_000, 'reported at its real amount'
    assert leg['convertible'] is False
    assert leg['pipeline_corporate'] is None
    assert UNRATED in a['fx']['missing_rates'], 'the page names the currency it cannot fold in'
    assert a['fx']['unconvertible_opportunities'] >= 1


def test_every_unconvertible_leg_in_the_panel_is_named_in_missing_rates(client, login, csrf_headers):
    """The invariant the UI depends on: `complete` is decided from `currency_totals`, but the message
    shown when it is false lists `fx.missing_rates`. A leg missing from that list would print an
    empty reason."""
    _as(client, login, SUPER)
    a = client.get('/api/dashboard/analytics').json()
    unconvertible = {r['currency'] for r in a['currency_totals'] if not r['convertible']}
    assert unconvertible <= set(a['fx']['missing_rates'])


# ------------------------------------------------------------------- uncounted names its bucket

def test_an_unrecognised_partnership_stage_is_tagged_so_the_link_opens_the_right_record(client, login, csrf_headers):
    """Prospect and partnership ids are independent sequences, so the dashboard cannot route by id
    alone — sending a partnership id to `pipeline?opp=` opens an unrelated prospect deal."""
    pid, h = _partnership(client, login, csrf_headers, SUPER, 'Dashboard Bucket Partner G')
    created = _add_opp(client, h, pid, name='Stage will be broken', amount=15_000, currency='USD', status='Qualified')
    opp_id = created['opportunity']['id']
    # A stage outside OPPORTUNITY_STAGES cannot be set through the API by design, so it is written
    # the only way it occurs in practice: straight into the row, as a bad import or migration leaves it.
    main.execute(main.update(main.partner_opportunities)
                 .where(main.partner_opportunities.c.id == opp_id).values(status='Qualified '))

    try:
        unrecognised = client.get('/api/dashboard/analytics').json()['uncounted']['unrecognised']
        mine = next((x for x in unrecognised if x['name'] == 'Stage will be broken'), None)
        assert mine is not None, 'a partnership deal with a bad stage must be named, not silently dropped'
        assert mine['bucket'] == 'partnership'
        assert mine['partnership_id'] == pid, 'carries the id Partnership 360 is addressed by'
        assert mine['status'] == 'Qualified ', 'the exact stored value, so a stray space is visible'
    finally:
        main.execute(main.update(main.partner_opportunities)
                     .where(main.partner_opportunities.c.id == opp_id).values(status='Qualified'))


def test_a_prospect_opportunity_is_still_tagged_as_a_prospect(client, login, csrf_headers):
    """The discriminator must not mislabel the prospect side, which has no partnership_id."""
    _as(client, login, SUPER)
    h = csrf_headers(client)
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    created = client.post(f'/api/leads/{lead_id}/opportunities',
                          json={'data': {'name': 'Prospect bad stage', 'amount': 9_000, 'currency': 'USD'}},
                          headers=h)
    assert created.status_code == 200, created.text
    opp_id = created.json()['opportunity']['id']
    main.execute(main.update(main.opportunities)
                 .where(main.opportunities.c.id == opp_id).values(status='qualified'))
    try:
        unrecognised = client.get('/api/dashboard/analytics').json()['uncounted']['unrecognised']
        mine = next(x for x in unrecognised if x['id'] == opp_id and x['bucket'] == 'prospect')
        assert mine['partnership_id'] is None
    finally:
        main.execute(main.update(main.opportunities)
                     .where(main.opportunities.c.id == opp_id).values(status='Qualified'))


def test_the_prospect_side_figures_are_untouched_by_the_change(client, login, csrf_headers):
    """Everything else on this page is prospect-only by design and must stay that way: the stage
    funnel, owner performance, ageing, the trend and the region view are all built from
    `opportunity_rows`, and a partnership deal must not leak into any of them."""
    # No re-login between the two reads: signing in again rotates the CSRF token and would
    # invalidate `h`. `_partnership` already left the session as SUPER.
    pid, h = _partnership(client, login, csrf_headers, SUPER, 'Dashboard Bucket Partner H')
    before = client.get('/api/dashboard/analytics').json()
    _add_opp(client, h, pid, name='Must not leak', amount=500_000, currency='USD', status='Qualified')
    after = client.get('/api/dashboard/analytics').json()

    for key in ('pipeline', 'ageing', 'owner_performance', 'quarter_trend', 'region_currency',
                'temperature', 'source_mix', 'region_mix', 'top_opportunities'):
        assert after[key] == before[key], f'{key} must stay prospect-only'
    # And the combined panel did move, so the comparison above is not vacuous.
    assert _leg(after['currency_totals'], 'USD')['pipeline'] > _leg(before['currency_totals'], 'USD')['pipeline']
