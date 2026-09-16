LONG = '3D, visualization, 3D Map , 3D Modeling , TrueOrtho, GIS, Geospatial, 3D Reconstruction, Inspection, photogrammetry, Orthophoto, and Globe visualization'


def test_vertical_has_no_length_limit(client, login, csrf_headers):
    client.cookies.clear()
    me = login(client, email='superadmin@jsan.local')['user']
    h = csrf_headers(client)
    assert len(LONG) > 120
    r = client.post('/api/leads/full', json={'data': {'company': {'name': 'Skyline Software Systems Test', 'vertical': LONG}, 'lead': {'owner_id': me['id']}, 'contacts': []}}, headers=h)
    assert r.status_code == 200, r.text
    lid, cid = r.json()['lead']['id'], r.json()['lead']['company_id']
    try:
        assert client.get(f'/api/leads/{lid}').json()['lead']['vertical'] == LONG
        assert client.put(f'/api/companies/{cid}', json={'data': {'vertical': LONG + ' and more'}}, headers=h).status_code == 200
    finally:
        client.delete(f'/api/leads/{lid}', headers=h)
