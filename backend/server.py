from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.responses import PlainTextResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
import logging
import uuid
import random
import secrets
import asyncio
import string
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import httpx

# ----------------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
APP_BASE_URL = os.environ.get('APP_BASE_URL', '')

app = FastAPI(title="TradeHub API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("tradehub")

UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id() -> str:
    return str(uuid.uuid4())

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

def create_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email,
               "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def gen_webhook_token() -> str:
    return "strat_" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))

async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def public_user(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u.get("name"), "is_admin": bool(u.get("is_admin"))}

# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------
class LoginIn(BaseModel):
    email: EmailStr
    password: str

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str = "Trader"

class OrderDefaults(BaseModel):
    order_type: str = "market"
    quantity: float = 1
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None

class StrategyIn(BaseModel):
    name: str
    description: str = ""
    asset_type: str = "stock"
    approval_mode: str = "auto_execute"
    auto_approve_seconds: int = 30
    message_template: str = "{action} {symbol} @ {price} (qty {quantity})"
    notify_platforms: List[str] = []
    active: bool = True
    order_defaults: OrderDefaults = OrderDefaults()

class TradeIn(BaseModel):
    symbol: str
    side: str = "long"
    asset_type: str = "stock"
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float = 1
    fees: float = 0
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    status: str = "closed"
    strategy_id: Optional[str] = None
    tags: List[str] = []
    notes: str = ""
    risk_amount: Optional[float] = None
    mfe: Optional[float] = None
    mae: Optional[float] = None
    option_expiry: Optional[str] = None
    option_strike: Optional[float] = None
    option_right: Optional[str] = None
    account: str = "paper"
    source: str = "manual"

class TagIn(BaseModel):
    name: str
    color: str = "#007AFF"
    type: str = "setup"

class SettingsIn(BaseModel):
    telegram: Dict[str, Any] = {}
    discord: Dict[str, Any] = {}
    whatsapp: Dict[str, Any] = {}
    ibkr: Dict[str, Any] = {}
    auto_trade_enabled: bool = False

# ----------------------------------------------------------------------------
# P&L computation
# ----------------------------------------------------------------------------
def compute_pnl(t: dict) -> dict:
    entry = t.get("entry_price")
    ex = t.get("exit_price")
    qty = t.get("quantity") or 0
    fees = t.get("fees") or 0
    mult = 100 if t.get("asset_type") == "option" else 1
    pnl = None
    if t.get("status") == "closed" and entry is not None and ex is not None:
        direction = 1 if t.get("side") == "long" else -1
        pnl = round((ex - entry) * direction * qty * mult - fees, 2)
    t["pnl"] = pnl
    risk = t.get("risk_amount")
    t["r_multiple"] = round(pnl / risk, 2) if (pnl is not None and risk) else None
    return t

# ----------------------------------------------------------------------------
# Notifications (outbound)
# ----------------------------------------------------------------------------
DEFAULT_EVENTS = ["signal", "order_success", "order_failure"]

async def get_settings(owner_id: str) -> dict:
    s = await db.settings.find_one({"id": owner_id}, {"_id": 0})
    return s or {"telegram": {}, "discord": {}, "whatsapp": {}, "ibkr": {}, "auto_trade_enabled": False}

async def _tg_send(token: str, chat: str, text: str, alert_id: str, with_actions: bool) -> dict:
    payload = {"chat_id": chat, "text": text}
    if with_actions:
        payload["reply_markup"] = {"inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve:{alert_id}"},
            {"text": "❌ Reject", "callback_data": f"reject:{alert_id}"},
        ]]}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
            ok = r.status_code == 200
            return {"ok": ok, "status": r.status_code, "detail": (None if ok else r.text[:300])}
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

async def send_telegram(text: str, alert_id: str, tg: dict, with_actions: bool = True) -> list:
    results = []
    for kind in ("personal", "group"):
        t = tg.get(kind) or {}
        if t.get("enabled") and t.get("bot_token") and t.get("chat_id"):
            r = await _tg_send(t["bot_token"], t["chat_id"], text, alert_id, with_actions)
            results.append({"target": kind, **r})
    if not results and tg.get("bot_token") and tg.get("chat_id"):
        r = await _tg_send(tg["bot_token"], tg["chat_id"], text, alert_id, with_actions)
        results.append({"target": "default", **r})
    if not results:
        results.append({"target": "telegram", "ok": False, "error": "not_configured"})
    return results

