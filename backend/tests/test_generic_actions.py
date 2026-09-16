from datetime import date, timedelta

# Demo hierarchy: Admin -> Director -> BD Manager -> BD Lead -> BD Executive A / B
EXEC1, EXEC2, LEAD, ADMIN, SUPER = 'bd.exec1@jsan.local', 'bd.exec2@jsan.local', 'bd.lead@jsan.local', 'admin@jsan.local', 'superadmin@jsan.local'
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _ids(client, **params):
    r = client.get('/api/generic-actions', params=params)
    assert r.status_code == 200, r.text
    return {a['id']: a for a in r.json()['items']}


def test_generic_action_lifecycle_and_hierarchy(client, login, csrf_headers):
    exec2 = _as(client, login, EXEC2)
    exec1 = _as(client, login, EXEC1)
    listing = client.get('/api/generic-actions').json()
    assert 'Presentation / PPT' in listing['types'] and 'Summit / event preparation' in listing['types']
    assert listing['can_create'] is True

    r = client.post('/api/generic-actions', json={'data': {'title': 'Prepare summit PPT', 'action_type': 'Presentation / PPT', 'due_date': TOMORROW, 'priority': 'High', 'description': 'Deck for GIS summit'}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    own = r.json()
    assert own['assigned_to'] == exec1['id'] and own['status'] == 'Open' and own['can_edit'] and own['can_delete']

    # A self-scoped executive cannot assign work to a peer
    r = client.post('/api/generic-actions', json={'data': {'title': 'x', 'due_date': TOMORROW, 'assigned_to': exec2['id']}}, headers=csrf_headers(client))
    assert r.status_code == 403, r.text

    # Peers cannot see, edit or delete each other's generic actions
    _as(client, login, EXEC2)
    assert own['id'] not in _ids(client)
    assert client.put(f"/api/generic-actions/{own['id']}", json={'data': {'status': 'Completed'}}, headers=csrf_headers(client)).status_code == 404
    assert client.delete(f"/api/generic-actions/{own['id']}", headers=csrf_headers(client)).status_code == 404

    # The manager above can see and update it, but not delete it (not admin, not creator)
    lead = _as(client, login, LEAD)
    seen = _ids(client)
    assert own['id'] in seen and seen[own['id']]['can_edit'] and not seen[own['id']]['can_delete']
    r = client.put(f"/api/generic-actions/{own['id']}", json={'data': {'status': 'In Progress'}}, headers=csrf_headers(client))
    assert r.status_code == 200 and r.json()['status'] == 'In Progress'
    assert client.delete(f"/api/generic-actions/{own['id']}", headers=csrf_headers(client)).status_code == 403

    # Manager assigns work down; the assignee sees it, can complete it, cannot delete it
    r = client.post('/api/generic-actions', json={'data': {'title': 'Summit booth logistics', 'action_type': 'Summit / event preparation', 'due_date': YESTERDAY, 'assigned_to': exec1['id']}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    assigned = r.json()
    _as(client, login, EXEC1)
    mine = _ids(client, filter='my')
    assert assigned['id'] in mine and not mine[assigned['id']]['can_delete']
    assert assigned['id'] in _ids(client, filter='overdue')
    r = client.put(f"/api/generic-actions/{assigned['id']}", json={'data': {'status': 'Completed'}}, headers=csrf_headers(client))
    assert r.status_code == 200 and r.json()['completion_date'] == date.today().isoformat()
    assert assigned['id'] in _ids(client, filter='completed') and assigned['id'] not in _ids(client, filter='overdue')
    notes = client.get('/api/notifications').json()
    assert any(n.get('entity_type') == 'generic_action' and n.get('entity_id') == assigned['id'] for n in notes), notes

    # Admins up the chain can delete; Super Admin sees everything
    _as(client, login, SUPER)
    assert {own['id'], assigned['id']} <= set(_ids(client))
    _as(client, login, ADMIN)
    assert client.delete(f"/api/generic-actions/{assigned['id']}", headers=csrf_headers(client)).status_code == 200
    # Creator can delete their own
    _as(client, login, EXEC1)
    assert client.delete(f"/api/generic-actions/{own['id']}", headers=csrf_headers(client)).status_code == 200
    assert own['id'] not in _ids(client)


def test_generic_action_validation_and_csrf(client, login, csrf_headers):
    _as(client, login, EXEC1)
    h = csrf_headers(client)
    assert client.post('/api/generic-actions', json={'data': {'title': '', 'due_date': TOMORROW}}, headers=h).status_code == 400
    assert client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': '15-09-2026'}}, headers=h).status_code == 400
    assert client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': TOMORROW, 'priority': 'Urgent!!'}}, headers=h).status_code == 400
    r = client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': TOMORROW, 'action_type': 'Not a type'}}, headers=h)
    assert r.status_code == 200 and r.json()['action_type'] == 'Other'
    assert client.put(f"/api/generic-actions/{r.json()['id']}", json={'data': {'status': 'Nope'}}, headers=h).status_code == 400
    # Mutations need the CSRF header
    assert client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': TOMORROW}}).status_code == 403
    assert client.delete(f"/api/generic-actions/{r.json()['id']}", headers=h).status_code == 200
