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


@pytest.fixture(scope="session", autouse=True)
def _enable_auto_trade_for_session(client):
    """The master Auto-Trade switch defaults to OFF; existing tests here assume
    auto_execute webhooks execute immediately, so enable it for the session and
    reset to OFF on teardown (per the new gating contract)."""
    client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": True})
    yield
    client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": False})
    client.post(f"{BASE_URL}/api/bot/broker", json={"connected": False})


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
    @pytest.fixture(autouse=True)
    def _autotrade_on(self, client):
        client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": True})
        client.post(f"{BASE_URL}/api/bot/mode", json={"live": False})
        yield

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


# --- Notification independence (decoupled from execution) ------------------
class TestNotificationIndependence:
    @pytest.fixture(autouse=True)
    def _autotrade_on(self, client):
        client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": True})
        yield

    def _make_strategy(self, client, mode, platforms=None, secs=2):
        payload = {"name": f"TEST_NI_{mode}", "approval_mode": mode,
                   "auto_approve_seconds": secs, "asset_type": "stock",
                   "message_template": "{action} {symbol} @ {price}",
                   "notify_platforms": platforms or ["telegram", "discord"],
                   "active": True,
                   "order_defaults": {"order_type": "market", "quantity": 1}}
        r = client.post(f"{BASE_URL}/api/strategies", json=payload)
        assert r.status_code == 200
        return r.json()

    def test_auto_execute_paper_logs_signal_and_creates_trade(self, client):
        """PAPER MODE SUCCESS: '⚡ SIGNAL' notification logged AND 1 bot trade AND alert 'executed'."""
        # ensure paper mode
        client.post(f"{BASE_URL}/api/bot/mode", json={"live": False})
        s = self._make_strategy(client, "auto_execute",
                                platforms=["telegram", "discord"])
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "NIPAPR", "quantity": 2, "price": 42.0},
                timeout=20)
            assert r.status_code == 200
            assert r.json()["status"] == "executed"
            aid = r.json()["alert_id"]

            # notifications: at least one per platform prefixed '⚡ SIGNAL:'
            notifs = client.get(f"{BASE_URL}/api/notifications").json()
            signal_rows = [n for n in notifs if n.get("alert_id") == aid
                           and n.get("message", "").startswith("⚡ SIGNAL:")]
            plats = {n["platform"] for n in signal_rows}
            assert "telegram" in plats and "discord" in plats, f"platforms={plats}"

            # exactly one trade
            trades = client.get(f"{BASE_URL}/api/trades?symbol=NIPAPR").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 1
            assert linked[0]["source"] == "bot"

            # alert status executed
            alerts = client.get(f"{BASE_URL}/api/alerts").json()
            target = next((a for a in alerts if a["id"] == aid), None)
            assert target and target["status"] == "executed"
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_auto_execute_live_failure_logs_signal_and_order_failed(self, client):
        """LIVE MODE FAILURE: '⚡ SIGNAL' logged, alert 'failed' w/ execution.error,
        ZERO trades, additional '⚠️ ORDER FAILED' notification present."""
        # switch to live; IBKR gateway unreachable in this env
        m = client.post(f"{BASE_URL}/api/bot/mode", json={"live": True})
        assert m.status_code == 200 and m.json()["mode"] == "live"
        s = self._make_strategy(client, "auto_execute",
                                platforms=["telegram", "discord"])
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "NILIVE", "quantity": 3, "price": 55.0},
                timeout=30)
            assert r.status_code == 200
            aid = r.json()["alert_id"]

            notifs = client.get(f"{BASE_URL}/api/notifications").json()
            row = [n for n in notifs if n.get("alert_id") == aid]
            signal_rows = [n for n in row if n["message"].startswith("⚡ SIGNAL:")]
            failed_rows = [n for n in row if n["message"].startswith("⚠️ ORDER FAILED:")]
            assert len(signal_rows) >= 1, "signal notif must be logged independent of exec"
            assert len(failed_rows) >= 1, "order-failed notif must be logged"

            # zero trades in live failure
            trades = client.get(f"{BASE_URL}/api/trades?symbol=NILIVE").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 0, f"expected 0 trades in live-failure, found {len(linked)}"

            # alert status 'failed' with execution.error populated
            alerts = client.get(f"{BASE_URL}/api/alerts").json()
            target = next((a for a in alerts if a["id"] == aid), None)
            assert target is not None
            assert target["status"] == "failed", f"got {target['status']}"
            assert target.get("execution", {}).get("error"), "execution.error must be set"
            assert not (target["execution"].get("filled"))
        finally:
            # RESET to paper regardless
            client.post(f"{BASE_URL}/api/bot/mode", json={"live": False})
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_require_approval_dispatches_approval_notification_before_execution(self, client):
        """require_approval webhook creates pending alert and dispatches
        approval-request notification (no SIGNAL/ORDER FAILED prefix) at receipt."""
        client.post(f"{BASE_URL}/api/bot/mode", json={"live": False})
        s = self._make_strategy(client, "require_approval",
                                platforms=["telegram"])
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "NIAPRV", "quantity": 1, "price": 10.0},
                timeout=20)
            assert r.json()["status"] == "pending_approval"
            aid = r.json()["alert_id"]

            notifs = client.get(f"{BASE_URL}/api/notifications").json()
            rows = [n for n in notifs if n.get("alert_id") == aid]
            assert len(rows) >= 1, "approval notification must be dispatched"
            # These approval notifications should NOT have SIGNAL/ORDER FAILED prefix
            assert not any(n["message"].startswith("⚡ SIGNAL:") for n in rows)
            assert not any(n["message"].startswith("⚠️ ORDER FAILED:") for n in rows)

            # Approving executes exactly one trade
            ap = client.post(f"{BASE_URL}/api/alerts/{aid}/approve")
            assert ap.status_code == 200 and ap.json()["status"] == "executed"
            trades = client.get(f"{BASE_URL}/api/trades?symbol=NIAPRV").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 1

            # Double approve guard still 400 and no duplicate trade
            ap2 = client.post(f"{BASE_URL}/api/alerts/{aid}/approve")
            assert ap2.status_code == 400
            trades2 = client.get(f"{BASE_URL}/api/trades?symbol=NIAPRV").json()
            linked2 = [t for t in trades2 if t.get("alert_id") == aid]
            assert len(linked2) == 1
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_auto_approve_timer_dispatches_notification_at_receipt(self, client):
        client.post(f"{BASE_URL}/api/bot/mode", json={"live": False})
        s = self._make_strategy(client, "auto_approve_timer",
                                platforms=["discord"], secs=2)
        try:
            r = requests.post(
                f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                json={"action": "buy", "symbol": "NITIMR", "quantity": 1, "price": 8.0},
                timeout=20)
            assert r.json()["status"] == "pending_approval"
            aid = r.json()["alert_id"]
            # notification recorded immediately at receipt
            notifs = client.get(f"{BASE_URL}/api/notifications").json()
            rows = [n for n in notifs if n.get("alert_id") == aid]
            assert len(rows) >= 1
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


