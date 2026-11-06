"""Editing an opportunity: what a role may change, and being told so before it tries.

Reported as "I am unable to edit the opportunities which are in pipeline". Probing every seeded role
against an open opportunity showed only one that fails, and two distinct reasons:

    role            edit remarks   edit amount                                close it
    Admin           OK             OK                                         OK
    Director        OK             OK                                         OK
    BD Manager      OK             OK                                         OK
    BD Lead         OK             OK                                         OK
    BD Executive    OK             OK                                         OK
    Presales Lead   OK             403 Field edit permission denied: amount   403 close permission

Neither is wrong as policy — a Presales Lead is deliberately kept off commercial figures. What was
wrong is that the Pipeline drawer offered every field to everyone and only revealed the truth on
submit, so a permission read as a broken app. These tests pin the two halves of the fix: the record
says what may be changed, and close permission gates the act of closing rather than the record.
"""
import pytest

SUPER, PRESALES, EXEC1 = 'superadmin@jsan.local', 'presales@jsan.local', 'bd.exec1@jsan.local'


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _open_opp(client):
    return next(o for o in client.get('/api/opportunities').json()
                if not str(o.get('status') or '').startswith('Closed '))


def _put(client, csrf_headers, opp_id, data):
    return client.put(f'/api/opportunities/{opp_id}', json={'data': data}, headers=csrf_headers(client))


# ------------------------------------------------- the record says what this user may change

def test_the_detail_payload_reports_what_this_role_may_edit(client, login, csrf_headers):
    _as(client, login, SUPER)
    opp_id = _open_opp(client)['id']
    p = client.get(f'/api/opportunities/{opp_id}').json()['permissions']
    assert p['can_edit'] is True and p['can_close'] is True
    assert p['readonly_fields'] == [] and p['hidden_fields'] == [], 'an admin is held back by nothing'


def test_a_presales_lead_is_told_which_fields_are_closed_to_them(client, login, csrf_headers):
    """The fields the seed deliberately keeps a Presales Lead off: the commercial ones."""
    _as(client, login, SUPER)
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    presales_id = next(x['id'] for x in client.get('/api/users').json() if x['email'] == PRESALES)
    created = client.post(f'/api/leads/{lead_id}/opportunities',
                          json={'data': {'name': 'Presales visible deal', 'amount': 120_000,
                                         'currency': 'USD', 'status': 'Qualified',
                                         'presales_owner_id': presales_id}},
                          headers=csrf_headers(client))
    assert created.status_code == 200, created.text
    opp_id = created.json()['opportunity']['id']

    _as(client, login, PRESALES)
    p = client.get(f'/api/opportunities/{opp_id}').json()['permissions']
    assert p['can_edit'] is True, 'they may edit the record, just not every field on it'
    assert p['can_close'] is False
    assert {'amount', 'currency', 'weighted_value'} <= set(p['readonly_fields'])
    assert 'final_amount' in p['hidden_fields']

    # And the claim is true: the named field is exactly the one the API refuses.
    assert _put(client, csrf_headers, opp_id, {'amount': 1}).status_code == 403
    assert _put(client, csrf_headers, opp_id, {'remarks': 'presales note'}).status_code == 200


# ------------------------------------- close permission gates closing, not the closed record

