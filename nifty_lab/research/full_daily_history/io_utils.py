"""Atomic artifact I/O and dataset locking."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from nifty_lab.config import FAKE_SECRET_SENTINEL


class DatasetLockError(Exception):
    """Another writer holds the dataset lock."""


@contextmanager
def dataset_lock(dataset_dir: Path, *, timeout_hint: str = "exclusive"):
    dataset_dir.mkdir(parents=True, exist_ok=True)
    lock_path = dataset_dir / ".writer.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise DatasetLockError(f"Dataset lock present ({timeout_hint}).") from exc
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_bytes(path: Path, data: bytes) -> None:
    _assert_no_sentinel_bytes(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    _assert_no_sentinel_text(text)
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    atomic_write_text(path, text)


def _assert_no_sentinel_text(text: str) -> None:
    if FAKE_SECRET_SENTINEL in text:
        raise ValueError("Secret sentinel would leak into history artifact.")


def _assert_no_sentinel_bytes(data: bytes) -> None:
    if FAKE_SECRET_SENTINEL.encode() in data:
        raise ValueError("Secret sentinel would leak into history artifact.")
