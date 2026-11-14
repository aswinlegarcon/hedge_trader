"""Deterministic protobuf frames for REPLAY transport (tests/UI default)."""
from __future__ import annotations

from .proto import MarketDataFeedV3_pb2 as pb


def ltpc_frame(*, instrument_key: str, ltp: float, trade_ms: int, receipt_ms: int | None = None) -> bytes:
    msg = pb.FeedResponse()
    msg.type = pb.Type.live_feed
    msg.currentTs = receipt_ms if receipt_ms is not None else trade_ms
    feed = msg.feeds[instrument_key]
    feed.ltpc.ltp = ltp
    feed.ltpc.ltt = trade_ms
    return msg.SerializeToString()


def market_info_frame(*, receipt_ms: int, segment: str = "NSE_EQ", status: pb.MarketStatus = pb.MarketStatus.NORMAL_OPEN) -> bytes:
    msg = pb.FeedResponse()
    msg.type = pb.Type.market_info
    msg.currentTs = receipt_ms
    msg.marketInfo.segmentStatus[segment] = status
    return msg.SerializeToString()