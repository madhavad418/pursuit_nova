from datetime import date, timedelta

# Demo hierarchy: Admin -> Director -> BD Manager -> BD Lead -> BD Executive A / B
EXEC1, EXEC2, LEAD, ADMIN, SUPER, PRESALES = 'bd.exec1@jsan.local', 'bd.exec2@jsan.local', 'bd.lead@jsan.local', 'admin@jsan.local', 'superadmin@jsan.local', 'presales@jsan.local'
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


import pytest

# Named "zz" so it runs last; it also removes what it created so other modules never see these records.
@pytest.fixture(scope='module', autouse=True)
def _cleanup(client):
    yield
    client.cookies.clear()
    assert client.post('/api/auth/login', json={'email': SUPER, 'password': 'PursuitNovaDemo@2026'}).status_code == 200
    csrf_headers = lambda c: {'X-CSRF-Token': c.cookies.get('pursuitnova_csrf')}
    for lead in client.get('/api/leads').json():
        if lead['company_name'] in {'Multi Owner Telco', 'Shared Ownership Corp', 'Hierarchy Visibility Inc', 'Admin Only Owners Ltd', 'Reassign Corp', 'Action Team Co', 'No Extra Assignees Co', 'Classic Single Owner Co'}:
            client.delete(f"/api/leads/{lead['id']}", headers=csrf_headers(client))
    for a in client.get('/api/generic-actions').json()['items']:
        if a['title'] in {'Solo', 'Summit deck'}:
            client.delete(f"/api/generic-actions/{a['id']}", headers=csrf_headers(client))


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _uid(client, login, email):
    return _as(client, login, email)['id']


