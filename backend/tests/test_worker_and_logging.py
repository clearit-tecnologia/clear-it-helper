from __future__ import annotations

import json
import logging

from clear_helper.logging_config import JsonFormatter
from clear_helper.worker import WorkerSettings, ping


async def test_ping_task() -> None:
    assert await ping({"job_id": "abc"}) == "pong"
    assert await ping({}, "hello") == "hello"


def test_worker_settings_register_ping() -> None:
    assert ping in WorkerSettings.functions


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.LogRecord("clear_helper.test", logging.INFO, __file__, 1, "evt", None, None)
    record.user_id = "123"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "evt"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "clear_helper.test"
    assert payload["user_id"] == "123"
    assert "ts" in payload
