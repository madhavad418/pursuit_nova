import time
from datetime import datetime, timezone, timedelta


def _parse(ts):
    assert ts and ts.endswith('Z'), ts
    return datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def test_overview_last_edited_timestamp(client, login, csrf_headers):
    client.cookies.clear()
    me = login(client, email='bd.lead@jsan.local')['user']
    h = csrf_headers(client)

    # A brand-new prospect has not been edited yet, but knows when it was created
    r = client.post('/api/leads/full', json={'data': {'company': {'name': 'Watermark Test Pty', 'vertical': 'Surveying'}, 'lead': {'owner_id': me['id']}, 'contacts': []}}, headers=h)
    assert r.status_code == 200, r.text
    lid = r.json()['lead']['id']
    detail = client.get(f'/api/leads/{lid}').json()
    assert detail['lead']['last_edited_at'] is None
    created = _parse(detail['lead']['created_at_utc'])
    assert abs(datetime.now(timezone.utc) - created) < timedelta(minutes=2)   # stored and sent as UTC

    # Editing a prospect field sets it
    time.sleep(1.1)
    assert client.put(f'/api/leads/{lid}', json={'data': {'remarks': 'Called'}}, headers=h).status_code == 200
    first = _parse(client.get(f'/api/leads/{lid}').json()['lead']['last_edited_at'])
    assert abs(datetime.now(timezone.utc) - first) < timedelta(minutes=2)

    # Activity that is not an Overview edit does not move it (unlike leads.updated_at)
    time.sleep(1.1)
    assert client.post(f'/api/leads/{lid}/meetings', json={'data': {'meeting_date': '2026-09-20', 'meeting_type': 'Discovery', 'status': 'Completed'}}, headers=h).status_code == 200
    assert _parse(client.get(f'/api/leads/{lid}').json()['lead']['last_edited_at']) == first

    # A company-only edit (Company / Vertical) moves it
    time.sleep(1.1)
    cid = client.get(f'/api/leads/{lid}').json()['lead']['company_id']
    assert client.put(f'/api/companies/{cid}', json={'data': {'vertical': 'Drone Survey'}}, headers=h).status_code == 200
    second = _parse(client.get(f'/api/leads/{lid}').json()['lead']['last_edited_at'])
    assert second > first
