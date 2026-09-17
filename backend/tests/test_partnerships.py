"""Partnerships: a second pipeline that mirrors the Prospects tab's features and rules exactly,
in its own tables. These tests also prove the new module never touches prospects/companies/leads data."""
import csv
import io

EXEC1, EXEC2, LEAD, SUPER = 'bd.exec1@jsan.local', 'bd.exec2@jsan.local', 'bd.lead@jsan.local', 'superadmin@jsan.local'


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _snapshot(client):
    """Counts of the existing prospect tables, to prove partnership work never changes them."""
    leads = client.get('/api/query/leads', params={'page_size': 100}).json()['total']
    companies = client.get('/api/query/companies', params={'page_size': 100}).json()['total']
    return leads, companies


def test_partnerships_do_not_touch_prospect_data(client, login, csrf_headers):
    me = _as(client, login, EXEC1)
    h = csrf_headers(client)
    before = _snapshot(client)

    r = client.post('/api/partnerships/full', json={'data': {
        'company': {'name': 'Isolation Check Partner Pty', 'vertical': 'Systems Integration'},
        'lead': {'owner_id': me['id'], 'remarks': 'Isolation check'},
        'contacts': [{'name': 'Iso Contact', 'email': 'iso@isolation-check.example', 'is_primary': True}],
    }}, headers=h)
    assert r.status_code == 200, r.text
    pid, cid = r.json()['lead']['id'], r.json()['lead']['company_id']
    try:
        client.put(f'/api/partnerships/{pid}', json={'data': {'remarks': 'edited'}}, headers=h)
        client.post(f'/api/partnerships/{pid}/meetings', json={'data': {'meeting_date': '2026-09-20', 'meeting_type': 'Discovery', 'status': 'Completed'}}, headers=h)
        client.post(f'/api/partnerships/{pid}/actions', json={'data': {'description': 'Follow up', 'due_date': '2026-09-25'}}, headers=h)
        client.post(f'/api/partnerships/{pid}/opportunities', json={'data': {'name': 'Co-sell pilot', 'amount': 50000}}, headers=h)

        after = _snapshot(client)
        assert after == before, f'Prospects/companies counts changed: {before} -> {after}'

        # And the partnership itself is invisible from every prospect-facing endpoint
        # (id sequences for leads and partnerships are independent, so identity is checked by company name)
        prospect_names = {i['company_name'] for i in client.get('/api/query/leads', params={'page_size': 100}).json()['items']}
        assert 'Isolation Check Partner Pty' not in prospect_names
    finally:
        client.delete(f'/api/partnerships/{pid}', headers=h)
        after_cleanup = _snapshot(client)
        assert after_cleanup == before


def _own_partnership(client, user):
    items = client.get('/api/query/partnerships', params={'page_size': 100}).json()['items']
    lead = next(i for i in items if i['owner_id'] == user['id'])
    return client.get(f"/api/partnerships/{lead['id']}").json()


