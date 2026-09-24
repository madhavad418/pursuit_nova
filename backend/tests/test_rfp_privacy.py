from sqlalchemy import select, insert
from app.db import engine, users, roles, rfps, rfp_documents, audit_logs


def test_rfp_privacy_matrix(client, login, csrf_headers):
    accounts=[]
    with engine.begin() as c:
        password=c.execute(select(users.c.password_hash).where(users.c.email=='bd.exec1@jsan.local')).scalar_one()
        for i, role in enumerate(['Presales Lead','Presales Lead','Admin','Admin','Super Admin','Super Admin']):
            role_id=c.execute(select(roles.c.id).where(roles.c.name==role)).scalar_one()
            email=f'rfp-matrix-{i}@jsan.local'
            uid=c.execute(insert(users).values(name=f'RFP Matrix {i}',email=email,password_hash=password,role_id=role_id,active=True)).inserted_primary_key[0]
            rid=c.execute(insert(rfps).values(name=f'PrivacyMatrix tender {i}',created_by=uid)).inserted_primary_key[0]
            did=c.execute(insert(rfp_documents).values(rfp_id=rid,filename=f'PrivacyMatrix-{i}.pdf',content_type='application/pdf',size_bytes=8,sha256='test',data=b'%PDF-1.7',uploaded_by=uid,category='general')).inserted_primary_key[0]
            c.execute(insert(audit_logs).values(user_id=uid,entity_type='rfp',entity_id=rid,action='CREATE',details='{}'))
            c.execute(insert(audit_logs).values(user_id=uid,entity_type='rfp_document',entity_id=did,action='CREATE',details='{}'))
            accounts.append((email,uid,rid,did))
    for i,(email,uid,rid,did) in enumerate(accounts):
        client.cookies.clear();login(client,email);h=csrf_headers(client)
        allowed={i} if i<2 else ({0,1,i} if i<4 else {0,1,2,3,i})
        visible={x['id'] for x in client.get('/api/rfps').json()['items']}
        expected={accounts[j][2] for j in allowed}
        assert visible & {x[2] for x in accounts} == expected
        search=client.get('/api/search?q=PrivacyMatrix').json()
        assert {x['id'] for x in search if x['type']=='RFP'}==expected
        if i>=2:
            audit=client.get('/api/audit-logs')
            assert audit.status_code==200,audit.text
            assert all(x['entity_id'] in expected for x in audit.json() if x['entity_type']=='rfp' and x['entity_id'] in {a[2] for a in accounts})
        for j,(_,_,other_rid,other_did) in enumerate(accounts):
            path=f'/api/rfps/{other_rid}'
            assert client.get(f'{path}/attachments/{other_did}').status_code==(200 if j in allowed else 404)
            if j not in allowed:
                assert client.post(f'{path}/approve',headers=h).status_code==(403 if i<2 else 404)
                assert client.put(path,json={'data':{'name':'Forbidden'}},headers=h).status_code==404
                assert client.delete(path,headers=h).status_code==404
                assert client.post(f'{path}/attachments',files={'file':('x.pdf',b'%PDF-1.7','application/pdf')},headers=h).status_code==404
                assert client.delete(f'{path}/attachments/{other_did}',headers=h).status_code==404
        created=client.post('/api/rfps',json={'data':{'name':'My own tender','created_by':accounts[0][1]}},headers=h)
        assert created.status_code==200,created.text
        assert created.json()['created_by']==uid