# ===========================================================================
# NEW-FEATURE TESTS (merged into this module so pytest-xdist loadscope pins
# them to the same worker as the existing tests — global /api/settings state
# is shared, so serial-per-module execution avoids cross-test contamination).
# ===========================================================================
def _mk_strategy(client, mode="auto_execute", platforms=None, name_suffix=""):
    payload = {
        "name": f"TEST_NF_{mode}_{name_suffix}",
        "approval_mode": mode,
        "auto_approve_seconds": 2,
        "asset_type": "stock",
        "message_template": "{action} {symbol} @ {price}",
        "notify_platforms": platforms or [],
        "active": True,
        "order_defaults": {"order_type": "market", "quantity": 1},
    }
    r = client.post(f"{BASE_URL}/api/strategies", json=payload)
    assert r.status_code == 200
    return r.json()


class TestAutoTradeGating:
    def test_default_status_flags(self, client):
        client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": False})
        client.post(f"{BASE_URL}/api/bot/broker", json={"connected": False})
        r = client.get(f"{BASE_URL}/api/bot/status")
        assert r.status_code == 200
        d = r.json()
        assert not (d["auto_trade_enabled"])
        assert not (d["broker_connected"])

    def test_auto_execute_held_when_auto_trade_off(self, client):
        # ensure OFF
        client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": False})
        s = _mk_strategy(client, "auto_execute", platforms=["telegram"], name_suffix="held")
        try:
            r = requests.post(f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                              json={"action": "buy", "symbol": "HELDX", "quantity": 1, "price": 10.0},
                              timeout=20)
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "pending_approval"
            aid = body["alert_id"]

            # zero trades
            trades = client.get(f"{BASE_URL}/api/trades?symbol=HELDX").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 0

            # approval notif logged
            notifs = client.get(f"{BASE_URL}/api/notifications").json()
            rows = [n for n in notifs if n.get("alert_id") == aid
                    and n.get("message", "").startswith("🔔 APPROVAL NEEDED:")]
            assert len(rows) >= 1
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

    def test_auto_execute_runs_when_auto_trade_on(self, client):
        r = client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": True})
        assert r.status_code == 200 and r.json()["auto_trade_enabled"]
        s = _mk_strategy(client, "auto_execute", platforms=["telegram"], name_suffix="run")
        try:
            r = requests.post(f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                              json={"action": "buy", "symbol": "RUNX", "quantity": 2, "price": 20.0},
                              timeout=20)
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "executed"
            aid = body["alert_id"]

            trades = client.get(f"{BASE_URL}/api/trades?symbol=RUNX").json()
            linked = [t for t in trades if t.get("alert_id") == aid]
            assert len(linked) == 1

            notifs = client.get(f"{BASE_URL}/api/notifications").json()
            rel = [n for n in notifs if n.get("alert_id") == aid]
            signal_rows = [n for n in rel if n["message"].startswith("⚡ SIGNAL:")
                           and n.get("event") == "signal"]
            fill_rows = [n for n in rel if n["message"].startswith("✅ ORDER FILLED")
                         and n.get("event") == "order_success"]
            assert len(signal_rows) >= 1, "expected ⚡ SIGNAL notif with event=signal"
            assert len(fill_rows) >= 1, "expected ✅ ORDER FILLED notif with event=order_success"
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")
            client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": False})


