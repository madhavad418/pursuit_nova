LONG = '3D, visualization, 3D Map , 3D Modeling , TrueOrtho, GIS, Geospatial, 3D Reconstruction, Inspection, photogrammetry, Orthophoto, and Globe visualization'
UNMATCHED_LONG = 'Bespoke artisanal candle-making, small-batch, hand-poured, wax blending, scent curation, and boutique candle craftsmanship for home decor gifting'


def test_vertical_has_no_length_limit(client, login, csrf_headers):
    client.cookies.clear()
    me = login(client, email='superadmin@jsan.local')['user']
    h = csrf_headers(client)
    assert len(UNMATCHED_LONG) > 120
    r = client.post('/api/leads/full', json={'data': {'company': {'name': 'Skyline Software Systems Test', 'vertical': UNMATCHED_LONG}, 'lead': {'owner_id': me['id']}, 'contacts': []}}, headers=h)
    assert r.status_code == 200, r.text
    lid, cid = r.json()['lead']['id'], r.json()['lead']['company_id']
    try:
        assert client.get(f'/api/leads/{lid}').json()['lead']['vertical'] == UNMATCHED_LONG
        assert client.put(f'/api/companies/{cid}', json={'data': {'vertical': UNMATCHED_LONG + ' and more'}}, headers=h).status_code == 200
    finally:
        client.delete(f'/api/leads/{lid}', headers=h)


def test_vertical_auto_classifies_recognizable_free_text(client, login, csrf_headers):
    # LONG is a comma-separated list of tags. Each tag is classified independently and
    # recognizable GIS/geospatial synonyms collapse into a single deduped "GIS / Geospatial"
    # tag, while unrecognized tags ("3D", "visualization", "TrueOrtho", "Inspection") are
    # kept as their own distinct tags rather than being forced into a category.
    client.cookies.clear()
    me = login(client, email='superadmin@jsan.local')['user']
    h = csrf_headers(client)
    assert len(LONG) > 120
    r = client.post('/api/leads/full', json={'data': {'company': {'name': 'Skyline Software Systems Test 2', 'vertical': LONG}, 'lead': {'owner_id': me['id']}, 'contacts': []}}, headers=h)
    assert r.status_code == 200, r.text
    lid = r.json()['lead']['id']
    try:
        assert client.get(f'/api/leads/{lid}').json()['lead']['vertical'] == '3D, visualization, GIS / Geospatial, TrueOrtho, Inspection'
    finally:
        client.delete(f'/api/leads/{lid}', headers=h)


def test_vertical_supports_unlimited_multi_tag_values(client, login, csrf_headers):
    # The vertical field is not capped at 2-3 values — a record can carry as many
    # comma-separated tags as the user adds, each classified on its own.
    client.cookies.clear()
    me = login(client, email='superadmin@jsan.local')['user']
    h = csrf_headers(client)
    tags = ['telecom', 'GIS mapping specialist', 'hospital network', 'EV manufacturer', 'e-commerce brand', 'power grid operator', 'Bespoke Artisan Woodworking']
    r = client.post('/api/leads/full', json={'data': {'company': {'name': 'Skyline Multi Vertical Test', 'vertical': ', '.join(tags)}, 'lead': {'owner_id': me['id']}, 'contacts': []}}, headers=h)
    assert r.status_code == 200, r.text
    lid = r.json()['lead']['id']
    try:
        got = client.get(f'/api/leads/{lid}').json()['lead']['vertical']
        assert got == 'Telecommunications, GIS / Geospatial, Healthcare, Automotive & Mobility, Retail, Utilities, Bespoke Artisan Woodworking'
        assert len(got.split(', ')) == 7
    finally:
        client.delete(f'/api/leads/{lid}', headers=h)
