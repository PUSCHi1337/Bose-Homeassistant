"""Regressions from passive overnight power-cycle logs; no live devices."""
import asyncio
import json
import logging
from types import SimpleNamespace
from ipaddress import ip_address
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.frame import async_setup as setup_frame
from pybose.BoseAuth import BoseAuth
from pybose.BoseSpeaker import BoseSpeaker

from bose.config_flow import BoseConfigFlow
from bose.const import DOMAIN, REQUEST_TIMEOUT
from bose.coordinator import BoseCoordinator
from bose.entity import BoseBaseEntity
from bose.sensor import BoseNetworkIpSensor
from .conftest import FakeHass
from .test_offline_availability import make_entity


async def test_transport_edges_publish_immediately_without_waiting_for_poll(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    setup_frame(hass)
    speaker = BoseSpeaker("speaker.invalid")
    speaker._set_connected(True)
    coordinator = BoseCoordinator(hass, speaker, "test-device")
    hass.data[DOMAIN] = {"entry": {"coordinator": coordinator}}
    entity = BoseBaseEntity(speaker)
    entity.hass = hass
    entity.platform = SimpleNamespace(config_entry=SimpleNamespace(entry_id="entry"))
    entity.entity_id = "sensor.test"
    writes, refreshes, removers = [], [], []
    entity.async_on_remove = removers.append
    entity.async_write_ha_state = lambda: writes.append(entity.available)
    entity.async_schedule_update_ha_state = lambda force_refresh=False: refreshes.append(force_refresh)
    try:
        await entity.async_added_to_hass()
        coordinator._cache_message({"header": {"resource": "/network/status"}, "body": {}})
        speaker._set_connected(False)
        assert writes == [False]
        assert not coordinator.data.connected
        assert not coordinator.data.cached_messages
        speaker._set_connected(False)
        assert writes == [False]
        speaker._set_connected(True)
        assert refreshes == [True]
    finally:
        for remove in removers:
            remove()
        await coordinator.async_shutdown()


async def test_coordinator_shutdown_detaches_owned_library_listeners(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    setup_frame(hass)
    speaker = BoseSpeaker("speaker.invalid")
    for _ in range(3):
        coordinator = BoseCoordinator(hass, speaker, "test-device")
        try:
            assert len(speaker._connection_listeners) == 1
            assert len(speaker._receivers) == 1
        finally:
            await coordinator.async_shutdown()
        assert not speaker._connection_listeners
        assert not speaker._receivers


@pytest.mark.parametrize("dual_stack", [False, True])
@pytest.mark.parametrize("state,should_reload", [
    (ConfigEntryState.LOADED, False), (ConfigEntryState.SETUP_RETRY, True),
])
async def test_discovery_uses_listener_owned_updates_without_deprecation(
    tmp_path, monkeypatch, caplog, state, should_reload, dual_stack
):
    hass = HomeAssistant(str(tmp_path))
    setup_frame(hass)
    entry = SimpleNamespace(data={"ip": "192.0.2.10", "guid": "test-device"},
                            state=state, update_listeners=[object()],
                            entry_id="entry", source="user")
    def update(target, **changes):
        changed = target.data != changes["data"]
        target.data = changes["data"]
        return changed
    entries = SimpleNamespace(
        async_entry_for_domain_unique_id=Mock(return_value=entry),
        async_update_entry=Mock(side_effect=update),
        async_schedule_reload=Mock(),
    )
    hass.config_entries = entries
    report_usage = Mock()
    monkeypatch.setattr('homeassistant.config_entries.report_usage', report_usage)
    flow = BoseConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {"source": "zeroconf", "unique_id": "test-device"}
    monkeypatch.setattr(flow, "async_set_unique_id", AsyncMock(return_value=entry))
    info = SimpleNamespace(host="2001:db8::20", properties={"GUID": "test-device"},
                           name="Test Speaker._bose-passport._tcp.local.",
                           ip_addresses=[ip_address("2001:db8::20")] +
                           ([ip_address("192.0.2.10")] if dual_stack else []))
    with caplog.at_level(logging.WARNING):
        with pytest.raises(AbortFlow):
            await flow.async_step_zeroconf(info)
    assert entry.data["ip"] == ("192.0.2.10" if dual_stack else "2001:db8::20")
    assert bool(entries.async_schedule_reload.call_count) is should_reload
    report_usage.assert_not_called()


async def test_silent_live_transport_finishes_sensor_poll_before_ha_slow_warning():
    auth = BoseAuth()
    auth.set_access_token("dummy", "dummy", "dummy")
    speaker = BoseSpeaker("speaker.invalid", device_id="test-device", bose_auth=auth,
                          auto_reconnect=False, request_timeout=REQUEST_TIMEOUT)
    speaker.has_capability = lambda resource: True
    socket = SimpleNamespace(send=AsyncMock(), close=AsyncMock())
    speaker._websocket = socket
    speaker._set_connected(True)
    coordinator = SimpleNamespace(get_network_status=speaker.get_network_status)
    entity = BoseNetworkIpSensor(speaker, SimpleNamespace(entry_id="entry", data={"ip": "speaker.invalid", "guid": "test-device"}),
                                FakeHass(), coordinator)
    try:
        await asyncio.wait_for(entity.async_update(), 9.25)
        assert not speaker.is_connected()
        assert not entity.available
        assert all(json.loads(c.args[0])["header"]["method"] == "GET"
                   for c in socket.send.await_args_list)
    finally:
        await speaker.disconnect()


async def test_cast_transport_is_closed_on_offline_and_restored_passively():
    entity, speaker, _, _ = make_entity("media")
    stopped = []
    cast = SimpleNamespace(disconnect=lambda **kwargs: stopped.append(True))
    entity._chromecast_device = cast
    entity._media_controller = object()
    async def executor(function, *args):
        return function(*args)
    entity.hass.async_add_executor_job = executor
    speaker.connected = False
    await entity._async_sync_chromecast()
    assert stopped == [True]
    assert entity._chromecast_device is None
    assert entity._media_controller is None
    speaker.connected = True
    entity._async_setup_chromecast = AsyncMock()
    await entity._async_sync_chromecast()
    entity._async_setup_chromecast.assert_awaited_once_with(allow_enable=False)
    speaker._request.assert_not_awaited()


async def test_media_poll_does_not_start_another_read_after_format_transport_loss():
    entity, speaker, coordinator, _ = make_entity("media")
    coordinator.get_now_playing.side_effect = None
    coordinator.get_now_playing.return_value = {}
    coordinator.get_audio_volume.side_effect = None
    coordinator.get_audio_volume.return_value = {}
    entity._parse_now_playing = lambda data: None
    entity._parse_audio_volume = lambda data: None
    async def drops():
        speaker.connected = False
    entity._refresh_audio_format = drops
    coordinator.get_bluetooth_sink_status = AsyncMock(side_effect=AssertionError("offline Bluetooth I/O"))
    coordinator.get_sources = AsyncMock(side_effect=AssertionError("offline followup I/O"))
    await entity.async_update()
    coordinator.get_bluetooth_sink_status.assert_not_awaited()
    coordinator.get_sources.assert_not_awaited()


@pytest.mark.parametrize("failure,should_warn", [
    (ConnectionRefusedError(111, "speaker is offline"), False),
    (RuntimeError("unexpected discovery failure"), True),
])
async def test_monitor_quiets_expected_absence_and_keeps_real_failures_visible(
    monkeypatch, caplog, failure, should_warn
):
    import bose
    from .conftest import FakeSpeaker
    from .test_offline_availability import StopMonitor
    speaker = FakeSpeaker()
    speaker.connected = False
    speaker.reconnect = AsyncMock(side_effect=failure)
    entry = SimpleNamespace(entry_id="entry", data={"guid": "test-device"})
    hass = FakeHass()
    hass.data = {DOMAIN: {"entry": {"speaker": speaker}}}
    elapsed = [0]
    async def sleep(delay):
        elapsed[0] += delay
        if elapsed[0] > 120:
            raise StopMonitor
    monkeypatch.setattr(bose.asyncio, "sleep", sleep)
    monkeypatch.setattr(bose, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(
        bose.config_flow, "Discover_Bose_Devices",
        AsyncMock(return_value=[{"guid": "test-device", "ip": "speaker.invalid"}]),
    )
    with caplog.at_level(logging.WARNING, logger="bose"):
        with pytest.raises(StopMonitor):
            await bose.reconnection_monitor(hass, entry, None)
    assert bool([r for r in caplog.records if r.name == "bose"
                 and r.levelno >= logging.WARNING]) is should_warn


async def test_background_cast_discovery_never_enables_speaker_features(monkeypatch, caplog):
    import importlib
    media_module = importlib.import_module("bose.media_player")
    entity, speaker, _, _ = make_entity("media")
    speaker.set_chromecast = AsyncMock()
    browser = SimpleNamespace(devices={}, start_discovery=Mock())
    async def executor(function, *args):
        return function(*args)
    entity.hass.async_add_executor_job = executor
    monkeypatch.setattr(media_module.zeroconf, "async_get_instance",
                        AsyncMock(return_value=object()))
    monkeypatch.setattr(media_module, "CastBrowser", lambda *args: browser)
    monkeypatch.setattr(media_module.discovery, "stop_discovery", Mock())
    monkeypatch.setattr(media_module.asyncio, "sleep", AsyncMock())
    with caplog.at_level(logging.WARNING, logger="bose"):
        await entity._async_sync_chromecast()
    speaker.set_chromecast.assert_not_awaited()
    assert not [r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]
