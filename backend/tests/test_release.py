import base64,hmac,hashlib,struct,time


def totp(secret):
    key=base64.b32decode(secret+'='*((8-len(secret)%8)%8)); counter=int(time.time())//30
    digest=hmac.new(key,struct.pack('>Q',counter),hashlib.sha1).digest(); pos=digest[-1]&0xf
    return f"{(struct.unpack('>I',digest[pos:pos+4])[0]&0x7fffffff)%1000000:06d}"


def fresh_client(client):
    client.cookies.clear()


def test_01_health_and_secure_cookie_session(client,login,csrf_headers):
    fresh_client(client)
    assert client.get('/api/health').json()['status']=='ok'
    d=login(client)
    assert d['user']['role']=='BD Executive'
    assert client.cookies.get('pursuitnova_session')
    assert client.get('/api/auth/me').status_code==200
    assert client.post('/api/leads/1/actions',json={'data':{'description':'blocked','due_date':'2026-09-20'}}).status_code==403
    assert csrf_headers(client).get('X-CSRF-Token')


def test_02_peer_isolation(client,login):
    fresh_client(client); login(client,'bd.exec1@jsan.local')
    ids={x['id'] for x in client.get('/api/leads').json()}; assert ids=={1,3}
    assert client.get('/api/leads/2').status_code==403


def test_03_hierarchy_rollup(client,login):
    fresh_client(client); login(client,'bd.lead@jsan.local')
    assert {x['id'] for x in client.get('/api/leads').json()}=={1,2,3,4}
    fresh_client(client); login(client,'bd.manager@jsan.local')
    assert len(client.get('/api/leads').json())>=4
    fresh_client(client); login(client,'director@jsan.local')
    assert len(client.get('/api/leads').json())>=4


def test_04_presales_cross_functional_visibility(client,login):
    fresh_client(client); login(client,'presales@jsan.local')
    ids={x['id'] for x in client.get('/api/leads').json()}; assert {1,2,3}.issubset(ids)
    opps=client.get('/api/opportunities').json(); assert len(opps)>=3
    acts=client.get('/api/actions').json(); assert any(a['assigned_to_name']=='Presales Lead' for a in acts)


