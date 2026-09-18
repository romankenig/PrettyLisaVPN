"""Executable entry point for the PrettyLisaVPN UDP obfuscator."""

import asyncio
import logging
import signal

from .config import Settings
from .logging import configure_logging, log_event
from .server import serve


async def _run() -> None:
    settings = Settings.from_environment()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await serve(settings, stop)


def main() -> None:
    configure_logging()
    logger = logging.getLogger("prettylisavpn.obfuscator")
    try:
        asyncio.run(_run())
    except (OSError, ValueError):
        log_event(logger, logging.CRITICAL, "obfuscator_start_failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
