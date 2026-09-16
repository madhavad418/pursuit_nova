from datetime import date


def _period():
    today = date.today()
    return today.year, f"Q{(today.month - 1) // 3 + 1}"


def test_leadership_map_region_counts(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    year, period = _period()
    data = client.get('/api/reports/period', params={'year': year, 'period': period}).json()
    counts = data['region_counts']
    total = data['summary']['leads_created']
    assert total > 0, 'demo data should have prospects in the current quarter'

    # One entry per region, adding up to the prospects total shown on the map
    assert sum(c['leads'] for c in counts) == total
    assert len({c['region'] for c in counts}) == len(counts)
    assert all(c['leads'] > 0 and c['region'] for c in counts)
    # Highest first, and every region is one the region filter offers
    assert [c['leads'] for c in counts] == sorted((c['leads'] for c in counts), reverse=True)
    assert {c['region'] for c in counts} <= set(data['regions'])

    # Filtering by a region leaves only that region's count
    top = counts[0]
    if top['region'] != 'Unassigned':
        filtered = client.get('/api/reports/period', params={'year': year, 'period': period, 'region': top['region']}).json()
        assert filtered['region_counts'] == [top]
        assert filtered['summary']['leads_created'] == top['leads']


def test_region_counts_follow_visibility(client, login):
    # A BD Executive only counts the prospects they can see
    year, period = _period()
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    everyone = sum(c['leads'] for c in client.get('/api/reports/period', params={'year': year, 'period': period}).json()['region_counts'])
    client.cookies.clear()
    login(client, email='bd.exec1@jsan.local')
    r = client.get('/api/reports/period', params={'year': year, 'period': period})
    if r.status_code == 403:
        return  # role has no report access
    own = r.json()
    assert sum(c['leads'] for c in own['region_counts']) == own['summary']['leads_created'] <= everyone
