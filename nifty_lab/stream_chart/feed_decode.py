"""Decode Upstox Market Data Feed V3 protobuf (official schema)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .proto import MarketDataFeedV3_pb2 as pb


@dataclass(frozen=True)
class DecodedTick:
    instrument_key: str
    price: float
    trade_ts_utc: datetime
    is_heartbeat: bool
    message_type: str


@dataclass(frozen=True)
class MarketInfoSnapshot:
    segment_status: dict[str, str]
    receipt_ts_utc: datetime


def _ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def decode_feed_message(raw: bytes) -> tuple[str, list[DecodedTick], MarketInfoSnapshot | None]:
    msg = pb.FeedResponse()
    msg.ParseFromString(raw)
    type_name = pb.Type.Name(msg.type) if msg.type in pb.Type.values() else "unknown"
    ticks: list[DecodedTick] = []
    market_info: MarketInfoSnapshot | None = None
    receipt = _ms_to_utc(int(msg.currentTs)) if msg.currentTs else datetime.now(timezone.utc)

    if type_name == "market_info":
        segs = {k: pb.MarketStatus.Name(v) for k, v in msg.marketInfo.segmentStatus.items()}
        market_info = MarketInfoSnapshot(segment_status=segs, receipt_ts_utc=receipt)
        return type_name, ticks, market_info

    if type_name not in ("live_feed", "initial_feed"):
        return type_name, ticks, market_info

    for ikey, feed in msg.feeds.items():
        if feed.WhichOneof("FeedUnion") != "ltpc":
            continue
        lt = feed.ltpc
        if lt.ltt <= 0 or lt.ltp <= 0:
            continue
        ticks.append(
            DecodedTick(
                instrument_key=ikey,
                price=float(lt.ltp),
                trade_ts_utc=_ms_to_utc(int(lt.ltt)),
                is_heartbeat=False,
                message_type=type_name,
            )
        )
    return type_name, ticks, market_info


def build_subscribe_frame(*, instrument_keys: list[str], mode: str = "ltpc", guid: str = "nsl-spec14") -> bytes:
    import json

    payload: dict[str, Any] = {
        "guid": guid,
        "method": "sub",
        "data": {"mode": mode, "instrumentKeys": instrument_keys},
    }
    return json.dumps(payload).encode("utf-8")