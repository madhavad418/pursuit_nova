"""The dashboard's "Key supports" counts: work waiting on a person today.

The list of attention items is capped so the payload stays small. The counts are not: they are taken
over the whole set before capping, because a tile reading 40 when there are 60 is the figure someone
plans their day on, and a silently truncated one is simply wrong. These tests pin that separation,
and that the counts follow record scope like everything else.
"""
import pytest

from app import main

SUPER, EXEC1 = 'superadmin@jsan.local', 'bd.exec1@jsan.local'
KINDS = {'Overdue Action': 'overdue_actions', 'Follow-up Overdue': 'followups_overdue',
         'Closure Approaching': 'closing_soon'}


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _attention(client):
    r = client.get('/api/dashboard/attention')
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------------------- the shape

def test_attention_reports_items_a_total_and_counts_per_kind(client, login):
    _as(client, login, SUPER)
    a = _attention(client)
    assert set(a) == {'items', 'total', 'shown', 'counts'}
    assert set(a['counts']) == set(KINDS.values())
    assert all(isinstance(v, int) and v >= 0 for v in a['counts'].values())
    assert a['shown'] == len(a['items'])


def test_the_counts_account_for_every_item(client, login):
    _as(client, login, SUPER)
    a = _attention(client)
    assert sum(a['counts'].values()) == a['total'], 'every item falls into exactly one counted kind'


def test_each_count_matches_the_items_of_that_kind_while_nothing_is_capped(client, login):
    """While the list is whole, the counts and the list must agree exactly — which is what makes the
    capped case below a statement about the cap rather than about the counting."""
    _as(client, login, SUPER)
    a = _attention(client)
    if a['total'] > main.ATTENTION_LIMIT: pytest.skip('fixture already exceeds the cap')
    from collections import Counter
    seen = Counter(i['kind'] for i in a['items'])
    for kind, key in KINDS.items():
        assert seen.get(kind, 0) == a['counts'][key], kind


# ------------------------------------------------------------------- the cap, which is the point

def test_the_counts_are_whole_even_when_the_list_is_capped(client, login, csrf_headers, monkeypatch):
    """The reason the counts exist at all. Squeeze the cap to one and the tile figures must not move."""
    _as(client, login, SUPER)
    h = csrf_headers(client)
    # Created here rather than hoped for: the fixture can hold a single attention item, and a cap of
    # one over a set of one proves nothing about capping.
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    for n in range(3):
        r = client.post(f'/api/leads/{lead_id}/actions',
                        json={'data': {'description': f'Cap probe {n}', 'due_date': '2020-01-01'}}, headers=h)
        assert r.status_code == 200, r.text
    whole = _attention(client)
    assert whole['total'] >= 2, 'need more than one item for the cap to bite'

    monkeypatch.setattr(main, 'ATTENTION_LIMIT', 1)
    capped = _attention(client)
    assert len(capped['items']) == 1 and capped['shown'] == 1, 'the list really was capped'
    assert capped['total'] == whole['total'], 'the total is the whole set, not the slice'
    assert capped['counts'] == whole['counts'], 'and so is every per-kind count'


def test_a_capped_list_still_says_how_much_it_is_showing(client, login, monkeypatch):
    _as(client, login, SUPER)
    monkeypatch.setattr(main, 'ATTENTION_LIMIT', 2)
    a = _attention(client)
    assert a['shown'] <= 2 and a['shown'] <= a['total']
    if a['total'] > 2: assert a['shown'] < a['total'], 'the gap between shown and total is visible'


# ------------------------------------------------------------------------------ what is counted

def test_an_overdue_action_is_counted(client, login, csrf_headers):
    _as(client, login, SUPER)
    h = csrf_headers(client)
    before = _attention(client)['counts']['overdue_actions']
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    r = client.post(f'/api/leads/{lead_id}/actions',
                    json={'data': {'description': 'Attention probe action', 'due_date': '2020-01-01'}},
                    headers=h)
    assert r.status_code == 200, r.text
    assert _attention(client)['counts']['overdue_actions'] == before + 1


def test_an_overdue_follow_up_on_an_open_deal_is_counted(client, login, csrf_headers):
    _as(client, login, SUPER)
    h = csrf_headers(client)
    before = _attention(client)['counts']['followups_overdue']
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    r = client.post(f'/api/leads/{lead_id}/opportunities',
                    json={'data': {'name': 'Attention probe deal', 'amount': 1000, 'currency': 'USD',
                                   'status': 'Qualified', 'next_follow_up_date': '2020-01-01'}},
                    headers=h)
    assert r.status_code == 200, r.text
    assert _attention(client)['counts']['followups_overdue'] == before + 1


def test_a_closed_deal_is_never_chased(client, login, csrf_headers):
    """Closed business needs no follow-up, so it belongs in no attention count."""
    _as(client, login, SUPER)
    h = csrf_headers(client)
    before = _attention(client)['counts']
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    r = client.post(f'/api/leads/{lead_id}/opportunities',
                    json={'data': {'name': 'Attention closed deal', 'amount': 1000, 'currency': 'USD',
                                   'status': 'Closed Lost', 'lost_reason': 'Gone',
                                   'next_follow_up_date': '2020-01-01',
                                   'expected_close_date': main.today_str()}},
                    headers=h)
    assert r.status_code == 200, r.text
    after = _attention(client)['counts']
    assert after['followups_overdue'] == before['followups_overdue']
    assert after['closing_soon'] == before['closing_soon']


def test_a_closure_inside_a_week_is_counted_and_one_beyond_it_is_not(client, login, csrf_headers):
    from datetime import date, timedelta
    _as(client, login, SUPER)
    h = csrf_headers(client)
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    before = _attention(client)['counts']['closing_soon']

    soon = (date.today() + timedelta(days=3)).isoformat()
    far = (date.today() + timedelta(days=30)).isoformat()
    for name, when in (('Attention closing soon', soon), ('Attention closing later', far)):
        r = client.post(f'/api/leads/{lead_id}/opportunities',
                        json={'data': {'name': name, 'amount': 1000, 'currency': 'USD',
                                       'status': 'Qualified', 'expected_close_date': when}},
                        headers=h)
        assert r.status_code == 200, r.text
    assert _attention(client)['counts']['closing_soon'] == before + 1, 'only the near one counts'


# ------------------------------------------------------------------------------------- scope

def test_the_counts_follow_record_scope(client, login):
    _as(client, login, SUPER)
    everyone = _attention(client)
    _as(client, login, EXEC1)
    mine = _attention(client)
    assert mine['total'] <= everyone['total']
    for key in KINDS.values():
        assert mine['counts'][key] <= everyone['counts'][key], key


def test_attention_needs_a_session(client):
    client.cookies.clear()
    assert client.get('/api/dashboard/attention').status_code == 401