def _new_prospect(client, csrf_headers, name, **lead):
    r = client.post('/api/leads/full', json={'data': {'company': {'name': name, 'vertical': 'Telecommunications'}, 'lead': lead}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    return r.json()['lead']


def _detail(client, lead_id):
    r = client.get(f'/api/leads/{lead_id}')
    assert r.status_code == 200, r.text
    return r.json()


def _put_lead(client, csrf_headers, lead_id, data):
    return client.put(f'/api/leads/{lead_id}', json={'data': data}, headers=csrf_headers(client))


def test_admin_adds_and_removes_multiple_owners_on_a_prospect(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1); e2 = _uid(client, login, EXEC2); lead_u = _uid(client, login, LEAD); pre = _uid(client, login, PRESALES)
    _as(client, login, SUPER)
    lead = _new_prospect(client, csrf_headers, 'Multi Owner Telco', owner_id=e1, co_owner_ids=[e2, lead_u, pre, e1, e2])
    # duplicates and the primary owner are dropped; order is kept
    assert [p['id'] for p in lead['co_owners']] == [e2, lead_u, pre]
    d = _detail(client, lead['id'])
    assert d['permissions']['can_manage_owners'] is True
    assert d['lead']['owner_id'] == e1 and [p['id'] for p in d['lead']['co_owners']] == [e2, lead_u, pre]

    # more than two extras, then shrink to one
    r = _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': [pre]})
    assert r.status_code == 200, r.text
    assert [p['id'] for p in r.json()['lead']['co_owners']] == [pre]
    # clearing all extras
    r = _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': []})
    assert r.status_code == 200 and r.json()['lead']['co_owners'] == []


def test_co_owner_sees_and_edits_the_prospect_and_it_is_listed(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1); e2 = _uid(client, login, EXEC2)
    _as(client, login, SUPER)
    lead = _new_prospect(client, csrf_headers, 'Shared Ownership Corp', owner_id=e1)
    # peer EXEC2 cannot see it yet
    _as(client, login, EXEC2)
    assert client.get(f"/api/leads/{lead['id']}").status_code == 403
    assert lead['id'] not in [x['id'] for x in client.get('/api/query/leads', params={'q': 'Shared Ownership'}).json()['items']]

    _as(client, login, SUPER)
    assert _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': [e2]}).status_code == 200

    _as(client, login, EXEC2)
    d = _detail(client, lead['id'])
    assert d['permissions']['can_edit'] is True and d['permissions']['can_manage_owners'] is False
    q = client.get('/api/query/leads', params={'q': 'Shared Ownership'}).json()
    row = next(x for x in q['items'] if x['id'] == lead['id'])
    assert row['can_edit'] is True and [p['id'] for p in row['co_owners']] == [e2]
    assert lead['id'] in [x['id'] for x in client.get('/api/leads').json()]
    # owner filter matches co-owners as well as the primary owner, and the facet lists them
    by_owner = client.get('/api/query/leads', params={'owner_id': e2}).json()
    assert lead['id'] in [x['id'] for x in by_owner['items']]
    assert e2 in [o['id'] for o in by_owner['facets']['owners']]
    # a co-owner can edit prospect fields
    assert _put_lead(client, csrf_headers, lead['id'], {'remarks': 'edited by co-owner'}).status_code == 200

    # removing them takes the access away again
    _as(client, login, SUPER)
    assert _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': []}).status_code == 200
    _as(client, login, EXEC2)
    assert client.get(f"/api/leads/{lead['id']}").status_code == 403


def test_managers_of_a_co_owner_see_the_prospect(client, login, csrf_headers):
    e2 = _uid(client, login, EXEC2)
    admin = _as(client, login, SUPER)
    lead = _new_prospect(client, csrf_headers, 'Hierarchy Visibility Inc', owner_id=admin['id'], co_owner_ids=[e2])
    _as(client, login, LEAD)  # BD Lead manages EXEC2
    assert client.get(f"/api/leads/{lead['id']}").status_code == 200


def test_only_admins_can_change_additional_owners(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1); e2 = _uid(client, login, EXEC2)
    _as(client, login, SUPER)
    lead = _new_prospect(client, csrf_headers, 'Admin Only Owners Ltd', owner_id=e1)
    # a non-admin creating a prospect with co-owners is refused, and nothing is created
    _as(client, login, EXEC1)
    r = client.post('/api/leads/full', json={'data': {'company': {'name': 'Should Not Exist Ltd', 'vertical': 'Telecommunications'}, 'lead': {'co_owner_ids': [e2]}}}, headers=csrf_headers(client))
    assert r.status_code == 403, r.text
    assert 'Should Not Exist' not in ' '.join(x['company_name'] for x in client.get('/api/leads').json())
    # ...and cannot edit them, but a no-op (empty list on a prospect with none) is harmless
    assert _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': [e2]}).status_code == 403
    assert _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': []}).status_code == 200
    # ordinary single-owner edits keep working for the owner
    assert _put_lead(client, csrf_headers, lead['id'], {'remarks': 'plain edit'}).status_code == 200


def test_owner_reassignment_and_bad_input(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1); e2 = _uid(client, login, EXEC2)
    _as(client, login, SUPER)
    lead = _new_prospect(client, csrf_headers, 'Reassign Corp', owner_id=e1, co_owner_ids=[e2])
    # promoting the co-owner to primary removes them from the extras (never listed twice)
    r = _put_lead(client, csrf_headers, lead['id'], {'owner_id': e2})
    assert r.status_code == 200, r.text
    assert r.json()['lead']['owner_id'] == e2 and r.json()['lead']['co_owners'] == []
    # promoting while re-sending the list keeps the old primary as an extra
    r = _put_lead(client, csrf_headers, lead['id'], {'owner_id': e1, 'co_owner_ids': [e2]})
    assert r.status_code == 200 and r.json()['lead']['owner_id'] == e1 and [p['id'] for p in r.json()['lead']['co_owners']] == [e2]
    # invalid input is rejected without changing anything
    assert _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': 'nope'}).status_code == 400
    assert _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': ['x']}).status_code == 400
    assert _put_lead(client, csrf_headers, lead['id'], {'co_owner_ids': [999999]}).status_code == 403
    assert [p['id'] for p in _detail(client, lead['id'])['lead']['co_owners']] == [e2]


def test_multiple_assignees_on_prospect_actions(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1); e2 = _uid(client, login, EXEC2); lead_u = _uid(client, login, LEAD)
    _as(client, login, SUPER)
    lead = _new_prospect(client, csrf_headers, 'Action Team Co', owner_id=e1)
    r = client.post(f"/api/leads/{lead['id']}/actions", json={'data': {'description': 'Send proposal', 'due_date': TOMORROW, 'assigned_to': e1, 'co_assignee_ids': [e2, lead_u, e1]}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    act = r.json()
    assert [p['id'] for p in act['co_assignees']] == [e2, lead_u]

    # each additional assignee is notified
    for email, uid in ((EXEC2, e2), (LEAD, lead_u)):
        _as(client, login, email)
        notes = client.get('/api/notifications').json()
        assert any(n.get('entity_type') == 'action' and n.get('entity_id') == act['id'] for n in notes), (email, notes)

    # EXEC2 (co-assignee, not a prospect owner) sees it under "My actions" with the full team, and may complete it
    _as(client, login, EXEC2)
    mine = {a['id']: a for a in client.get('/api/actions', params={'filter': 'my'}).json()}
    assert act['id'] in mine and [p['id'] for p in mine[act['id']]['co_assignees']] == [e2, lead_u]
    r = client.put(f"/api/actions/{act['id']}", json={'data': {'status': 'In Progress'}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    # ...but cannot change who is on it
    r = client.put(f"/api/actions/{act['id']}", json={'data': {'co_assignee_ids': []}}, headers=csrf_headers(client))
    assert r.status_code == 403, r.text

    # the prospect page shows the team on each action
    _as(client, login, SUPER)
    d = _detail(client, lead['id'])
    shown = next(a for a in d['actions'] if a['id'] == act['id'])
    assert [p['id'] for p in shown['co_assignees']] == [e2, lead_u]

    # admin edits the team: shrink, then reassign the primary to a current extra (no duplicate)
    r = client.put(f"/api/actions/{act['id']}", json={'data': {'co_assignee_ids': [e2]}}, headers=csrf_headers(client))
    assert r.status_code == 200 and [p['id'] for p in r.json()['co_assignees']] == [e2]
    r = client.put(f"/api/actions/{act['id']}", json={'data': {'assigned_to': e2}}, headers=csrf_headers(client))
    assert r.status_code == 200 and r.json()['assigned_to'] == e2 and r.json()['co_assignees'] == []

    # removed people lose "My actions"
    _as(client, login, LEAD)
    assert act['id'] not in [a['id'] for a in client.get('/api/actions', params={'filter': 'my'}).json()]


def test_non_admin_cannot_add_assignees_when_creating_an_action(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1); e2 = _uid(client, login, EXEC2)
    _as(client, login, SUPER)
    lead = _new_prospect(client, csrf_headers, 'No Extra Assignees Co', owner_id=e1)
    _as(client, login, EXEC1)
    r = client.post(f"/api/leads/{lead['id']}/actions", json={'data': {'description': 'x', 'due_date': TOMORROW, 'co_assignee_ids': [e2]}}, headers=csrf_headers(client))
    assert r.status_code == 403, r.text
    r = client.post(f"/api/leads/{lead['id']}/actions", json={'data': {'description': 'plain', 'due_date': TOMORROW}}, headers=csrf_headers(client))
    assert r.status_code == 200 and r.json()['co_assignees'] == []


def test_multiple_assignees_on_generic_actions(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1); e2 = _uid(client, login, EXEC2); lead_u = _uid(client, login, LEAD)
    _as(client, login, SUPER)
    r = client.post('/api/generic-actions', json={'data': {'title': 'Summit deck', 'action_type': 'PPT', 'due_date': TOMORROW, 'assigned_to': e1, 'co_assignee_ids': [e2, lead_u]}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    act = r.json()
    assert [p['id'] for p in act['co_assignees']] == [e2, lead_u]

    # a co-assignee (a peer of the primary) sees, filters and edits it; another peer-only user would not
    _as(client, login, EXEC2)
    items = {a['id']: a for a in client.get('/api/generic-actions').json()['items']}
    assert act['id'] in items and items[act['id']]['can_edit'] is True
    assert act['id'] in {a['id'] for a in client.get('/api/generic-actions', params={'filter': 'my'}).json()['items']}
    r = client.put(f"/api/generic-actions/{act['id']}", json={'data': {'status': 'In Progress'}}, headers=csrf_headers(client))
    assert r.status_code == 200 and [p['id'] for p in r.json()['co_assignees']] == [e2, lead_u]
    assert client.put(f"/api/generic-actions/{act['id']}", json={'data': {'co_assignee_ids': []}}, headers=csrf_headers(client)).status_code == 403
    # notified
    notes = client.get('/api/notifications').json()
    assert any(n.get('entity_type') == 'generic_action' and n.get('entity_id') == act['id'] for n in notes)

    # admin edits the team; removed people lose access
    _as(client, login, SUPER)
    r = client.put(f"/api/generic-actions/{act['id']}", json={'data': {'co_assignee_ids': [lead_u]}}, headers=csrf_headers(client))
    assert r.status_code == 200 and [p['id'] for p in r.json()['co_assignees']] == [lead_u]
    _as(client, login, EXEC2)
    assert act['id'] not in {a['id'] for a in client.get('/api/generic-actions').json()['items']}

    # deleting the action removes its people rows
    _as(client, login, SUPER)
    assert client.delete(f"/api/generic-actions/{act['id']}", headers=csrf_headers(client)).status_code == 200
    from app.db import engine, record_people
    from sqlalchemy import select, func
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(record_people).where(record_people.c.entity_type == 'generic_action', record_people.c.entity_id == act['id'])).scalar() == 0


def test_deleting_a_prospect_removes_its_people_rows(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1); e2 = _uid(client, login, EXEC2)
    _as(client, login, SUPER)
    lead = _new_prospect(client, csrf_headers, 'Delete Cleanup Co', owner_id=e1, co_owner_ids=[e2])
    r = client.post(f"/api/leads/{lead['id']}/actions", json={'data': {'description': 'a', 'due_date': TOMORROW, 'assigned_to': e1, 'co_assignee_ids': [e2]}}, headers=csrf_headers(client))
    act_id = r.json()['id']
    assert client.delete(f"/api/leads/{lead['id']}", headers=csrf_headers(client)).status_code == 200
    from app.db import engine, record_people
    from sqlalchemy import select, func, and_, or_
    with engine.connect() as c:
        n = c.execute(select(func.count()).select_from(record_people).where(or_(and_(record_people.c.entity_type == 'lead', record_people.c.entity_id == lead['id']), and_(record_people.c.entity_type == 'action', record_people.c.entity_id == act_id)))).scalar()
    assert n == 0


def test_existing_single_owner_flows_are_unchanged(client, login, csrf_headers):
    e1 = _uid(client, login, EXEC1)
    _as(client, login, EXEC1)
    lead = _new_prospect(client, csrf_headers, 'Classic Single Owner Co')
    assert lead['owner_id'] == e1 and lead['co_owners'] == []
    rows_ = client.get('/api/query/leads', params={'q': 'Classic Single'}).json()['items']
    assert rows_ and rows_[0]['co_owners'] == [] and rows_[0]['can_edit'] is True
    r = client.post('/api/generic-actions', json={'data': {'title': 'Solo', 'action_type': 'Other', 'due_date': TOMORROW}}, headers=csrf_headers(client))
    assert r.status_code == 200 and r.json()['co_assignees'] == []
