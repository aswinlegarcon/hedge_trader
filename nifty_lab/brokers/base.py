"""Broker abstraction — READ-ONLY by design in Version 1.

There is intentionally no ``place_order`` method on this interface. Adding
live execution requires a separate design review (see README).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class ConnectionState(str, Enum):
    NOT_CONFIGURED = "NOT CONFIGURED"
    CONFIGURED_NOT_CONNECTED = "CONFIGURED (not connected)"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class BrokerStatus:
    name: str
    state: ConnectionState
    detail: str
    docs_url: str
    pricing_note: str
    verified_on: str


class ReadOnlyBroker(ABC):
    name: str = "abstract"

    @abstractmethod
    def status(self) -> BrokerStatus: ...

    @abstractmethod
    def historical(self, symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
        """Return OHLCV frame. Must raise NotImplementedError/ConnectionError when unavailable."""

    @abstractmethod
    def option_chain(self, underlying: str, expiry: str) -> pd.DataFrame:
        """Return option chain with executable bid/ask per strike, or raise."""
