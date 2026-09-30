from datetime import date


def _period():
    today = date.today()
    return today.year, f"Q{(today.month - 1) // 3 + 1}"


def test_source_breakdown_partitions_the_flat_rollups(client, login):
    """Clicking a lead-source slice filters the tables below, so each source's vertical and owner
    rows must add back up to the unfiltered tables."""
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')
    year, period = _period()
    data = client.get('/api/reports/period', params={'year': year, 'period': period}).json()

    breakdown = data['source_breakdown']
    assert [b['source'] for b in breakdown] == [s['source'] for s in data['sources']]

    for key, rows_key, metrics in (('vertical', 'verticals', ('leads', 'pipeline', 'won')),
                                   ('owner', 'owners', ('opportunities', 'pipeline', 'won'))):
        flat = {r[key]: r for r in data[rows_key]}
        totals = {}
        for b in breakdown:
            for r in b[rows_key]:
                assert r[key] in flat, f'{r[key]} only appears in the per-source {rows_key}'
                acc = totals.setdefault(r[key], dict.fromkeys(metrics, 0))
                for m in metrics:
                    acc[m] += r[m]
        assert set(totals) == set(flat), f'per-source {rows_key} must cover every flat row'
        for name, acc in totals.items():
            for m in metrics:
                assert round(acc[m], 2) == round(flat[name][m], 2), f'{rows_key}/{name}/{m}'
        # Highest pipeline first, same as the unfiltered table
        for b in breakdown:
            pipes = [r['pipeline'] for r in b[rows_key]]
            assert pipes == sorted(pipes, reverse=True)
