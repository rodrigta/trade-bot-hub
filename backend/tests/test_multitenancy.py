"""Multi-tenancy + admin user-management tests for TradeHub."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "trader@tradehub.io")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "trade1234")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    return r


def _hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"]["is_admin"] is True
    return d["token"]


@pytest.fixture()
def fresh_user(admin_token):
    """Register a fresh test user. Cleaned up via admin DELETE at teardown."""
    email = f"qauser+{uuid.uuid4().hex[:8]}@example.com"
    password = "Passw0rd!"
    r = requests.post(f"{BASE_URL}/api/auth/register",
                      json={"name": "QA User", "email": email, "password": password},
                      timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"]["is_admin"] is False
    yield {"email": email, "password": password, "token": data["token"], "id": data["user"]["id"]}
    # Cleanup via admin
    requests.delete(f"{BASE_URL}/api/users/{data['user']['id']}",
                    headers=_hdr(admin_token), timeout=20)


# ---------------- Admin login (bug fix) ----------------
class TestAdminLogin:
    def test_admin_login_ok(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(admin_token))
        assert r.status_code == 200
        assert r.json()["is_admin"] is True
        assert r.json()["email"] == ADMIN_EMAIL

    def test_invalid_password_401(self):
        r = _login(ADMIN_EMAIL, "wrongpass")
        assert r.status_code == 401


# ---------------- Self-registration ----------------
class TestRegistration:
    def test_register_creates_user_with_6_tags(self, fresh_user):
        tok = fresh_user["token"]
        r = requests.get(f"{BASE_URL}/api/tags", headers=_hdr(tok))
        assert r.status_code == 200
        assert len(r.json()) == 6, f"expected 6 default tags, got {len(r.json())}"

    def test_duplicate_email_400(self, fresh_user):
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"name": "Dup", "email": fresh_user["email"],
                                "password": "another"}, timeout=20)
        assert r.status_code == 400


# ---------------- Data isolation (CRITICAL) ----------------
class TestDataIsolation:
    def test_admin_sees_seeded_workspace(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/analytics/overview", headers=_hdr(admin_token))
        assert r.status_code == 200
        assert r.json()["total_trades"] == 120
        strats = requests.get(f"{BASE_URL}/api/strategies", headers=_hdr(admin_token)).json()
        assert len(strats) == 3

    def test_new_user_workspace_empty(self, fresh_user):
        tok = fresh_user["token"]
        ov = requests.get(f"{BASE_URL}/api/analytics/overview", headers=_hdr(tok)).json()
        assert ov["total_trades"] == 0
        assert requests.get(f"{BASE_URL}/api/strategies", headers=_hdr(tok)).json() == []
        assert requests.get(f"{BASE_URL}/api/trades", headers=_hdr(tok)).json() == []
        assert requests.get(f"{BASE_URL}/api/alerts", headers=_hdr(tok)).json() == []

    def test_cross_account_isolation(self, admin_token, fresh_user):
        utok = fresh_user["token"]
        # New user creates strategy + trade
        strat_r = requests.post(f"{BASE_URL}/api/strategies", headers=_hdr(utok),
                                json={"name": "TEST_UserStrat", "asset_type": "stock",
                                      "approval_mode": "auto_execute",
                                      "auto_approve_seconds": 30,
                                      "message_template": "{action} {symbol}",
                                      "notify_platforms": [], "active": True,
                                      "order_defaults": {"order_type": "market", "quantity": 1}})
        assert strat_r.status_code == 200
        user_strat_id = strat_r.json()["id"]

        trade_r = requests.post(f"{BASE_URL}/api/trades", headers=_hdr(utok),
                                json={"symbol": "USRISO", "side": "long", "asset_type": "stock",
                                      "entry_price": 10, "exit_price": 12, "quantity": 5,
                                      "fees": 0, "status": "closed", "tags": [], "notes": "TEST_"})
        assert trade_r.status_code == 200
        user_trade_id = trade_r.json()["id"]

        # Admin's strategies (grab one to cross-check)
        admin_strats = requests.get(f"{BASE_URL}/api/strategies", headers=_hdr(admin_token)).json()
        admin_strat_id = admin_strats[0]["id"]

        # Admin should NOT see user's strategy or trade
        admin_strat_ids = {s["id"] for s in admin_strats}
        assert user_strat_id not in admin_strat_ids
        admin_trades = requests.get(f"{BASE_URL}/api/trades?symbol=USRISO",
                                    headers=_hdr(admin_token)).json()
        assert not any(t["id"] == user_trade_id for t in admin_trades)

        # User should NOT see admin strategy
        user_strats = requests.get(f"{BASE_URL}/api/strategies", headers=_hdr(utok)).json()
        assert not any(s["id"] == admin_strat_id for s in user_strats)

        # Cross-account by-id → 404
        r1 = requests.get(f"{BASE_URL}/api/strategies/{admin_strat_id}", headers=_hdr(utok))
        assert r1.status_code == 404
        r2 = requests.get(f"{BASE_URL}/api/strategies/{user_strat_id}", headers=_hdr(admin_token))
        assert r2.status_code == 404

        # Cleanup user strategy
        requests.delete(f"{BASE_URL}/api/strategies/{user_strat_id}", headers=_hdr(utok))


# ---------------- Admin user management ----------------
class TestAdminUserManagement:
    def test_list_users(self, admin_token, fresh_user):
        r = requests.get(f"{BASE_URL}/api/users", headers=_hdr(admin_token))
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) >= 2
        emails = {u["email"] for u in users}
        assert ADMIN_EMAIL in emails and fresh_user["email"] in emails
        for u in users:
            assert "trade_count" in u and "strategy_count" in u and "is_admin" in u

    def test_admin_create_user(self, admin_token):
        email = f"qauser+admincreate{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{BASE_URL}/api/users", headers=_hdr(admin_token),
                          json={"name": "AdminMade", "email": email, "password": "Passw0rd!"})
        assert r.status_code == 200
        uid = r.json()["id"]
        assert r.json()["is_admin"] is False
        # cleanup
        d = requests.delete(f"{BASE_URL}/api/users/{uid}", headers=_hdr(admin_token))
        assert d.status_code == 200

    def test_admin_delete_removes_data(self, admin_token):
        # Register a user
        email = f"qauser+deltest{uuid.uuid4().hex[:6]}@example.com"
        reg = requests.post(f"{BASE_URL}/api/auth/register",
                            json={"name": "Del", "email": email, "password": "Passw0rd!"})
        assert reg.status_code == 200
        uid = reg.json()["user"]["id"]
        utok = reg.json()["token"]
        # Create strategy + trade
        s = requests.post(f"{BASE_URL}/api/strategies", headers=_hdr(utok),
                         json={"name": "TEST_ToDelete", "asset_type": "stock",
                               "approval_mode": "auto_execute", "auto_approve_seconds": 30,
                               "message_template": "{action} {symbol}", "notify_platforms": [],
                               "active": True,
                               "order_defaults": {"order_type": "market", "quantity": 1}}).json()
        # Delete user
        d = requests.delete(f"{BASE_URL}/api/users/{uid}", headers=_hdr(admin_token))
        assert d.status_code == 200
        # Try login → 401
        r = _login(email, "Passw0rd!")
        assert r.status_code == 401

    def test_admin_cannot_delete_self(self, admin_token):
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(admin_token)).json()
        r = requests.delete(f"{BASE_URL}/api/users/{me['id']}", headers=_hdr(admin_token))
        assert r.status_code == 400


# ---------------- Authorization ----------------
class TestAuthorization:
    def test_non_admin_forbidden_user_endpoints(self, fresh_user):
        tok = fresh_user["token"]
        assert requests.get(f"{BASE_URL}/api/users", headers=_hdr(tok)).status_code == 403
        assert requests.post(f"{BASE_URL}/api/users", headers=_hdr(tok),
                             json={"email": "x@y.z", "password": "p"}).status_code == 403
        assert requests.delete(f"{BASE_URL}/api/users/anyid",
                               headers=_hdr(tok)).status_code == 403

    def test_no_bearer_401(self):
        assert requests.get(f"{BASE_URL}/api/strategies").status_code == 401
        assert requests.get(f"{BASE_URL}/api/trades").status_code == 401
        assert requests.get(f"{BASE_URL}/api/users").status_code == 401


# ---------------- Webhook ownership ----------------
class TestWebhookOwnership:
    def test_webhook_creates_alert_for_owner_only(self, admin_token, fresh_user):
        utok = fresh_user["token"]
        # Ensure user auto_trade off (default) so alert is held pending
        s = requests.post(f"{BASE_URL}/api/strategies", headers=_hdr(utok),
                        json={"name": "TEST_WHOwn", "asset_type": "stock",
                              "approval_mode": "auto_execute", "auto_approve_seconds": 30,
                              "message_template": "{action} {symbol}", "notify_platforms": [],
                              "active": True,
                              "order_defaults": {"order_type": "market", "quantity": 1}}).json()
        wh_token = s["webhook_token"]
        r = requests.post(f"{BASE_URL}/api/webhook/{wh_token}",
                         json={"action": "buy", "symbol": "WHOWN", "quantity": 1, "price": 5.0})
        assert r.status_code == 200
        aid = r.json()["alert_id"]

        # Owner sees alert
        user_alerts = requests.get(f"{BASE_URL}/api/alerts", headers=_hdr(utok)).json()
        assert any(a["id"] == aid for a in user_alerts)

        # Admin does NOT see it
        admin_alerts = requests.get(f"{BASE_URL}/api/alerts", headers=_hdr(admin_token)).json()
        assert not any(a["id"] == aid for a in admin_alerts)

        # cleanup
        requests.delete(f"{BASE_URL}/api/strategies/{s['id']}", headers=_hdr(utok))
