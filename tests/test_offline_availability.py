"""Disconnected speakers must not trigger repeated polling errors."""
import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import bose
from bose import number
from bose.const import DOMAIN
from bose.coordinator import BoseCoordinator
from bose.entity import BoseBaseEntity
from bose.media_player import BoseMediaPlayer
from bose.number import BoseAudioSlider
from bose.select import BoseAudioSelect
from bose.sensor import (
    BoseBatteryLevelSensor, BoseNetworkIpSensor, BoseWifiSignalSensor,
)
from bose.switch import BoseStandbySettingSwitch, BoseSubwooferSwitch
from homeassistant.core import HomeAssistant
from homeassistant.helpers.frame import async_setup as setup_frame

from .conftest import FakeHass, FakeSpeaker

KINDS = ("slider", "network", "wifi", "battery", "select", "accessory", "standby", "media")
NETWORK = {"primaryIpAddress": "example.invalid", "interfaces": []}
BATTERY = {"percent": 50}
WIFI = {"signalDbm": -45}


def make_entity(kind):
    speaker = FakeSpeaker()
    getters = (
        "get_now_playing", "get_audio_volume", "get_audio_setting",
        "get_network_status", "get_wifi_status", "get_battery_status",
        "get_accessories", "get_system_timeout", "get_audio_mode",
    )
    coordinator = SimpleNamespace(
        **{name: AsyncMock(side_effect=AssertionError("Unexpected offline I/O"))
           for name in getters}
    )
    for name in getters:
        setattr(speaker, name, AsyncMock(
            side_effect=AssertionError("Unexpected offline I/O")
        ))
    speaker._request = AsyncMock(
        side_effect=AssertionError("Unexpected offline raw request")
    )
    entry = SimpleNamespace(
        entry_id="entry", data={"ip": "example.invalid", "guid": "device-1"},
        options={}, async_on_unload=lambda callback: None,
        add_update_listener=lambda callback: lambda: None,
    )
    hass = FakeHass()
    hass.data = {DOMAIN: {}}
    info = {"name": "Speaker", "guid": "device-1", "productName": "Soundbar"}
    if kind == "slider":
        entity = BoseAudioSlider(speaker, entry, "bass", {"value": 10}, coordinator)
    elif kind == "network":
        entity = BoseNetworkIpSensor(speaker, entry, hass, coordinator)
    elif kind == "wifi":
        entity = BoseWifiSignalSensor(speaker, entry, hass, coordinator)
    elif kind == "battery":
        entity = BoseBatteryLevelSensor(speaker, entry, hass, coordinator)
    elif kind == "select":
        entity = BoseAudioSelect(speaker, info, entry, hass)
    elif kind == "accessory":
        entity = BoseSubwooferSwitch(speaker, info, {"enabled": {"subs": True}}, entry)
    elif kind == "standby":
        entity = BoseStandbySettingSwitch(speaker, info, entry, hass)
    else:
        entity = BoseMediaPlayer(speaker, info, hass, coordinator, entry)
    entity._attr_available = True
    entity.async_write_ha_state = lambda: None
    return entity, speaker, coordinator, getters


@pytest.mark.parametrize("kind", KINDS)
async def test_known_offline_entities_do_not_poll_or_warn(kind, caplog):
    entity, speaker, coordinator, getters = make_entity(kind)
    speaker.connected = False
    with caplog.at_level(logging.WARNING, logger="bose"):
        for _ in range(3):
            await entity.async_update()
    assert not entity.available
    for name in getters:
        getattr(speaker, name).assert_not_awaited()
        getattr(coordinator, name).assert_not_awaited()
    speaker._request.assert_not_awaited()
    assert not [r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]


@pytest.mark.parametrize("kind,getter", [
    ("slider", "get_audio_setting"), ("network", "get_network_status"),
    ("wifi", "get_wifi_status"), ("battery", "get_battery_status"),
    ("media", "get_now_playing"),
])
async def test_disconnect_during_a_read_is_quiet_and_has_no_fallback(
    kind, getter, monkeypatch, caplog
):
    entity, speaker, coordinator, _ = make_entity(kind)

    async def drops_connection(*args):
        speaker.connected = False
        raise ConnectionError("transport closed during request")

    getattr(coordinator, getter).side_effect = drops_connection
    fallback = AsyncMock(side_effect=AssertionError("No retry while disconnected"))
    monkeypatch.setattr(number, "read_setting", fallback)
    with caplog.at_level(logging.WARNING, logger="bose"):
        await entity.async_update()
    assert not entity.available
    fallback.assert_not_awaited()
    speaker._request.assert_not_awaited()
    assert not [r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]


@pytest.mark.parametrize("kind,getter,response", [
    ("network", "get_network_status", NETWORK),
    ("wifi", "get_wifi_status", WIFI),
    ("battery", "get_battery_status", BATTERY),
])
async def test_connected_sensor_errors_are_visible_once_and_rearm_after_success(
    kind, getter, response, caplog
):
    entity, speaker, coordinator, _ = make_entity(kind)
    read = getattr(coordinator, getter)
    read.side_effect = RuntimeError("genuine online error")
    with caplog.at_level(logging.WARNING, logger="bose"):
        await entity.async_update()
        await entity.async_update()
        assert not entity.available
        assert len([r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]) == 1
        read.side_effect = None
        read.return_value = response
        await entity.async_update()
        assert entity.available
        read.side_effect = RuntimeError("another online error")
        await entity.async_update()
    assert len([r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]) == 2
    resource = {"network": "/network/status", "wifi": "/network/wifi/status", "battery": "/system/battery"}[kind]
    entity._parse_message({"header": {"resource": resource}, "body": response})
    assert entity.available, "A successful push must also restore availability"


