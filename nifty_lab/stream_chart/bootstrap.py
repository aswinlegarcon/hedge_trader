"""One intraday candle bootstrap per explicit Start."""
from __future__ import annotations

from datetime import datetime, timezone

from nifty_lab.brokers.upstox_candles import INTERVAL_5M, CandleIntervalSpec, candles_to_frame, parse_candle_response
from nifty_lab.brokers.upstox_errors import UpstoxEmptyError
from nifty_lab.brokers.upstox_instruments import encode_instrument_key
from nifty_lab.brokers.upstox_transport import API_HOST, HttpTransport, build_auth_header
from nifty_lab.brokers.upstox_market_data import read_access_token

from .candles import CandleBar
from .constants import INSTRUMENT_KEY


def fetch_intraday_bootstrap(transport: HttpTransport) -> list[CandleBar]:
    token = read_access_token()
    enc = encode_instrument_key(INSTRUMENT_KEY)
    path = f"/v3/historical-candle/intraday/{enc}/{INTERVAL_5M.unit}/{INTERVAL_5M.interval}"
    url = f"https://{API_HOST}{path}"
    status, body, _ = transport.get(url, headers=build_auth_header(token), allow_redirects=False)
    if status != 200:
        raise RuntimeError(f"Bootstrap candle request failed ({status}).")
    spec = CandleIntervalSpec(INTERVAL_5M.unit, INTERVAL_5M.interval, INTERVAL_5M.label)
    try:
        candles = parse_candle_response(body)
    except UpstoxEmptyError:
        return []  # closed market / pre-open: no intraday candles yet is a valid, empty bootstrap
    frame = candles_to_frame(candles, spec=spec)
    bars: list[CandleBar] = []
    for ts, row in frame.iterrows():
        dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else datetime.fromisoformat(str(ts))
        epoch = int(dt.astimezone(timezone.utc).timestamp())
        o, h, lo, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        bars.append(CandleBar(epoch, o, h, lo, c, complete=True, source="bootstrap"))
    return bars