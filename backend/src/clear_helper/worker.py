"""Background worker (arq): ``python -m clear_helper.worker``.

Phase 0 only ships a ``ping`` task; real ingestion arrives in Phase 1.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from arq import run_worker
from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine

from clear_helper.config import get_settings
from clear_helper.logging_config import configure_logging

logger = logging.getLogger(__name__)


async def ping(ctx: dict[str, Any], message: str = "pong") -> str:
    """Example task used to validate the queue end to end."""
    logger.info("worker.ping", extra={"job_id": ctx.get("job_id")})
    return message


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)
    logger.info("worker.started")


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("worker.stopped")


class WorkerSettings:
    functions: ClassVar[list[WorkerCoroutine]] = [ping]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    handle_signals = True


def main() -> None:
    configure_logging(get_settings().log_level)
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
