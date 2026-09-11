from datetime import date

def test_field_permission_presales_masks_final_amount(client, login):
    login(client,'presales@jsan.local')
    os=client.get('/api/opportunities'); assert os.status_code==200
    if os.json(): assert 'final_amount' in os.json()[0] and os.json()[0]['final_amount'] is None

def test_currency_endpoint_and_fx_normalized_forecast(client, login):
    login(client,'director@jsan.local')
    c=client.get('/api/admin/currency'); assert c.status_code==200; assert c.json()['corporate_currency']=='USD'
    q=f"Q{((date.today().month-1)//3)+1}"
    f=client.get(f'/api/forecast/summary?year={date.today().year}&quarter={q}'); assert f.status_code==200
    assert f.json()['currency']=='USD' and 'fx_as_of' in f.json()

def test_saved_views_and_dashboard_preferences(client, login, csrf_headers):
    login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    r=client.post('/api/saved-views',headers=h,json={'data':{'module':'leads','name':'My Hot','filters':{'temperature':'Hot'},'columns':['company_name','temperature'],'is_default':True}}); assert r.status_code==200, r.text
    views=client.get('/api/saved-views?module=leads'); assert views.status_code==200 and any(v['name']=='My Hot' for v in views.json())
    r=client.put('/api/dashboard/preferences',headers=h,json={'data':{'widgets':['quarterTrend','funnel','attention'],'layout':{'density':'comfortable'}}}); assert r.status_code==200
    pref=client.get('/api/dashboard/preferences'); assert pref.status_code==200 and 'quarterTrend' in pref.json()['widgets_json']

def test_server_side_pagination(client, login):
    login(client,'director@jsan.local')
    for path in ('/api/query/companies?page=1&page_size=2','/api/query/leads?page=1&page_size=2','/api/query/opportunities?page=1&page_size=2'):
        r=client.get(path); assert r.status_code==200; d=r.json(); assert len(d['items'])<=2 and d['page']==1 and 'total' in d

def test_monitoring_and_prometheus(client, login):
    login(client,'director@jsan.local')
    r=client.get('/api/monitoring/metrics'); assert r.status_code==200 and r.json()['product']=='JSAN PursuitNova'
    r=client.get('/metrics'); assert r.status_code==200 and 'pursuitnova_requests_total' in r.text

def test_microsoft_status_safe_when_unconfigured(client, login):
    login(client,'bd.exec1@jsan.local')
    r=client.get('/api/integrations/microsoft/status'); assert r.status_code==200 and r.json()['configured'] is False

def test_sql_injection_like_search_is_inert(client, login):
    login(client,'director@jsan.local')
    r=client.get('/api/query/leads',params={'q':"%' OR 1=1 --",'page':1,'page_size':10}); assert r.status_code==200
    assert isinstance(r.json()['items'],list)

def test_security_headers_and_unauthenticated_access(client):
    client.cookies.clear()
    r=client.get('/'); assert r.status_code==200
    assert r.headers.get('x-content-type-options')=='nosniff'
    assert r.headers.get('x-frame-options')=='DENY'
    assert 'frame-ancestors' in r.headers.get('content-security-policy','')
    assert client.get('/api/leads').status_code==401
    login=client.post('/api/auth/login',json={'email':'bd.exec1@jsan.local','password':'PursuitNovaDemo@2026'}); assert login.status_code==200
    cookies=login.headers.get('set-cookie','')
    assert 'HttpOnly' in cookies and 'SameSite=lax' in cookies

def test_field_level_edit_denied_for_presales(client, login, csrf_headers):
    login(client,'presales@jsan.local'); h=csrf_headers(client)
    os=client.get('/api/opportunities').json()
    if os:
        r=client.put(f"/api/opportunities/{os[0]['id']}",headers=h,json={'data':{'final_amount':999999}})
        assert r.status_code==403

def test_fx_normalization_changes_forecast_by_converted_value(client, login, csrf_headers):
    from datetime import date
    login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    q=f"Q{((date.today().month-1)//3)+1}"; year=date.today().year
    before=client.get(f'/api/forecast/summary?year={year}&quarter={q}').json()
    b=next(x for x in before['rows'] if x['user_id']==6)['pipeline']
    close=f"{year}-{date.today().month:02d}-{min(date.today().day+3,28):02d}"
    r=client.post('/api/leads/1/opportunities',headers=h,json={'data':{'name':'INR FX Regression Deal','status':'New Opportunity','forecast_category':'Pipeline','amount':100000,'currency':'INR','probability':25,'expected_close_date':close}})
    assert r.status_code==200, r.text
    after=client.get(f'/api/forecast/summary?year={year}&quarter={q}').json()
    a=next(x for x in after['rows'] if x['user_id']==6)['pipeline']
    assert round(a-b,2)==1200.00
    assert after['currency']=='USD'


def test_dynamic_field_permission_blocks_contact_email_edit(client, login, csrf_headers):
    login(client,'superadmin@jsan.local'); h=csrf_headers(client)
    perms=client.get('/api/admin/field-permissions').json()
    rule=next(x for x in perms if x['role']=='BD Executive' and x['entity_type']=='contact' and x['field_name']=='email')
    original_edit=bool(rule['can_edit'])
    r=client.put('/api/admin/field-permissions',headers=h,json={'data':{'role_id':rule['role_id'],'entity_type':'contact','field_name':'email','can_view':True,'can_edit':False}})
    assert r.status_code==200
    client.cookies.clear(); login(client,'bd.exec1@jsan.local'); h=csrf_headers(client)
    r=client.put('/api/contacts/1',headers=h,json={'data':{'email':'should-not-change@example.com'}})
    assert r.status_code==403
    # Restore the shared role configuration so this test cannot contaminate
    # later duplicate/contact regression scenarios in the same test session.
    client.cookies.clear(); login(client,'superadmin@jsan.local'); h=csrf_headers(client)
    r=client.put('/api/admin/field-permissions',headers=h,json={'data':{'role_id':rule['role_id'],'entity_type':'contact','field_name':'email','can_view':True,'can_edit':original_edit}})
    assert r.status_code==200
