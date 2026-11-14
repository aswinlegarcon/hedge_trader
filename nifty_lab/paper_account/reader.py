"""Read-only SQLite snapshot of the Paper execution ledger."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from nifty_lab.execution.modes import ExecutionMode
from nifty_lab.execution.types import OrderStatus

_REQUIRED_TABLES = (
    "ledger_meta",
    "orders",
    "fills",
    "positions",
    "cash_ledger",
    "realized_events",
)

_REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "ledger_meta": ("key", "value"),
    "orders": (
        "local_id",
        "mode",
        "status",
        "side",
        "quantity",
        "filled_qty",
        "reserved_cash",
        "reserved_risk",
        "instrument_key",
        "symbol",
    ),
    "fills": ("fill_event_id", "fill_id", "local_order_id", "qty", "price", "fees", "filled_at"),
    "positions": (
        "instrument_key",
        "symbol",
        "quantity",
        "avg_price",
        "entry_fees_inr",
        "mark_price",
        "mark_time",
    ),
    "cash_ledger": ("delta_cash", "delta_fees", "note"),
    "realized_events": ("fill_event_id", "gross_inr", "net_inr"),
}

_ACTIVE_ORDER_STATUSES = (
    OrderStatus.PENDING.value,
    OrderStatus.OPEN.value,
    OrderStatus.PARTIALLY_FILLED.value,
    OrderStatus.UNKNOWN_SUBMISSION.value,
)

_TERMINAL_ORDER_STATUSES = (
    OrderStatus.FILLED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.REJECTED.value,
)


@dataclass
class PaperSnapshot:
    db_path: Path
    snapshot_at_utc: str
    meta: dict[str, str]
    cash_ledger: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    fills: list[dict[str, Any]]
    positions: list[dict[str, Any]]
    realized_events: list[dict[str, Any]]
    schema_tables: list[str]
    read_only_verified: bool = False
    load_status: str = "OK"
    load_error: str | None = None
    notes: list[str] = field(default_factory=list)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(r[0]) for r in rows}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    if table not in _REQUIRED_TABLES:
        return set()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _missing_schema_columns(conn: sqlite3.Connection, tables: set[str]) -> list[str]:
    missing: list[str] = []
    for table in _REQUIRED_TABLES:
        if table not in tables:
            continue
        cols = _column_names(conn, table)
        for req in _REQUIRED_COLUMNS[table]:
            if req not in cols:
                missing.append(f"{table}.{req}")
    return missing


def readonly_db_uri(db_path: Path) -> str:
    return f"{db_path.resolve().as_uri()}?mode=ro"


def open_readonly_connection(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.is_file():
        return None
    uri = readonly_db_uri(db_path)
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def verify_connection_readonly(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute("PRAGMA query_only").fetchone()
        return row is not None and int(row[0]) == 1
    except (sqlite3.Error, TypeError, ValueError):
        return False


def load_paper_snapshot(db_path: Path) -> PaperSnapshot:
    now = datetime.now(timezone.utc).isoformat()
    if not db_path.is_file():
        return PaperSnapshot(
            db_path=db_path,
            snapshot_at_utc=now,
            meta={},
            cash_ledger=[],
            orders=[],
            fills=[],
            positions=[],
            realized_events=[],
            schema_tables=[],
            load_status="NOT_INITIALIZED",
            load_error="DB_MISSING",
        )
    try:
        conn = open_readonly_connection(db_path)
    except sqlite3.Error:
        return PaperSnapshot(
            db_path=db_path,
            snapshot_at_utc=now,
            meta={},
            cash_ledger=[],
            orders=[],
            fills=[],
            positions=[],
            realized_events=[],
            schema_tables=[],
            load_status="READ_UNAVAILABLE",
            load_error="SQLITE_OPEN",
        )
    if conn is None:
        return PaperSnapshot(
            db_path=db_path,
            snapshot_at_utc=now,
            meta={},
            cash_ledger=[],
            orders=[],
            fills=[],
            positions=[],
            realized_events=[],
            schema_tables=[],
            load_status="READ_UNAVAILABLE",
            load_error="SQLITE_OPEN",
        )
    ro_ok = False
    try:
        conn.execute("BEGIN")
        ro_ok = verify_connection_readonly(conn)
        tables = _table_names(conn)
        missing = [t for t in _REQUIRED_TABLES if t not in tables]
        missing_cols = _missing_schema_columns(conn, tables) if not missing else []
        if missing or missing_cols:
            conn.execute("ROLLBACK")
            return PaperSnapshot(
                db_path=db_path,
                snapshot_at_utc=now,
                meta={},
                cash_ledger=[],
                orders=[],
                fills=[],
                positions=[],
                realized_events=[],
                schema_tables=sorted(tables),
                read_only_verified=ro_ok,
                load_status="UNSUPPORTED_SCHEMA",
                load_error="MISSING_TABLE" if missing else "MISSING_COLUMN",
            )
        if not ro_ok:
            conn.execute("ROLLBACK")
            return PaperSnapshot(
                db_path=db_path,
                snapshot_at_utc=now,
                meta={},
                cash_ledger=[],
                orders=[],
                fills=[],
                positions=[],
                realized_events=[],
                schema_tables=sorted(tables),
                read_only_verified=False,
                load_status="READ_UNAVAILABLE",
                load_error="READ_ONLY_UNVERIFIED",
            )
        meta = {
            str(r["key"]): str(r["value"])
            for r in conn.execute("SELECT key, value FROM ledger_meta")
        }
        cash_ledger = [dict(r) for r in conn.execute("SELECT * FROM cash_ledger")]
        orders = [dict(r) for r in conn.execute("SELECT * FROM orders")]
        fills = [dict(r) for r in conn.execute("SELECT * FROM fills")]
        positions = [dict(r) for r in conn.execute("SELECT * FROM positions")]
        realized_events = [dict(r) for r in conn.execute("SELECT * FROM realized_events")]
        conn.execute("COMMIT")
    except sqlite3.Error:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        return PaperSnapshot(
            db_path=db_path,
            snapshot_at_utc=now,
            meta={},
            cash_ledger=[],
            orders=[],
            fills=[],
            positions=[],
            realized_events=[],
            schema_tables=[],
            read_only_verified=ro_ok,
            load_status="READ_UNAVAILABLE",
            load_error="SQLITE_READ",
        )
    finally:
        conn.close()
    return PaperSnapshot(
        db_path=db_path,
        snapshot_at_utc=now,
        meta=meta,
        cash_ledger=cash_ledger,
        orders=orders,
        fills=fills,
        positions=positions,
        realized_events=realized_events,
        schema_tables=sorted(tables),
        read_only_verified=ro_ok,
        load_status="OK",
    )


def paper_orders_only(orders: list[dict]) -> tuple[list[dict], str | None]:
    paper = [o for o in orders if str(o.get("mode", "")).upper() == ExecutionMode.PAPER.value]
    other = [o for o in orders if str(o.get("mode", "")).upper() != ExecutionMode.PAPER.value]
    if other:
        return paper, "NON_PAPER_ORDERS"
    return paper, None
