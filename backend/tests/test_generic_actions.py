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
    r = client.post('/api/generic-actions', json={'data': {'title': 'x', 'action_type': 'PPT', 'due_date': TOMORROW, 'assigned_to': exec2['id']}}, headers=csrf_headers(client))
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
    r = client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': TOMORROW, 'action_type': '  Client workshop prep  '}}, headers=h)
    assert r.status_code == 200 and r.json()['action_type'] == 'Client workshop prep'   # typed value kept, trimmed
    assert client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': TOMORROW, 'action_type': '   '}}, headers=h).status_code == 400
    assert client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': TOMORROW}}, headers=h).status_code == 400
    assert client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': TOMORROW, 'action_type': 'x' * 61}}, headers=h).status_code == 400
    assert client.post('/api/generic-actions', json={'data': {'title': 'Deck 60', 'due_date': TOMORROW, 'action_type': 'y' * 60}}, headers=h).json()['action_type'] == 'y' * 60
    upd = client.put(f"/api/generic-actions/{r.json()['id']}", json={'data': {'action_type': 'Board review deck'}}, headers=h)
    assert upd.status_code == 200 and upd.json()['action_type'] == 'Board review deck'
    assert client.put(f"/api/generic-actions/{r.json()['id']}", json={'data': {'action_type': ''}}, headers=h).status_code == 400
    assert client.put(f"/api/generic-actions/{r.json()['id']}", json={'data': {'priority': 'High'}}, headers=h).json()['action_type'] == 'Board review deck'  # untouched when not sent
    assert client.put(f"/api/generic-actions/{r.json()['id']}", json={'data': {'status': 'Nope'}}, headers=h).status_code == 400
    # Mutations need the CSRF header
    assert client.post('/api/generic-actions', json={'data': {'title': 'Deck', 'due_date': TOMORROW}}).status_code == 403
    assert client.delete(f"/api/generic-actions/{r.json()['id']}", headers=h).status_code == 200


def test_post_overdue_date_on_generic_and_prospect_actions(client, login, csrf_headers):
    ext = (date.today() + timedelta(days=5)).isoformat()
    _as(client, login, EXEC1)
    h = csrf_headers(client)

    # Generic action: stored on create, returned in the row and the list
    r = client.post('/api/generic-actions', json={'data': {'title': 'Reschedule deck', 'action_type': 'Presentation / PPT', 'due_date': YESTERDAY, 'post_overdue_date': ext}}, headers=h)
    assert r.status_code == 200, r.text
    g = r.json()
    assert g['post_overdue_date'] == ext
    assert _ids(client)[g['id']]['post_overdue_date'] == ext

    # Update it, then clear it with a blank value
    assert client.put(f"/api/generic-actions/{g['id']}", json={'data': {'post_overdue_date': TOMORROW}}, headers=h).json()['post_overdue_date'] == TOMORROW
    assert client.put(f"/api/generic-actions/{g['id']}", json={'data': {'post_overdue_date': ''}}, headers=h).json()['post_overdue_date'] is None
    # An invalid date is rejected, and omitting the field leaves it untouched
    assert client.put(f"/api/generic-actions/{g['id']}", json={'data': {'post_overdue_date': '99-99-9999'}}, headers=h).status_code == 400
    assert client.put(f"/api/generic-actions/{g['id']}", json={'data': {'priority': 'High'}}, headers=h).json()['post_overdue_date'] is None
    assert client.post('/api/generic-actions', json={'data': {'title': 'Bad', 'action_type': 'Other', 'due_date': TOMORROW, 'post_overdue_date': 'nope'}}, headers=h).status_code == 400
    assert client.delete(f"/api/generic-actions/{g['id']}", headers=h).status_code == 200

    # Prospect action: created against a visible lead with a post overdue date
    leads = client.get('/api/leads').json()
    assert leads, 'expected demo leads'
    lead = leads[0]
    r = client.post(f"/api/leads/{lead['id']}/actions", json={'data': {'description': 'Send revised timeline', 'due_date': YESTERDAY, 'post_overdue_date': ext}}, headers=h)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a['post_overdue_date'] == ext
    listed = {x['id']: x for x in client.get('/api/actions').json()}
    assert listed[a['id']]['post_overdue_date'] == ext
    # Update through the prospect action endpoint
    assert client.put(f"/api/actions/{a['id']}", json={'data': {'post_overdue_date': TOMORROW}}, headers=h).json()['post_overdue_date'] == TOMORROW
    assert client.put(f"/api/actions/{a['id']}", json={'data': {'post_overdue_date': 'bad'}}, headers=h).status_code == 400


