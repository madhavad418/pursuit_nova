"""KPI review: each reviewable person carries their assigned regions and the currency each region
works in, so the review screen can show the conversion for every region — two regions, two rates."""
from app import main
from app.db import region_currency


def _admin(client, login):
    client.cookies.clear()
    login(client, email='superadmin@jsan.local')


def _reviewable(client, csrf_headers, region="India, UK"):
    """The seed assigns no KPI category, so give one active user a category and regions."""
    me = client.get('/api/auth/me').json()
    target = next(u for u in client.get('/api/users').json() if u["id"] != me["id"] and u.get("active", True))
    r = client.put(f'/api/users/{target["id"]}', json={"data": {"category": "Business Development Manager", "region": region}}, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    return target


def test_review_users_carry_regions_and_currencies(client, login, csrf_headers):
    _admin(client, login)
    _reviewable(client, csrf_headers)
    users = client.get('/api/kpi/users-with-category').json()
    assert users, "demo data has people with a KPI category"
    corp = main.norm_currency(main.corporate_currency())
    for u in users:
        assert isinstance(u["regions"], list) and isinstance(u["currencies"], list)
        assert len(u["currencies"]) == len(u["regions"])
        for x in u["currencies"]:
            assert x["currency"] == region_currency(x["region"], corp)


def test_two_regions_give_two_conversions(client, login, csrf_headers):
    _admin(client, login)
    target = _reviewable(client, csrf_headers, region="India, UK")
    try:
        u = next(x for x in client.get('/api/kpi/users-with-category').json() if x["id"] == target["id"])
        assert u["regions"] == ["India", "UK"]
        assert [x["currency"] for x in u["currencies"]] == ["INR", "GBP"], "one conversion per assigned region"
        assert {"INR", "GBP"} <= main.currencies_in_use(), "both count as in use, so a refresh fetches their rates"
    finally:
        client.put(f'/api/users/{target["id"]}', json={"data": {"region": target.get("region") or ""}}, headers=csrf_headers(client))


def test_review_list_is_scoped_to_the_requested_person(client, login, csrf_headers):
    _admin(client, login)
    _reviewable(client, csrf_headers)
    users = client.get('/api/kpi/users-with-category').json()
    month = main.date.today().strftime("%Y-%m")
    everyone = client.get(f'/api/kpi/review?month={month}').json()
    for u in users[:3]:
        mine = client.get(f'/api/kpi/review?month={month}&user_id={u["id"]}').json()
        assert all(g["user_id"] == u["id"] for g in mine)
        assert len(mine) <= len(everyone)
