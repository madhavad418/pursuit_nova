EXEC1, EXEC2, LEAD, SUPER = 'bd.exec1@jsan.local', 'bd.exec2@jsan.local', 'bd.lead@jsan.local', 'superadmin@jsan.local'


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _own_lead(client, user):
    items = client.get('/api/query/leads', params={'page_size': 100}).json()['items']
    lead = next(i for i in items if i['owner_id'] == user['id'])
    return client.get(f"/api/leads/{lead['id']}").json()


def test_owner_can_edit_company_details_after_creation(client, login, csrf_headers):
    me = _as(client, login, EXEC1)
    detail = _own_lead(client, me)
    perms = detail['permissions']
    assert perms['can_edit'] and perms['can_edit_company'] and perms['can_edit_contacts'] and not perms['can_delete']
    cid = detail['lead']['company_id']
    h = csrf_headers(client)

    # The reported case: add the company LinkedIn page later
    r = client.put(f'/api/companies/{cid}', json={'data': {'linkedin_url': 'linkedin.com/company/northstar-mobility', 'website': 'northstar.example', 'external_url': ''}}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()['linkedin_url'] == 'https://linkedin.com/company/northstar-mobility'
    assert r.json()['website'] == 'https://northstar.example' and r.json()['domain'] == 'northstar.example' and r.json()['external_url'] is None
    refreshed = client.get(f"/api/leads/{detail['lead']['id']}").json()['lead']
    assert refreshed['linkedin_url'] == 'https://linkedin.com/company/northstar-mobility'

    # Name and vertical can change, but cannot be blank or collide with another company
    original_name = detail['lead']['company_name']
    assert client.put(f'/api/companies/{cid}', json={'data': {'name': '   '}}, headers=h).status_code == 400
    assert client.put(f'/api/companies/{cid}', json={'data': {'vertical': ''}}, headers=h).status_code == 400
    assert client.put(f'/api/companies/{cid}', json={'data': {'linkedin_url': 'not a link'}}, headers=h).status_code == 400
    other = next(i for i in client.get('/api/query/companies', params={'page_size': 50}).json()['items'] if i['id'] != cid)
    assert client.put(f'/api/companies/{cid}', json={'data': {'name': other['name'].upper()}}, headers=h).status_code == 409
    r = client.put(f'/api/companies/{cid}', json={'data': {'name': original_name + ' Group', 'vertical': 'Automotive'}}, headers=h)
    assert r.status_code == 200 and r.json()['name'] == original_name + ' Group'
    assert client.put(f'/api/companies/{cid}', json={'data': {'name': original_name}}, headers=h).status_code == 200


def test_prospect_fields_are_validated(client, login, csrf_headers):
    me = _as(client, login, EXEC1)
    lid = _own_lead(client, me)['lead']['id']
    h = csrf_headers(client)
    ok = client.put(f'/api/leads/{lid}', json={'data': {'source': 'Referral', 'source_detail': ' Met at GIS summit ', 'status': 'Engaged', 'temperature': 'Hot', 'city': 'Austin', 'next_follow_up': '2026-10-01'}}, headers=h)
    assert ok.status_code == 200, ok.text
    lead = ok.json()['lead']
    assert (lead['source'], lead['source_detail'], lead['status'], lead['temperature'], lead['city'], lead['next_follow_up']) == ('Referral', 'Met at GIS summit', 'Engaged', 'Hot', 'Austin', '2026-10-01')
    assert client.put(f'/api/leads/{lid}', json={'data': {'next_follow_up': ''}}, headers=h).json()['lead']['next_follow_up'] is None
    assert client.put(f'/api/leads/{lid}', json={'data': {'status': 'Maybe'}}, headers=h).status_code == 400
    assert client.put(f'/api/leads/{lid}', json={'data': {'temperature': 'Lukewarm'}}, headers=h).status_code == 400
    assert client.put(f'/api/leads/{lid}', json={'data': {'next_follow_up': '31/12/2026'}}, headers=h).status_code == 400
    assert client.put(f'/api/leads/{lid}', json={'data': {'source': ''}}, headers=h).status_code == 400


def test_contacts_can_be_edited_and_removed(client, login, csrf_headers):
    me = _as(client, login, EXEC1)
    detail = _own_lead(client, me)
    cid, lid = detail['lead']['company_id'], detail['lead']['id']
    h = csrf_headers(client)
    a = client.post(f'/api/companies/{cid}/contacts', json={'data': {'name': 'Priya Nair', 'email': 'priya@northstar.example'}}, headers=h).json()
    b = client.post(f'/api/companies/{cid}/contacts', json={'data': {'name': 'Tom Hale', 'email': 'tom@northstar.example'}}, headers=h).json()

    r = client.put(f"/api/contacts/{a['id']}", json={'data': {'designation': 'Head of GIS', 'phone': '+1 512 555 0100', 'linkedin_url': 'www.linkedin.com/in/priya-nair', 'is_primary': True}}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()['linkedin_url'] == 'https://www.linkedin.com/in/priya-nair' and r.json()['designation'] == 'Head of GIS'
    contacts = client.get(f'/api/leads/{lid}').json()['contacts']
    assert [c['name'] for c in contacts if c['is_primary']] == ['Priya Nair']  # only one primary

    assert client.put(f"/api/contacts/{b['id']}", json={'data': {'name': ''}}, headers=h).status_code == 400
    assert client.put(f"/api/contacts/{b['id']}", json={'data': {'email': 'PRIYA@northstar.example'}}, headers=h).status_code == 409
    assert client.put(f"/api/contacts/{b['id']}", json={'data': {'email': 'not-an-email'}}, headers=h).status_code == 400

    assert client.put(f"/api/contacts/{b['id']}", json={'data': {'active': False}}, headers=h).status_code == 200
    assert 'Tom Hale' not in [c['name'] for c in client.get(f'/api/leads/{lid}').json()['contacts']]


def test_anyone_who_can_open_a_prospect_can_edit_all_of_it(client, login, csrf_headers):
    owner = _as(client, login, EXEC1)
    detail = _own_lead(client, owner)
    lid, cid = detail['lead']['id'], detail['lead']['company_id']
    contact_id = client.post(f'/api/companies/{cid}/contacts', json={'data': {'name': 'Edit Test Contact', 'email': 'edit.test@northstar.example'}}, headers=csrf_headers(client)).json()['id']

    # Someone who cannot see the prospect still cannot touch it
    _as(client, login, EXEC2)
    h = csrf_headers(client)
    assert lid not in {i['id'] for i in client.get('/api/query/leads', params={'page_size': 100}).json()['items']}
    assert client.put(f'/api/leads/{lid}', json={'data': {'remarks': 'x'}}, headers=h).status_code == 403
    assert client.put(f'/api/companies/{cid}', json={'data': {'linkedin_url': 'https://linkedin.com/company/x'}}, headers=h).status_code == 403
    assert client.put(f'/api/contacts/{contact_id}', json={'data': {'phone': '1'}}, headers=h).status_code == 403

    # Anyone who can open it can edit every part: prospect, owner, company and contacts
    _as(client, login, LEAD)
    items = {i['id']: i for i in client.get('/api/query/leads', params={'page_size': 100}).json()['items']}
    assert items and all(i['can_edit'] for i in items.values())
    perms = client.get(f'/api/leads/{lid}').json()['permissions']
    assert perms['can_edit'] and perms['can_edit_company'] and perms['can_edit_contacts'] and perms['can_reassign'] and not perms['can_delete']
    h = csrf_headers(client)
    assert client.put(f'/api/companies/{cid}', json={'data': {'remarks': 'Strategic account'}}, headers=h).status_code == 200
    assert client.put(f'/api/contacts/{contact_id}', json={'data': {'phone': '+1 555 0101'}}, headers=h).status_code == 200
    assert client.put(f'/api/leads/{lid}', json={'data': {'owner_id': owner['id'], 'status': 'Qualified'}}, headers=h).status_code == 200
    assert client.put(f'/api/leads/{lid}', json={'data': {'owner_id': 999999}}, headers=h).status_code == 400

    # A Presales Lead who can see a prospect only through an assigned action may edit it too.
    # Contact fields an admin has locked for that role (field permissions) stay locked.
    _as(client, login, SUPER)
    presales = next(u for u in client.get('/api/users').json() if u['email'] == 'presales@jsan.local')
    assert client.post(f'/api/leads/{lid}/actions', json={'data': {'description': 'Prepare technical note', 'due_date': '2026-12-01', 'assigned_to': presales['id']}}, headers=csrf_headers(client)).status_code == 200
    _as(client, login, 'presales@jsan.local')
    h = csrf_headers(client)
    assert client.get(f'/api/leads/{lid}').status_code == 200
    assert client.put(f'/api/contacts/{contact_id}', json={'data': {'designation': 'Programme lead'}}, headers=h).status_code == 200
    assert client.put(f'/api/contacts/{contact_id}', json={'data': {'email': 'locked@northstar.example'}}, headers=h).status_code == 403
    assert client.put(f'/api/companies/{cid}', json={'data': {'website': 'northstar-group.example'}}, headers=h).status_code == 200
    assert client.post(f'/api/companies/{cid}/contacts', json={'data': {'name': 'Added by presales'}}, headers=h).status_code == 200

    # Delete remains limited to Super Admin / Admin
    _as(client, login, SUPER)
    assert client.get(f'/api/leads/{lid}').json()['permissions']['can_delete']
