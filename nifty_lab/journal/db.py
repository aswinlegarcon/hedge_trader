"""SQLite research & paper-trading journal.

Simulated results are stored here and are NEVER mixed with real account data.
Every row carries ``is_paper = 1`` so later versions can keep the separation.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    instrument TEXT NOT NULL,
    strategy TEXT NOT NULL,
    market_regime TEXT,
    signal TEXT,
    entry_thesis TEXT,
    legs_json TEXT,
    fill_prices_json TEXT,
    lots INTEGER DEFAULT 1,
    quantity INTEGER DEFAULT 0,
    net_premium_inr REAL,
    max_risk_inr REAL,
    max_profit_inr REAL,
    profit_target_inr REAL,
    planned_exit TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    closed_at TEXT,
    realised_pnl_inr REAL,
    outcome_notes TEXT,
    mistakes TEXT,
    lessons TEXT,
    data_source TEXT,
    is_paper INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS research_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    tags TEXT
);
CREATE TABLE IF NOT EXISTS signal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    as_of TEXT,
    instrument TEXT,
    signal TEXT,
    regime TEXT,
    report_json TEXT,
    data_source TEXT
);
"""


@dataclass
class JournalEntry:
    trade_date: str
    instrument: str
    strategy: str
    market_regime: str = ""
    signal: str = ""
    entry_thesis: str = ""
    legs: list[dict] = field(default_factory=list)
    fill_prices: dict = field(default_factory=dict)
    lots: int = 1
    quantity: int = 0
    net_premium_inr: float | None = None
    max_risk_inr: float | None = None
    max_profit_inr: float | None = None
    profit_target_inr: float | None = None
    planned_exit: str = ""
    status: str = "OPEN"
    closed_at: str | None = None
    realised_pnl_inr: float | None = None
    outcome_notes: str = ""
    mistakes: str = ""
    lessons: str = ""
    data_source: str = ""
    is_paper: int = 1
    id: int | None = None
    created_at: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # --- entries -----------------------------------------------------------
    def add_entry(self, e: JournalEntry) -> int:
        if e.is_paper != 1:
            raise ValueError("v1 journal only accepts paper entries (is_paper=1)")
        with self._conn() as con:
            cur = con.execute(
                """INSERT INTO journal_entries (created_at, trade_date, instrument, strategy, market_regime, signal, entry_thesis,
                   legs_json, fill_prices_json, lots, quantity, net_premium_inr, max_risk_inr, max_profit_inr, profit_target_inr,
                   planned_exit, status, closed_at, realised_pnl_inr, outcome_notes, mistakes, lessons, data_source, is_paper)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _now(), e.trade_date, e.instrument, e.strategy, e.market_regime, e.signal, e.entry_thesis,
                    json.dumps(e.legs), json.dumps(e.fill_prices), e.lots, e.quantity, e.net_premium_inr, e.max_risk_inr,
                    e.max_profit_inr, e.profit_target_inr, e.planned_exit, e.status, e.closed_at, e.realised_pnl_inr,
                    e.outcome_notes, e.mistakes, e.lessons, e.data_source, 1,
                ),
            )
            return int(cur.lastrowid)

    def close_entry(self, entry_id: int, realised_pnl_inr: float, outcome_notes: str = "", mistakes: str = "", lessons: str = "") -> None:
        with self._conn() as con:
            cur = con.execute(
                "UPDATE journal_entries SET status='CLOSED', closed_at=?, realised_pnl_inr=?, outcome_notes=?, mistakes=?, lessons=? WHERE id=? AND status='OPEN'",
                (_now(), realised_pnl_inr, outcome_notes, mistakes, lessons, entry_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"No OPEN entry with id {entry_id}")

    def entries(self, status: str | None = None) -> pd.DataFrame:
        q = "SELECT * FROM journal_entries"
        params: tuple = ()
        if status:
            q += " WHERE status=?"
            params = (status,)
        q += " ORDER BY trade_date DESC, id DESC"
        with self._conn() as con:
            return pd.read_sql_query(q, con, params=params)

    def open_risk_inr(self) -> float:
        with self._conn() as con:
            row = con.execute("SELECT COALESCE(SUM(max_risk_inr),0) AS r FROM journal_entries WHERE status='OPEN'").fetchone()
            return float(row["r"])

    def realised_pnl_inr(self) -> float:
        with self._conn() as con:
            row = con.execute("SELECT COALESCE(SUM(realised_pnl_inr),0) AS p FROM journal_entries WHERE status='CLOSED'").fetchone()
            return float(row["p"])

    def performance_summary(self) -> dict[str, float | int]:
        df = self.entries(status="CLOSED")
        if df.empty:
            return {"trades": 0}
        pnl = df["realised_pnl_inr"].astype(float)
        wins = pnl[pnl > 0]
        losses = pnl[pnl <= 0]
        gross_profit = float(wins.sum())
        gross_loss = float(-losses.sum())
        return {
            "trades": int(len(pnl)),
            "net_pnl_inr": float(pnl.sum()),
            "win_rate": float(len(wins) / len(pnl)),
            "avg_win_inr": float(wins.mean()) if len(wins) else 0.0,
            "avg_loss_inr": float(losses.mean()) if len(losses) else 0.0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else float("inf"),
            "expectancy_inr": float(pnl.mean()),
            "largest_loss_inr": float(pnl.min()),
        }

    # --- notes / signal log --------------------------------------------------
    def add_note(self, title: str, body: str, tags: str = "") -> int:
        with self._conn() as con:
            cur = con.execute("INSERT INTO research_notes (created_at, title, body, tags) VALUES (?,?,?,?)", (_now(), title, body, tags))
            return int(cur.lastrowid)

    def notes(self) -> pd.DataFrame:
        with self._conn() as con:
            return pd.read_sql_query("SELECT * FROM research_notes ORDER BY id DESC", con)

    def log_signal(self, as_of: str, instrument: str, signal: str, regime: str, report: dict, data_source: str) -> int:
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO signal_log (created_at, as_of, instrument, signal, regime, report_json, data_source) VALUES (?,?,?,?,?,?,?)",
                (_now(), as_of, instrument, signal, regime, json.dumps(report, default=str), data_source),
            )
            return int(cur.lastrowid)

    def signal_history(self, limit: int = 100) -> pd.DataFrame:
        with self._conn() as con:
            return pd.read_sql_query("SELECT id, created_at, as_of, instrument, signal, regime, data_source FROM signal_log ORDER BY id DESC LIMIT ?", con, params=(limit,))
