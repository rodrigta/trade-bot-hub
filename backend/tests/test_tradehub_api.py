"""TradeHub backend API tests using pytest.
Covers auth, strategies, webhooks, alerts approval, trades, tags, analytics,
bot status, settings.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # Fallback to internal in case env not loaded for pytest CLI
    BASE_URL = "http://localhost:8001"

EMAIL = os.environ.get("ADMIN_EMAIL", "trader@tradehub.io")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "trade1234")


# --- Fixtures ---------------------------------------------------------------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Content-Type": "application/json"})
    return s


# --- Auth -------------------------------------------------------------------
class TestAuth:
    def test_login_success(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": EMAIL, "password": PASSWORD}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 20
        assert data["user"]["email"] == EMAIL

    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": EMAIL, "password": "wrong"}, timeout=20)
        assert r.status_code == 401

    def test_me_with_bearer(self, client):
        r = client.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == EMAIL

    def test_me_no_token(self):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401


# --- Strategies CRUD --------------------------------------------------------
class TestStrategies:
    def test_list_seeded(self, client):
        r = client.get(f"{BASE_URL}/api/strategies")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 3
        s = data[0]
        for f in ("id", "name", "webhook_url", "webhook_token",
                  "total_trades", "total_pnl", "win_rate"):
            assert f in s, f"missing {f}"
        assert s["webhook_url"].endswith(s["webhook_token"])

    def test_create_update_toggle_delete(self, client):
        payload = {"name": "TEST_Strat", "description": "test",
                   "asset_type": "stock", "approval_mode": "auto_execute",
                   "auto_approve_seconds": 30,
                   "message_template": "{action} {symbol}",
                   "notify_platforms": [], "active": True,
                   "order_defaults": {"order_type": "market", "quantity": 1}}
        r = client.post(f"{BASE_URL}/api/strategies", json=payload)
        assert r.status_code == 200
        s = r.json()
        sid = s["id"]
        assert s["webhook_token"].startswith("strat_")
        assert s["webhook_url"].endswith(s["webhook_token"])

        # GET
        r = client.get(f"{BASE_URL}/api/strategies/{sid}")
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Strat"

        # PUT
        payload["description"] = "updated"
        r = client.put(f"{BASE_URL}/api/strategies/{sid}", json=payload)
        assert r.status_code == 200
        assert r.json()["description"] == "updated"

        # Toggle
        r = client.post(f"{BASE_URL}/api/strategies/{sid}/toggle")
        assert r.status_code == 200
        assert r.json()["active"] in (True, False)

        # Delete
        r = client.delete(f"{BASE_URL}/api/strategies/{sid}")
        assert r.status_code == 200
        r = client.get(f"{BASE_URL}/api/strategies/{sid}")
        assert r.status_code == 404


# --- Webhook + Approval flow ------------------------------------------------
class TestWebhookFlow:
    def _make_strategy(self, client, mode, secs=2):
        payload = {"name": f"TEST_WH_{mode}", "approval_mode": mode,
                   "auto_approve_seconds": secs, "asset_type": "stock",
                   "message_template": "{action} {symbol}",
                   "notify_platforms": [], "active": True,
                   "order_defaults": {"order_type": "market", "quantity": 1}}
        r = client.post(f"{BASE_URL}/api/strategies", json=payload)
        assert r.status_code == 200
        return r.json()

    def test_webhook_auto_execute(self, client):
        s = self._make_strategy(client, "auto_execute")
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "TESTX", "quantity": 5, "price": 100.0},
                timeout=20)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "executed"
            aid = r.json()["alert_id"]

            # Verify alert is executed and a bot trade exists
            r2 = client.get(f"{BASE_URL}/api/alerts?status=executed")
            assert r2.status_code == 200
            assert any(a["id"] == aid for a in r2.json())

            trades = client.get(f"{BASE_URL}/api/trades?symbol=TESTX").json()
            assert any(t.get("source") == "bot" and t.get("symbol") == "TESTX"
                       for t in trades)
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_webhook_require_approval_and_approve(self, client):
        s = self._make_strategy(client, "require_approval")
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "TESTY", "quantity": 3, "price": 50.0},
                timeout=20)
            assert r.status_code == 200
            assert r.json()["status"] == "pending_approval"
            aid = r.json()["alert_id"]

            pending = client.get(f"{BASE_URL}/api/alerts/pending").json()
            assert any(a["id"] == aid for a in pending)

            ra = client.post(f"{BASE_URL}/api/alerts/{aid}/approve")
            assert ra.status_code == 200
            assert ra.json()["status"] == "executed"
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_webhook_reject(self, client):
        s = self._make_strategy(client, "require_approval")
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "sell", "symbol": "TESTZ", "quantity": 1, "price": 10.0})
            aid = r.json()["alert_id"]
            rj = client.post(f"{BASE_URL}/api/alerts/{aid}/reject")
            assert rj.status_code == 200
            assert rj.json()["status"] == "rejected"
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_webhook_auto_approve_timer(self, client):
        s = self._make_strategy(client, "auto_approve_timer", secs=2)
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "TESTT", "quantity": 1, "price": 25.0})
            assert r.json()["status"] == "pending_approval"
            aid = r.json()["alert_id"]
            # poll
            time.sleep(4)
            alerts = client.get(f"{BASE_URL}/api/alerts").json()
            target = next((a for a in alerts if a["id"] == aid), None)
            assert target and target["status"] == "executed"
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_webhook_unknown_token(self):
        r = requests.post(f"{BASE_URL}/api/webhook/bogus_token",
                          json={"action": "buy", "symbol": "X"})
        assert r.status_code == 404

    # --- Regression: duplicate-execution guard in execute_alert() -----------
    def test_double_approve_returns_400_no_duplicate_trade(self, client):
        """Approving an already-approved/executed alert must 400 and NOT
        create a second bot trade for the same alert_id."""
        s = self._make_strategy(client, "require_approval")
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "DUPCHK", "quantity": 2, "price": 77.0},
                timeout=20)
            assert r.json()["status"] == "pending_approval"
            aid = r.json()["alert_id"]

            # First approve -> executed
            r1 = client.post(f"{BASE_URL}/api/alerts/{aid}/approve")
            assert r1.status_code == 200
            assert r1.json()["status"] == "executed"

            # Second approve -> must 400 because status is no longer 'pending'
            r2 = client.post(f"{BASE_URL}/api/alerts/{aid}/approve")
            assert r2.status_code == 400, f"expected 400, got {r2.status_code}: {r2.text}"

            # Verify exactly ONE trade exists for this alert_id
            trades = client.get(f"{BASE_URL}/api/trades?symbol=DUPCHK").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 1, f"expected exactly 1 trade for alert {aid}, found {len(linked)}"
            assert linked[0]["source"] == "bot"
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_reject_then_approve_returns_400_no_trade(self, client):
        """A rejected alert must not be approvable and must have no bot trade."""
        s = self._make_strategy(client, "require_approval")
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "sell", "symbol": "REJCHK", "quantity": 1, "price": 12.0},
                timeout=20)
            aid = r.json()["alert_id"]

            rj = client.post(f"{BASE_URL}/api/alerts/{aid}/reject")
            assert rj.status_code == 200
            assert rj.json()["status"] == "rejected"

            # Approving a rejected alert must 400
            ap = client.post(f"{BASE_URL}/api/alerts/{aid}/approve")
            assert ap.status_code == 400, ap.text

            # No bot trade should exist for this alert_id
            trades = client.get(f"{BASE_URL}/api/trades?symbol=REJCHK").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 0
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_auto_execute_creates_exactly_one_trade(self, client):
        """auto_execute webhook must create exactly one bot trade for the alert."""
        s = self._make_strategy(client, "auto_execute")
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "ONECHK", "quantity": 4, "price": 33.0},
                timeout=20)
            assert r.json()["status"] == "executed"
            aid = r.json()["alert_id"]
            trades = client.get(f"{BASE_URL}/api/trades?symbol=ONECHK").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 1
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_auto_approve_timer_creates_exactly_one_trade(self, client):
        """auto_approve_timer must auto-execute exactly once."""
        s = self._make_strategy(client, "auto_approve_timer", secs=2)
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "TMRCHK", "quantity": 1, "price": 19.0},
                timeout=20)
            aid = r.json()["alert_id"]
            time.sleep(4)
            alerts = client.get(f"{BASE_URL}/api/alerts").json()
            target = next((a for a in alerts if a["id"] == aid), None)
            assert target and target["status"] == "executed"
            trades = client.get(f"{BASE_URL}/api/trades?symbol=TMRCHK").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 1
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")


# --- Trades / Journal -------------------------------------------------------
class TestTrades:
    def test_list_filters(self, client):
        r = client.get(f"{BASE_URL}/api/trades")
        assert r.status_code == 200
        assert len(r.json()) >= 50

    def test_create_long_pnl(self, client):
        payload = {"symbol": "TESTPNL", "side": "long", "asset_type": "stock",
                   "entry_price": 100, "exit_price": 110, "quantity": 10,
                   "fees": 5, "status": "closed", "risk_amount": 50,
                   "tags": [], "notes": "TEST_"}
        r = client.post(f"{BASE_URL}/api/trades", json=payload)
        assert r.status_code == 200
        t = r.json()
        # (110-100)*10*1 - 5 = 95
        assert t["pnl"] == 95.0
        assert t["r_multiple"] == round(95 / 50, 2)
        tid = t["id"]

        # GET persistence
        g = client.get(f"{BASE_URL}/api/trades/{tid}").json()
        assert g["pnl"] == 95.0

        # Update -> short
        payload["side"] = "short"
        payload["exit_price"] = 90
        u = client.put(f"{BASE_URL}/api/trades/{tid}", json=payload)
        assert u.status_code == 200
        # short: (90-100)*-1*10 - 5 = 95
        assert u.json()["pnl"] == 95.0

        # delete
        d = client.delete(f"{BASE_URL}/api/trades/{tid}")
        assert d.status_code == 200
        assert client.get(f"{BASE_URL}/api/trades/{tid}").status_code == 404

    def test_create_option_multiplier(self, client):
        payload = {"symbol": "TESTOPT", "side": "long", "asset_type": "option",
                   "entry_price": 2.0, "exit_price": 3.5, "quantity": 2,
                   "fees": 1, "status": "closed",
                   "option_expiry": "2026-07-17", "option_strike": 100,
                   "option_right": "call", "tags": [], "notes": "TEST_"}
        r = client.post(f"{BASE_URL}/api/trades", json=payload)
        assert r.status_code == 200
        # (3.5-2)*2*100 - 1 = 299
        assert r.json()["pnl"] == 299.0
        client.delete(f"{BASE_URL}/api/trades/{r.json()['id']}")


# --- Tags -------------------------------------------------------------------
class TestTags:
    def test_crud(self, client):
        r = client.get(f"{BASE_URL}/api/tags")
        assert r.status_code == 200 and len(r.json()) >= 6
        c = client.post(f"{BASE_URL}/api/tags",
                        json={"name": "TEST_TAG", "color": "#000", "type": "setup"})
        assert c.status_code == 200
        tid = c.json()["id"]
        d = client.delete(f"{BASE_URL}/api/tags/{tid}")
        assert d.status_code == 200


# --- Analytics --------------------------------------------------------------
class TestAnalytics:
    def test_overview(self, client):
        r = client.get(f"{BASE_URL}/api/analytics/overview")
        assert r.status_code == 200
        d = r.json()
        for f in ("total_pnl", "total_trades", "win_rate", "profit_factor",
                  "expectancy", "best_streak", "worst_streak"):
            assert f in d

    def test_equity(self, client):
        r = client.get(f"{BASE_URL}/api/analytics/equity-curve")
        assert r.status_code == 200
        d = r.json()
        assert "points" in d and "max_drawdown" in d
        assert len(d["points"]) > 0

    def test_calendar(self, client):
        from datetime import datetime
        now = datetime.utcnow()
        r = client.get(f"{BASE_URL}/api/analytics/calendar?year={now.year}&month={now.month}")
        assert r.status_code == 200
        assert "days" in r.json()

    @pytest.mark.parametrize("dim", ["symbol", "strategy", "tag", "side"])
    def test_by(self, client, dim):
        r = client.get(f"{BASE_URL}/api/analytics/by/{dim}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_mfe_mae_time_strategy(self, client):
        assert client.get(f"{BASE_URL}/api/analytics/mfe-mae").status_code == 200
        assert client.get(f"{BASE_URL}/api/analytics/time-of-day").status_code == 200
        assert client.get(f"{BASE_URL}/api/analytics/strategy-comparison").status_code == 200


# --- Bot status -------------------------------------------------------------
class TestBot:
    def test_status_and_mode(self, client):
        r = client.get(f"{BASE_URL}/api/bot/status")
        assert r.status_code == 200
        d = r.json()
        assert "ibkr_connected" in d and "mode" in d and "stats" in d

        m = client.post(f"{BASE_URL}/api/bot/mode", json={"live": False})
        assert m.status_code == 200
        assert m.json()["mode"] == "paper"


# --- Settings ---------------------------------------------------------------
class TestSettings:
    def test_get_put(self, client):
        r = client.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200
        payload = {"telegram": {"bot_token": "x", "chat_id": "y"},
                   "discord": {}, "whatsapp": {}, "ibkr": {"host": "127.0.0.1", "port": 7497, "enabled": False}}
        u = client.put(f"{BASE_URL}/api/settings", json=payload)
        assert u.status_code == 200
        g = client.get(f"{BASE_URL}/api/settings").json()
        assert g["telegram"]["bot_token"] == "x"
