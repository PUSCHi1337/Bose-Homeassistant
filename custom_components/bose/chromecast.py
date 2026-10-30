"""Close the integration-owned Cast transport without a spurious cancel error."""
from __future__ import annotations

import logging
from threading import Event
from typing import Any

import pychromecast

_STOPPED_CONNECT = "Failed to connect: %s. aborting due to stop signal."


class _ShutdownLogger(logging.LoggerAdapter):
    """Keep an explicitly cancelled connect diagnostic local to this socket."""

    def __init__(self, logger: logging.Logger | logging.LoggerAdapter, stop: Event) -> None:
        super().__init__(logger, {})
        self._stop = stop

    def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:
        # PyChromecast can finish a blocking TCP connect after disconnect() set
        # its stop event. It currently logs that requested cancellation as ERROR.
        # Preserve it at DEBUG, retaining the original adapter's device prefix.
        # No other message, client, logger level or filter is changed.
        if (
            level == logging.ERROR
            and msg == _STOPPED_CONNECT
            and self._stop.is_set()
        ):
            level = logging.DEBUG
        kwargs["stacklevel"] = kwargs.get("stacklevel", 1) + 1
        self.logger.log(level, msg, *args, **kwargs)


def disconnect_chromecast(cast: pychromecast.Chromecast, *, timeout: float) -> None:
    """Signal and await the owned Cast worker; leave other failures visible."""
    client = getattr(cast, "socket_client", None)
    logger = getattr(client, "logger", None)
    stop = getattr(client, "stop", None)
    if (
        isinstance(logger, (logging.Logger, logging.LoggerAdapter))
        and not isinstance(logger, _ShutdownLogger)
        and isinstance(stop, Event)
    ):
        client.logger = _ShutdownLogger(logger, stop)
    cast.disconnect(timeout=timeout)
