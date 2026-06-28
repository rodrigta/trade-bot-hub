# TradeHub — PRD

## Original Problem Statement
Single-user automated trading bot + strategy manager + approval/notification layer + trade journal + Tradervue-style analytics. Stack: React + FastAPI + MongoDB, IBKR via ib_insync, Telegram/Discord/WhatsApp(Twilio) notifications.

## User Choices (locked)
- Auth: JWT email/password (single user, seeded)
- Theme: light/dark toggle (dark default)
- IBKR: real ib_insync code + paper simulation fallback (sim used in cloud)
- Notifications: Telegram, Discord, WhatsApp (credentials via Settings page)
- Options: full single-leg contract fields + optional on stock trades

## Architecture
- Backend `/app/backend/server.py` — all routes under `/api`. JWT Bearer auth. uuid string ids, ISO datetimes. asyncio auto-approve timers. httpx outbound notifications. ib_insync execution with paper fallback. Seeds 1 user, 6 tags, 3 strategies, 120 closed trades, 2 pending alerts on startup.
- Frontend `/app/frontend/src` — React, Tailwind, shadcn/ui, recharts, lucide. Pages: Login, Dashboard, Strategies, StrategyDetail, Bot, Journal, Analysis, Notifications. axios w/ Bearer token (localStorage `th_token`).
- Login: trader@tradehub.io / trade1234

## Implemented (2026-06-28)
- Phase 1 Foundation: JWT auth, app shell + sidebar + routing, theme toggle ✓
- Phase 2 Strategies Manager: full CRUD, auto webhook endpoints, approval modes, notification multi-select, order defaults, list cards + detail ✓
- Phase 3 Approval/Notification: pending alerts, in-app approval center w/ live countdowns, auto-approve timers, Telegram/Discord/WhatsApp outbound + Telegram callback + Twilio reply webhooks, notification log ✓
- Phase 4 Trading Bot: strategy-aware webhook routing, alert parsing, IBKR exec (sim fallback), paper/live toggle, bot dashboard + execution log, alert status tracking ✓
- Phase 5 Journal: bot auto-log + manual entry, tags, notes, screenshot upload, filters/search, detail view ✓
- Phase 6 Analytics: calendar P&L, equity curve, drawdown, win rate/streaks, R-multiples/expectancy, MFE/MAE scatter, breakdowns (symbol/strategy/tag/side), time-of-day, strategy comparison ✓

## Status
Tested: backend 25/25 pytest pass, all critical frontend flows pass. No open bugs.

## MOCKED / Self-host Notes
- IBKR live execution requires TWS/IB Gateway on a self-hosted backend; cloud uses paper simulation.
- Telegram/Discord/Twilio outbound delivery needs user-provided credentials (Settings); logs "failed" until configured.
- Inbound bot webhooks (Telegram/Twilio) need public HTTPS + webhook registration on the platform side.

## Backlog / Next
- P1: On-startup recovery scan to resume orphaned auto-approve timers after restart.
- P1: Per-strategy notification credentials (currently global settings).
- P2: Split server.py into modules; add DialogDescription for a11y.
- P2: Equity curve date-range selector; export reports CSV/PDF.
- P2: Real-time WebSocket push for new pending alerts (currently 5s polling).
