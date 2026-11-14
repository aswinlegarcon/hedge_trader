"""Decode Upstox Market Data Feed V3 protobuf (official schema)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .constants import MAX_TRADE_TS_MS
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


@dataclass(frozen=True)
class DecodedFrame:
    message_type: str
    ticks: list[DecodedTick]
    market_info: MarketInfoSnapshot | None
    rejected_ticks: int  # ltpc entries dropped for non-positive / non-finite / out-of-range fields


def _valid_receipt(ms: int) -> bool:
    return 0 < ms <= MAX_TRADE_TS_MS


def decode_feed_frame(raw: bytes) -> DecodedFrame:
    """Decode one Feed V3 frame. Raises on undecodable bytes; invalid ltpc fields are counted, not raised."""
    msg = pb.FeedResponse()
    msg.ParseFromString(raw)
    type_name = pb.Type.Name(msg.type) if msg.type in pb.Type.values() else "unknown"
    ticks: list[DecodedTick] = []
    rejected = 0
    receipt = _ms_to_utc(int(msg.currentTs)) if _valid_receipt(int(msg.currentTs)) else datetime.now(timezone.utc)

    if type_name == "market_info":
        segs = {k: pb.MarketStatus.Name(v) for k, v in msg.marketInfo.segmentStatus.items()}
        return DecodedFrame(type_name, ticks, MarketInfoSnapshot(segment_status=segs, receipt_ts_utc=receipt), 0)

    if type_name not in ("live_feed", "initial_feed"):
        return DecodedFrame(type_name, ticks, None, 0)

    for ikey, feed in msg.feeds.items():
        if feed.WhichOneof("FeedUnion") != "ltpc":
            continue
        lt = feed.ltpc
        price = float(lt.ltp)
        ltt = int(lt.ltt)
        if not math.isfinite(price) or price <= 0 or ltt <= 0 or ltt > MAX_TRADE_TS_MS:
            rejected += 1
            continue
        ticks.append(DecodedTick(instrument_key=ikey, price=price, trade_ts_utc=_ms_to_utc(ltt), is_heartbeat=False, message_type=type_name))
    return DecodedFrame(type_name, ticks, None, rejected)


def decode_feed_message(raw: bytes) -> tuple[str, list[DecodedTick], MarketInfoSnapshot | None]:
    frame = decode_feed_frame(raw)
    return frame.message_type, frame.ticks, frame.market_info


def build_subscribe_frame(*, instrument_keys: list[str], mode: str = "ltpc", guid: str = "nsl-spec14") -> bytes:
    import json

    payload: dict[str, Any] = {
        "guid": guid,
        "method": "sub",
        "data": {"mode": mode, "instrumentKeys": instrument_keys},
    }
    return json.dumps(payload).encode("utf-8")