def _closed_opp_visible_to_presales(client, login, csrf_headers, name, status, **outcome):
    _as(client, login, SUPER)
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    presales_id = next(x['id'] for x in client.get('/api/users').json() if x['email'] == PRESALES)
    r = client.post(f'/api/leads/{lead_id}/opportunities',
                    json={'data': {'name': name, 'amount': 90_000, 'currency': 'USD',
                                   'status': status, 'presales_owner_id': presales_id, **outcome}},
                    headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    return r.json()['opportunity']['id']


def test_a_closed_deal_can_still_be_annotated_without_close_permission(client, login, csrf_headers):
    """The bug. The guard tested the status the edit would END on, so a deal that was already closed
    locked out anyone without close permission — they could not fix a typo in a remark on their own
    presales work, and the message blamed closing, which they were not attempting."""
    opp_id = _closed_opp_visible_to_presales(client, login, csrf_headers,
                                             'Closed and annotatable', 'Closed Lost', lost_reason='Price')
    _as(client, login, PRESALES)
    r = _put(client, csrf_headers, opp_id, {'remarks': 'adding context after the loss'})
    assert r.status_code == 200, r.text
    assert client.get(f'/api/opportunities/{opp_id}').json()['opportunity']['remarks'] == 'adding context after the loss'


def test_the_status_is_untouched_by_an_edit_that_does_not_mention_it(client, login, csrf_headers):
    """The other half: letting the edit through must not quietly re-close or re-date the deal."""
    opp_id = _closed_opp_visible_to_presales(client, login, csrf_headers,
                                             'Closed stays closed', 'Closed Lost', lost_reason='Timing')
    _as(client, login, SUPER)
    before = client.get(f'/api/opportunities/{opp_id}').json()['opportunity']
    _as(client, login, PRESALES)
    assert _put(client, csrf_headers, opp_id, {'next_follow_up_date': '2027-03-01'}).status_code == 200
    _as(client, login, SUPER)
    after = client.get(f'/api/opportunities/{opp_id}').json()['opportunity']
    assert after['status'] == before['status'] == 'Closed Lost'
    assert after['closed_at'] == before['closed_at'], 'the close date is not restamped by an unrelated edit'
    assert after['lost_reason'] == before['lost_reason']


def test_moving_between_two_closed_stages_still_needs_close_permission(client, login, csrf_headers):
    """Re-closing a deal differently is a closing decision, so it stays gated."""
    opp_id = _closed_opp_visible_to_presales(client, login, csrf_headers,
                                             'Closed to reclose', 'Closed Lost', lost_reason='Budget')
    _as(client, login, PRESALES)
    # Closed Lost -> Closed Hold, whose outcome fields this role may edit, so the only thing that can
    # refuse is the close guard itself. (Closed Won would be rejected a step earlier, by the field
    # permission on final_amount — a 403 that would not prove what this test is about.)
    r = _put(client, csrf_headers, opp_id, {'status': 'Closed Hold', 'hold_reason': 'Revisit', 'hold_review_date': '2027-04-01'})
    assert r.status_code == 403
    assert 'close' in r.json()['detail'].lower(), r.json()['detail']


def test_closing_an_open_deal_still_needs_close_permission(client, login, csrf_headers):
    """Unchanged, and the reason the guard exists at all."""
    opp_id = _closed_opp_visible_to_presales(client, login, csrf_headers,
                                             'Open then closed', 'Qualified')
    _as(client, login, PRESALES)
    r = _put(client, csrf_headers, opp_id, {'status': 'Closed Lost', 'lost_reason': 'Lost it'})
    assert r.status_code == 403


def test_a_role_with_close_permission_is_unaffected(client, login, csrf_headers):
    """None of this loosens anything for the roles that could already close."""
    opp_id = _closed_opp_visible_to_presales(client, login, csrf_headers,
                                             'Admin recloses freely', 'Closed Lost', lost_reason='Scope')
    _as(client, login, SUPER)
    assert _put(client, csrf_headers, opp_id, {'status': 'Closed Won', 'final_amount': 70_000}).status_code == 200
    assert client.get(f'/api/opportunities/{opp_id}').json()['opportunity']['status'] == 'Closed Won'


# --------------------------------------------------------------- the partnership side matches

def test_the_partnership_editor_follows_the_same_rule(client, login, csrf_headers):
    """Partnerships carry an identical update path, so the identical defect lived there too."""
    me = _as(client, login, SUPER)
    h = csrf_headers(client)
    presales_id = next(x['id'] for x in client.get('/api/users').json() if x['email'] == PRESALES)
    r = client.post('/api/partnerships/full', json={'data': {
        'company': {'name': 'Edit Rule Partner', 'vertical': 'Systems Integration'},
        'lead': {'owner_id': me['id']}, 'contacts': [],
    }}, headers=h)
    assert r.status_code == 200, r.text
    pid = r.json()['lead']['id']
    o = client.post(f'/api/partnerships/{pid}/opportunities',
                    json={'data': {'name': 'Closed partner deal', 'amount': 40_000, 'currency': 'USD',
                                   'status': 'Closed Lost', 'lost_reason': 'Partner withdrew',
                                   'presales_owner_id': presales_id}}, headers=h)
    assert o.status_code == 200, o.text
    opp_id = o.json()['opportunity']['id']

    _as(client, login, PRESALES)
    h2 = csrf_headers(client)
    annotate = client.put(f'/api/partner-opportunities/{opp_id}', json={'data': {'remarks': 'partner note'}}, headers=h2)
    assert annotate.status_code == 200, annotate.text
    reclose = client.put(f'/api/partner-opportunities/{opp_id}',
                         json={'data': {'status': 'Closed Won', 'final_amount': 10_000}}, headers=h2)
    assert reclose.status_code == 403, 're-closing is still a closing decision'
