"""Report generation: the Reports tab.

A report is a saved question asked of data the caller can already see. The rule that matters is that
it cannot become a side door: every dataset reads through the same row helper its own page uses, so
a report never widens visibility, never shows a field a role may not view, and never drifts from
what that page reports. Export stays behind DATA_EXPORT, exactly as the older CSV endpoint did.
"""
import csv
import io

import pytest

SUPER, EXEC1, EXEC2, PRESALES = 'superadmin@jsan.local', 'bd.exec1@jsan.local', 'bd.exec2@jsan.local', 'presales@jsan.local'
DATASETS = ['opportunities', 'partner_opportunities', 'prospects', 'partnerships']


def _as(client, login, email):
    client.cookies.clear()
    return login(client, email=email)['user']


def _run(client, dataset='opportunities', **params):
    q = '&'.join(f'{k}={v}' for k, v in params.items() if v != '')
    return client.get(f'/api/reports/run?dataset={dataset}' + (f'&{q}' if q else ''))


# ------------------------------------------------------------------------------ the basics

def test_options_name_the_reports_and_the_filter_vocabularies(client, login):
    _as(client, login, SUPER)
    o = client.get('/api/reports/options').json()
    assert [d['key'] for d in o['datasets']] == DATASETS
    assert all(d['label'] and d['stages'] for d in o['datasets']), 'every report is named and filterable'
    assert o['can_export'] is True
    assert isinstance(o['owners'], list)


@pytest.mark.parametrize('dataset', DATASETS)
def test_every_report_runs_and_describes_its_own_columns(client, login, dataset):
    _as(client, login, SUPER)
    r = _run(client, dataset)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b['dataset'] == dataset and b['label']
    assert b['columns'] and all(c['key'] and c['label'] for c in b['columns'])
    keys = {c['key'] for c in b['columns']}
    for row in b['rows']:
        assert set(row) == keys, 'a row carries exactly the declared columns, no more'
    assert b['total'] >= len(b['rows'])
    assert b['generated_at']


def test_an_unknown_report_is_a_400_not_a_500(client, login):
    _as(client, login, SUPER)
    assert _run(client, 'not_a_dataset').status_code == 400


# --------------------------------------------------------------------------------- filters

def test_a_status_filter_narrows_to_exactly_that_status(client, login):
    _as(client, login, SUPER)
    everything = _run(client, 'opportunities').json()
    assert everything['total'], 'the fixture has opportunities to filter'
    status = everything['rows'][0]['status']
    only = _run(client, 'opportunities', status=status).json()
    assert only['total'] <= everything['total']
    assert {r['status'] for r in only['rows']} == {status}


def test_an_owner_filter_narrows_to_that_owner(client, login):
    _as(client, login, SUPER)
    o = client.get('/api/reports/options').json()
    if not o['owners']: pytest.skip('no owners in the fixture')
    owner = o['owners'][0]
    only = _run(client, 'opportunities', owner_id=owner['id']).json()
    assert {r['owner_name'] for r in only['rows']} <= {owner['name']}


def test_a_date_window_excludes_what_falls_outside_it(client, login):
    _as(client, login, SUPER)
    assert _run(client, 'opportunities', date_from='2099-01-01').json()['total'] == 0
    assert _run(client, 'opportunities', date_to='1999-12-31').json()['total'] == 0
    wide = _run(client, 'opportunities', date_from='1999-01-01', date_to='2099-12-31').json()
    assert wide['total'] == _run(client, 'opportunities').json()['total']


def test_the_search_term_matches_the_company_or_the_name(client, login):
    _as(client, login, SUPER)
    everything = _run(client, 'opportunities').json()
    term = (everything['rows'][0]['company_name'] or '')[:6]
    if not term.strip(): pytest.skip('no company name to search on')
    hits = _run(client, 'opportunities', q=term).json()
    assert hits['total'] >= 1
    for r in hits['rows']:
        assert term.lower() in f"{r['company_name']} {r['name']} {r['owner_name']}".lower()


# ------------------------------------------------------- a report is not a visibility side door

@pytest.mark.parametrize('dataset', DATASETS)
def test_a_report_shows_only_what_that_role_could_already_open(client, login, dataset):
    """The whole safety argument. A BD Executive's report must be a subset of the whole business,
    and must match the count the matching page would give them."""
    _as(client, login, SUPER)
    everyone = _run(client, dataset).json()['total']
    _as(client, login, EXEC1)
    mine = _run(client, dataset).json()['total']
    assert mine <= everyone, 'a report can only ever narrow'


def test_an_executive_report_matches_their_own_opportunity_list(client, login):
    _as(client, login, EXEC1)
    report = _run(client, 'opportunities').json()
    visible = client.get('/api/opportunities').json()
    assert report['total'] == len(visible), 'exactly the rows this user can open, no more and no fewer'