# ---------------------------------------------------------------------------
# 2. Broker connect/disconnect
# ---------------------------------------------------------------------------
class TestBrokerConnect:
    def test_connect_disconnect_persists_host_port(self, client):
        # first set auto_trade + some settings we want preserved
        client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": True})
        client.put(f"{BASE_URL}/api/settings",
                   json={"telegram": {"personal": {"enabled": True, "bot_token": "pTok", "chat_id": "111"}},
                         "discord": {}, "whatsapp": {},
                         "ibkr": {}, "auto_trade_enabled": True})

        r = client.post(f"{BASE_URL}/api/bot/broker",
                        json={"connected": True, "host": "192.168.99.5", "port": 4001})
        assert r.status_code == 200
        assert r.json()["broker_connected"]

        st = client.get(f"{BASE_URL}/api/bot/status").json()
        assert st["broker_connected"]
        assert st["host"] == "192.168.99.5"
        assert st["port"] == 4001
        # auto_trade preserved
        assert st["auto_trade_enabled"]
        # settings.telegram preserved
        gs = client.get(f"{BASE_URL}/api/settings").json()
        assert gs["telegram"]["personal"]["bot_token"] == "pTok"

        # disconnect
        r = client.post(f"{BASE_URL}/api/bot/broker", json={"connected": False})
        assert not (r.status_code == 200 and r.json()["broker_connected"])
        st = client.get(f"{BASE_URL}/api/bot/status").json()
        assert not (st["broker_connected"])
        # host/port and other settings still there
        assert st["host"] == "192.168.99.5"
        assert st["auto_trade_enabled"]

        # cleanup
        client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": False})


