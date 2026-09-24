from sqlalchemy import insert, update
from app.db import engine, users, kpi_templates, kpi_targets


def test_overall_submission_approval(client, login, csrf_headers):
    person=login(client)['user']
    with engine.begin() as c:
        c.execute(update(users).where(users.c.id==person['id']).values(category='Presales Lead'))
        tid=c.execute(insert(kpi_templates).values(category='Presales Lead',kra='Test',kpi='Summary test',active=True,sort_order=999)).inserted_primary_key[0]
        c.execute(insert(kpi_targets).values(template_id=tid,month='2035-01',target_value=10))
    client.cookies.clear()
    login(client)
    def post(path,data):
        return client.post(path,json={'data':data},headers=csrf_headers(client))
    def put(path,data):
        return client.put(path,json={'data':data},headers=csrf_headers(client))
    assert put('/api/kpi/actuals',{'template_id':tid,'month':'2035-01','actual_value':8}).status_code==200
    assert post('/api/kpi/submit',{'month':'2035-01','summary':'  '}).status_code==400
    assert post('/api/kpi/submit',{'month':'2035-01','summary':'Eight demos; two postponed.'}).status_code==200
    sub=client.get('/api/kpi/my?month=2035-01').json()['submission']
    assert sub['summary']=='Eight demos; two postponed.'
    assert put(f"/api/kpi/submissions/{sub['id']}/review",{'feedback':'Good work'}).status_code==403
    client.cookies.clear()
    login(client,email='admin@jsan.local')
    review=client.get('/api/kpi/review?month=2035-01').json()
    assert next(g for g in review if g['user_id']==person['id'])['submission']['id']==sub['id']
    assert put(f"/api/kpi/submissions/{sub['id']}/review",{'feedback':' '}).status_code==400
    assert put(f"/api/kpi/submissions/{sub['id']}/review",{'feedback':'Good work; follow up next month.'}).status_code==200
    approved=client.get('/api/kpi/review?month=2035-01').json()[0]['submission']
    assert approved['overall_percentage']==80
    assert approved['status']=='approved'
    client.cookies.clear()
    login(client)
    assert client.get('/api/kpi/my?month=2035-01').json()['submission']==approved
    assert put('/api/kpi/actuals',{'template_id':tid,'month':'2035-01','actual_value':9}).status_code==400
    assert post('/api/kpi/submit',{'month':'2035-01','summary':'Changed'}).status_code==400


def test_legacy_kpis_support_overall_feedback(client, login, csrf_headers):
    from app.db import kpi_actuals
    client.cookies.clear()
    person=login(client)['user']
    with engine.begin() as c:
        tid=c.execute(insert(kpi_templates).values(category='Presales',kra='Legacy',kpi='Old submission',active=True,sort_order=998)).inserted_primary_key[0]
        c.execute(insert(kpi_targets).values(template_id=tid,month='2035-02',target_value=10))
        c.execute(insert(kpi_actuals).values(user_id=person['id'],template_id=tid,month='2035-02',actual_value=6,status='submitted',remarks=''))
    client.cookies.clear()
    login(client,email='admin@jsan.local')
    group=client.get('/api/kpi/review?month=2035-02').json()[0]
    assert group['submission'] is None
    r=client.put('/api/kpi/review-overall',json={'data':{'user_id':person['id'],'category':'Presales Lead','month':'2035-02','feedback':'Reviewed existing work'}},headers=csrf_headers(client))
    assert r.status_code==200,r.text
    sub=client.get('/api/kpi/review?month=2035-02').json()[0]['submission']
    assert sub['feedback']=='Reviewed existing work'
    assert sub['overall_percentage']==60
    client.cookies.clear()
    login(client)
    assert client.get('/api/kpi/my?month=2035-02').json()['submission']==sub


def test_summary_survives_profile_change_and_draft_rows(client, login, csrf_headers):
    from app.db import kpi_submissions
    client.cookies.clear()
    person=login(client)['user']
    with engine.begin() as c:
        c.execute(insert(kpi_submissions).values(user_id=person['id'],category='Presales',month='2035-03',summary='Submitted work remains visible',status='submitted'))
        c.execute(update(users).where(users.c.id==person['id']).values(category='Business Development Manager'))
    client.cookies.clear()
    login(client,email='admin@jsan.local')
    group=client.get('/api/kpi/review?month=2035-03').json()[0]
    assert group['category']=='Presales Lead'
    assert group['submission']['summary']=='Submitted work remains visible'
    assert group['items']==[]
