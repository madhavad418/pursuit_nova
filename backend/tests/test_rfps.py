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
        'name': 'ABC Telecom Managed Services', 'description': 'National managed-services tender',
        'rfp_date': '2026-09-01', 'submission_eta': '2026-10-15', 'qa_timeline': 'Questions by 2026-09-20',
        'qa_status': 'Questions submitted', 'technical_response': 'JSAN governance model', 'pricing': 'USD 1.2M',
        'jsan_status': 'In progress', 'vendor_status': 'Initiated'}})
    assert r.status_code == 200, r.text
    rid = r.json()['id']

    lst = client.get('/api/rfps').json()
    assert lst['can_download'] is False  # director is not the download custodian
    assert lst['statuses'][0] == 'Initiated' and 'Close' in lst['statuses']
    item = next(x for x in lst['items'] if x['id'] == rid)
    assert item['name'] == 'ABC Telecom Managed Services' and item['jsan_status'] == 'In progress'
    assert item['document_count'] == 0 and 'data' not in item

    # Validation: bad statuses, bad date and a missing name are all rejected
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Bad', 'jsan_status': 'Won'}}).status_code == 400
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Bad', 'vendor_status': 'Lost'}}).status_code == 400
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Bad', 'qa_status': 'Maybe'}}).status_code == 400
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Bad', 'rfp_date': '01/10/2026'}}).status_code == 400
    assert client.post('/api/rfps', headers=h, json={'data': {'description': 'no name'}}).status_code == 400

    # Both participation tracks update independently
    u = client.put(f'/api/rfps/{rid}', headers=h, json={'data': {'jsan_status': 'Submitted', 'vendor_status': 'In progress', 'qa_status': 'Answers received'}})
    assert u.status_code == 200 and u.json()['jsan_status'] == 'Submitted' and u.json()['vendor_status'] == 'In progress'

    assert client.delete(f'/api/rfps/{rid}', headers=h).status_code == 200
    assert all(x['id'] != rid for x in client.get('/api/rfps').json()['items'])


def test_rfp_view_needs_company_view_and_edit_needs_company_edit(client, login, csrf_headers):
    # Presales Lead has COMPANY_VIEW but not COMPANY_EDIT
    fresh(client); login(client, 'presales@jsan.local'); h = csrf_headers(client)
    assert client.get('/api/rfps').status_code == 200
    assert client.post('/api/rfps', headers=h, json={'data': {'name': 'Nope'}}).status_code == 403


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
