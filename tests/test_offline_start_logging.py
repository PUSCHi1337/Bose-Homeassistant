"""A powered-off speaker is normal during config-entry setup."""
import errno
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import bose
from pybose.BoseSpeaker import BoseRequestException

from .conftest import FakeHass, FakeSpeaker


@pytest.mark.parametrize("failure,should_warn", [
    (OSError(errno.EHOSTUNREACH, "speaker is offline"), False),
    (ConnectionRefusedError(errno.ECONNREFUSED, "speaker is offline"), False),
    (OSError(errno.ENETUNREACH, "network is temporarily unreachable"), False),
    (TimeoutError("speaker did not answer"), False),
    (PermissionError(errno.EACCES, "access denied"), True),
    (ValueError("unexpected handshake data"), True),
    (BoseRequestException("GET", "/system/info", {}, 401, 0, "authentication rejected"), True),
])
async def test_offline_setup_is_quiet_but_unexpected_errors_are_visible(
    monkeypatch, caplog, failure, should_warn
):
    speaker = FakeSpeaker()
    speaker.connect = AsyncMock(side_effect=failure)
    speaker.disconnect = AsyncMock()
    monkeypatch.setattr(bose, "BoseSpeaker", lambda **kwargs: speaker)
    entry = SimpleNamespace(data={"ip": "speaker.invalid", "guid": "test-device"})

    with caplog.at_level(logging.WARNING, logger="bose"):
        for _ in range(3):
            assert await bose.connect_to_bose(FakeHass(), entry, None) is None

    assert speaker.connect.await_count == 3
    assert speaker.disconnect.await_count == 3
    warnings = [r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]
    assert len(warnings) == (3 if should_warn else 0)
