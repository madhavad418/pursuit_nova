"""The Opportunity Pipeline board, grouped by region.

Region lives on the prospect, not the opportunity, so the board reaches it through the lead join
rather than keeping a second copy that could drift. The totals that matter are per region AND per
stage, rolled up over the whole filtered set: a region's column header must never be the sum of
whichever of its deals happened to land on the page being shown, which is the same rule the flat
column headers have followed since mixed-currency columns were being added raw.
"""
import pytest

from app.main import UNASSIGNED_REGION

SUPER, EXEC1 = 'superadmin@jsan.local', 'bd.exec1@jsan.local'


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _board(client, **params):
    q = '&'.join(f'{k}={v}' for k, v in params.items() if v != '')
    return client.get('/api/query/opportunities?page_size=100' + (f'&{q}' if q else '')).json()


def _rollup(by_region):
    """by_region folded back into a flat stage map, computed independently of the server's."""
    from collections import defaultdict
    acc = defaultdict(lambda: {'count': 0, 'value': 0.0, 'unrated': 0})
    for stages in by_region.values():
        for st, g in stages.items():
            acc[st]['count'] += g['count']; acc[st]['value'] += g['value']; acc[st]['unrated'] += g['unrated']
    return acc


# ----------------------------------------------------------------- region reaches the board

def test_every_opportunity_carries_its_prospects_region(client, login):
    _as(client, login, SUPER)
    b = _board(client)
    assert b['items'], 'the fixture has opportunities'
    assert all('region' in o for o in b['items']), 'the card needs a region to be grouped by'


def test_the_regions_list_covers_the_board_and_sorts_unassigned_last(client, login):
    _as(client, login, SUPER)
    b = _board(client)
    assert b['regions'], 'the filter needs a vocabulary'
    assert set(b['summary']['by_region']) <= set(b['regions']), 'every region on the board is offered'
    if UNASSIGNED_REGION in b['regions']:
        assert b['regions'][-1] == UNASSIGNED_REGION, 'a real region reads before the absence of one'


# ------------------------------------------------------------------ the totals have to agree

def test_region_stage_totals_sum_to_the_flat_stage_totals(client, login):
    """Two roll-ups of the same set, computed in the same pass — so they are a check on each other,
    and on the grouping not dropping or double-counting a deal."""
    _as(client, login, SUPER)
    b = _board(client)
    acc = _rollup(b['summary']['by_region'])
    assert set(acc) == set(b['summary']['by_status']), 'the same stages appear in both'
    for st, flat in b['summary']['by_status'].items():
        assert acc[st]['count'] == flat['count'], st
        assert acc[st]['value'] == pytest.approx(flat['value'], abs=0.05), st
        assert acc[st]['unrated'] == flat['unrated'], st


def test_region_totals_cover_the_whole_set_not_the_page(client, login):
    """The bug this design exists to prevent. Ask for one row per page and the roll-up must not move."""
    _as(client, login, SUPER)
    whole = _board(client)['summary']['by_region']
    sliced = client.get('/api/query/opportunities?page_size=1').json()
    assert len(sliced['items']) == 1, 'the page really is one row'
    assert sliced['summary']['by_region'] == whole, 'the roll-up is over the filtered set, not the page'


def test_a_region_total_counts_that_region_only(client, login):
    _as(client, login, SUPER)
    b = _board(client)
    for rg, stages in b['summary']['by_region'].items():
        in_region = [o for o in b['items'] if (str(o.get('region') or '').strip() or UNASSIGNED_REGION) == rg]
        assert sum(g['count'] for g in stages.values()) == len(in_region), rg
        for st, g in stages.items():
            assert g['count'] == len([o for o in in_region if o['status'] == st]), f'{rg}/{st}'


# ------------------------------------------------------------------------------- the filter

