"""Check owned Cast shutdown with the actual dependency's logger and format."""
import logging
import threading
from types import SimpleNamespace

import pytest
from pychromecast.error import ChromecastConnectionError
from pychromecast.models import HostServiceInfo
from pychromecast.socket_client import SocketClient

from bose.chromecast import disconnect_chromecast

STOP_MESSAGE = "Failed to connect: %s. aborting due to stop signal."
LEGACY_STOP_MESSAGE = "[%s(%s):%s] " + STOP_MESSAGE
STOP_SUFFIX = "Failed to connect: simulated TCP timeout. aborting due to stop signal."


@pytest.mark.parametrize("friendly_name", [None, "Test 100% speaker"])
def test_real_socket_client_stopped_during_connect_is_diagnostic(
    monkeypatch, caplog, friendly_name
):
    """Keep the real SocketClient logger; fake only the unreachable TCP endpoint."""
    entered, release = threading.Event(), threading.Event()
    client = SocketClient(
        cast_type="audio", tries=1, timeout=0.1, retry_wait=0.01,
        services={HostServiceInfo("192.0.2.10", 8009)}, zconf=None,
    )
    client.fn = friendly_name
    original_logger = client.logger
    failures = []

    def pending_connection(*args, **kwargs):
        entered.set()
        if not release.wait(2):
            raise AssertionError("shutdown did not release the simulated connect")
        raise TimeoutError("simulated TCP timeout")

    monkeypatch.setattr(
        "pychromecast.socket_client.socket.create_connection", pending_connection
    )
    # 14.0.x calls new_socket().connect(); 14.1 calls create_connection().
    # Give the legacy fake a local socketpair FD for the real selector only.
    legacy_socket = SimpleNamespace(
        connect=pending_connection, settimeout=lambda timeout: None,
        fileno=client.socketpair[1].fileno, close=lambda: None,
    )
    monkeypatch.setattr(
        "pychromecast.socket_client.new_socket", lambda: legacy_socket, raising=False
    )

    def connect():
        try:
            client.initialize_connection()
        except BaseException as err:
            failures.append(err)

    worker = threading.Thread(target=connect)

    def disconnect(*, timeout):
        client.disconnect()
        release.set()
        worker.join(timeout)
        assert not worker.is_alive()

    cast = SimpleNamespace(socket_client=client, disconnect=disconnect)
    logger = logging.getLogger("pychromecast.socket_client")
    original_level, original_filters = logger.level, tuple(logger.filters)

    try:
        with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
            worker.start()
            assert entered.wait(2), repr(failures)
            disconnect_chromecast(cast, timeout=2)
        assert not worker.is_alive()
        assert len(failures) == 1
        assert isinstance(failures[0], ChromecastConnectionError)
        records = [r for r in caplog.records if r.getMessage().endswith(STOP_SUFFIX)]
        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG
        assert f"[{friendly_name or ''}(192.0.2.10):8009]" in records[0].getMessage()
        assert client.logger is not original_logger
        assert logger.level == original_level
        assert tuple(logger.filters) == original_filters
    finally:
        client.stop.set()
        release.set()
        if worker.ident is not None:
            worker.join(2)
        for local_socket in client.socketpair:
            local_socket.close()
        client.selector.close()
    assert not worker.is_alive()


@pytest.mark.parametrize("message,args", [
    (STOP_MESSAGE, ("simulated",)),
    (LEGACY_STOP_MESSAGE, ("Test speaker", "192.0.2.10", 8009, "simulated")),
])
@pytest.mark.parametrize("stopped,level,expected", [
    (True, logging.ERROR, logging.DEBUG),
    (False, logging.ERROR, logging.ERROR),
    (True, logging.WARNING, logging.WARNING),
])
def test_shutdown_formats_are_scoped_to_the_stopped_owned_client(
    caplog, message, args, stopped, level, expected
):
    logger = logging.getLogger("pychromecast.socket_client")
    stop = threading.Event()
    client = SimpleNamespace(
        stop=stop,
        logger=logging.LoggerAdapter(logger, {"cast_test": "owned"}),
    )
    other_logger = logging.LoggerAdapter(logger, {"cast_test": "other"})
    original_level, original_filters = logger.level, tuple(logger.filters)

    def disconnect(*, timeout):
        if stopped:
            stop.set()
        client.logger.log(level, message, *args)
        other_logger.log(level, message, *args)

    cast = SimpleNamespace(socket_client=client, disconnect=disconnect)
    with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
        disconnect_chromecast(cast, timeout=2)
    records = [r for r in caplog.records if hasattr(r, "cast_test")]
    assert [(r.levelno, r.cast_test) for r in records] == [
        (expected, "owned"), (level, "other")
    ]
    assert logger.level == original_level
    assert tuple(logger.filters) == original_filters


@pytest.mark.parametrize("message,args", [
    ("Authentication failed: %s", ("simulated",)),
    ("Unexpected worker failure: %s", ("simulated",)),
    ("Failed to connect. No retries.", ()),
    (STOP_MESSAGE + " unexpected suffix", ("simulated",)),
    (LEGACY_STOP_MESSAGE + " unexpected suffix",
     ("Test speaker", "192.0.2.10", 8009, "simulated")),
])
def test_stopped_owned_client_keeps_other_errors_visible(caplog, message, args):
    stop = threading.Event()
    logger = logging.getLogger("pychromecast.socket_client")
    client = SimpleNamespace(stop=stop, logger=logger)

    def disconnect(*, timeout):
        stop.set()
        client.logger.error(message, *args)

    cast = SimpleNamespace(socket_client=client, disconnect=disconnect)
    with caplog.at_level(logging.DEBUG, logger="pychromecast.socket_client"):
        disconnect_chromecast(cast, timeout=2)
    records = [r for r in caplog.records if r.name == logger.name]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
