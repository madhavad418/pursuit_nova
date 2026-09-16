EXEC1, SUPER = 'bd.exec1@jsan.local', 'superadmin@jsan.local'


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _own_lead(client, user):
    items = client.get('/api/query/leads', params={'page_size': 100}).json()['items']
    return next(i for i in items if i['owner_id'] == user['id'])


def test_locked_contact_fields_follow_field_permissions(client, login, csrf_headers):
    admin = _as(client, login, SUPER)
    lid = client.get('/api/query/leads', params={'page_size': 1}).json()['items'][0]['id']
    assert client.get(f'/api/leads/{lid}').json()['permissions']['locked_contact_fields'] == []

    field_perms = client.get('/api/admin/field-permissions').json()
    exec_role = {'id': next(p['role_id'] for p in field_perms if p['role'] == 'BD Executive')}
    before = [p for p in field_perms if p['role_id'] == exec_role['id'] and p['entity_type'] == 'contact' and p['field_name'] == 'phone']
    h = csrf_headers(client)
    assert client.put('/api/admin/field-permissions', json={'data': {'role_id': exec_role['id'], 'entity_type': 'contact', 'field_name': 'phone', 'can_view': True, 'can_edit': False}}, headers=h).status_code == 200
    try:
        me = _as(client, login, EXEC1)
        detail = client.get(f"/api/leads/{_own_lead(client, me)['id']}").json()
        # The edit form locks exactly what the server would refuse
        assert detail['permissions']['locked_contact_fields'] == ['phone']
        cid = detail['lead']['company_id']
        h = csrf_headers(client)
        contact = client.post(f'/api/companies/{cid}/contacts', json={'data': {'name': 'Locked Phone Check'}}, headers=h).json()
        assert client.put(f"/api/contacts/{contact['id']}", json={'data': {'phone': '123'}}, headers=h).status_code == 403
        assert client.put(f"/api/contacts/{contact['id']}", json={'data': {'designation': 'Buyer'}}, headers=h).status_code == 200
        client.put(f"/api/contacts/{contact['id']}", json={'data': {'active': False}}, headers=h)
    finally:
        _as(client, login, SUPER)
        restore = before[0] if before else {'can_view': True, 'can_edit': True}
        client.put('/api/admin/field-permissions', json={'data': {'role_id': exec_role['id'], 'entity_type': 'contact', 'field_name': 'phone', 'can_view': restore['can_view'], 'can_edit': restore['can_edit']}}, headers=csrf_headers(client))
    _as(client, login, EXEC1)
    assert client.get(f"/api/leads/{_own_lead(client, me)['id']}").json()['permissions']['locked_contact_fields'] == []


def test_edit_form_save_flow(client, login, csrf_headers):
    """The requests the edit form sends: company, primary contact, prospect (including Status)."""
    me = _as(client, login, EXEC1)
    lid = _own_lead(client, me)['id']
    detail = client.get(f'/api/leads/{lid}').json()
    cid = detail['lead']['company_id']
    h = csrf_headers(client)
    added = []
    try:
        assert client.put(f'/api/companies/{cid}', json={'data': {'website': 'edit-form.example', 'linkedin_url': 'linkedin.com/company/edit-form'}}, headers=h).status_code == 200
        # No primary contact yet on this company -> the form adds one as primary
        for c in detail['contacts']:
            if c['is_primary']:
                break
        else:
            r = client.post(f'/api/companies/{cid}/contacts', json={'data': {'name': 'Form Primary', 'designation': 'CTO', 'email': 'form.primary@edit-form.example', 'is_primary': True}}, headers=h)
            assert r.status_code == 200, r.text
            added.append(r.json()['id'])
        primary = next(c for c in client.get(f'/api/leads/{lid}').json()['contacts'] if c['is_primary'])
        assert client.put(f"/api/contacts/{primary['id']}", json={'data': {'phone': '+1 512 555 0199', 'linkedin_url': 'linkedin.com/in/form-primary'}}, headers=h).status_code == 200
        r = client.put(f'/api/leads/{lid}', json={'data': {'region': 'Europe', 'country': 'UK', 'temperature': 'Hot', 'source': 'Referral', 'source_detail': 'Form test', 'next_follow_up': '2026-10-05', 'status': 'Engaged', 'remarks': 'Edited via form'}}, headers=h)
        assert r.status_code == 200, r.text
        after = client.get(f'/api/leads/{lid}').json()
        l = after['lead']
        assert l['website'] == 'https://edit-form.example' and l['linkedin_url'] == 'https://linkedin.com/company/edit-form'
        assert (l['region'], l['country'], l['temperature'], l['source'], l['source_detail'], l['next_follow_up'], l['status'], l['remarks']) == ('Europe', 'UK', 'Hot', 'Referral', 'Form test', '2026-10-05', 'Engaged', 'Edited via form')
        p = next(c for c in after['contacts'] if c['is_primary'])
        assert p['id'] == primary['id'] and p['phone'] == '+1 512 555 0199' and p['linkedin_url'] == 'https://linkedin.com/in/form-primary'
        assert l['last_edited_at']  # the Overview watermark picks the edit up
    finally:
        # Put the shared demo prospect back the way it was
        o = detail['lead']
        client.put(f'/api/leads/{lid}', json={'data': {k: o[k] for k in ('region', 'country', 'temperature', 'source', 'source_detail', 'next_follow_up', 'status', 'remarks')}}, headers=h)
        client.put(f'/api/companies/{cid}', json={'data': {'website': o['website'] or '', 'linkedin_url': o['linkedin_url'] or ''}}, headers=h)
        for x in added:
            client.put(f'/api/contacts/{x}', json={'data': {'active': False}}, headers=h)
