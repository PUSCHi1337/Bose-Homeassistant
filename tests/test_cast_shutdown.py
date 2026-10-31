"""Exercise the Cast shutdown race through the real installed socket client."""
import logging
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pychromecast.error import ChromecastConnectionError
from pychromecast.models import HostServiceInfo
from pychromecast.socket_client import SocketClient

from .test_offline_availability import make_entity

STOP_MESSAGE = "Failed to connect: %s. aborting due to stop signal."


async def test_stopping_inflight_cast_connection_is_diagnostic_not_error(monkeypatch, caplog):
    """A pending TCP connect may time out after our disconnect has stopped it."""
    entity, _, _, _ = make_entity("media")
    entered, release, stop = threading.Event(), threading.Event(), threading.Event()
    logger = logging.getLogger("pychromecast.socket_client")
    client = SimpleNamespace(
        socket=None, _request_callbacks={}, tries=1, connecting=True,
        services={HostServiceInfo("192.0.2.10", 8009)}, retry_wait=0.01,
        stop=stop, host="speaker.invalid", port=8009, zconf=None, timeout=0.1,
        fn="", selector=Mock(),
        logger=logger, _report_connection_status=Mock(),
    )
    failures = []

    def pending_connection(*args, **kwargs):
        entered.set()
        if not release.wait(2):
            raise AssertionError("shutdown did not release the simulated connect")
        raise TimeoutError("simulated TCP timeout")

    monkeypatch.setattr("pychromecast.socket_client.socket.create_connection", pending_connection)
    monkeypatch.setattr(
        "pychromecast.socket_client.new_socket",
        lambda: SimpleNamespace(connect=pending_connection, settimeout=Mock()),
        raising=False,
    )

    def connect():
        try:
            SocketClient.initialize_connection(client)
        except BaseException as err:
            failures.append(err)

    worker = threading.Thread(target=connect)
    def disconnect(*, timeout):
        stop.set()
        release.set()
        worker.join(timeout)
        assert not worker.is_alive()

    entity._chromecast_device = SimpleNamespace(socket_client=client, disconnect=disconnect)
    entity._media_controller = object()
    async def executor(function, *args):
        return function(*args)
    entity.hass.async_add_executor_job = executor

    with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
        worker.start()
        try:
            assert entered.wait(2)
            await entity._async_disconnect_chromecast()
        finally:
            release.set()
            worker.join(2)
    assert not worker.is_alive()
    assert len(failures) == 1 and isinstance(failures[0], ChromecastConnectionError)
    records = [r for r in caplog.records if r.getMessage().endswith(
        "Failed to connect: simulated TCP timeout. aborting due to stop signal."
    )]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert entity._chromecast_device is None
    assert entity._media_controller is None
    assert client.logger is not logger
    assert not logger.filters


@pytest.mark.parametrize("stopped,message,level,expected", [
    (True, STOP_MESSAGE, logging.ERROR, logging.DEBUG),
    (False, STOP_MESSAGE, logging.ERROR, logging.ERROR),
    (True, "Authentication failed: %s", logging.ERROR, logging.ERROR),
    (True, "Unexpected worker failure: %s", logging.ERROR, logging.ERROR),
    (True, STOP_MESSAGE, logging.WARNING, logging.WARNING),
])
async def test_only_expected_stop_message_on_owned_client_is_reclassified(
    caplog, stopped, message, level, expected
):
    entity, _, _, _ = make_entity("media")
    stop = threading.Event()
    logger = logging.getLogger("pychromecast.socket_client")
    original_level = logger.level
    client = SimpleNamespace(stop=stop, logger=logging.LoggerAdapter(logger, {"cast_test": "owned"}))
    other = SimpleNamespace(logger=logging.LoggerAdapter(logger, {"cast_test": "other"}))
    original_other_logger = other.logger

    def disconnect(*, timeout):
        if stopped:
            stop.set()
        client.logger.log(level, message, "simulated")
        other.logger.error(STOP_MESSAGE, "other client")
    entity._chromecast_device = SimpleNamespace(socket_client=client, disconnect=disconnect)
    entity._media_controller = object()
    async def executor(function, *args):
        return function(*args)
    entity.hass.async_add_executor_job = executor

    with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
        await entity._async_disconnect_chromecast()
    records = [r for r in caplog.records if r.name == "pychromecast.socket_client"]
    assert [(r.levelno, r.cast_test) for r in records] == [(expected, "owned"), (logging.ERROR, "other")]
    assert other.logger is original_other_logger
    assert logger.level == original_level
    assert not logger.filters