def test_05_existing_company_lead_creation(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    before=len(client.get('/api/companies').json())
    r=client.post('/api/leads/full',headers=h,json={'data':{'company_id':1,'lead':{'owner_id':6,'temperature':'Warm','source':'LinkedIn','status':'New','remarks':'Second workstream'},'contacts':[]}})
    assert r.status_code==200,r.text
    after=len(client.get('/api/companies').json()); assert after==before
    assert r.json()['lead']['company_id']==1


def test_06_duplicate_company_and_contact_controls(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    r=client.post('/api/companies',headers=h,json={'data':{'name':'Northstar Mobility Ltd','vertical':'Automotive & Mobility','website':'https://northstar.example'}})
    assert r.status_code==409
    r=client.post('/api/companies/1/contacts',headers=h,json={'data':{'name':'Alex Duplicate','email':'alex@northstar.example'}})
    assert r.status_code==409
    q=client.get('/api/data-quality/company-duplicates?name=Northstar%20Mobility&website=https://northstar.example')
    assert q.status_code==200 and q.json()[0]['score']>=.75


def test_07_actions_and_notifications(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    r=client.post('/api/leads/1/actions',headers=h,json={'data':{'description':'SVP test action','assigned_to':6,'due_date':'2026-09-10','priority':'High'}})
    assert r.status_code==200
    acts=client.get('/api/actions?filter=all').json(); assert any(a['description']=='SVP test action' for a in acts)
    ns=client.get('/api/notifications').json(); assert any('Action' in n['title'] for n in ns)


def test_08_opportunity_outcome_business_rules(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    assert client.put('/api/opportunities/1',headers=h,json={'data':{'status':'Closed Lost','lost_reason':''}}).status_code==400
    assert client.put('/api/opportunities/1',headers=h,json={'data':{'status':'Closed Hold','hold_reason':'Budget'}}).status_code==400
    r=client.put('/api/opportunities/1',headers=h,json={'data':{'status':'Closed Won','final_amount':700000,'forecast_category':'Closed'}})
    assert r.status_code==200 and r.json()['opportunity']['final_amount']==700000
    # restore for later tests
    assert client.put('/api/opportunities/1',headers=h,json={'data':{'status':'Awaiting Response','forecast_category':'Best Case'}}).status_code==200


def test_09_followup_history_updates_last_next_and_count(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    before=client.get('/api/opportunities/1').json()['opportunity']['follow_up_count']
    r=client.post('/api/opportunities/1/followups',headers=h,json={'data':{'follow_up_date':'2026-09-10','response':'Customer reviewing','next_follow_up_date':'2026-09-13'}})
    assert r.status_code==200
    o=r.json()['opportunity']; assert o['follow_up_count']==before+1 and o['last_follow_up_date']=='2026-09-10' and o['next_follow_up_date']=='2026-09-13'


def test_10_targets_and_forecast_rollup(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.manager@jsan.local'); h=csrf_headers(client)
    r=client.post('/api/targets',headers=h,json={'data':{'user_id':6,'year':2026,'quarter':'Q3','target_amount':600000,'currency':'USD'}})
    assert r.status_code==200
    f=client.get('/api/forecast/summary?year=2026&quarter=Q3'); assert f.status_code==200
    row6=next(x for x in f.json()['rows'] if x['user_id']==6); assert row6['target']==600000


def test_11_explicit_share_and_global_search_document_trace(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.lead@jsan.local'); h=csrf_headers(client)
    r=client.post('/api/leads/1/share',headers=h,json={'data':{'user_id':7,'access_level':'view'}}); assert r.status_code==200
    fresh_client(client); login(client,'bd.exec2@jsan.local')
    assert client.get('/api/leads/1').status_code==200
    s=client.get('/api/search?q=Northstar'); assert s.status_code==200 and any(x['type']=='Company' for x in s.json())
    h=csrf_headers(client)
    r=client.post('/api/documents',headers=h,json={'data':{'entity_type':'lead','entity_id':1,'name':'Capability Deck','document_type':'Proposal','url':'https://docs.example/capability','version':'1.0'}})
    assert r.status_code==200


def test_12_mfa_and_security_audit(client,login,csrf_headers):
    fresh_client(client); login(client,'admin@jsan.local'); h=csrf_headers(client)
    setup=client.post('/api/auth/mfa/setup',headers=h,json={}); assert setup.status_code==200
    code=totp(setup.json()['secret'])
    enabled=client.post('/api/auth/mfa/enable',headers=h,json={'data':{'code':code}}); assert enabled.status_code==200
    client.post('/api/auth/logout',headers=h,json={})
    fresh_client(client)
    r=client.post('/api/auth/login',json={'email':'admin@jsan.local','password':'PursuitNovaDemo@2026'}); assert r.status_code==200 and r.json().get('mfa_required')
    r=client.post('/api/auth/login',json={'email':'admin@jsan.local','password':'PursuitNovaDemo@2026','otp':totp(setup.json()['secret'])}); assert r.status_code==200
    sec=client.get('/api/security-logs'); assert sec.status_code==200 and any(x['event_type']=='LOGIN_SUCCESS' for x in sec.json())

def test_13_executive_dashboard_analytics(client,login):
    fresh_client(client); login(client,'director@jsan.local')
    r=client.get('/api/dashboard/analytics'); assert r.status_code==200
    d=r.json()
    for key in ('temperature','source_mix','pipeline','ageing','owner_performance','quarter_trend','top_opportunities'):
        assert key in d
    assert len(d['quarter_trend'])==6
    assert any(x['pipeline']>0 or x['won']>0 for x in d['quarter_trend'])


def test_14_company_contact_relationship_privacy(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.exec2@jsan.local'); h=csrf_headers(client)
    # A shared company master remains discoverable, but another executive's relationship PII is private.
    d=client.get('/api/companies/3'); assert d.status_code==200
    assert d.json()['relationship_access'] is False and d.json()['contacts']==[]
    r=client.put('/api/companies/3',headers=h,json={'data':{'remarks':'unauthorized edit'}})
    assert r.status_code==403


def test_15_peer_opportunity_reassignment_is_atomic(client,login,csrf_headers):
    fresh_client(client); login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    before=client.get('/api/opportunities/1').json()['opportunity']['owner_id']; assert before==6
    r=client.put('/api/opportunities/1',headers=h,json={'data':{'owner_id':7}})
    assert r.status_code==403
    after=client.get('/api/opportunities/1').json()['opportunity']['owner_id']; assert after==6

def test_16_workflow_toggle_controls_notification_execution(client,login,csrf_headers):
    fresh_client(client); login(client,'superadmin@jsan.local'); h=csrf_headers(client)
    rules=client.get('/api/admin/workflows').json(); rid=next(x['id'] for x in rules if x['code']=='ACTION_OVERDUE')
    assert client.put(f'/api/admin/workflows/{rid}',headers=h,json={'data':{'enabled':False}}).status_code==200
    fresh_client(client); login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    text='Disabled-rule unique overdue action'
    ar=client.post('/api/leads/1/actions',headers=h,json={'data':{'description':text,'assigned_to':6,'due_date':'2026-09-01','priority':'High'}}); assert ar.status_code==200
    aid=ar.json()['id']; notices=client.get('/api/notifications').json(); assert not any(n.get('notification_type')=='ACTION_DUE' and n.get('entity_id')==aid for n in notices)
    fresh_client(client); login(client,'superadmin@jsan.local'); h=csrf_headers(client)
    assert client.put(f'/api/admin/workflows/{rid}',headers=h,json={'data':{'enabled':True}}).status_code==200