async def send_discord(text: str, dc: dict) -> dict:
    url = dc.get("webhook_url")
    if not url:
        return {"ok": False, "error": "not_configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, json={"embeds": [{"title": "TradeHub Alert", "description": text, "color": 31487}]})
            return {"ok": r.status_code in (200, 204), "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

async def send_whatsapp(text: str, wa: dict) -> dict:
    sid, tok = wa.get("account_sid"), wa.get("auth_token")
    frm, to = wa.get("from_number"), wa.get("to_number")
    if not (sid and tok and frm and to):
        return {"ok": False, "error": "not_configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                             data={"From": frm, "To": to, "Body": text}, auth=(sid, tok))
            return {"ok": r.status_code in (200, 201), "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

def render_template(tpl: str, alert: dict) -> str:
    out = tpl
    for k in ["symbol", "action", "price", "quantity", "order_type"]:
        out = out.replace("{" + k + "}", str(alert.get(k, "")))
    return out or f"{alert.get('action')} {alert.get('symbol')}"

async def _log_notif(alert, strategy, platform, msg, event, res, target=None):
    await db.notifications.insert_one({
        "id": new_id(), "owner_id": alert.get("owner_id") or strategy.get("owner_id"),
        "alert_id": alert.get("id"), "strategy_id": strategy.get("id"),
        "platform": platform, "target": target, "event": event, "message": msg,
        "status": "delivered" if res.get("ok") else "failed",
        "detail": res, "response": None, "sent_at": now_iso(), "responded_at": None,
    })

async def dispatch_notifications(strategy: dict, alert: dict, event: str = "signal",
                                 with_actions: bool = True, prefix: str = ""):
    """Send a notification to all configured platforms. Runs independently of
    order execution, using the strategy owner's saved credentials."""
    owner_id = strategy.get("owner_id") or alert.get("owner_id")
    settings = await get_settings(owner_id)
    msg = (prefix + render_template(strategy.get("message_template", ""), alert)).strip()
    for plat in strategy.get("notify_platforms", []):
        cfg = settings.get(plat) or {}
        if event not in (cfg.get("events") or DEFAULT_EVENTS):
            continue
        if plat == "telegram":
            for r in await send_telegram(msg, alert["id"], cfg, with_actions):
                await _log_notif(alert, strategy, "telegram", msg, event, r, r.get("target"))
        elif plat == "discord":
            r = await send_discord(msg, cfg)
            await _log_notif(alert, strategy, "discord", msg, event, r, cfg.get("chat_type"))
        elif plat == "whatsapp":
            r = await send_whatsapp(msg, cfg)
            await _log_notif(alert, strategy, "whatsapp", msg, event, r)

# ----------------------------------------------------------------------------
# IBKR execution (real if self-hosted, simulated fallback)
# ----------------------------------------------------------------------------
async def execute_via_ibkr(alert: dict, ibkr_cfg: dict) -> dict:
    host = ibkr_cfg.get("host", "127.0.0.1")
    port = int(ibkr_cfg.get("port", 7497))
    if ibkr_cfg.get("enabled"):
        try:
            from ib_insync import IB, Stock, Option, MarketOrder, LimitOrder
            ib = IB()
            await asyncio.wait_for(ib.connectAsync(host, port, clientId=random.randint(1, 9999)), timeout=5)
            if alert.get("asset_type") == "option":
                contract = Option(alert["symbol"], alert.get("option_expiry"),
                                  alert.get("option_strike"), alert.get("option_right", "C")[0].upper(), "SMART")
            else:
                contract = Stock(alert["symbol"], "SMART", "USD")
            ib.qualifyContracts(contract)
            action = "BUY" if alert.get("action") in ("buy", "long") else "SELL"
            qty = alert.get("quantity", 1)
            order = MarketOrder(action, qty) if alert.get("order_type") == "market" else LimitOrder(action, qty, alert.get("price"))
            ib.placeOrder(contract, order)
            await asyncio.sleep(1)
            fill_price = alert.get("price")
            ib.disconnect()
            return {"mode": "live", "filled": True, "fill_price": fill_price}
        except Exception as e:
            logger.warning(f"IBKR live order failed: {e}")
            return {"mode": "failed", "filled": False, "error": str(e) or type(e).__name__}
    base = alert.get("price") or round(random.uniform(50, 400), 2)
    return {"mode": "paper", "filled": True, "fill_price": round(base, 2)}

async def execute_alert(alert_id: str):
    alert = await db.alerts.find_one({"id": alert_id}, {"_id": 0})
    if not alert or alert["status"] not in ("pending", "approved"):
        return
    owner_id = alert.get("owner_id")
    settings = await get_settings(owner_id)
    try:
        result = await execute_via_ibkr(alert, settings.get("ibkr", {}))
    except Exception as e:
        result = {"mode": "failed", "filled": False, "error": str(e) or type(e).__name__}

    strategy = await db.strategies.find_one({"id": alert["strategy_id"]}, {"_id": 0})
    if not result.get("filled"):
        await db.alerts.update_one({"id": alert_id}, {"$set": {
            "status": "failed", "failed_at": now_iso(), "execution": result}})
        if strategy:
            await dispatch_notifications(strategy, alert, event="order_failure",
                                         with_actions=False, prefix="⚠️ ORDER FAILED: ")
        return

    side = "long" if alert.get("action") in ("buy", "long") else "short"
    trade = {
        "id": new_id(), "owner_id": owner_id, "symbol": alert["symbol"], "side": side,
        "asset_type": alert.get("asset_type", "stock"),
        "entry_price": result["fill_price"], "exit_price": None,
        "quantity": alert.get("quantity", 1), "fees": 0,
        "entry_time": now_iso(), "exit_time": None, "status": "open",
        "strategy_id": alert["strategy_id"], "tags": [], "notes": "Auto-logged from bot alert",
        "risk_amount": None, "mfe": None, "mae": None,
        "option_expiry": alert.get("option_expiry"), "option_strike": alert.get("option_strike"),
        "option_right": alert.get("option_right"),
        "account": result["mode"], "source": "bot", "alert_id": alert_id,
        "created_at": now_iso(),
    }
    trade = compute_pnl(trade)
    await db.trades.insert_one({**trade})
    await db.alerts.update_one({"id": alert_id}, {"$set": {
        "status": "executed", "executed_at": now_iso(),
        "execution": result, "trade_id": trade["id"]}})
    if strategy:
        await dispatch_notifications(strategy, alert, event="order_success", with_actions=False,
                                     prefix=f"✅ ORDER FILLED @ {result['fill_price']}: ")

async def auto_approve_timer(alert_id: str, seconds: int):
    await asyncio.sleep(seconds)
    alert = await db.alerts.find_one({"id": alert_id}, {"_id": 0})
    if alert and alert["status"] == "pending":
        await db.alerts.update_one({"id": alert_id}, {"$set": {"status": "approved"}})
        await execute_alert(alert_id)

# ----------------------------------------------------------------------------
# Auth routes
# ----------------------------------------------------------------------------
async def seed_user_tags(owner_id: str):
    for t in SETUP_TAGS:
        await db.tags.insert_one({"id": new_id(), "owner_id": owner_id, **t})

@api.post("/auth/login")
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user["id"], user["email"])
    return {"token": token, "user": public_user(user)}

@api.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = new_id()
    await db.users.insert_one({
        "id": uid, "email": email, "password_hash": hash_password(body.password),
        "name": body.name or "Trader", "is_admin": False, "created_at": now_iso(),
    })
    await seed_user_tags(uid)
    token = create_token(uid, email)
    return {"token": token, "user": {"id": uid, "email": email, "name": body.name, "is_admin": False}}

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

# ----------------------------------------------------------------------------
# User management (admin)
# ----------------------------------------------------------------------------
@api.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", 1).to_list(500)
    for u in users:
        u["is_admin"] = bool(u.get("is_admin"))
        u["trade_count"] = await db.trades.count_documents({"owner_id": u["id"]})
        u["strategy_count"] = await db.strategies.count_documents({"owner_id": u["id"]})
    return users

@api.post("/users")
async def create_user(body: RegisterIn, admin: dict = Depends(require_admin)):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = new_id()
    await db.users.insert_one({
        "id": uid, "email": email, "password_hash": hash_password(body.password),
        "name": body.name or "Trader", "is_admin": False, "created_at": now_iso(),
    })
    await seed_user_tags(uid)
    return {"id": uid, "email": email, "name": body.name, "is_admin": False}

@api.delete("/users/{uid}")
async def delete_user(uid: str, admin: dict = Depends(require_admin)):
    if uid == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    for col in (db.strategies, db.trades, db.alerts, db.notifications, db.tags, db.settings):
        await col.delete_many({"owner_id": uid})
    await db.users.delete_one({"id": uid})
    return {"deleted": True}

# ----------------------------------------------------------------------------
# Strategy routes
# ----------------------------------------------------------------------------
@api.get("/strategies")
async def list_strategies(user: dict = Depends(get_current_user)):
    owner = user["id"]
    strategies = await db.strategies.find({"owner_id": owner}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for s in strategies:
        trades = await db.trades.find({"strategy_id": s["id"], "owner_id": owner}, {"_id": 0}).to_list(2000)
        closed = [t for t in trades if t.get("pnl") is not None]
        s["total_trades"] = len(trades)
        s["total_pnl"] = round(sum(t["pnl"] for t in closed), 2)
        wins = [t for t in closed if t["pnl"] > 0]
        s["win_rate"] = round(len(wins) / len(closed) * 100, 1) if closed else 0
        last = await db.alerts.find({"strategy_id": s["id"]}, {"_id": 0}).sort("received_at", -1).to_list(1)
        s["last_alert"] = last[0]["received_at"] if last else None
        s["webhook_url"] = f"{APP_BASE_URL}/api/webhook/{s['webhook_token']}"
    return strategies

@api.post("/strategies")
async def create_strategy(body: StrategyIn, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc["order_defaults"] = body.order_defaults.model_dump()
    doc.update({"id": new_id(), "owner_id": user["id"], "webhook_token": gen_webhook_token(), "created_at": now_iso()})
    await db.strategies.insert_one({**doc})
    doc.pop("_id", None)
    doc["webhook_url"] = f"{APP_BASE_URL}/api/webhook/{doc['webhook_token']}"
    return doc

@api.get("/strategies/{sid}")
async def get_strategy(sid: str, user: dict = Depends(get_current_user)):
    s = await db.strategies.find_one({"id": sid, "owner_id": user["id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Strategy not found")
    s["webhook_url"] = f"{APP_BASE_URL}/api/webhook/{s['webhook_token']}"
    s["alerts"] = await db.alerts.find({"strategy_id": sid}, {"_id": 0}).sort("received_at", -1).to_list(100)
    s["trades"] = await db.trades.find({"strategy_id": sid, "owner_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return s

@api.put("/strategies/{sid}")
async def update_strategy(sid: str, body: StrategyIn, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc["order_defaults"] = body.order_defaults.model_dump()
    res = await db.strategies.update_one({"id": sid, "owner_id": user["id"]}, {"$set": doc})
    if res.matched_count == 0:
        raise HTTPException(404, "Strategy not found")
    return await get_strategy(sid, user)

@api.post("/strategies/{sid}/toggle")
async def toggle_strategy(sid: str, user: dict = Depends(get_current_user)):
    s = await db.strategies.find_one({"id": sid, "owner_id": user["id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Strategy not found")
    await db.strategies.update_one({"id": sid}, {"$set": {"active": not s.get("active", True)}})
    return {"active": not s.get("active", True)}

@api.delete("/strategies/{sid}")
async def delete_strategy(sid: str, user: dict = Depends(get_current_user)):
    await db.strategies.delete_one({"id": sid, "owner_id": user["id"]})
    return {"deleted": True}

# ----------------------------------------------------------------------------
# Webhook (public) + Alerts
# ----------------------------------------------------------------------------
@api.post("/webhook/{token}")
async def receive_webhook(token: str, request: Request):
    strategy = await db.strategies.find_one({"webhook_token": token}, {"_id": 0})
    if not strategy:
        raise HTTPException(404, "Unknown webhook")
    owner_id = strategy.get("owner_id")
    try:
        payload = await request.json()
    except Exception:
        raw = (await request.body()).decode()
        payload = {"raw": raw}
    od = strategy.get("order_defaults", {})
    alert = {
        "id": new_id(), "owner_id": owner_id, "strategy_id": strategy["id"], "strategy_name": strategy["name"],
        "action": str(payload.get("action", "buy")).lower(),
        "symbol": str(payload.get("symbol", payload.get("ticker", "UNKNOWN"))).upper(),
        "quantity": payload.get("quantity", od.get("quantity", 1)),
        "order_type": payload.get("order_type", od.get("order_type", "market")),
        "price": payload.get("price"),
        "stop_loss": payload.get("stop_loss"), "take_profit": payload.get("take_profit"),
        "asset_type": payload.get("asset_type", strategy.get("asset_type", "stock")),
        "option_expiry": payload.get("expiry"), "option_strike": payload.get("strike"),
        "option_right": payload.get("right"),
        "raw_payload": payload, "received_at": now_iso(), "status": "received",
    }
    if not strategy.get("active", True):
        alert["status"] = "ignored_paused"
        await db.alerts.insert_one({**alert})
        return {"status": "ignored", "reason": "strategy paused"}

    settings = await get_settings(owner_id)
    auto_on = bool(settings.get("auto_trade_enabled"))
    mode = strategy.get("approval_mode", "auto_execute")

    if mode == "auto_execute" and auto_on:
        alert["status"] = "approved"
        await db.alerts.insert_one({**alert})
        await dispatch_notifications(strategy, alert, event="signal", with_actions=False, prefix="⚡ SIGNAL: ")
        await execute_alert(alert["id"])
        return {"status": "executed", "alert_id": alert["id"]}

    alert["status"] = "pending"
    schedule_timer = (mode == "auto_approve_timer" and auto_on)
    if schedule_timer:
        secs = strategy.get("auto_approve_seconds", 30)
        alert["auto_approve_at"] = (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat()
        alert["auto_approve_seconds"] = secs
    if not auto_on and mode != "require_approval":
        alert["held_reason"] = "auto_trade_disabled"
    await db.alerts.insert_one({**alert})
    await dispatch_notifications(strategy, alert, event="signal", with_actions=True,
                                 prefix="🔔 APPROVAL NEEDED: ")
    if schedule_timer:
        asyncio.create_task(auto_approve_timer(alert["id"], strategy.get("auto_approve_seconds", 30)))
    return {"status": "pending_approval", "alert_id": alert["id"]}

@api.get("/alerts")
async def list_alerts(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"owner_id": user["id"]}
    if status:
        q["status"] = status
    return await db.alerts.find(q, {"_id": 0}).sort("received_at", -1).to_list(300)

@api.get("/alerts/pending")
async def pending_alerts(user: dict = Depends(get_current_user)):
    return await db.alerts.find({"status": "pending", "owner_id": user["id"]}, {"_id": 0}).sort("received_at", -1).to_list(100)

@api.post("/alerts/{aid}/approve")
async def approve_alert(aid: str, user: dict = Depends(get_current_user)):
    alert = await db.alerts.find_one({"id": aid, "owner_id": user["id"]}, {"_id": 0})
    if not alert:
        raise HTTPException(404, "Alert not found")
    if alert["status"] != "pending":
        raise HTTPException(400, f"Alert is {alert['status']}")
    await db.alerts.update_one({"id": aid}, {"$set": {"status": "approved"}})
    await execute_alert(aid)
    return {"status": "executed"}

@api.post("/alerts/{aid}/reject")
async def reject_alert(aid: str, user: dict = Depends(get_current_user)):
    res = await db.alerts.update_one({"id": aid, "owner_id": user["id"], "status": "pending"},
                                     {"$set": {"status": "rejected", "rejected_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(400, "Alert not pending")
    return {"status": "rejected"}

# ----------------------------------------------------------------------------
# Bot
# ----------------------------------------------------------------------------
@api.get("/bot/status")
async def bot_status(user: dict = Depends(get_current_user)):
    owner = user["id"]
    settings = await get_settings(owner)
    ibkr = settings.get("ibkr", {})
    connected = bool(ibkr.get("enabled"))
    recent = await db.alerts.find({"owner_id": owner}, {"_id": 0}).sort("received_at", -1).to_list(25)
    total = await db.alerts.count_documents({"owner_id": owner})
    executed = await db.alerts.count_documents({"owner_id": owner, "status": "executed"})
    pending = await db.alerts.count_documents({"owner_id": owner, "status": "pending"})
    failed = await db.alerts.count_documents({"owner_id": owner, "status": "failed"})
    return {
        "auto_trade_enabled": bool(settings.get("auto_trade_enabled")),
        "broker_connected": connected, "ibkr_connected": connected,
        "mode": "live" if connected else "paper",
        "host": ibkr.get("host", "127.0.0.1"), "port": ibkr.get("port", 7497),
        "recent_alerts": recent,
        "stats": {"total": total, "executed": executed, "pending": pending, "failed": failed},
    }

async def _update_settings(owner: str, patch: dict):
    await db.settings.update_one({"id": owner}, {"$set": {**patch, "id": owner, "owner_id": owner}}, upsert=True)

@api.post("/bot/auto-trade")
async def set_auto_trade(body: dict, user: dict = Depends(get_current_user)):
    enabled = bool(body.get("enabled"))
    await _update_settings(user["id"], {"auto_trade_enabled": enabled})
    return {"auto_trade_enabled": enabled}

@api.post("/bot/broker")
async def set_broker(body: dict, user: dict = Depends(get_current_user)):
    connected = bool(body.get("connected"))
    s = await get_settings(user["id"])
    ibkr = s.get("ibkr", {})
    ibkr["enabled"] = connected
    if body.get("host"):
        ibkr["host"] = body["host"]
    if body.get("port"):
        ibkr["port"] = body["port"]
    await _update_settings(user["id"], {"ibkr": ibkr})
    return {"broker_connected": connected, "host": ibkr.get("host"), "port": ibkr.get("port")}

@api.post("/bot/mode")
async def set_bot_mode(body: dict, user: dict = Depends(get_current_user)):
    enabled = bool(body.get("live"))
    s = await get_settings(user["id"])
    ibkr = s.get("ibkr", {})
    ibkr["enabled"] = enabled
    await _update_settings(user["id"], {"ibkr": ibkr})
    return {"mode": "live" if enabled else "paper"}

@api.post("/notifications/test")
async def test_notification(body: dict, user: dict = Depends(get_current_user)):
    platform = body.get("platform")
    settings = await get_settings(user["id"])
    cfg = settings.get(platform) or {}
    msg = f"🧪 TradeHub test — your {platform} notifications are working!"
    ref = {"id": "test", "owner_id": user["id"]}
    if platform == "telegram":
        results = await send_telegram(msg, "test", cfg, with_actions=False)
        ok = any(r.get("ok") for r in results)
        detail = results
        for r in results:
            await _log_notif(ref, ref, "telegram", msg, "test", r, r.get("target"))
    elif platform == "discord":
        detail = await send_discord(msg, cfg)
        ok = detail.get("ok")
        await _log_notif(ref, ref, "discord", msg, "test", detail, cfg.get("chat_type"))
    elif platform == "whatsapp":
        detail = await send_whatsapp(msg, cfg)
        ok = detail.get("ok")
        await _log_notif(ref, ref, "whatsapp", msg, "test", detail)
    else:
        raise HTTPException(400, "Unknown platform")
    return {"ok": bool(ok), "detail": detail}

# ----------------------------------------------------------------------------
# Trades (journal)
# ----------------------------------------------------------------------------
@api.get("/trades")
async def list_trades(
    symbol: Optional[str] = None, side: Optional[str] = None,
    strategy_id: Optional[str] = None, tag: Optional[str] = None,
    start: Optional[str] = None, end: Optional[str] = None,
    user: dict = Depends(get_current_user)):
    q: Dict[str, Any] = {"owner_id": user["id"]}
    if symbol: q["symbol"] = symbol.upper()
    if side: q["side"] = side
    if strategy_id: q["strategy_id"] = strategy_id
    if tag: q["tags"] = tag
    trades = await db.trades.find(q, {"_id": 0}).sort("entry_time", -1).to_list(2000)
    def tdate(t):
        return t.get("exit_time") or t.get("entry_time") or ""
    if start:
        trades = [t for t in trades if tdate(t) >= start]
    if end:
        trades = [t for t in trades if tdate(t) <= end + "T23:59:59"]
    return trades

@api.post("/trades")
async def create_trade(body: TradeIn, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["owner_id"] = user["id"]
    doc["entry_time"] = doc.get("entry_time") or now_iso()
    doc["source"] = "manual"
    doc["created_at"] = now_iso()
    doc = compute_pnl(doc)
    await db.trades.insert_one({**doc})
    doc.pop("_id", None)
    return doc

@api.get("/trades/{tid}")
async def get_trade(tid: str, user: dict = Depends(get_current_user)):
    t = await db.trades.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Trade not found")
    return t

@api.put("/trades/{tid}")
async def update_trade(tid: str, body: TradeIn, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc = compute_pnl(doc)
    res = await db.trades.update_one({"id": tid, "owner_id": user["id"]}, {"$set": doc})
    if res.matched_count == 0:
        raise HTTPException(404, "Trade not found")
    return await get_trade(tid, user)

@api.delete("/trades/{tid}")
async def delete_trade(tid: str, user: dict = Depends(get_current_user)):
    await db.trades.delete_one({"id": tid, "owner_id": user["id"]})
    return {"deleted": True}

@api.post("/trades/{tid}/attachment")
async def upload_attachment(tid: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    t = await db.trades.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Trade not found")
    ext = Path(file.filename).suffix
    fname = f"{tid}_{new_id()}{ext}"
    content = await file.read()
    (UPLOAD_DIR / fname).write_bytes(content)
    url = f"{APP_BASE_URL}/api/uploads/{fname}"
    await db.trades.update_one({"id": tid}, {"$set": {"screenshot_url": url}})
    return {"url": url}

@api.get("/uploads/{fname}")
async def get_upload(fname: str):
    fpath = UPLOAD_DIR / fname
    if not fpath.exists():
        raise HTTPException(404, "Not found")
    from fastapi.responses import FileResponse
    return FileResponse(str(fpath))

# ----------------------------------------------------------------------------
# Tags
# ----------------------------------------------------------------------------
@api.get("/tags")
async def list_tags(user: dict = Depends(get_current_user)):
    return await db.tags.find({"owner_id": user["id"]}, {"_id": 0}).to_list(200)

@api.post("/tags")
async def create_tag(body: TagIn, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["owner_id"] = user["id"]
    await db.tags.insert_one({**doc})
    doc.pop("_id", None)
    return doc

@api.delete("/tags/{tid}")
async def delete_tag(tid: str, user: dict = Depends(get_current_user)):
    await db.tags.delete_one({"id": tid, "owner_id": user["id"]})
    return {"deleted": True}

# ----------------------------------------------------------------------------
# Notifications + Settings
# ----------------------------------------------------------------------------
@api.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user)):
    return await db.notifications.find({"owner_id": user["id"]}, {"_id": 0}).sort("sent_at", -1).to_list(300)

@api.get("/settings")
async def get_settings_route(user: dict = Depends(get_current_user)):
    s = await get_settings(user["id"])
    s.pop("id", None)
    s.pop("owner_id", None)
    return s

@api.put("/settings")
async def update_settings(body: SettingsIn, user: dict = Depends(get_current_user)):
    doc = body.model_dump()
    doc["id"] = user["id"]
    doc["owner_id"] = user["id"]
    await db.settings.update_one({"id": user["id"]}, {"$set": doc}, upsert=True)
    return {"saved": True}

# ----------------------------------------------------------------------------
# Analytics
# ----------------------------------------------------------------------------
async def closed_trades(owner_id: str) -> List[dict]:
    trades = await db.trades.find({"owner_id": owner_id, "status": "closed", "pnl": {"$ne": None}}, {"_id": 0}).to_list(5000)
    trades.sort(key=lambda t: t.get("exit_time") or t.get("entry_time") or "")
    return trades

@api.get("/analytics/overview")
async def analytics_overview(user: dict = Depends(get_current_user)):
    owner = user["id"]
    trades = await closed_trades(owner)
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total = round(sum(pnls), 2)
    win_rate = round(len(wins) / len(pnls) * 100, 1) if pnls else 0
    avg_win = round(sum(wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(losses) / len(losses), 2) if losses else 0
    profit_factor = round(sum(wins) / abs(sum(losses)), 2) if losses else (round(sum(wins), 2) if wins else 0)
    rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    expectancy = round(sum(rs) / len(rs), 2) if rs else 0
    cur = best = worst = 0
    for p in pnls:
        if p > 0:
            cur = cur + 1 if cur > 0 else 1
        elif p < 0:
            cur = cur - 1 if cur < 0 else -1
        best = max(best, cur); worst = min(worst, cur)
    open_count = await db.trades.count_documents({"owner_id": owner, "status": "open"})
    return {
        "total_pnl": total, "total_trades": len(pnls), "win_rate": win_rate,
        "avg_win": avg_win, "avg_loss": avg_loss, "profit_factor": profit_factor,
        "expectancy": expectancy, "wins": len(wins), "losses": len(losses),
        "current_streak": cur, "best_streak": best, "worst_streak": worst,
        "open_positions": open_count,
        "largest_win": round(max(pnls), 2) if pnls else 0,
        "largest_loss": round(min(pnls), 2) if pnls else 0,
    }

@api.get("/analytics/equity-curve")
async def equity_curve(user: dict = Depends(get_current_user)):
    trades = await closed_trades(user["id"])
    out = []
    cum = peak = max_dd = 0
    for i, t in enumerate(trades):
        cum = round(cum + t["pnl"], 2)
        peak = max(peak, cum)
        dd = round(cum - peak, 2)
        max_dd = min(max_dd, dd)
        out.append({"i": i + 1, "date": (t.get("exit_time") or t.get("entry_time") or "")[:10],
                    "pnl": t["pnl"], "cumulative": cum, "drawdown": dd, "symbol": t["symbol"]})
    return {"points": out, "max_drawdown": max_dd}

@api.get("/analytics/calendar")
async def calendar(year: int, month: int, user: dict = Depends(get_current_user)):
    trades = await closed_trades(user["id"])
    days: Dict[str, dict] = {}
    for t in trades:
        d = (t.get("exit_time") or t.get("entry_time") or "")[:10]
        if not d.startswith(f"{year:04d}-{month:02d}"):
            continue
        days.setdefault(d, {"pnl": 0, "trades": 0})
        days[d]["pnl"] = round(days[d]["pnl"] + t["pnl"], 2)
        days[d]["trades"] += 1
    month_pnl = round(sum(v["pnl"] for v in days.values()), 2)
    return {"days": days, "month_pnl": month_pnl, "trading_days": len(days)}

@api.get("/analytics/by/{dim}")
async def analytics_by(dim: str, user: dict = Depends(get_current_user)):
    owner = user["id"]
    trades = await closed_trades(owner)
    strat_map = {s["id"]: s["name"] for s in await db.strategies.find({"owner_id": owner}, {"_id": 0}).to_list(500)}
    groups: Dict[str, List[dict]] = {}
    for t in trades:
        if dim == "symbol": keys = [t.get("symbol", "—")]
        elif dim == "side": keys = [t.get("side", "—")]
        elif dim == "strategy": keys = [strat_map.get(t.get("strategy_id"), "Unassigned")]
        elif dim == "tag": keys = t.get("tags") or ["Untagged"]
        else: keys = ["—"]
        for k in keys:
            groups.setdefault(k, []).append(t)
    out = []
    for k, ts in groups.items():
        pnls = [t["pnl"] for t in ts]
        wins = [p for p in pnls if p > 0]
        out.append({"key": k, "trades": len(ts), "pnl": round(sum(pnls), 2),
                    "win_rate": round(len(wins) / len(ts) * 100, 1) if ts else 0})
    out.sort(key=lambda x: x["pnl"], reverse=True)
    return out

@api.get("/analytics/mfe-mae")
async def mfe_mae(user: dict = Depends(get_current_user)):
    trades = await closed_trades(user["id"])
    return [{"symbol": t["symbol"], "mfe": t.get("mfe"), "mae": t.get("mae"), "pnl": t["pnl"],
             "r_multiple": t.get("r_multiple")} for t in trades if t.get("mfe") is not None or t.get("mae") is not None]

@api.get("/analytics/time-of-day")
async def time_of_day(user: dict = Depends(get_current_user)):
    trades = await closed_trades(user["id"])
    buckets: Dict[int, dict] = {h: {"pnl": 0, "trades": 0} for h in range(24)}
    for t in trades:
        try:
            hr = datetime.fromisoformat(t.get("entry_time") or "").hour
        except Exception:
            continue
        buckets[hr]["pnl"] = round(buckets[hr]["pnl"] + t["pnl"], 2)
        buckets[hr]["trades"] += 1
    return [{"hour": hr, **buckets[hr]} for hr in range(24) if buckets[hr]["trades"] > 0]

@api.get("/analytics/strategy-comparison")
async def strategy_comparison(user: dict = Depends(get_current_user)):
    owner = user["id"]
    strategies = await db.strategies.find({"owner_id": owner}, {"_id": 0}).to_list(500)
    out = []
    for s in strategies:
        trades = await db.trades.find({"strategy_id": s["id"], "owner_id": owner, "status": "closed", "pnl": {"$ne": None}}, {"_id": 0}).to_list(2000)
        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
        out.append({"name": s["name"], "trades": len(pnls), "pnl": round(sum(pnls), 2),
                    "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
                    "expectancy": round(sum(rs) / len(rs), 2) if rs else 0})
    return out

# ----------------------------------------------------------------------------
# Telegram + Twilio inbound webhooks
# ----------------------------------------------------------------------------
@api.post("/webhook/telegram/callback")
async def telegram_callback(request: Request):
    update = await request.json()
    cb = update.get("callback_query")
    if not cb:
        return {"ok": True}
    parts = (cb.get("data", "") or "").split(":", 1)
    if len(parts) != 2:
        return {"ok": True}
    action, aid = parts
    alert = await db.alerts.find_one({"id": aid}, {"_id": 0})
    if alert and alert["status"] == "pending":
        if action == "approve":
            await db.alerts.update_one({"id": aid}, {"$set": {"status": "approved"}})
            await execute_alert(aid)
        elif action == "reject":
            await db.alerts.update_one({"id": aid}, {"$set": {"status": "rejected", "rejected_at": now_iso()}})
        await db.notifications.update_one({"alert_id": aid, "platform": "telegram"},
                                          {"$set": {"response": action, "responded_at": now_iso()}})
    return {"ok": True}

@api.post("/webhook/whatsapp/reply")
async def whatsapp_reply(Body: str = Form(""), From: str = Form("")):
    text = Body.strip().lower()
    pending = await db.alerts.find_one({"status": "pending"}, {"_id": 0}, sort=[("received_at", -1)])
    if pending:
        if text in ("yes", "y"):
            await db.alerts.update_one({"id": pending["id"]}, {"$set": {"status": "approved"}})
            await execute_alert(pending["id"])
            return PlainTextResponse("✅ Approved")
        elif text in ("no", "n"):
            await db.alerts.update_one({"id": pending["id"]}, {"$set": {"status": "rejected", "rejected_at": now_iso()}})
            return PlainTextResponse("❌ Rejected")
    return PlainTextResponse("Reply YES or NO to act on the latest pending alert.")

# ----------------------------------------------------------------------------
# Seeding
# ----------------------------------------------------------------------------
SAMPLE_SYMBOLS = ["AAPL", "TSLA", "NVDA", "SPY", "AMD", "MSFT", "META", "QQQ", "AMZN", "GOOGL"]
SETUP_TAGS = [
    {"name": "Breakout", "color": "#10B981", "type": "setup"},
    {"name": "Reversal", "color": "#F59E0B", "type": "setup"},
    {"name": "Trend", "color": "#007AFF", "type": "setup"},
    {"name": "Gap Fill", "color": "#A855F7", "type": "setup"},
    {"name": "Trending Mkt", "color": "#06B6D4", "type": "market"},
    {"name": "Choppy Mkt", "color": "#EF4444", "type": "market"},
]

async def seed():
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        admin_id = new_id()
        await db.users.insert_one({
            "id": admin_id, "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Trader", "is_admin": True, "created_at": now_iso(),
        })
        logger.info("Seeded admin user")
    else:
        admin_id = existing["id"]
        if not verify_password(admin_password, existing["password_hash"]):
            await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
            logger.info("Admin password re-synced from env")
        if not existing.get("is_admin"):
            await db.users.update_one({"email": admin_email}, {"$set": {"is_admin": True}})

    # Backfill legacy (pre multi-user) data to the admin owner
    for col in (db.strategies, db.trades, db.alerts, db.notifications, db.tags):
        await col.update_many({"owner_id": {"$exists": False}}, {"$set": {"owner_id": admin_id}})
    await db.settings.update_one({"id": "global"}, {"$set": {"id": admin_id, "owner_id": admin_id}})

    if await db.tags.count_documents({"owner_id": admin_id}) == 0:
        await seed_user_tags(admin_id)

    if await db.strategies.count_documents({"owner_id": admin_id}) == 0:
        strats = [
            {"name": "Momentum Scalp", "description": "Fast intraday momentum scalps on liquid names.",
             "asset_type": "stock", "approval_mode": "auto_execute", "notify_platforms": ["telegram"]},
            {"name": "Swing Breakout", "description": "Multi-day breakout swings, requires manual approval.",
             "asset_type": "stock", "approval_mode": "require_approval", "notify_platforms": ["telegram", "discord"]},
            {"name": "Options Flow", "description": "Single-leg options on unusual flow with timed auto-approve.",
             "asset_type": "option", "approval_mode": "auto_approve_timer", "auto_approve_seconds": 45,
             "notify_platforms": ["telegram", "discord", "whatsapp"]},
        ]
        for s in strats:
            doc = StrategyIn(**s).model_dump()
            doc["order_defaults"] = OrderDefaults().model_dump()
            doc.update({"id": new_id(), "owner_id": admin_id, "webhook_token": gen_webhook_token(), "created_at": now_iso()})
            await db.strategies.insert_one({**doc})
        logger.info("Seeded strategies")

    if await db.trades.count_documents({"owner_id": admin_id}) == 0:
        rnd = random.Random(42)
        strategies = await db.strategies.find({"owner_id": admin_id}, {"_id": 0}).to_list(10)
        tags = await db.tags.find({"owner_id": admin_id}, {"_id": 0}).to_list(20)
        setup_names = [t["name"] for t in tags]
        start = datetime.now(timezone.utc) - timedelta(days=70)
        trades = []
        for i in range(120):
            day = start + timedelta(days=rnd.randint(0, 69), hours=rnd.randint(9, 15), minutes=rnd.randint(0, 59))
            sym = rnd.choice(SAMPLE_SYMBOLS)
            side = rnd.choice(["long", "long", "long", "short"])
            strat = rnd.choice(strategies)
            asset = strat["asset_type"]
            entry = round(rnd.uniform(50, 450), 2)
            win = rnd.random() < 0.56
            move_pct = rnd.uniform(0.005, 0.05) * (1 if win else -1)
            direction = 1 if side == "long" else -1
            ex = round(entry * (1 + move_pct * direction), 2)
            qty = rnd.choice([1, 2, 5, 10]) if asset == "option" else rnd.choice([10, 25, 50, 100])
            risk = round(entry * 0.02 * qty * (100 if asset == "option" else 1), 2)
            exit_time = day + timedelta(minutes=rnd.randint(5, 600))
            t = {
                "id": new_id(), "owner_id": admin_id, "symbol": sym, "side": side, "asset_type": asset,
                "entry_price": entry, "exit_price": ex, "quantity": qty, "fees": round(rnd.uniform(0.5, 3), 2),
                "entry_time": day.isoformat(), "exit_time": exit_time.isoformat(), "status": "closed",
                "strategy_id": strat["id"], "tags": rnd.sample(setup_names, k=rnd.randint(1, 2)),
                "notes": "", "risk_amount": risk,
                "mfe": round(abs(move_pct) * entry * rnd.uniform(1.0, 1.8) * qty * (100 if asset == "option" else 1), 2),
                "mae": round(-abs(move_pct) * entry * rnd.uniform(0.3, 1.2) * qty * (100 if asset == "option" else 1), 2),
                "option_expiry": "2026-07-17" if asset == "option" else None,
                "option_strike": round(entry) if asset == "option" else None,
                "option_right": rnd.choice(["call", "put"]) if asset == "option" else None,
                "account": "paper", "source": rnd.choice(["bot", "manual"]), "created_at": day.isoformat(),
            }
            trades.append(compute_pnl(t))
        await db.trades.insert_many(trades)
        logger.info(f"Seeded {len(trades)} trades")

    if await db.alerts.count_documents({"owner_id": admin_id}) == 0:
        strategies = await db.strategies.find({"owner_id": admin_id}, {"_id": 0}).to_list(10)
        approval_strat = next((s for s in strategies if s["approval_mode"] != "auto_execute"), strategies[0])
        for i in range(2):
            await db.alerts.insert_one({
                "id": new_id(), "owner_id": admin_id, "strategy_id": approval_strat["id"],
                "strategy_name": approval_strat["name"], "action": "buy",
                "symbol": random.choice(SAMPLE_SYMBOLS), "quantity": 10, "order_type": "market",
                "price": round(random.uniform(100, 300), 2), "asset_type": approval_strat["asset_type"],
                "status": "pending", "received_at": now_iso(), "raw_payload": {},
            })

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.strategies.create_index("webhook_token")
    await db.strategies.create_index("owner_id")
    await db.trades.create_index("owner_id")
    await db.alerts.create_index("owner_id")
    await seed()
    Path("/app/memory/test_credentials.md").write_text(
        "# Test Credentials\n\n"
        "Multi-user app (JWT Bearer). Admin account (can manage users):\n"
        f"- email: {os.environ['ADMIN_EMAIL']}\n"
        f"- password: {os.environ['ADMIN_PASSWORD']}\n\n"
        "Any new user can self-register at POST /api/auth/register or be created by an admin (POST /api/users).\n"
        "Auth: POST /api/auth/login, POST /api/auth/register, GET /api/auth/me (Authorization: Bearer <token>)\n"
        "Admin-only: GET/POST /api/users, DELETE /api/users/{id}\n"
    )

@app.on_event("shutdown")
async def shutdown():
    client.close()

app.include_router(api)
app.add_middleware(
    CORSMiddleware, allow_credentials=False,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"], allow_headers=["*"],
)
