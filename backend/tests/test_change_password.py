PW = 'PursuitNovaDemo@2026'


def change(client, h, current, new):
    return client.post('/api/auth/change-password', headers=h, json={'data': {'current_password': current, 'new_password': new}})


def test_user_can_change_own_password(client, login, csrf_headers):
    client.cookies.clear(); login(client, 'bd.lead@jsan.local'); h = csrf_headers(client)
    assert change(client, h, 'wrong-password', 'NewPass@2026').status_code == 400
    assert change(client, h, PW, 'short').status_code == 400
    assert change(client, h, PW, PW).status_code == 400
    assert change(client, h, PW, 'NewPass@2026').status_code == 200

    client.cookies.clear()
    assert client.post('/api/auth/login', json={'email': 'bd.lead@jsan.local', 'password': PW}).status_code == 401
    login(client, 'bd.lead@jsan.local', 'NewPass@2026'); h = csrf_headers(client)
    # Restore the shared demo password so later tests can still sign in as this user.
    assert change(client, h, 'NewPass@2026', PW).status_code == 200


def test_admin_reset_requires_minimum_length(client, login, csrf_headers):
    client.cookies.clear(); login(client, 'rreddy@jsanconsulting.com'); h = csrf_headers(client)
    target = next(x for x in client.get('/api/users').json() if x['email'] == 'bd.exec2@jsan.local')
    assert client.put(f"/api/users/{target['id']}", headers=h, json={'data': {'password': 'short'}}).status_code == 400