async def test_connected_slider_failures_remain_visible_without_repeated_warnings(
    monkeypatch, caplog
):
    entity, _, coordinator, _ = make_entity("slider")
    coordinator.get_audio_setting.side_effect = ValueError("getter refused setting")
    fallback = AsyncMock(return_value=None)
    monkeypatch.setattr(number, "read_setting", fallback)
    with caplog.at_level(logging.WARNING, logger="bose"):
        await entity.async_update()
        await entity.async_update()
        assert not entity.available
        assert len([r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]) == 1
        fallback.return_value = {"value": 42}
        await entity.async_update()
        assert entity.available and entity.native_value == 42
        fallback.return_value = None
        await entity.async_update()
    assert len([r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]) == 2


async def test_connected_slider_retains_the_raw_getter_fallback(monkeypatch):
    entity, _, coordinator, _ = make_entity("slider")
    coordinator.get_audio_setting.side_effect = ValueError("unknown library setting")
    fallback = AsyncMock(return_value={"value": 30})
    monkeypatch.setattr(number, "read_setting", fallback)
    await entity.async_update()
    assert entity.available and entity.native_value == 30
    fallback.assert_awaited_once()


async def test_coordinator_invalidates_old_cache_on_both_connection_edges(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    setup_frame(hass)
    speaker = FakeSpeaker()
    coordinator = BoseCoordinator(hass, speaker, "device-1")
    try:
        coordinator._cache_message({"header": {"resource": "/audio/volume"}, "body": {"value": 9}})
        speaker.connected = False
        await coordinator.async_refresh()
        assert not coordinator.data.cached_messages
        assert not coordinator.data.connected
        coordinator._cache_message({"header": {"resource": "/audio/volume"}, "body": {"value": 99}})
        speaker.connected = True
        await coordinator.async_refresh()
        assert not coordinator.data.cached_messages
        assert coordinator.data.connected
        assert coordinator.update_interval == timedelta(seconds=30)
    finally:
        await coordinator.async_shutdown()


async def test_entity_connection_listener_updates_and_is_removed_on_unload(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    setup_frame(hass)
    speaker = FakeSpeaker()
    coordinator = BoseCoordinator(hass, speaker, "device-1")
    hass.data[DOMAIN] = {"entry": {"coordinator": coordinator}}
    entity = BoseBaseEntity(speaker)
    entity.hass = hass
    entity.platform = SimpleNamespace(config_entry=SimpleNamespace(entry_id="entry"))
    entity.entity_id = "sensor.test"
    removers, writes, refreshes = [], [], []
    entity.async_on_remove = removers.append
    entity.async_write_ha_state = lambda: writes.append(entity.available)
    entity.async_schedule_update_ha_state = lambda force_refresh=False: refreshes.append(force_refresh)
    try:
        await entity.async_added_to_hass()
        speaker.connected = False
        await coordinator.async_refresh()
        assert not entity.available
        assert writes == [False]
        await coordinator.async_refresh()
        assert writes == [False], "Unchanged disconnection must not keep writing states"
        speaker.connected = True
        await coordinator.async_refresh()
        assert refreshes == [True], "Reconnect must request a fresh read"
        assert len(removers) == 1
        removers[0]()
        speaker.connected = False
        await coordinator.async_refresh()
        assert writes == [False]
        assert refreshes == [True]
    finally:
        await coordinator.async_shutdown()


class StopMonitor(BaseException):
    pass


@pytest.mark.parametrize("discovery_fails", [False, True])
async def test_missing_offline_device_is_quiet_but_discovery_errors_are_visible(
    monkeypatch, caplog, discovery_fails
):
    speaker = FakeSpeaker()
    speaker.connected = False
    entry = SimpleNamespace(entry_id="entry", data={"guid": "device-1"})
    hass = FakeHass()
    hass.data = {DOMAIN: {"entry": {"speaker": speaker}}}
    elapsed = [0]

    async def sleep(delay):
        elapsed[0] += delay
        if elapsed[0] > 120:
            raise StopMonitor

    async def discover(hass):
        if discovery_fails:
            raise RuntimeError("mDNS service failed")
        return []

    monkeypatch.setattr(bose.asyncio, "sleep", sleep)
    monkeypatch.setattr(bose, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(bose.config_flow, "Discover_Bose_Devices", discover)
    with caplog.at_level(logging.WARNING, logger="bose"):
        with pytest.raises(StopMonitor):
            await bose.reconnection_monitor(hass, entry, None)
    warnings = [r for r in caplog.records if r.name == "bose" and r.levelno >= logging.WARNING]
    assert bool(warnings) is discovery_fails


async def test_connected_media_failure_stays_visible_and_marks_data_unavailable():
    entity, _, coordinator, _ = make_entity("media")
    coordinator.get_now_playing.side_effect = RuntimeError("genuine online error")
    with pytest.raises(RuntimeError, match="genuine online error"):
        await entity.async_update()
    assert not entity.available
