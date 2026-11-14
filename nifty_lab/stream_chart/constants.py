"""Fixed prototype scope (Spec 14)."""
from __future__ import annotations

from zoneinfo import ZoneInfo

INSTRUMENT_KEY = "NSE_EQ|INE090A01021"
INSTRUMENT_LABEL = "ICICIBANK"
CANDLE_MINUTES = 5
IST = ZoneInfo("Asia/Kolkata")

LIGHTWEIGHT_CHARTS_VERSION = "4.2.1"
LIGHTWEIGHT_CHARTS_CDN = (
    f"https://unpkg.com/lightweight-charts@{LIGHTWEIGHT_CHARTS_VERSION}/"
    "dist/lightweight-charts.standalone.production.js"
)

FEED_AUTHORIZE_PATH = "/v3/feed/market-data-feed/authorize"
SUBSCRIBE_MODE = "ltpc"

RENDER_INTERVAL_SEC = 1.0
# LIVE freshness / admission policy (Spec 15 design §1) — operational display policy, not an exchange guarantee.
SOURCE_FRESH_SECONDS = 30.0  # latest accepted source trade time must be within this of receipt UTC
RECEIPT_PROGRESS_SECONDS = 30.0  # monotonic time since source time last progressed
MAX_FUTURE_SKEW_SECONDS = 2.0  # trade timestamps beyond receipt UTC + skew are rejected, never admitted
MAX_TRADE_TS_MS = 4_102_444_800_000  # 2100-01-01T00:00Z — decoder upper bound for int64 ltt
STALE_TRADE_SECONDS = int(RECEIPT_PROGRESS_SECONDS)  # legacy alias
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_BACKOFF_SEC = (1.0, 2.0, 4.0)
# Ownership lease (Spec 15 design §4) and shutdown budgets (§5)
OWNER_LEASE_SECONDS = 20.0
LEASE_MONITOR_INTERVAL_SEC = 2.0
STOP_JOIN_BUDGET_SEC = 20.0
WS_OPEN_TIMEOUT_SEC = 10.0
WS_CLOSE_TIMEOUT_SEC = 1.0
WS_RECV_POLL_SEC = 0.5

REPLAY_BANNER = "REPLAY — synthetic fixture timeline; zero broker HTTP/WebSocket."
REPLAY_FRAME_DELAY_SEC = 0.4
MAX_RETAINED_BARS = 500
MAX_DEDUPE_KEYS = 10_000
IDLE_SESSION_SEC = 120.0

LWC_ATTRIBUTION = (
    "Charts by TradingView Lightweight Charts v"
    f"{LIGHTWEIGHT_CHARTS_VERSION} (Apache-2.0). See docs/spec_14/NOTICE_LIGHTWEIGHT_CHARTS.md."
)