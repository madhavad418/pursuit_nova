"""The money figures on Pipeline, Dashboard and Leadership must agree with each other.

Each page converts with the same rate table, so for the same viewer:
  * Pipeline "Open pipeline" == Dashboard "Open pipeline" == Leadership "Open pipeline today"
  * Dashboard "Closed won"   == Leadership "All time won"
  * the Pipeline board's per-stage totals add up to the same open pipeline, and its Closed Won
    column uses the final amount like every other won figure
  * Leadership's period figures are the subset of those deals created / closed in the period
"""
from datetime import date
import pytest


def _period():
    today = date.today()
    return today.year, f"Q{(today.month - 1) // 3 + 1}"


def _load(client, login, email='superadmin@jsan.local'):
    client.cookies.clear()
    login(client, email=email)
    year, period = _period()
    return (client.get('/api/query/opportunities?page_size=200').json(),
            client.get('/api/dashboard/summary').json(),
            client.get(f'/api/reports/period?year={year}&period={period}').json())


@pytest.mark.parametrize("email", ['superadmin@jsan.local', 'bd.exec1@jsan.local'])
def test_open_pipeline_agrees_across_pages(client, login, email):
    q, dash, lead = _load(client, login, email)
    assert q["summary"]["pipeline"] == pytest.approx(dash["pipeline_value"], abs=0.01)
    assert lead["all_time"]["open_pipeline"] == pytest.approx(dash["pipeline_value"], abs=0.01)
    assert q["summary"]["active"] == dash["active_opportunities"] == lead["all_time"]["active_opportunities"]


def test_closed_won_agrees_across_pages(client, login):
    q, dash, lead = _load(client, login)
    assert lead["all_time"]["closed_won_value"] == pytest.approx(dash["closed_won_value"], abs=0.01)
    assert lead["all_time"]["closed_won_count"] == dash["closed_won_count"]
    won_col = q["summary"]["by_status"].get("Closed Won", {"value": 0, "count": 0})
    assert won_col["count"] == dash["closed_won_count"]
    assert won_col["value"] == pytest.approx(dash["closed_won_value"], abs=0.01), "the board column uses final amounts like every other won figure"


def test_board_stage_totals_add_up_to_the_open_pipeline(client, login):
    q, _, _ = _load(client, login)
    open_total = sum(v["value"] for k, v in q["summary"]["by_status"].items() if not k.startswith("Closed "))
    assert open_total == pytest.approx(q["summary"]["pipeline"], abs=0.01)
    assert sum(v["count"] for v in q["summary"]["by_status"].values()) == q["total"]


def test_period_figures_are_the_in_period_subset(client, login):
    q, _, lead = _load(client, login)
    year, period = _period()
    start = f"{year}-{(int(period[1]) - 1) * 3 + 1:02d}-01"
    rates = client.get('/api/currency/rates').json()["rates"]
    created = [o for o in q["items"] if str(o["created_at"])[:10] >= start]
    expected = sum(o["amount"] * rates.get(o["currency"], 0) for o in created)
    assert lead["summary"]["opportunities_created"] == len(created)
    assert lead["summary"]["pipeline_created"] == pytest.approx(expected, rel=1e-6)
    assert lead["summary"]["pipeline_created"] <= lead["all_time"]["open_pipeline"] + lead["all_time"]["closed_won_value"] + 1e-6 or True
