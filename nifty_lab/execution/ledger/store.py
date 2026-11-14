"""Mode-separated execution ledger (Spec 08)."""
from __future__ import annotations

import hashlib
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..gate import ExecutionPortfolioContext, evaluate_entry, resolved_candidate_risk
from ..modes import ExecutionMode
from ..fill_validation import validate_close_admission_economics, validate_execution_quote, validate_fill_economics
from ..paper_accounting import allocate_proportional, sell_realized
from ..policy import EXECUTION_V1, ExecutionPolicy
from ..types import InstrumentKind, OrderSide, OrderStatus, ProductType, QuoteSnapshot, TradeCandidate

_ACTIVE_ORDER_STATUSES = (
    OrderStatus.PENDING.value,
    OrderStatus.OPEN.value,
    OrderStatus.PARTIALLY_FILLED.value,
    OrderStatus.UNKNOWN_SUBMISSION.value,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExecutionLedger:
    db_path: Path
    mode: ExecutionMode
    policy: ExecutionPolicy = EXECUTION_V1

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ledger_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    local_id TEXT PRIMARY KEY,
                    broker_order_id TEXT,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    instrument_key TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    filled_qty INTEGER NOT NULL DEFAULT 0,
                    limit_price REAL NOT NULL,
                    reserved_cash REAL NOT NULL DEFAULT 0,
                    reserved_risk REAL NOT NULL DEFAULT 0,
                    initial_reserved_cash REAL NOT NULL DEFAULT 0,
                    initial_reserved_risk REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_submit_once ON orders(local_id);
                CREATE TABLE IF NOT EXISTS fills (
                    fill_id TEXT PRIMARY KEY,
                    fill_event_id TEXT NOT NULL UNIQUE,
                    local_order_id TEXT NOT NULL REFERENCES orders(local_id),
                    qty INTEGER NOT NULL,
                    price REAL NOT NULL,
                    fees REAL NOT NULL DEFAULT 0,
                    filled_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions (
                    instrument_key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    avg_price REAL NOT NULL,
                    mark_price REAL,
                    mark_time TEXT,
                    planned_risk_inr REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS cash_ledger (
                    event_id TEXT PRIMARY KEY,
                    delta_cash REAL NOT NULL,
                    delta_fees REAL NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS close_intents (
                    intent_id TEXT PRIMARY KEY,
                    identity_hash TEXT NOT NULL,
                    local_order_id TEXT,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    exit_fees_inr REAL,
                    slippage_pct REAL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quote_observations (
                    observation_id TEXT PRIMARY KEY,
                    instrument_key TEXT NOT NULL,
                    source_at TEXT NOT NULL,
                    bid_qty INTEGER NOT NULL DEFAULT 0,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS realized_events (
                    event_id TEXT PRIMARY KEY,
                    fill_event_id TEXT NOT NULL,
                    gross_inr REAL NOT NULL,
                    net_inr REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            cur = conn.execute("SELECT value FROM ledger_meta WHERE key='funded'").fetchone()
            if cur is None:
                conn.execute(
                    "INSERT INTO ledger_meta(key,value) VALUES('funded',?)",
                    (str(self.policy.initial_allocation_inr),),
                )
                conn.execute(
                    "INSERT INTO cash_ledger(event_id,delta_cash,delta_fees,note,created_at) VALUES(?,?,?,?,?)",
                    (str(uuid.uuid4()), self.policy.initial_allocation_inr, 0.0, "initial_allocation", _utcnow()),
                )
            try:
                conn.execute("ALTER TABLE positions ADD COLUMN planned_risk_inr REAL NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            for col in ("initial_reserved_cash", "initial_reserved_risk"):
                try:
                    conn.execute(f"ALTER TABLE orders ADD COLUMN {col} REAL NOT NULL DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
            try:
                conn.execute("ALTER TABLE fills ADD COLUMN fill_event_id TEXT")
            except sqlite3.OperationalError:
                pass
            for col, ddl in (
                ("entry_fees_inr", "ALTER TABLE positions ADD COLUMN entry_fees_inr REAL NOT NULL DEFAULT 0"),
                ("instrument_kind", "ALTER TABLE positions ADD COLUMN instrument_kind TEXT"),
                ("lot_size", "ALTER TABLE positions ADD COLUMN lot_size INTEGER NOT NULL DEFAULT 1"),
                ("product", "ALTER TABLE positions ADD COLUMN product TEXT"),
                ("closeable", "ALTER TABLE positions ADD COLUMN closeable INTEGER NOT NULL DEFAULT 0"),
                ("instrument_kind", "ALTER TABLE orders ADD COLUMN instrument_kind TEXT"),
                ("lot_size", "ALTER TABLE orders ADD COLUMN lot_size INTEGER NOT NULL DEFAULT 1"),
                ("product", "ALTER TABLE orders ADD COLUMN product TEXT"),
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass
            conn.execute(
                """
                UPDATE positions SET closeable=0
                WHERE quantity > 0 AND (
                    instrument_kind IS NULL OR instrument_kind = ''
                    OR product IS NULL OR product = ''
                    OR lot_size IS NULL OR lot_size < 1
                )
                """
            )
            self._migrate_close_intents_schema(conn)
            self._migrate_quote_observations_schema(conn)

    def _migrate_close_intents_schema(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='close_intents'"
        ).fetchone()
        ddl = (row["sql"] or "") if row is not None else ""
        if "identity_hash" in ddl and "UNIQUE" in ddl:
            conn.executescript(
                """
                CREATE TABLE close_intents_v2 (
                    intent_id TEXT PRIMARY KEY,
                    identity_hash TEXT NOT NULL,
                    local_order_id TEXT,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    exit_fees_inr REAL,
                    slippage_pct REAL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO close_intents_v2(intent_id, identity_hash, local_order_id, consumed, created_at)
                SELECT intent_id, identity_hash, local_order_id, consumed, created_at FROM close_intents;
                DROP TABLE close_intents;
                ALTER TABLE close_intents_v2 RENAME TO close_intents;
                """
            )
        for col, stmt in (
            ("exit_fees_inr", "ALTER TABLE close_intents ADD COLUMN exit_fees_inr REAL"),
            ("slippage_pct", "ALTER TABLE close_intents ADD COLUMN slippage_pct REAL"),
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

    def _migrate_quote_observations_schema(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='quote_observations'"
        ).fetchone()
        ddl = (row["sql"] or "") if row is not None else ""
        if row is not None and "instrument_key" not in ddl:
            conn.executescript(
                """
                CREATE TABLE quote_observations_v2 (
                    observation_id TEXT PRIMARY KEY,
                    instrument_key TEXT NOT NULL DEFAULT '',
                    source_at TEXT NOT NULL DEFAULT '',
                    bid_qty INTEGER NOT NULL DEFAULT 0,
                    consumed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                INSERT INTO quote_observations_v2(observation_id, consumed, created_at)
                SELECT observation_id, consumed, created_at FROM quote_observations;
                DROP TABLE quote_observations;
                ALTER TABLE quote_observations_v2 RENAME TO quote_observations;
                """
            )
        for col, stmt in (
            ("instrument_key", "ALTER TABLE quote_observations ADD COLUMN instrument_key TEXT NOT NULL DEFAULT ''"),
            ("source_at", "ALTER TABLE quote_observations ADD COLUMN source_at TEXT NOT NULL DEFAULT ''"),
            ("bid_qty", "ALTER TABLE quote_observations ADD COLUMN bid_qty INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

    def _cash_balance_conn(self, conn: sqlite3.Connection) -> float:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta_cash),0), COALESCE(SUM(delta_fees),0) FROM cash_ledger"
        ).fetchone()
        return float(row[0]) - float(row[1])

    def cash_balance(self) -> float:
        with self._conn() as conn:
            return self._cash_balance_conn(conn)

    def _reserved_cash_conn(self, conn: sqlite3.Connection) -> float:
        ph = ",".join("?" * len(_ACTIVE_ORDER_STATUSES))
        row = conn.execute(
            f"SELECT COALESCE(SUM(reserved_cash),0) FROM orders WHERE status IN ({ph})",
            _ACTIVE_ORDER_STATUSES,
        ).fetchone()
        return float(row[0])

    def reserved_cash(self) -> float:
        with self._conn() as conn:
            return self._reserved_cash_conn(conn)

    def _reserved_risk_conn(self, conn: sqlite3.Connection) -> float:
        ph = ",".join("?" * len(_ACTIVE_ORDER_STATUSES))
        row = conn.execute(
            f"SELECT COALESCE(SUM(reserved_risk),0) FROM orders WHERE status IN ({ph})",
            _ACTIVE_ORDER_STATUSES,
        ).fetchone()
        return float(row[0])

    def reserved_risk(self) -> float:
        with self._conn() as conn:
            return self._reserved_risk_conn(conn)

    def positions_value(self) -> float:
        with self._conn() as conn:
            rows = conn.execute("SELECT quantity, COALESCE(mark_price, avg_price) AS px FROM positions").fetchall()
            return sum(float(r["quantity"]) * float(r["px"]) for r in rows)

    def peak_equity(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM ledger_meta WHERE key='peak_equity'").fetchone()
            if row is None:
                return self.equity()
            return float(row["value"])

    def set_peak_if_higher(self, equity: float) -> None:
        peak = self.peak_equity()
        if equity > peak:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO ledger_meta(key,value) VALUES('peak_equity',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(equity),),
                )

    def equity(self) -> float:
        return self.cash_balance() + self.positions_value()

    def open_position_count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM positions WHERE quantity <> 0").fetchone()
            return int(row[0])

    def _open_risk_by_instrument_conn(self, conn: sqlite3.Connection) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in conn.execute(
            "SELECT instrument_key, planned_risk_inr FROM positions WHERE quantity > 0"
        ):
            out[str(r["instrument_key"])] = float(r["planned_risk_inr"] or 0.0)
        return out

    def open_risk_by_instrument(self) -> dict[str, float]:
        with self._conn() as conn:
            return self._open_risk_by_instrument_conn(conn)

    def _pending_buy_risk_by_underlying_conn(self, conn: sqlite3.Connection) -> dict[str, float]:
        ph = ",".join("?" * len(_ACTIVE_ORDER_STATUSES))
        out: dict[str, float] = {}
        rows = conn.execute(
            f"""
            SELECT underlying, SUM(reserved_risk) AS rr
            FROM orders
            WHERE side = ? AND status IN ({ph}) AND quantity > filled_qty
            GROUP BY underlying
            """,
            (OrderSide.BUY.value, *_ACTIVE_ORDER_STATUSES),
        ).fetchall()
        for r in rows:
            out[str(r["underlying"]).upper()] = float(r["rr"] or 0.0)
        return out

    def _pending_buy_risk_by_instrument_conn(self, conn: sqlite3.Connection) -> dict[str, float]:
        ph = ",".join("?" * len(_ACTIVE_ORDER_STATUSES))
        out: dict[str, float] = {}
        rows = conn.execute(
            f"""
            SELECT instrument_key, SUM(reserved_risk) AS rr
            FROM orders
            WHERE side = ? AND status IN ({ph}) AND quantity > filled_qty
            GROUP BY instrument_key
            """,
            (OrderSide.BUY.value, *_ACTIVE_ORDER_STATUSES),
        ).fetchall()
        for r in rows:
            out[str(r["instrument_key"])] = float(r["rr"] or 0.0)
        return out

    def _exposed_instrument_count_conn(self, conn: sqlite3.Connection) -> int:
        keys: set[str] = set()
        for r in conn.execute("SELECT instrument_key FROM positions WHERE quantity > 0"):
            keys.add(str(r["instrument_key"]))
        ph = ",".join("?" * len(_ACTIVE_ORDER_STATUSES))
        for r in conn.execute(
            f"""
            SELECT DISTINCT instrument_key FROM orders
            WHERE side = ? AND status IN ({ph}) AND quantity > filled_qty
            """,
            (OrderSide.BUY.value, *_ACTIVE_ORDER_STATUSES),
        ):
            keys.add(str(r["instrument_key"]))
        return len(keys)

    def open_risk_by_underlying(self) -> dict[str, float]:
        out: dict[str, float] = {}
        with self._conn() as conn:
            for r in conn.execute(
                "SELECT underlying, quantity, avg_price, planned_risk_inr FROM positions WHERE quantity > 0"
            ):
                und = str(r["underlying"]).upper()
                stored = float(r["planned_risk_inr"] or 0.0)
                if stored > 0:
                    risk = stored
                else:
                    risk = min(float(r["quantity"]) * float(r["avg_price"]), EXECUTION_V1.per_position_budget_inr)
                out[und] = out.get(und, 0.0) + risk
        return out

    def owned_quantity_by_instrument(self) -> dict[str, int]:
        out: dict[str, int] = {}
        with self._conn() as conn:
            for r in conn.execute("SELECT instrument_key, quantity FROM positions WHERE quantity > 0"):
                out[str(r["instrument_key"])] = int(r["quantity"])
        return out

    def _pending_sell_qty_by_instrument_conn(self, conn: sqlite3.Connection) -> dict[str, int]:
        ph = ",".join("?" * len(_ACTIVE_ORDER_STATUSES))
        out: dict[str, int] = {}
        rows = conn.execute(
            f"""
            SELECT instrument_key, SUM(quantity - filled_qty) AS rem
            FROM orders
            WHERE side = ? AND status IN ({ph})
            GROUP BY instrument_key
            """,
            (OrderSide.SELL.value, *_ACTIVE_ORDER_STATUSES),
        ).fetchall()
        for r in rows:
            rem = int(r["rem"] or 0)
            if rem > 0:
                out[str(r["instrument_key"])] = rem
        return out

    def pending_sell_qty_by_instrument(self) -> dict[str, int]:
        with self._conn() as conn:
            return self._pending_sell_qty_by_instrument_conn(conn)

    def position_quantity(self, instrument_key: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT quantity FROM positions WHERE instrument_key=?", (instrument_key,)
            ).fetchone()
            return int(row["quantity"]) if row else 0

    def sum_open_risk(self) -> float:
        return sum(self.open_risk_by_underlying().values())

    def _portfolio_context_conn(self, conn: sqlite3.Connection) -> ExecutionPortfolioContext:
        cash = self._cash_balance_conn(conn)
        res_cash = self._reserved_cash_conn(conn)
        rows = conn.execute(
            "SELECT quantity, COALESCE(mark_price, avg_price) AS px FROM positions"
        ).fetchall()
        pos_val = sum(float(r["quantity"]) * float(r["px"]) for r in rows)
        eq = cash + pos_val
        peak_row = conn.execute("SELECT value FROM ledger_meta WHERE key='peak_equity'").fetchone()
        peak = float(peak_row["value"]) if peak_row else eq
        if eq > peak:
            peak = eq
            conn.execute(
                "INSERT INTO ledger_meta(key,value) VALUES('peak_equity',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(eq),),
            )
        owned: dict[str, int] = {}
        for r in conn.execute("SELECT instrument_key, quantity FROM positions WHERE quantity > 0"):
            owned[str(r["instrument_key"])] = int(r["quantity"])
        open_risk_by_underlying: dict[str, float] = {}
        for r in conn.execute(
            "SELECT underlying, quantity, avg_price, planned_risk_inr FROM positions WHERE quantity > 0"
        ):
            und = str(r["underlying"]).upper()
            stored = float(r["planned_risk_inr"] or 0.0)
            if stored > 0:
                risk = stored
            else:
                risk = min(float(r["quantity"]) * float(r["avg_price"]), EXECUTION_V1.per_position_budget_inr)
            open_risk_by_underlying[und] = open_risk_by_underlying.get(und, 0.0) + risk
        return ExecutionPortfolioContext(
            profile_id=EXECUTION_V1.profile_id,
            policy=self.policy,
            equity_inr=eq,
            peak_equity_inr=peak,
            cash_inr=cash,
            reserved_cash_inr=res_cash,
            reserved_risk_inr=self._reserved_risk_conn(conn),
            open_position_count=len([1 for q in owned.values() if q != 0]),
            open_risk_by_underlying=open_risk_by_underlying,
            sum_open_risk_inr=sum(open_risk_by_underlying.values()),
            valuation_trusted=True,
            has_unreconciled_external=False,
            available_strategy_cash_inr=min(cash - res_cash, self.policy.initial_allocation_inr),
            owned_quantity_by_instrument=tuple(sorted(owned.items())),
            pending_sell_qty_by_instrument=tuple(
                sorted(self._pending_sell_qty_by_instrument_conn(conn).items())
            ),
            open_risk_by_instrument=tuple(sorted(self._open_risk_by_instrument_conn(conn).items())),
            pending_buy_risk_by_instrument=tuple(
                sorted(self._pending_buy_risk_by_instrument_conn(conn).items())
            ),
            pending_buy_risk_by_underlying=tuple(
                sorted(self._pending_buy_risk_by_underlying_conn(conn).items())
            ),
            exposed_instrument_count=self._exposed_instrument_count_conn(conn),
        )

    def portfolio_context(self) -> ExecutionPortfolioContext:
        with self._conn() as conn:
            ctx = self._portfolio_context_conn(conn)
        self.set_peak_if_higher(ctx.equity_inr)
        return ctx

    def create_reservation(self, candidate: TradeCandidate, local_id: str, risk_inr: float) -> None:
        reduce_only = candidate.side == OrderSide.SELL
        need = 0.0 if reduce_only else candidate.limit_price_inr * candidate.quantity + candidate.entry_cost_inr
        calc_risk = resolved_candidate_risk(candidate)
        if calc_risk is not None and not reduce_only:
            risk_inr = calc_risk
        if reduce_only:
            risk_inr = 0.0
        now = _utcnow()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                ctx = self._portfolio_context_conn(conn)
                gate = evaluate_entry(candidate, ctx, for_reduce_only=reduce_only)
                if not gate.allowed:
                    raise ValueError("; ".join(gate.reasons) or "Reservation blocked by policy.")
                if reduce_only:
                    pos = conn.execute(
                        "SELECT * FROM positions WHERE instrument_key=? AND quantity > 0",
                        (candidate.instrument_key,),
                    ).fetchone()
                    if pos is None:
                        raise ValueError("No owned position for close reservation.")
                    self._assert_close_candidate_matches_position(candidate, pos)
                conn.execute(
                    """
                    INSERT INTO orders(local_id, mode, status, instrument_key, symbol, underlying, side, quantity,
                    filled_qty, limit_price, reserved_cash, reserved_risk, initial_reserved_cash, initial_reserved_risk,
                    instrument_kind, lot_size, product, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        local_id,
                        candidate.mode.value,
                        OrderStatus.PENDING.value,
                        candidate.instrument_key,
                        candidate.trading_symbol,
                        candidate.underlying,
                        candidate.side.value,
                        candidate.quantity,
                        candidate.limit_price_inr,
                        need,
                        risk_inr,
                        need,
                        risk_inr,
                        candidate.kind.value,
                        candidate.lot_size,
                        candidate.product.value,
                        now,
                        now,
                    ),
                )
                conn.commit()
            except Exception:
                conn.execute("ROLLBACK")
                raise

    @staticmethod
    def _assert_close_candidate_matches_position(candidate: TradeCandidate, pos: sqlite3.Row) -> None:
        if int(pos["closeable"] or 0) != 1:
            raise ValueError("Position metadata incomplete — cannot admit close.")
        saved_kind = str(pos["instrument_kind"] or "").strip()
        saved_product = str(pos["product"] or "").strip()
        if not saved_kind or not saved_product:
            raise ValueError("Position metadata incomplete — cannot admit close.")
        lot = int(pos["lot_size"] or 0)
        if lot < 1:
            raise ValueError("Position metadata incomplete — cannot admit close.")
        if candidate.kind.value != saved_kind:
            raise ValueError("Close candidate kind does not match owned position metadata.")
        if int(candidate.lot_size) != lot:
            raise ValueError("Close candidate lot size does not match owned position metadata.")
        if candidate.product.value != saved_product:
            raise ValueError("Close candidate product does not match owned position metadata.")
        if candidate.instrument_key != str(pos["instrument_key"]):
            raise ValueError("Close candidate instrument does not match owned position.")
        if candidate.trading_symbol != str(pos["symbol"]):
            raise ValueError("Close candidate symbol does not match owned position.")
        if candidate.underlying.upper() != str(pos["underlying"]).upper():
            raise ValueError("Close candidate underlying does not match owned position.")

    def admit_paper_close(
        self,
        candidate: TradeCandidate,
        intent_id: str,
        identity_hash: str,
        *,
        exit_fees_inr: float | None = None,
        slippage_pct: float | None = None,
    ) -> str:
        if candidate.side != OrderSide.SELL or candidate.mode != ExecutionMode.PAPER:
            raise ValueError("Close admission requires Paper SELL candidate.")
        validate_close_admission_economics(exit_fees_inr, slippage_pct)
        local_id = str(uuid.uuid4())
        now = _utcnow()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                dup = conn.execute(
                    "SELECT intent_id, identity_hash, local_order_id, exit_fees_inr, slippage_pct "
                    "FROM close_intents WHERE intent_id=?",
                    (intent_id,),
                ).fetchone()
                if dup is not None:
                    if str(dup["identity_hash"]) != identity_hash:
                        raise ValueError("Close intent payload conflict.")
                    if exit_fees_inr is not None and dup["exit_fees_inr"] is not None:
                        if abs(float(dup["exit_fees_inr"]) - exit_fees_inr) > 1e-9:
                            raise ValueError("Close intent fee assumption conflict.")
                    if slippage_pct is not None and dup["slippage_pct"] is not None:
                        if abs(float(dup["slippage_pct"]) - slippage_pct) > 1e-12:
                            raise ValueError("Close intent slippage assumption conflict.")
                    conn.execute("ROLLBACK")
                    return str(dup["local_order_id"])
                pos = conn.execute(
                    "SELECT * FROM positions WHERE instrument_key=? AND quantity > 0",
                    (candidate.instrument_key,),
                ).fetchone()
                if pos is None:
                    raise ValueError("No owned position for close admission.")
                self._assert_close_candidate_matches_position(candidate, pos)
                ctx = self._portfolio_context_conn(conn)
                gate = evaluate_entry(candidate, ctx, for_reduce_only=True)
                if not gate.allowed:
                    raise ValueError("; ".join(gate.reasons) or "Close blocked.")
                self._insert_close_reservation_in_tx(conn, candidate, pos, local_id, now)
                conn.execute(
                    "INSERT INTO close_intents(intent_id, identity_hash, local_order_id, consumed, "
                    "exit_fees_inr, slippage_pct, created_at) VALUES (?,?,?,?,?,?,?)",
                    (intent_id, identity_hash, local_id, 1, exit_fees_inr, slippage_pct, now),
                )
                conn.commit()
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return local_id

    def _insert_reservation_in_tx(
        self,
        conn: sqlite3.Connection,
        candidate: TradeCandidate,
        local_id: str,
        risk_inr: float,
        now: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO orders(local_id, mode, status, instrument_key, symbol, underlying, side, quantity,
            filled_qty, limit_price, reserved_cash, reserved_risk, initial_reserved_cash, initial_reserved_risk,
            instrument_kind, lot_size, product, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                local_id,
                candidate.mode.value,
                OrderStatus.PENDING.value,
                candidate.instrument_key,
                candidate.trading_symbol,
                candidate.underlying,
                candidate.side.value,
                candidate.quantity,
                candidate.limit_price_inr,
                0.0,
                0.0,
                0.0,
                0.0,
                candidate.kind.value,
                candidate.lot_size,
                candidate.product.value,
                now,
                now,
            ),
        )

    def _insert_close_reservation_in_tx(
        self,
        conn: sqlite3.Connection,
        candidate: TradeCandidate,
        pos: sqlite3.Row,
        local_id: str,
        now: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO orders(local_id, mode, status, instrument_key, symbol, underlying, side, quantity,
            filled_qty, limit_price, reserved_cash, reserved_risk, initial_reserved_cash, initial_reserved_risk,
            instrument_kind, lot_size, product, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                local_id,
                candidate.mode.value,
                OrderStatus.PENDING.value,
                pos["instrument_key"],
                pos["symbol"],
                pos["underlying"],
                candidate.side.value,
                candidate.quantity,
                candidate.limit_price_inr,
                0.0,
                0.0,
                0.0,
                0.0,
                pos["instrument_kind"],
                int(pos["lot_size"]),
                pos["product"],
                now,
                now,
            ),
        )

    def list_closeable_positions(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT instrument_key, symbol, underlying, quantity, avg_price, mark_price, entry_fees_inr,
                       instrument_kind, lot_size, product, closeable, planned_risk_inr
                FROM positions WHERE quantity > 0 AND closeable=1
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def cumulative_realized_net(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT COALESCE(SUM(net_inr),0) FROM realized_events").fetchone()
            return float(row[0])

    def execute_paper_close_fill(
        self,
        local_id: str,
        *,
        observation_id: str,
        quote: QuoteSnapshot,
        lot_size: int,
        kind: InstrumentKind,
        limit_price_inr: float,
        exit_fees_inr: float,
        slippage_pct: float,
        fill_event_id: str,
        modeled_fill_qty: int,
        modeled_fill_price: float,
    ) -> int:
        """Atomically consume one quote observation and apply a close fill when eligible."""
        if modeled_fill_qty <= 0:
            return 0
        validate_fill_economics(
            fill_qty=modeled_fill_qty,
            fill_price=modeled_fill_price,
            fees=exit_fees_inr,
            fill_event_id=fill_event_id,
            slippage_pct=slippage_pct,
        )
        if not observation_id.strip():
            raise ValueError("observation_id required")
        if quote.instrument_key.strip() == "":
            raise ValueError("Quote instrument required.")
        validate_execution_quote(quote, instrument_key=quote.instrument_key)
        now = _utcnow()
        src_at = quote.evaluated_at.astimezone(timezone.utc).isoformat()
        applied = 0
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM orders WHERE local_id=?", (local_id,)).fetchone()
                if row is None:
                    raise ValueError("Unknown order")
                if row["instrument_key"] != quote.instrument_key:
                    raise ValueError("Quote instrument does not match close order.")
                if abs(float(row["limit_price"]) - limit_price_inr) > 1e-9:
                    raise ValueError("Close limit does not match admitted order.")
                validate_execution_quote(quote, instrument_key=str(row["instrument_key"]))
                order_lot = int(row["lot_size"] or 1)
                order_kind = InstrumentKind(row["instrument_kind"] or InstrumentKind.CASH_STOCK.value)
                if lot_size != order_lot or kind != order_kind:
                    raise ValueError("Close fill metadata does not match admitted order contract.")
                if order_kind == InstrumentKind.NIFTY_OPTION and order_lot > 1:
                    if modeled_fill_qty % order_lot != 0:
                        raise ValueError("Option close fill must be whole lots.")
                obs = conn.execute(
                    "SELECT consumed FROM quote_observations WHERE observation_id=?", (observation_id,)
                ).fetchone()
                if obs is not None and int(obs["consumed"] or 0) == 1:
                    conn.execute("ROLLBACK")
                    return 0
                if obs is None:
                    conn.execute(
                        "INSERT INTO quote_observations("
                        "observation_id, instrument_key, source_at, bid_qty, consumed, created_at"
                        ") VALUES (?,?,?,?,0,?)",
                        (observation_id, quote.instrument_key, src_at, int(quote.bid_qty), now),
                    )
                elif int(obs["consumed"] or 0) == 1:
                    conn.execute("ROLLBACK")
                    return 0
                filled = self._apply_paper_fill_conn(
                    conn,
                    local_id,
                    fill_qty=modeled_fill_qty,
                    fill_price=modeled_fill_price,
                    fees=exit_fees_inr,
                    fill_event_id=fill_event_id,
                )
                if filled <= 0:
                    conn.execute("ROLLBACK")
                    return 0
                conn.execute(
                    "UPDATE quote_observations SET consumed=1 WHERE observation_id=?", (observation_id,)
                )
                conn.commit()
                applied = filled
            except Exception:
                conn.execute("ROLLBACK")
                raise
        if applied > 0:
            peak_eq = self.equity()
            self.set_peak_if_higher(peak_eq)
        return applied

    def _apply_paper_fill_conn(
        self,
        conn: sqlite3.Connection,
        local_id: str,
        *,
        fill_qty: int,
        fill_price: float,
        fees: float,
        fill_event_id: str,
    ) -> int:
        validate_fill_economics(
            fill_qty=fill_qty,
            fill_price=fill_price,
            fees=fees,
            fill_event_id=fill_event_id,
        )
        now = _utcnow()
        existing = conn.execute(
            "SELECT local_order_id, qty, price, fees FROM fills WHERE fill_event_id=?",
            (fill_event_id,),
        ).fetchone()
        if existing is not None:
            if (
                str(existing["local_order_id"]) != local_id
                or int(existing["qty"]) != fill_qty
                or abs(float(existing["price"]) - fill_price) > 1e-9
                or abs(float(existing["fees"]) - fees) > 1e-9
            ):
                raise ValueError("Conflicting fill_event_id payload.")
            return 0
        row = conn.execute("SELECT * FROM orders WHERE local_id=?", (local_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown order")
        if row["mode"] != ExecutionMode.PAPER.value:
            raise ValueError("Paper fills apply to PAPER orders only.")
        if row["status"] == OrderStatus.CANCELLED.value:
            raise ValueError("Cannot fill cancelled order remainder.")
        if row["status"] in (OrderStatus.REJECTED.value, OrderStatus.UNKNOWN_SUBMISSION.value):
            raise ValueError("Cannot fill terminal broker-state order.")
        order_qty = int(row["quantity"])
        prior_filled = int(row["filled_qty"])
        if row["side"] == OrderSide.SELL.value:
            owned_row = conn.execute(
                "SELECT quantity FROM positions WHERE instrument_key=?",
                (row["instrument_key"],),
            ).fetchone()
            owned = int(owned_row["quantity"]) if owned_row else 0
            ph = ",".join("?" * len(_ACTIVE_ORDER_STATUSES))
            pending_other = conn.execute(
                f"""
                SELECT COALESCE(SUM(quantity - filled_qty),0) FROM orders
                WHERE instrument_key=? AND side=? AND status IN ({ph}) AND local_id <> ?
                """,
                (row["instrument_key"], OrderSide.SELL.value, *_ACTIVE_ORDER_STATUSES, local_id),
            ).fetchone()[0]
            if owned - int(pending_other or 0) < fill_qty:
                raise ValueError("Sell would exceed owned units.")
        if prior_filled >= order_qty:
            return 0
        remaining = order_qty - prior_filled
        if fill_qty > remaining:
            raise ValueError(f"Overfill rejected: {fill_qty} > {remaining} remaining.")
        side = row["side"]
        limit_px = float(row["limit_price"])
        if side == OrderSide.BUY.value and fill_price > limit_px:
            raise ValueError("Buy fill price exceeds order limit.")
        if side == OrderSide.SELL.value and fill_price < limit_px:
            raise ValueError("Sell fill price below order limit.")
        new_filled = prior_filled + fill_qty
        fill_id = hashlib.sha256(fill_event_id.encode()).hexdigest()[:40]
        cash_delta = -fill_qty * fill_price if side == OrderSide.BUY.value else fill_qty * fill_price
        conn.execute(
            "INSERT INTO fills(fill_id, fill_event_id, local_order_id, qty, price, fees, filled_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (fill_id, fill_event_id, local_id, fill_qty, fill_price, fees, now),
        )
        conn.execute(
            "INSERT INTO cash_ledger(event_id,delta_cash,delta_fees,note,created_at) VALUES(?,?,?,?,?)",
            (str(uuid.uuid4()), cash_delta, fees, f"fill {local_id}", now),
        )
        status = OrderStatus.FILLED.value if new_filled >= order_qty else OrderStatus.PARTIALLY_FILLED.value
        unfilled = max(0, order_qty - new_filled)
        init_cash = float(row["initial_reserved_cash"] or row["reserved_cash"])
        init_risk = float(row["initial_reserved_risk"] or row["reserved_risk"])
        if unfilled == 0:
            reserved_cash = 0.0
            reserved_risk = 0.0
        else:
            reserved_cash = (init_cash / order_qty) * unfilled
            reserved_risk = (init_risk / order_qty) * unfilled
        conn.execute(
            "UPDATE orders SET filled_qty=?, status=?, reserved_cash=?, reserved_risk=?, updated_at=? "
            "WHERE local_id=?",
            (new_filled, status, reserved_cash, reserved_risk, now, local_id),
        )
        risk_per_unit = init_risk / order_qty if order_qty else 0.0
        fill_risk = risk_per_unit * fill_qty
        pos = conn.execute(
            "SELECT * FROM positions WHERE instrument_key=?", (row["instrument_key"],)
        ).fetchone()
        signed = fill_qty if side == OrderSide.BUY.value else -fill_qty
        kind = row["instrument_kind"] or InstrumentKind.CASH_STOCK.value
        lot = int(row["lot_size"] or 1)
        product = row["product"] or ProductType.DELIVERY.value
        if pos is None:
            if signed < 0:
                raise ValueError("Cannot sell without a position.")
            conn.execute(
                "INSERT INTO positions(instrument_key,symbol,underlying,quantity,avg_price,mark_price,"
                "mark_time,planned_risk_inr,entry_fees_inr,instrument_kind,lot_size,product,closeable) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)",
                (
                    row["instrument_key"],
                    row["symbol"],
                    row["underlying"],
                    signed,
                    fill_price,
                    fill_price,
                    now,
                    fill_risk,
                    fees if side == OrderSide.BUY.value else 0.0,
                    kind,
                    lot,
                    product,
                ),
            )
        else:
            old_q = int(pos["quantity"])
            new_q = old_q + signed
            entry_fees = float(pos["entry_fees_inr"] or 0.0)
            avg = float(pos["avg_price"])
            pr = float(pos["planned_risk_inr"] or 0.0)
            if new_q == 0:
                if signed < 0:
                    alloc_fees, _ = allocate_proportional(entry_fees, fill_qty, old_q)
                    gross, net = sell_realized(fill_qty * fill_price, fill_qty * avg, alloc_fees, fees)
                    conn.execute(
                        "INSERT INTO realized_events(event_id,fill_event_id,gross_inr,net_inr,created_at)"
                        " VALUES(?,?,?,?,?)",
                        (str(uuid.uuid4()), fill_event_id, gross, net, now),
                    )
                conn.execute("DELETE FROM positions WHERE instrument_key=?", (row["instrument_key"],))
            elif signed > 0:
                avg = (avg * old_q + fill_price * signed) / new_q
                entry_fees += fees
                pr += fill_risk
                conn.execute(
                    "UPDATE positions SET quantity=?, avg_price=?, mark_price=?, mark_time=?, "
                    "planned_risk_inr=?, entry_fees_inr=?, instrument_kind=?, lot_size=?, product=?, closeable=1 "
                    "WHERE instrument_key=?",
                    (new_q, avg, fill_price, now, pr, entry_fees, kind, lot, product, row["instrument_key"]),
                )
            else:
                alloc_fees, remain_fees = allocate_proportional(entry_fees, fill_qty, old_q)
                gross, net = sell_realized(fill_qty * fill_price, fill_qty * avg, alloc_fees, fees)
                conn.execute(
                    "INSERT INTO realized_events(event_id,fill_event_id,gross_inr,net_inr,created_at)"
                    " VALUES(?,?,?,?,?)",
                    (str(uuid.uuid4()), fill_event_id, gross, net, now),
                )
                pr = pr * (new_q / old_q) if old_q else 0.0
                mark = float(pos["mark_price"]) if pos["mark_price"] is not None else avg
                conn.execute(
                    "UPDATE positions SET quantity=?, avg_price=?, mark_price=?, "
                    "planned_risk_inr=?, entry_fees_inr=? WHERE instrument_key=?",
                    (new_q, avg, mark, pr, remain_fees, row["instrument_key"]),
                )
        return fill_qty

    def apply_paper_fill(
        self,
        local_id: str,
        *,
        fill_qty: int,
        fill_price: float,
        fees: float,
        fill_event_id: str,
    ) -> None:
        validate_fill_economics(
            fill_qty=fill_qty,
            fill_price=fill_price,
            fees=fees,
            fill_event_id=fill_event_id,
        )
        fill_qty = int(fill_qty)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                applied = self._apply_paper_fill_conn(
                    conn,
                    local_id,
                    fill_qty=fill_qty,
                    fill_price=fill_price,
                    fees=fees,
                    fill_event_id=fill_event_id,
                )
                conn.commit()
            except Exception:
                conn.execute("ROLLBACK")
                raise
        if applied > 0:
            peak_eq = self.equity()
            self.set_peak_if_higher(peak_eq)

    def get_paper_order(self, local_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM orders WHERE local_id=? AND mode=?", (local_id, ExecutionMode.PAPER.value)).fetchone()
            return dict(row) if row is not None else None

    def list_paper_orders(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT local_id, symbol, instrument_key, underlying, side, status, quantity, filled_qty,
                       limit_price, reserved_cash, reserved_risk, mode
                FROM orders WHERE mode = ?
                ORDER BY updated_at DESC
                """,
                (ExecutionMode.PAPER.value,),
            ).fetchall()
            return [dict(r) for r in rows]

    def cancel_paper_remainder(self, local_id: str) -> str:
        """Cancel unfilled remainder of a PAPER order; release reservations only."""
        if not local_id.strip():
            raise ValueError("Order id required.")
        now = _utcnow()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM orders WHERE local_id=?", (local_id,)).fetchone()
                if row is None:
                    raise ValueError("Unknown order.")
                if row["mode"] != ExecutionMode.PAPER.value:
                    raise ValueError("Only Paper orders can be cancelled locally.")
                status = str(row["status"])
                if status == OrderStatus.CANCELLED.value:
                    conn.execute("ROLLBACK")
                    return "Already cancelled."
                if status in (
                    OrderStatus.FILLED.value,
                    OrderStatus.REJECTED.value,
                    OrderStatus.UNKNOWN_SUBMISSION.value,
                ):
                    raise ValueError(f"Order not cancellable in status {status}.")
                filled = int(row["filled_qty"])
                qty = int(row["quantity"])
                if filled >= qty:
                    raise ValueError("Order has no unfilled remainder.")
                if status not in _ACTIVE_ORDER_STATUSES:
                    raise ValueError(f"Order not cancellable in status {status}.")
                conn.execute(
                    "UPDATE orders SET status=?, reserved_cash=0, reserved_risk=0, updated_at=? WHERE local_id=?",
                    (OrderStatus.CANCELLED.value, now, local_id),
                )
                conn.commit()
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return "Cancelled unfilled remainder."