def test_the_region_filter_narrows_to_exactly_that_region(client, login):
    _as(client, login, SUPER)
    b = _board(client)
    regions = list(b['summary']['by_region'])
    if len(regions) < 2: pytest.skip('needs two regions to prove narrowing')
    pick = regions[0]
    only = _board(client, region=pick)
    assert list(only['summary']['by_region']) == [pick]
    assert {(str(o.get('region') or '').strip() or UNASSIGNED_REGION) for o in only['items']} == {pick}
    assert only['total'] < b['total'], 'it genuinely narrowed'


def test_the_unassigned_bucket_is_selectable(client, login, csrf_headers):
    """A prospect with no region is a real bucket on the board, so it has to be filterable too."""
    me = _as(client, login, SUPER)
    h = csrf_headers(client)
    # Created here rather than hunted for: every seeded prospect carries a region, so relying on the
    # fixture skipped this entirely and left the bucket people actually hit in real data untested.
    made = client.post('/api/leads/full', json={'data': {
        'company': {'name': 'No Region Prospect Ltd', 'vertical': 'Systems Integration'},
        'lead': {'owner_id': me['id']}, 'contacts': [],
    }}, headers=h)
    assert made.status_code == 200, made.text
    blank = made.json()['lead']['id']
    assert not (made.json()['lead'].get('region') or '').strip(), 'the prospect really has no region'
    r = client.post(f'/api/leads/{blank}/opportunities',
                    json={'data': {'name': 'No region deal', 'amount': 11_000, 'currency': 'USD', 'status': 'Qualified'}},
                    headers=h)
    assert r.status_code == 200, r.text

    only = _board(client, region=UNASSIGNED_REGION)
    assert only['total'] >= 1
    assert all(not (str(o.get('region') or '').strip()) for o in only['items'])
    assert 'No region deal' in {o['name'] for o in only['items']}
    assert list(only['summary']['by_region']) == [UNASSIGNED_REGION]


def test_an_unknown_region_returns_an_empty_board_not_an_error(client, login):
    _as(client, login, SUPER)
    b = _board(client, region='Atlantis')
    assert b['total'] == 0 and b['items'] == [] and b['summary']['by_region'] == {}


# -------------------------------------------------------------------------- scope and rates

def test_the_region_board_follows_record_scope(client, login):
    """A BD Executive's regions and counts are their own, not the whole business."""
    _as(client, login, SUPER)
    everyone = _board(client)
    _as(client, login, EXEC1)
    mine = _board(client)
    assert sum(g['count'] for s in mine['summary']['by_region'].values() for g in s.values()) <= \
           sum(g['count'] for s in everyone['summary']['by_region'].values() for g in s.values())
    assert set(mine['regions']) <= set(everyone['regions'])
    visible = {o['id'] for o in client.get('/api/opportunities').json()}
    assert {o['id'] for o in mine['items']} <= visible, 'the board shows nothing they could not open'


def test_a_deal_with_no_rate_is_counted_in_its_region_but_not_valued(client, login, csrf_headers):
    """Same rule as the flat columns: an unrated deal is named, never folded in as a zero amount."""
    _as(client, login, SUPER)
    h = csrf_headers(client)
    lead = next(l for l in client.get('/api/leads').json() if (l.get('region') or '').strip())
    before = _board(client, region=lead['region'])['summary']['by_region'].get(lead['region'], {}).get('Qualified', {'count': 0, 'value': 0.0, 'unrated': 0})
    r = client.post(f"/api/leads/{lead['id']}/opportunities",
                    json={'data': {'name': 'Region unrated deal', 'amount': 50_000, 'currency': 'XPF', 'status': 'Qualified'}},
                    headers=h)
    assert r.status_code == 200, r.text

    after = _board(client, region=lead['region'])['summary']['by_region'][lead['region']]['Qualified']
    assert after['count'] == before['count'] + 1, 'it is counted'
    assert after['unrated'] == before['unrated'] + 1, 'and flagged'
    assert after['value'] == pytest.approx(before['value']), 'but adds nothing to the figure'