# ---------------------------------------------------------------------------
# 3. Per-platform event filtering
# ---------------------------------------------------------------------------
class TestEventFiltering:
    def test_telegram_event_filter_excludes_and_includes_order_success(self, client):
        # Setup: auto-trade ON so auto_execute fires; telegram configured with dummy creds.
        client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": True})
        client.put(f"{BASE_URL}/api/settings", json={
            "telegram": {
                "personal": {"enabled": True, "bot_token": "dummy", "chat_id": "999"},
                "events": ["signal"],  # only signal, no order_success
            },
            "discord": {}, "whatsapp": {},
            "ibkr": {}, "auto_trade_enabled": True,
        })
        s = _mk_strategy(client, "auto_execute", platforms=["telegram"], name_suffix="evfilt1")
        try:
            r = requests.post(f"{BASE_URL}/api/webhook/{s['webhook_token']}",
                              json={"action": "buy", "symbol": "EVFLT1", "quantity": 1, "price": 5.0},
                              timeout=20)
            aid = r.json()["alert_id"]
            time.sleep(0.5)
            notifs = client.get(f"{BASE_URL}/api/notifications").json()
            rel = [n for n in notifs if n.get("alert_id") == aid and n["platform"] == "telegram"]
            signal_rows = [n for n in rel if n.get("event") == "signal"]
            success_rows = [n for n in rel if n.get("event") == "order_success"]
            assert len(signal_rows) >= 1, "expected telegram signal row"
            assert len(success_rows) == 0, f"expected NO telegram order_success row, got {len(success_rows)}"
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s['id']}")

        # Now include order_success and re-fire.
        client.put(f"{BASE_URL}/api/settings", json={
            "telegram": {
                "personal": {"enabled": True, "bot_token": "dummy", "chat_id": "999"},
                "events": ["signal", "order_success"],
            },
            "discord": {}, "whatsapp": {},
            "ibkr": {}, "auto_trade_enabled": True,
        })
        s2 = _mk_strategy(client, "auto_execute", platforms=["telegram"], name_suffix="evfilt2")
        try:
            r = requests.post(f"{BASE_URL}/api/webhook/{s2['webhook_token']}",
                              json={"action": "buy", "symbol": "EVFLT2", "quantity": 1, "price": 5.0},
                              timeout=20)
            aid = r.json()["alert_id"]
            time.sleep(0.5)
            notifs = client.get(f"{BASE_URL}/api/notifications").json()
            rel = [n for n in notifs if n.get("alert_id") == aid and n["platform"] == "telegram"]
            success_rows = [n for n in rel if n.get("event") == "order_success"]
            assert len(success_rows) >= 1, "expected telegram order_success row now that it's opted in"
        finally:
            client.delete(f"{BASE_URL}/api/strategies/{s2['id']}")
            client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": False})


# ---------------------------------------------------------------------------
# 4. Telegram personal + group
# ---------------------------------------------------------------------------
class TestTelegramPersonalGroup:
    def test_two_targets_produce_two_rows(self, client):
        client.put(f"{BASE_URL}/api/settings", json={
            "telegram": {
                "personal": {"enabled": True, "bot_token": "x", "chat_id": "111"},
                "group":    {"enabled": True, "bot_token": "y", "chat_id": "-100222"},
            },
            "discord": {}, "whatsapp": {}, "ibkr": {}, "auto_trade_enabled": False,
        })
        r = client.post(f"{BASE_URL}/api/notifications/test", json={"platform": "telegram"})
        assert r.status_code == 200
        time.sleep(0.3)
        notifs = client.get(f"{BASE_URL}/api/notifications").json()
        # Find the two most recent telegram test rows
        tg_test = [n for n in notifs if n["platform"] == "telegram" and n.get("event") == "test"]
        assert len(tg_test) >= 2
        # Look within top-6 to find the pair produced by this call
        recent = tg_test[:6]
        targets = {n.get("target") for n in recent}
        assert "personal" in targets and "group" in targets, f"targets seen: {targets}"