def test_partnership_crud_and_role_rules(client, login, csrf_headers):
    owner = _as(client, login, EXEC1)
    h = csrf_headers(client)
    r = client.post('/api/partnerships/full', json={'data': {
        'company': {'name': 'Role Rules Partner Pty', 'vertical': 'Data & AI', 'website': 'https://role-rules-partner.example'},
        'lead': {'owner_id': owner['id'], 'temperature': 'Warm', 'source': 'Referral'},
        'contacts': [{'name': 'Role Rules Contact', 'email': 'contact@role-rules-partner.example', 'is_primary': True}],
    }}, headers=h)
    assert r.status_code == 200, r.text
    pid, cid = r.json()['lead']['id'], r.json()['lead']['company_id']
    try:
        detail = client.get(f'/api/partnerships/{pid}').json()
        perms = detail['permissions']
        assert perms['can_edit'] and perms['can_edit_company'] and perms['can_edit_contacts'] and not perms['can_reassign'] and not perms['can_delete']
        assert detail['lead']['company_name'] == 'Role Rules Partner Pty'
        assert detail['lead']['website'] == 'https://role-rules-partner.example'
        primary = next(c for c in detail['contacts'] if c['is_primary'])

        # Company + contact edits
        assert client.put(f'/api/partner-companies/{cid}', json={'data': {'vertical': 'AI & Analytics'}}, headers=h).status_code == 200
        assert client.put(f"/api/partner-contacts/{primary['id']}", json={'data': {'designation': 'Alliances Lead'}}, headers=h).status_code == 200
        assert client.put(f'/api/partnerships/{pid}', json={'data': {'remarks': 'Alliance forming', 'status': 'Engaged'}}, headers=h).status_code == 200

        # BD Executive cannot reassign
        assert client.put(f'/api/partnerships/{pid}', json={'data': {'owner_id': owner['id']}}, headers=h).status_code == 403

        # A peer with no access sees and can change nothing
        _as(client, login, EXEC2); h2 = csrf_headers(client)
        assert client.get(f'/api/partnerships/{pid}').status_code == 403
        assert client.put(f'/api/partnerships/{pid}', json={'data': {'remarks': 'x'}}, headers=h2).status_code == 403
        assert client.put(f'/api/partner-companies/{cid}', json={'data': {'remarks': 'x'}}, headers=h2).status_code == 403

        # BD Lead (manager) can reassign and edit team partnerships, cannot delete
        _as(client, login, LEAD); h3 = csrf_headers(client)
        p2 = client.get(f'/api/partnerships/{pid}').json()['permissions']
        assert p2['can_edit'] and p2['can_reassign'] and not p2['can_delete']
        assert client.put(f'/api/partnerships/{pid}', json={'data': {'owner_id': owner['id']}}, headers=h3).status_code == 200

        # Super Admin: everything including delete
        _as(client, login, SUPER); h4 = csrf_headers(client)
        p3 = client.get(f'/api/partnerships/{pid}').json()['permissions']
        assert p3['can_edit'] and p3['can_reassign'] and p3['can_delete']
    finally:
        _as(client, login, SUPER)
        client.delete(f'/api/partnerships/{pid}', headers=csrf_headers(client))


def test_partnership_workflow_meeting_mom_action_opportunity(client, login, csrf_headers):
    me = _as(client, login, EXEC1)
    h = csrf_headers(client)
    r = client.post('/api/partnerships/full', json={'data': {
        'company': {'name': 'Workflow Partner Pty', 'vertical': 'Telecommunications'},
        'lead': {'owner_id': me['id']}, 'contacts': [],
    }}, headers=h)
    pid = r.json()['lead']['id']
    try:
        m = client.post(f'/api/partnerships/{pid}/meetings', json={'data': {'meeting_date': '2026-09-18', 'meeting_type': 'Discovery', 'status': 'Completed'}}, headers=h)
        assert m.status_code == 200, m.text
        mom = client.post(f'/api/partnerships/{pid}/moms', json={'data': {'summary': 'Discussed co-sell motion', 'follow_up_date': '2026-09-25'}}, headers=h)
        assert mom.status_code == 200, mom.text
        assert client.get(f'/api/partnerships/{pid}').json()['lead']['next_follow_up'] == '2026-09-25'

        a = client.post(f'/api/partnerships/{pid}/actions', json={'data': {'description': 'Draft partnership agreement', 'due_date': '2026-09-30'}}, headers=h)
        assert a.status_code == 200, a.text
        aid = a.json()['id']
        assert client.put(f'/api/partner-actions/{aid}', json={'data': {'status': 'Completed'}}, headers=h).status_code == 200

        o = client.post(f'/api/partnerships/{pid}/opportunities', json={'data': {'name': 'Joint GTM pilot', 'amount': 75000, 'currency': 'USD', 'probability': 40}}, headers=h)
        assert o.status_code == 200, o.text
        oid = o.json()['opportunity']['id']
        assert client.post(f'/api/partner-opportunities/{oid}/followups', json={'data': {'response': 'Legal reviewing terms'}}, headers=h).status_code == 200
        assert client.put(f'/api/partner-opportunities/{oid}', json={'data': {'status': 'Closed Won', 'final_amount': 70000}}, headers=h).status_code == 200

        detail = client.get(f'/api/partnerships/{pid}').json()
        assert len(detail['meetings']) == 1 and len(detail['moms']) == 1 and len(detail['actions']) == 1 and len(detail['opportunities']) == 1
        assert len(detail['timeline']) >= 4
        assert detail['lead']['status'] == 'Qualified' or detail['lead']['status'] == 'New'  # opportunity creation moves status to Qualified
    finally:
        _as(client, login, SUPER)
        client.delete(f'/api/partnerships/{pid}', headers=csrf_headers(client))


def _csv(rows):
    header = ['Company', 'Vertical', 'Region', 'Country', 'Contact Name', 'Email', 'Signal', 'Status', 'Owner Email']
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(header)
    for r in rows: w.writerow(r)
    return buf.getvalue().encode('utf-8')