def test_one_executive_cannot_report_on_anothers_prospects(client, login, csrf_headers):
    _as(client, login, EXEC2)
    h = csrf_headers(client)
    me = client.get('/api/auth/me').json()
    created = client.post('/api/leads/full', json={'data': {
        'company': {'name': 'Report Scope Only Exec2 Ltd', 'vertical': 'Systems Integration'},
        'lead': {'owner_id': me['id']}, 'contacts': [],
    }}, headers=h)
    assert created.status_code == 200, created.text

    names = lambda: {r['company_name'] for r in _run(client, 'prospects', limit=2000).json()['rows']}
    assert 'Report Scope Only Exec2 Ltd' in names(), 'the owner sees their own record'
    _as(client, login, EXEC1)
    assert 'Report Scope Only Exec2 Ltd' not in names(), "another executive's prospect stays out"


def test_a_hidden_field_never_reaches_a_report(client, login):
    """A Presales Lead may not view final_amount, so no report column may carry it."""
    _as(client, login, PRESALES)
    for dataset in ('opportunities', 'partner_opportunities'):
        b = _run(client, dataset).json()
        assert 'final_amount' not in {c['key'] for c in b['columns']}


# ------------------------------------------------------------------------ preview vs the file

def test_the_preview_is_capped_and_says_so(client, login):
    _as(client, login, SUPER)
    b = _run(client, 'opportunities', limit=1).json()
    assert len(b['rows']) <= 1
    assert b['shown'] <= b['total']
    assert b['total'] == _run(client, 'opportunities').json()['total'], 'the true total is reported, not the slice'


def test_the_csv_carries_every_row_and_a_provenance_footer(client, login):
    _as(client, login, SUPER)
    b = _run(client, 'opportunities', limit=1).json()
    r = client.get('/api/reports/run.csv?dataset=opportunities')
    assert r.status_code == 200, r.text
    assert 'text/csv' in r.headers['content-type']
    assert 'attachment; filename=pursuitnova_opportunities_' in r.headers['content-disposition']

    parsed = list(csv.reader(io.StringIO(r.text)))
    header, body = parsed[0], [x for x in parsed[1:] if x]
    assert header == [c['label'] for c in b['columns']]
    footer = body[-1]
    assert footer[0].startswith('Generated ') and 'rows' in footer[1] and 'rates as of' in footer[2]
    assert len(body) - 1 == b['total'], 'the file holds the whole report, not the capped preview'


def test_export_stays_behind_the_export_permission(client, login):
    """BD roles can build and read reports; only the roles that already had DATA_EXPORT get the file."""
    _as(client, login, EXEC1)
    assert client.get('/api/reports/options').json()['can_export'] is False
    assert _run(client, 'opportunities').status_code == 200, 'reading is allowed'
    assert client.get('/api/reports/run.csv?dataset=opportunities').status_code == 403


def test_reports_need_a_session(client):
    client.cookies.clear()
    assert client.get('/api/reports/options').status_code == 401
    assert client.get('/api/reports/run?dataset=opportunities').status_code == 401


# ------------------------------------------------------------------------- converted amounts

def test_money_columns_carry_the_native_amount_and_a_corporate_equivalent(client, login):
    _as(client, login, SUPER)
    b = _run(client, 'opportunities').json()
    corp = b['currency'].lower()
    keys = {c['key'] for c in b['columns']}
    assert {'amount', 'currency', f'amount_{corp}'} <= keys
    for r in b['rows']:
        if r['currency'] == b['currency'] and r['amount']:
            assert r[f'amount_{corp}'] == pytest.approx(r['amount']), 'the corporate currency converts to itself'


# A real code no other suite puts into this shared database. It matters that it is unclaimed:
# test_fx_provider gives every currency *in use* a rate, so a code another suite has already booked a
# deal in is rated by the time this runs, and the assertion below would be testing nothing.
# BHD, KWD and OMR are taken by test_currency_totals, test_region_currency and the partnership suite.
REPORT_UNRATED = 'XPF'


def test_an_unrated_currency_leaves_the_converted_column_blank_not_zero(client, login, csrf_headers):
    """A blank is obviously missing; a 0 silently understates the row and any total taken from it."""
    _as(client, login, SUPER)
    assert REPORT_UNRATED not in client.get('/api/currency/rates').json()['rates'],         f'{REPORT_UNRATED} has acquired a rate — pick a code no other suite books a deal in'
    h = csrf_headers(client)
    lead_id = next(l['id'] for l in client.get('/api/leads').json())
    r = client.post(f'/api/leads/{lead_id}/opportunities',
                    json={'data': {'name': 'Report unrated currency', 'amount': 42_000, 'currency': REPORT_UNRATED}},
                    headers=h)
    assert r.status_code == 200, r.text

    b = _run(client, 'opportunities', q='Report unrated currency', limit=2000).json()
    corp = b['currency'].lower()
    row = next(x for x in b['rows'] if x['name'] == 'Report unrated currency')
    assert row['amount'] == 42_000 and row['currency'] == REPORT_UNRATED
    assert row[f'amount_{corp}'] == '', 'no rate means no converted figure, not a zero'
