import csv
import io

EXEC1, EXEC2, LEAD, SUPER = 'bd.exec1@jsan.local', 'bd.exec2@jsan.local', 'bd.lead@jsan.local', 'superadmin@jsan.local'
HEADER = ['Company', 'Vertical', 'Region', 'Country', 'State', 'City', 'Contact Name', 'Email', 'Signal', 'Source', 'Status', 'Remarks', 'Owner Email']


def _csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode('utf-8')


def _row(company, owner_email):
    return [company, 'Drone Survey', 'Global', 'Australia', 'Victoria', 'Croydon', 'Test Contact', '', 'Warm', 'LinkedIn', 'Contacted',
            'Mailed them on info@lidarsolutions.com.au', owner_email]


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _import(client, csrf_headers, data, with_csrf=True):
    return client.post('/api/leads/import', files={'file': ('prospects.csv', data, 'text/csv')}, headers=csrf_headers(client) if with_csrf else {})


def _owner_of(client, company):
    items = client.get('/api/query/leads', params={'q': company, 'page_size': 50}).json()['items']
    match = [i for i in items if i['company_name'] == company]
    assert len(match) == 1, (company, [i['company_name'] for i in items])
    return match[0]


def test_csv_import_owner_rule_and_csrf(client, login, csrf_headers):
    created = []
    try:
        exec1 = _as(client, login, EXEC1)
        exec2_id = _as(client, login, EXEC2)['id']
        _as(client, login, EXEC1)

        # Import needs the CSRF token like every other change
        assert _import(client, csrf_headers, _csv([_row('CSV Owner NoCsrf Pty', EXEC1)]), with_csrf=False).status_code == 403

        # BD Executive: own rows keep them as owner; a peer as owner is not allowed and falls back to the importer
        r = _import(client, csrf_headers, _csv([
            _row('CSV Owner Self Pty', EXEC1),
            _row('CSV Owner Peer Pty', EXEC2),
            _row('CSV Owner Unknown Pty', 'nobody@example.com'),
        ]))
        assert r.status_code == 200, r.text
        res = r.json()
        created += ['CSV Owner Self Pty', 'CSV Owner Peer Pty', 'CSV Owner Unknown Pty']
        assert res['imported'] == 3 and res['errors'] == [], res
        warnings = {w['row']: w['message'] for w in res['warnings']}
        assert warnings[3] == 'You cannot assign prospects to BD Executive B — assigned to you', warnings
        assert "not found — assigned to you" in warnings[4], warnings
        assert 2 not in warnings, warnings
        assert _owner_of(client, 'CSV Owner Self Pty')['owner_id'] == exec1['id']
        assert _owner_of(client, 'CSV Owner Peer Pty')['owner_id'] == exec1['id']
        assert _owner_of(client, 'CSV Owner Unknown Pty')['owner_id'] == exec1['id']

        # BD Lead importing for someone in their team keeps that owner
        _as(client, login, LEAD)
        r = _import(client, csrf_headers, _csv([_row('CSV Owner Team Pty', EXEC2)]))
        assert r.status_code == 200 and r.json()['warnings'] == [], r.text
        created.append('CSV Owner Team Pty')
        assert _owner_of(client, 'CSV Owner Team Pty')['owner_id'] == exec2_id

        # Super Admin can assign to anyone
        _as(client, login, SUPER)
        r = _import(client, csrf_headers, _csv([_row('CSV Owner Super Pty', EXEC2)]))
        assert r.status_code == 200 and r.json()['warnings'] == [], r.text
        created.append('CSV Owner Super Pty')
        assert _owner_of(client, 'CSV Owner Super Pty')['owner_id'] == exec2_id
    finally:
        # Remove the imported prospects so the shared demo data other tests rely on stays as seeded
        _as(client, login, SUPER)
        for company in created:
            items = client.get('/api/query/leads', params={'q': company, 'page_size': 50}).json()['items']
            for i in items:
                if i['company_name'] == company:
                    client.delete(f"/api/leads/{i['id']}", headers=csrf_headers(client))
