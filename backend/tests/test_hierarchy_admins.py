"""Super Admins see everything; each Admin sees only their own reporting tree and the roles their organisation created."""


def as_user(client, login, email):
    client.cookies.clear()
    return login(client, email)['user']


def test_super_admin_sees_all_work_admin_sees_only_own_tree(client, login):
    as_user(client, login, 'rreddy@jsanconsulting.com')
    assert len(client.get('/api/leads').json()) > 0
    assert len(client.get('/api/opportunities').json()) > 0
    # Chandrika's tree has no demo work; the demo data sits under another admin's hierarchy.
    as_user(client, login, 'chandrika@jsan.local')
    assert client.get('/api/leads').json() == []
    assert client.get('/api/opportunities').json() == []
    assert client.get('/api/dashboard/summary').json()['scope'] == 'My Team'


def test_admin_roles_and_users_stay_inside_their_organisation(client, login, csrf_headers):
    chandrika = as_user(client, login, 'chandrika@jsan.local'); h = csrf_headers(client)
    r = client.post('/api/admin/roles', headers=h, json={'data': {'name': 'Regional BD Lead', 'scope_type': 'team', 'permissions': ['LEAD_VIEW', 'LEAD_CREATE', 'LEAD_EDIT']}})
    assert r.status_code == 200, r.text
    role_id = r.json()['id']
    assert client.post('/api/admin/roles', headers=h, json={'data': {'name': 'Shadow Admin', 'scope_type': 'all'}}).status_code == 403
    assert client.post('/api/admin/roles', headers=h, json={'data': {'name': 'Peer Admin', 'scope_type': 'team', 'rank': 2}}).status_code == 403
    super_role = next(x for x in client.get('/api/admin/roles').json()['roles'] if x['name'] == 'Super Admin')
    assert super_role['editable'] is False and super_role['assignable'] is False
    assert client.put(f"/api/admin/roles/{super_role['id']}/permissions", headers=h, json={'data': {'permissions': []}}).status_code == 403

    r = client.post('/api/users', headers=h, json={'data': {'name': 'Chandrika Team Lead', 'email': 'c.lead@jsan.local', 'password': 'TempPass@2026', 'role': 'Regional BD Lead'}})
    assert r.status_code == 200, r.text
    team_lead = r.json(); assert team_lead['manager_id'] == chandrika['id']
    assert client.post('/api/users', headers=h, json={'data': {'name': 'X', 'email': 'x@jsan.local', 'password': 'TempPass@2026', 'role': 'Admin'}}).status_code == 403
    listed = {x['email'] for x in client.get('/api/users').json()}
    assert 'c.lead@jsan.local' in listed and 'vsatish@jsanconsulting.com' not in listed and 'director@jsan.local' not in listed

    # A peer admin cannot see or touch Chandrika's role, users or audit trail.
    as_user(client, login, 'vsatish@jsanconsulting.com'); h = csrf_headers(client)
    assert 'Regional BD Lead' not in {x['name'] for x in client.get('/api/admin/roles').json()['roles']}
    assert client.put(f'/api/admin/roles/{role_id}', headers=h, json={'data': {'permissions': []}}).status_code == 404
    assert client.put(f"/api/users/{team_lead['id']}", headers=h, json={'data': {'title': 'hijack'}}).status_code == 403
    assert all(x['user_id'] != chandrika['id'] for x in client.get('/api/audit-logs').json())

    # The Super Admin still sees and can manage everything.
    as_user(client, login, 'rreddy@jsanconsulting.com'); h = csrf_headers(client)
    assert 'Regional BD Lead' in {x['name'] for x in client.get('/api/admin/roles').json()['roles']}
    assert {'c.lead@jsan.local', 'vsatish@jsanconsulting.com'} <= {x['email'] for x in client.get('/api/users').json()}
