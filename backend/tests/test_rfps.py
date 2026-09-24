import io
import zipfile

import app.main as main

DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def make_docx(text='RFP document'):
    """Build a small but genuine .docx in memory (same shape the MoM tests use)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


def fresh(client):
    client.cookies.clear()


def test_rfp_crud_and_validation(client, login, csrf_headers):
    fresh(client); login(client, 'director@jsan.local'); h = csrf_headers(client)
    r = client.post('/api/rfps', headers=h, json={'data': {
        'department': 'Telecom', 'country': 'India', 'region': 'APAC',
        'name': 'ABC Telecom Managed Services', 'description': 'National managed-services tender',
        'rfp_date': '2026-09-01', 'submission_eta': '2026-10-15', 'qa_timeline': 'Questions by 2026-09-20',
        'qa_status': 'Questions submitted', 'technical_response_given_by': 'Anita Rao', 'technical_response': 'JSAN governance model', 'pricing': 'USD 1.2M',
        'jsan_status': 'In progress', 'vendor_status': 'Initiated'}})
    assert r.status_code == 200, r.text
    rid = r.json()['id']

    lst = client.get('/api/rfps').json()
    assert lst['can_download'] is False  # director is not the download custodian
    assert lst['statuses'][0] == 'Initiated' and 'Close' in lst['statuses']
    item = next(x for x in lst['items'] if x['id'] == rid)
    assert item['name'] == 'ABC Telecom Managed Services' and item['jsan_status'] == 'In progress'
    assert (item['department'],item['country'],item['region']) == ('Telecom','India','APAC')
    assert item['technical_response_given_by']=='Anita Rao'
    assert item['document_count'] == 0 and 'data' not in item

    # Validation: bad statuses, bad date and a missing name are all rejected
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Bad', 'jsan_status': 'Won'}}).status_code == 400
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Bad', 'vendor_status': 'Lost'}}).status_code == 400
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Bad', 'qa_status': 'Maybe'}}).status_code == 400
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Bad', 'rfp_date': '01/10/2026'}}).status_code == 400
    assert client.post('/api/rfps', headers=h, json={'data': {'description': 'no name'}}).status_code == 400

    # Both participation tracks update independently
    u = client.put(f'/api/rfps/{rid}', headers=h, json={'data': {'technical_response_given_by':'Ravi Kumar', 'department': 'IT', 'country': 'France', 'region': '', 'jsan_status': 'Submitted', 'vendor_status': 'In progress', 'qa_status': 'Answers received'}})
    assert u.status_code == 200 and u.json()['jsan_status'] == 'Submitted' and u.json()['vendor_status'] == 'In progress'

    saved=next(x for x in client.get('/api/rfps').json()['items'] if x['id']==rid)
    assert saved['technical_response_given_by']=='Ravi Kumar'
    assert (saved['department'],saved['country'],saved['region']) == ('IT','France',None)
    assert client.delete(f'/api/rfps/{rid}', headers=h).status_code == 200
    assert all(x['id'] != rid for x in client.get('/api/rfps').json()['items'])


def test_every_user_can_manage_own_rfps(client, login, csrf_headers):
    # RFP access is available even without COMPANY_EDIT
    fresh(client); login(client, 'presales@jsan.local'); h = csrf_headers(client)
    assert client.get('/api/rfps').status_code == 200
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'My presales RFP'}}).status_code == 200


def test_rfp_document_view_open_download_custodian_only(client, login, csrf_headers, monkeypatch):
    fresh(client); login(client, 'director@jsan.local'); h = csrf_headers(client)
    rid = client.post('/api/rfps', headers=h, json={'data': {'name': 'Doc RFP'}}).json()['id']
    doc = make_docx('JSAN technical response')

    # CSRF is required; RFP documents accept a broad set of business file types...
    assert client.post(f'/api/rfps/{rid}/attachments', files={'file': ('x.docx', doc, DOCX_MIME)}).status_code == 403
    pdf = client.post(f'/api/rfps/{rid}/attachments', files={'file': ('notes.pdf', b'%PDF-1.7\n%mock', 'application/pdf')}, headers=h)
    assert pdf.status_code == 200, pdf.text
    assert pdf.json()['category'] == 'general'
    # ...but not arbitrary/dangerous ones, and content must match the claimed extension
    assert client.post(f'/api/rfps/{rid}/attachments', files={'file': ('notes.exe', b'MZ...', 'application/octet-stream')}, headers=h).status_code == 400
    assert client.post(f'/api/rfps/{rid}/attachments', files={'file': ('page.html', b'<script>1</script>', 'text/html')}, headers=h).status_code == 400
    assert client.post(f'/api/rfps/{rid}/attachments', files={'file': ('fake.pdf', b'not really a pdf', 'application/pdf')}, headers=h).status_code == 400

    up = client.post(f'/api/rfps/{rid}/attachments', files={'file': ('JSAN Technical Response.docx', doc, DOCX_MIME)}, data={'category': 'technical_response'}, headers=h)
    assert up.status_code == 200, up.text
    att = up.json(); did = att['id']
    assert att['filename'] == 'JSAN Technical Response.docx' and att['size_bytes'] == len(doc) and att['can_delete'] and att['category'] == 'technical_response'

    # The list exposes document metadata (including category) but never the bytes
    item = next(x for x in client.get('/api/rfps').json()['items'] if x['id'] == rid)
    assert item['document_count'] == 2 and all('data' not in x for x in item['documents'])
    assert {x['category'] for x in item['documents']} == {'general', 'technical_response'}

    # A non-custodian can still preview the bytes (COMPANY_VIEW is enough), served inline not as a download
    v = client.get(f'/api/rfps/{rid}/attachments/{did}')
    assert v.status_code == 200 and v.content == doc and v.headers['content-disposition'].startswith('inline;')

    # Once this login is the custodian, the same bytes come back as a real attachment download
    monkeypatch.setattr(main, 'RFP_DOWNLOAD_EMAIL', 'director@jsan.local')
    assert client.get('/api/rfps').json()['can_download'] is True
    d = client.get(f'/api/rfps/{rid}/attachments/{did}')
    assert d.status_code == 200 and d.content == doc
    assert d.headers['content-type'].startswith(DOCX_MIME)
    assert d.headers['content-disposition'].startswith('attachment;') and 'JSAN%20Technical%20Response.docx' in d.headers['content-disposition']
    assert 'no-store' in d.headers['cache-control'] and d.headers['x-content-type-options'] == 'nosniff'

    # Uploader removes it; deleting the RFP would also clear its documents
    assert client.delete(f'/api/rfps/{rid}/attachments/{did}', headers=h).status_code == 200
    assert client.get(f'/api/rfps/{rid}/attachments/{did}').status_code == 404

def test_pricing_workbook_upload(client, login, csrf_headers):
    from pathlib import Path
    fresh(client);login(client,'presales@jsan.local');h=csrf_headers(client)
    rid=client.post('/api/rfps',headers=h,json={'data':{'name':'Workbook pricing'}}).json()['id']
    workbook=Path(__file__).resolve().parents[2]/'frontend/public/templates/JSAN_GIS_Navigation_Pricing_Templates_v2.xlsx'
    data=workbook.read_bytes()
    path=f'/api/rfps/{rid}/attachments'
    response=client.post(path,headers=h,data={'category':'pricing'},files={'file':('pricing.xlsx',data,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert response.status_code==200,response.text
    assert response.json()['category']=='pricing'
    item=next(r for r in client.get('/api/rfps').json()['items'] if r['id']==rid)
    assert item['documents'][0]['filename']=='pricing.xlsx'
    assert item['documents'][0]['category']=='pricing'
    assert client.post(path,headers=h,data={'category':'pricing'},files={'file':('notes.pdf',b'%PDF-1.7','application/pdf')}).status_code==400

def test_rfp_approval_once_and_shared_status(client, login, csrf_headers):
    fresh(client);login(client,'presales@jsan.local')
    rid=client.post('/api/rfps',headers=csrf_headers(client),json={'data':{'name':'Approval test','technical_response_given_by':'Ravi'}}).json()['id']
    path=f'/api/rfps/{rid}/approve'
    assert client.post(path,headers=csrf_headers(client)).status_code==403
    fresh(client);login(client,'admin@jsan.local')
    item=next(r for r in client.get('/api/rfps').json()['items'] if r['id']==rid)
    assert item['can_approve'] and item['technical_response_given_by']=='Ravi'
    assert client.post(path).status_code==403
    approved=client.post(path,headers=csrf_headers(client))
    assert approved.status_code==200,approved.text
    assert approved.json()['approved_by_name']
    fresh(client);login(client,'superadmin@jsan.local')
    assert client.post(path,headers=csrf_headers(client)).status_code==409
    item=next(r for r in client.get('/api/rfps').json()['items'] if r['id']==rid)
    assert not item['can_approve'] and item['approved_by']==approved.json()['approved_by']
    assert item['approved_by_name']==approved.json()['approved_by_name']
    fresh(client);login(client,'presales@jsan.local')
    item=next(r for r in client.get('/api/rfps').json()['items'] if r['id']==rid)
    assert item['approved_by']==approved.json()['approved_by']
    assert item['approved_by_name']==approved.json()['approved_by_name']
    assert not item['can_approve']


def test_concurrent_rfp_approval_has_one_winner(client, login):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import insert,select
    from app.db import engine,rfps,users
    from fastapi import HTTPException
    fresh(client);admin=login(client,'admin@jsan.local')['user']
    fresh(client);superadmin=login(client,'superadmin@jsan.local')['user']
    with engine.begin() as c:
        owner=c.execute(select(users.c.id).where(users.c.email=='presales@jsan.local')).scalar_one()
        rid=c.execute(insert(rfps).values(name='Concurrent approval',created_by=owner)).inserted_primary_key[0]
    def approve(user):
        try: main.approve_rfp(rid,u=user);return 200
        except HTTPException as e: return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(approve,[admin,superadmin]))
    assert sorted(results)==[200,409]
