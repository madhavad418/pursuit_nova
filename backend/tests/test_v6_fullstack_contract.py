def fresh_client(client):
    client.cookies.clear()


def test_v6_full_seller_workflow_contract(client, login, csrf_headers):
    fresh_client(client)
    login(client, 'director@jsan.local')
    h = csrf_headers(client)

    created = client.post('/api/leads/full', headers=h, json={'data': {
        'company': {
            'name': 'V6 Integration Industries',
            'vertical': 'IT Services',
            'website': 'https://v6-integration.example',
            'region': 'APAC',
            'country': 'India',
            'state': 'Telangana',
            'city': 'Hyderabad'
        },
        'lead': {
            'owner_id': 6,
            'temperature': 'Hot',
            'source': 'Referral',
            'source_detail': 'V6 contract test',
            'status': 'New',
            'next_follow_up': '2026-09-15',
            'remarks': 'Created from the React v6 workflow contract.'
        },
        'contacts': [{
            'name': 'V6 Decision Maker',
            'designation': 'VP Operations',
            'email': 'decision.maker@v6-integration.example',
            'phone': '+91 90000 00000',
            'is_primary': True
        }]
    }})
    assert created.status_code == 200, created.text
    lead_id = created.json()['lead']['id']

    meeting = client.post(f'/api/leads/{lead_id}/meetings', headers=h, json={'data': {
        'meeting_date': '2026-09-12',
        'meeting_time': '11:00',
        'meeting_type': 'Discovery',
        'status': 'Completed',
        'purpose': 'Validate requirements',
        'customer_participants': 'V6 Decision Maker',
        'jsan_participants': 'BD Executive A'
    }})
    assert meeting.status_code == 200, meeting.text

    mom = client.post(f'/api/leads/{lead_id}/moms', headers=h, json={'data': {
        'summary': 'Customer confirmed the target scope.',
        'customer_requirements': 'Governed delivery and weekly reporting',
        'jsan_commitments': 'Share solution and commercials',
        'next_steps': 'Prepare proposal',
        'follow_up_date': '2026-09-16'
    }})
    assert mom.status_code == 200, mom.text

    action = client.post(f'/api/leads/{lead_id}/actions', headers=h, json={'data': {
        'description': 'Prepare solution and commercials',
        'assigned_to': 6,
        'due_date': '2026-09-16',
        'priority': 'High',
        'status': 'Open'
    }})
    assert action.status_code == 200, action.text

    opp = client.post(f'/api/leads/{lead_id}/opportunities', headers=h, json={'data': {
        'name': 'V6 Managed Services Pursuit',
        'service_practice': 'Managed Services',
        'owner_id': 6,
        'status': 'Awaiting Response',
        'forecast_category': 'Best Case',
        'amount': 275000,
        'currency': 'USD',
        'probability': 60,
        'expected_close_date': '2026-10-15',
        'next_follow_up_date': '2026-09-18'
    }})
    assert opp.status_code == 200, opp.text
    opp_id = opp.json()['opportunity']['id']

    followup = client.post(f'/api/opportunities/{opp_id}/followups', headers=h, json={'data': {
        'follow_up_date': '2026-09-18',
        'response': 'Customer is reviewing the proposal',
        'next_follow_up_date': '2026-09-22'
    }})
    assert followup.status_code == 200, followup.text

    lead = client.get(f'/api/leads/{lead_id}')
    assert lead.status_code == 200
    body = lead.json()
    assert len(body['contacts']) == 1
    assert len(body['meetings']) == 1
    assert len(body['moms']) == 1
    assert len(body['actions']) == 1
    assert any(x['id'] == opp_id for x in body['opportunities'])
    assert any(x['type'] == 'Follow-up' for x in body['timeline'])

    q = client.get('/api/query/leads?q=V6%20Integration&page=1&page_size=20')
    assert q.status_code == 200 and any(x['id'] == lead_id for x in q.json()['items'])
    oq = client.get('/api/query/opportunities?q=V6%20Managed&page=1&page_size=20')
    assert oq.status_code == 200 and any(x['id'] == opp_id for x in oq.json()['items'])
    assert client.get('/api/dashboard/summary').status_code == 200
    assert client.get('/api/dashboard/analytics').status_code == 200