def test_admin_reply_on_generic_and_prospect_actions(client, login, csrf_headers):
    # admin_reply is an admin-authored response to the assignee's remarks; a reply is never authored by the assignee
    _as(client, login, EXEC1)
    h = csrf_headers(client)

    # ── Generic action ──
    r = client.post('/api/generic-actions', json={'data': {'title': 'Pricing deck', 'action_type': 'Presentation / PPT', 'due_date': TOMORROW, 'remarks': 'Which template should I use?'}}, headers=h)
    assert r.status_code == 200, r.text
    g = r.json()
    assert not g.get('admin_reply')
    # The non-admin assignee cannot author a reply (silently ignored, not an error)
    assert not client.put(f"/api/generic-actions/{g['id']}", json={'data': {'admin_reply': 'self-reply'}}, headers=h).json().get('admin_reply')
    # A Super Admin adds the reply; it is trimmed and returned in the row and in the list
    _as(client, login, SUPER)
    r = client.put(f"/api/generic-actions/{g['id']}", json={'data': {'admin_reply': '  Use the standard pricing template  '}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    assert r.json()['admin_reply'] == 'Use the standard pricing template'
    assert _ids(client)[g['id']]['admin_reply'] == 'Use the standard pricing template'
    # The assignee now sees the reply on their own action
    _as(client, login, EXEC1)
    assert _ids(client)[g['id']]['admin_reply'] == 'Use the standard pricing template'
    # An admin can clear the reply with a blank value
    _as(client, login, SUPER)
    assert client.put(f"/api/generic-actions/{g['id']}", json={'data': {'admin_reply': ''}}, headers=csrf_headers(client)).json()['admin_reply'] is None

    # ── Prospect action ──
    _as(client, login, EXEC1)
    h = csrf_headers(client)
    leads = client.get('/api/leads').json()
    assert leads, 'expected demo leads'
    r = client.post(f"/api/leads/{leads[0]['id']}/actions", json={'data': {'description': 'Send revised timeline', 'due_date': TOMORROW, 'remarks': 'Please review'}}, headers=h)
    assert r.status_code == 200, r.text
    a = r.json()
    assert not a.get('admin_reply')
    # The assignee (non-admin) cannot author a reply even though they can edit their own action
    assert not client.put(f"/api/actions/{a['id']}", json={'data': {'admin_reply': 'nope'}}, headers=h).json().get('admin_reply')
    # A Super Admin replies; it flows out on the row and in the list the assignee sees
    _as(client, login, SUPER)
    r = client.put(f"/api/actions/{a['id']}", json={'data': {'admin_reply': ' Looks good, send it '}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    assert r.json()['admin_reply'] == 'Looks good, send it'
    assert {x['id']: x for x in client.get('/api/actions').json()}[a['id']]['admin_reply'] == 'Looks good, send it'
    _as(client, login, EXEC1)
    assert {x['id']: x for x in client.get('/api/actions').json()}[a['id']]['admin_reply'] == 'Looks good, send it'

    # Clean up both actions so the shared test database stays tidy
    _as(client, login, SUPER)
    hc = csrf_headers(client)
    assert client.delete(f"/api/generic-actions/{g['id']}", headers=hc).status_code == 200
    assert client.delete(f"/api/actions/{a['id']}", headers=hc).status_code == 200
