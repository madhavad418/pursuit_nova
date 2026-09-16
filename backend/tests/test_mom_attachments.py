import io
import zipfile

DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def make_docx(text='Minutes of meeting', macro=False, extra_parts=None):
    """Build a small but genuine .docx in memory."""
    ct_main = 'application/vnd.ms-word.document.macroEnabled.main+xml' if macro else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="{ct_main}"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
        for name, data in (extra_parts or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


def _setup(client, login, csrf_headers, email='bd.exec1@jsan.local'):
    client.cookies.clear()
    login(client, email=email)
    lead = next(l for l in client.get('/api/leads').json())
    r = client.post(f"/api/leads/{lead['id']}/moms", json={'data': {'summary': 'Kick-off call'}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    return lead, r.json()


def _upload(client, csrf_headers, mom_id, name, data, content_type=DOCX_MIME, headers=True):
    return client.post(f'/api/moms/{mom_id}/attachments', files={'file': (name, data, content_type)}, headers=csrf_headers(client) if headers else {})


def test_upload_view_download_and_delete_docx(client, login, csrf_headers):
    lead, mom = _setup(client, login, csrf_headers)
    doc = make_docx('Agreed next steps: pilot in October')
    r = _upload(client, csrf_headers, mom['id'], 'Kickoff MoM.docx', doc)
    assert r.status_code == 200, r.text
    att = r.json()
    assert att['filename'] == 'Kickoff MoM.docx' and att['size_bytes'] == len(doc) and att['can_delete']

    # Shows up on the prospect page, without the file bytes
    detail = client.get(f"/api/leads/{lead['id']}").json()
    listed = next(m for m in detail['moms'] if m['id'] == mom['id'])['attachments']
    assert [a['filename'] for a in listed] == ['Kickoff MoM.docx'] and 'data' not in listed[0]

    # Download returns the exact same bytes as a Word file, never cached, never rendered inline
    d = client.get(f"/api/moms/{mom['id']}/attachments/{att['id']}")
    assert d.status_code == 200 and d.content == doc
    assert d.headers['content-type'].startswith(DOCX_MIME)
    assert d.headers['content-disposition'].startswith('attachment;') and 'Kickoff%20MoM.docx' in d.headers['content-disposition']
    assert 'no-store' in d.headers['cache-control'] and d.headers['x-content-type-options'] == 'nosniff'

    # Wrong MoM id for this attachment -> not found
    other = client.post(f"/api/leads/{lead['id']}/moms", json={'data': {'summary': 'Second call'}}, headers=csrf_headers(client)).json()
    assert client.get(f"/api/moms/{other['id']}/attachments/{att['id']}").status_code == 404

    # Uploader can delete it
    assert client.delete(f"/api/moms/{mom['id']}/attachments/{att['id']}", headers=csrf_headers(client)).status_code == 200
    assert client.get(f"/api/moms/{mom['id']}/attachments/{att['id']}").status_code == 404


def test_rejects_non_docx_and_unsafe_files(client, login, csrf_headers):
    _, mom = _setup(client, login, csrf_headers)
    m = mom['id']
    assert _upload(client, csrf_headers, m, 'notes.pdf', b'%PDF-1.7 fake').status_code == 400          # wrong extension
    assert _upload(client, csrf_headers, m, 'renamed.docx', b'MZ\x90\x00 not a zip').status_code == 400  # renamed binary
    assert _upload(client, csrf_headers, m, 'empty.docx', b'').status_code == 400
    assert _upload(client, csrf_headers, m, 'macro.docx', make_docx(macro=True)).status_code == 400
    assert _upload(client, csrf_headers, m, 'vba.docx', make_docx(extra_parts={'word/vbaProject.bin': b'\x00' * 10})).status_code == 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('hello.txt', 'a plain zip, not Word')
    assert _upload(client, csrf_headers, m, 'zip.docx', buf.getvalue()).status_code == 400
    assert _upload(client, csrf_headers, m, 'big.docx', b'PK\x03\x04' + b'0' * (10 * 1024 * 1024)).status_code == 413
    bomb = make_docx(extra_parts={'word/media/huge.bin': b'\x00' * (101 * 1024 * 1024)})
    assert len(bomb) < 10 * 1024 * 1024
    assert _upload(client, csrf_headers, m, 'bomb.docx', bomb).status_code == 400
    # Path-like names are reduced to a safe base name
    r = _upload(client, csrf_headers, m, '..\\..\\evil<script>.docx', make_docx())
    assert r.status_code == 200 and r.json()['filename'] == 'evilscript.docx'
    # CSRF header is required
    assert _upload(client, csrf_headers, m, 'ok.docx', make_docx(), headers=False).status_code == 403


def test_attachment_access_follows_prospect_visibility(client, login, csrf_headers):
    lead, mom = _setup(client, login, csrf_headers, email='bd.exec1@jsan.local')
    att = _upload(client, csrf_headers, mom['id'], 'private.docx', make_docx()).json()

    # A peer who cannot see the prospect cannot download, upload or delete
    client.cookies.clear(); login(client, email='bd.exec2@jsan.local')
    assert lead['id'] not in {l['id'] for l in client.get('/api/leads').json()}
    assert client.get(f"/api/moms/{mom['id']}/attachments/{att['id']}").status_code == 404
    assert _upload(client, csrf_headers, mom['id'], 'x.docx', make_docx()).status_code == 404
    assert client.delete(f"/api/moms/{mom['id']}/attachments/{att['id']}", headers=csrf_headers(client)).status_code == 404

    # A manager who can see it may download but not delete someone else's file
    client.cookies.clear(); login(client, email='bd.lead@jsan.local')
    assert client.get(f"/api/moms/{mom['id']}/attachments/{att['id']}").status_code == 200
    assert client.delete(f"/api/moms/{mom['id']}/attachments/{att['id']}", headers=csrf_headers(client)).status_code == 403

    # Admin may delete
    client.cookies.clear(); login(client, email='superadmin@jsan.local')
    assert client.delete(f"/api/moms/{mom['id']}/attachments/{att['id']}", headers=csrf_headers(client)).status_code == 200