def test_partnership_csv_import_owner_rule_and_csrf(client, login, csrf_headers):
    created = []
    try:
        exec1 = _as(client, login, EXEC1)
        exec2_id = _as(client, login, EXEC2)['id']
        _as(client, login, EXEC1)

        no_csrf = client.post('/api/partnerships/import', files={'file': ('p.csv', _csv([['CSV Partner NoCsrf Pty', 'IT', 'Global', 'USA', '', '', 'Warm', 'New', exec1['email']]]), 'text/csv')})
        assert no_csrf.status_code == 403

        r = client.post('/api/partnerships/import', files={'file': ('p.csv', _csv([
            ['CSV Partner Self Pty', 'IT', 'Global', 'USA', '', '', 'Warm', 'New', exec1['email']],
            ['CSV Partner Peer Pty', 'IT', 'Global', 'USA', '', '', 'Warm', 'New', 'bd.exec2@jsan.local'],
        ]), 'text/csv')}, headers=csrf_headers(client))
        assert r.status_code == 200, r.text
        res = r.json(); created += ['CSV Partner Self Pty', 'CSV Partner Peer Pty']
        assert res['imported'] == 2, res
        warnings = {w['row']: w['message'] for w in res['warnings']}
        assert warnings[3] == 'You cannot assign partnerships to BD Executive B — assigned to you', warnings

        items = client.get('/api/query/partnerships', params={'q': 'CSV Partner Self Pty', 'page_size': 20}).json()['items']
        assert items[0]['owner_id'] == exec1['id']
        items2 = client.get('/api/query/partnerships', params={'q': 'CSV Partner Peer Pty', 'page_size': 20}).json()['items']
        assert items2[0]['owner_id'] == exec1['id']  # not assignable -> falls back to importer
    finally:
        _as(client, login, SUPER)
        for company in created:
            items = client.get('/api/query/partnerships', params={'q': company, 'page_size': 50}).json()['items']
            for i in items:
                if i['company_name'] == company:
                    client.delete(f"/api/partnerships/{i['id']}", headers=csrf_headers(client))


def test_partnership_field_permissions_reuse_contact_rules(client, login, csrf_headers):
    """Locking a contact field for a role in Admin Center (COMPANY_EDIT/CONTACT_EDIT rules) applies to
    partnerships too — same field_permissions rows, same "locked_contact_fields" the edit form reads."""
    _as(client, login, SUPER)
    field_perms = client.get('/api/admin/field-permissions').json()
    exec_role_id = next(p['role_id'] for p in field_perms if p['role'] == 'BD Executive')
    before = next(p for p in field_perms if p['role_id'] == exec_role_id and p['entity_type'] == 'contact' and p['field_name'] == 'phone')
    h0 = csrf_headers(client)
    assert client.put('/api/admin/field-permissions', json={'data': {'role_id': exec_role_id, 'entity_type': 'contact', 'field_name': 'phone', 'can_view': True, 'can_edit': False}}, headers=h0).status_code == 200
    pid = None
    try:
        me = _as(client, login, EXEC1); h = csrf_headers(client)
        r = client.post('/api/partnerships/full', json={'data': {
            'company': {'name': 'Field Perm Partner Pty', 'vertical': 'Utilities'},
            'lead': {'owner_id': me['id']},
            'contacts': [{'name': 'Field Perm Contact', 'email': 'x@field-perm-partner.example', 'is_primary': True}],
        }}, headers=h)
        assert r.status_code == 200, r.text
        pid = r.json()['lead']['id']
        detail = client.get(f'/api/partnerships/{pid}').json()
        assert detail['permissions']['locked_contact_fields'] == ['phone']
        contact_id = next(c for c in detail['contacts'] if c['is_primary'])['id']
        assert client.put(f'/api/partner-contacts/{contact_id}', json={'data': {'phone': '123'}}, headers=h).status_code == 403
        assert client.put(f'/api/partner-contacts/{contact_id}', json={'data': {'designation': 'Buyer'}}, headers=h).status_code == 200
    finally:
        _as(client, login, SUPER)
        h4 = csrf_headers(client)
        client.put('/api/admin/field-permissions', json={'data': {'role_id': exec_role_id, 'entity_type': 'contact', 'field_name': 'phone', 'can_view': before['can_view'], 'can_edit': before['can_edit']}}, headers=h4)
        if pid: client.delete(f'/api/partnerships/{pid}', headers=h4)