# ---------------------------------------------------------------------------
# 5. /api/notifications/test endpoint
# ---------------------------------------------------------------------------
class TestNotificationsTestEndpoint:
    @pytest.mark.parametrize("platform", ["discord", "whatsapp"])
    def test_not_configured_returns_ok_false_and_logs_row(self, client, platform):
        # clear out that platform's config
        client.put(f"{BASE_URL}/api/settings", json={
            "telegram": {}, "discord": {}, "whatsapp": {},
            "ibkr": {}, "auto_trade_enabled": False,
        })
        r = client.post(f"{BASE_URL}/api/notifications/test", json={"platform": platform})
        assert r.status_code == 200
        body = r.json()
        assert not (body["ok"])
        # detail contains not_configured error
        detail = body["detail"]
        # discord returns dict; telegram returns list; whatsapp returns dict
        if isinstance(detail, list):
            assert any((d.get("error") == "not_configured") for d in detail)
        else:
            assert detail.get("error") == "not_configured"

        time.sleep(0.2)
        notifs = client.get(f"{BASE_URL}/api/notifications").json()
        test_rows = [n for n in notifs if n["platform"] == platform and n.get("event") == "test"]
        assert len(test_rows) >= 1

    def test_telegram_not_configured(self, client):
        client.put(f"{BASE_URL}/api/settings", json={
            "telegram": {}, "discord": {}, "whatsapp": {},
            "ibkr": {}, "auto_trade_enabled": False,
        })
        r = client.post(f"{BASE_URL}/api/notifications/test", json={"platform": "telegram"})
        assert r.status_code == 200
        assert not (r.json()["ok"])


# ---------------------------------------------------------------------------
# 6. Settings persistence
# ---------------------------------------------------------------------------
class TestSettingsPersistence:
    def test_full_roundtrip(self, client):
        payload = {
            "telegram": {
                "events": ["signal", "order_failure"],
                "personal": {"enabled": True, "bot_token": "tp", "chat_id": "1"},
                "group": {"enabled": True, "bot_token": "tg", "chat_id": "-99"},
            },
            "discord": {"events": ["signal"], "chat_type": "personal", "webhook_url": "https://x"},
            "whatsapp": {"events": ["order_success"], "account_sid": "sid",
                         "auth_token": "tok", "from_number": "whatsapp:+1", "to_number": "whatsapp:+2"},
            "ibkr": {"host": "10.0.0.1", "port": 7497, "enabled": False},
            "auto_trade_enabled": True,
        }
        u = client.put(f"{BASE_URL}/api/settings", json=payload)
        assert u.status_code == 200
        g = client.get(f"{BASE_URL}/api/settings").json()

        assert g["telegram"]["personal"]["bot_token"] == "tp"
        assert g["telegram"]["group"]["chat_id"] == "-99"
        assert g["telegram"]["events"] == ["signal", "order_failure"]
        assert g["discord"]["chat_type"] == "personal"
        assert g["discord"]["events"] == ["signal"]
        assert g["whatsapp"]["events"] == ["order_success"]
        assert g["ibkr"]["host"] == "10.0.0.1"
        assert g["auto_trade_enabled"]

        # cleanup: reset auto_trade
        client.post(f"{BASE_URL}/api/bot/auto-trade", json={"enabled": False})
