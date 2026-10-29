"""Offline config-entry lifecycle regressions (fork changes, 2026-10-29)."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import bose
from bose.entity import BoseBaseEntity
from .test_setup import ENTRY_DATA


class StopMonitor(BaseException):
    pass


class Entry:
    entry_id = "entry"
    title = "Speaker"
    unique_id = "guid-1"

    def __init__(self):
        self.data = dict(ENTRY_DATA)
        self.bound_tasks = []

    def async_create_background_task(self, hass, target, name, eager_start=True):
        task = hass.async_create_background_task(target, name)
        self.bound_tasks.append(task)
        return task


class Entries:
    def __init__(self, entry):
        self.entry = entry
        self.unload_ok = True
        self.forward_error = None
        self.events = []

    def async_entry_for_domain_unique_id(self, *args):
        return self.entry

    def async_get_entry(self, entry_id):
        return self.entry

    def async_update_entry(self, entry, **changes):
        for key, value in changes.items():
            setattr(entry, key, value)
        return True

    async def async_forward_entry_setups(self, entry, platforms):
        if self.forward_error:
            raise self.forward_error

    async def async_unload_platforms(self, entry, platforms):
        self.events.append("platforms")
        return self.unload_ok

    async def async_forward_entry_unload(self, entry, platform):
        return self.unload_ok


class Hass:
    def __init__(self, entry):
        self.data = {}
        self.config_entries = Entries(entry)
        self.tasks = []

    def async_create_background_task(self, target, name, *args, **kwargs):
        task = asyncio.create_task(target, name=name)
        self.tasks.append(task)
        return task

    def async_create_task(self, target, *args, **kwargs):
        return self.async_create_background_task(target, "foreground")


class Speaker:
    def __init__(self):
        self.connected = True
        self.disconnections = 0
        self.receivers = []
        self.host = ENTRY_DATA["ip"]
        self.reconnects = []
        self.reconnect_gate = None

    def get_device_id(self):
        return "guid-1"

    def attach_receiver(self, callback):
        self.receivers.append(callback)
        return len(self.receivers)

    def has_capability(self, resource):
        return False

    def is_connected(self):
        return self.connected

    async def get_system_info(self):
        return dict(name="Speaker", productName="Soundbar", serialNumber="S1",
                    softwareVersion="1")

    async def get_capabilities(self):
        return {}

    async def get_accessories(self):
        return {}

    async def subscribe(self):
        pass

    async def disconnect(self):
        self.disconnections += 1
        self.connected = False

    async def reconnect(self, host=None):
        self.reconnects.append(host)
        if self.reconnect_gate is not None:
            await self.reconnect_gate.wait()
        self.host = host or self.host
        self.connected = True


class Coordinator:
    def __init__(self, hass, speaker, device_id):
        self.speaker = speaker

    async def async_config_entry_first_refresh(self):
        pass


@asynccontextmanager
async def setup_rig(monkeypatch):
    entry = Entry()
    hass = Hass(entry)
    speaker = Speaker()
    registry = SimpleNamespace(async_get_or_create=lambda **kwargs:
                               SimpleNamespace(id="speaker"))

    async def connects(*args):
        return speaker

    monkeypatch.setattr(bose, "connect_to_bose", connects)
    monkeypatch.setattr(bose, "BoseCoordinator", Coordinator)
    monkeypatch.setattr(bose.dr, "async_get", lambda hass: registry)
    try:
        yield hass, entry, speaker
    finally:
        for task in hass.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*hass.tasks, return_exceptions=True)


async def test_successful_setup_binds_both_tasks_to_the_entry(monkeypatch):
    async with setup_rig(monkeypatch) as (hass, entry, speaker):
        assert await bose.async_setup_entry(hass, entry)
        assert len(entry.bound_tasks) == 2
        assert len(hass.tasks) == 2


async def test_unload_cancels_and_awaits_entry_tasks_before_removing_data(monkeypatch):
    async with setup_rig(monkeypatch) as (hass, entry, speaker):
        await bose.async_setup_entry(hass, entry)
        await asyncio.sleep(0)
        assert await bose.async_unload_entry(hass, entry)
        assert all(task.done() for task in hass.tasks)
        assert entry.entry_id not in hass.data[bose.DOMAIN]
        assert speaker.disconnections == 1
        assert hass.config_entries.events == ["platforms"]


async def test_failed_platform_unload_keeps_the_loaded_runtime(monkeypatch):
    async with setup_rig(monkeypatch) as (hass, entry, speaker):
        await bose.async_setup_entry(hass, entry)
        hass.config_entries.unload_ok = False
        assert not await bose.async_unload_entry(hass, entry)
        assert speaker.disconnections == 0
        assert entry.entry_id in hass.data[bose.DOMAIN]
        assert all(not task.done() for task in hass.tasks)


async def test_failed_platform_setup_cleans_up_socket_and_runtime(monkeypatch):
    async with setup_rig(monkeypatch) as (hass, entry, speaker):
        hass.config_entries.forward_error = RuntimeError("platform setup failed")
        with pytest.raises(RuntimeError, match="platform setup failed"):
            await bose.async_setup_entry(hass, entry)
        assert speaker.disconnections == 1
        assert all(task.done() for task in hass.tasks)
        assert entry.entry_id not in hass.data[bose.DOMAIN]


async def test_cancelled_platform_setup_closes_the_connected_speaker(monkeypatch):
    async with setup_rig(monkeypatch) as (hass, entry, speaker):
        entered = asyncio.Event()

        async def blocked(*args):
            entered.set()
            await asyncio.Event().wait()

        hass.config_entries.async_forward_entry_setups = blocked
        task = asyncio.create_task(bose.async_setup_entry(hass, entry))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert speaker.disconnections == 1
        assert all(task.done() for task in hass.tasks)
        assert entry.entry_id not in hass.data[bose.DOMAIN]


async def test_repeated_setup_unload_does_not_accumulate_tasks(monkeypatch):
    async with setup_rig(monkeypatch) as (hass, entry, speaker):
        for _ in range(5):
            speaker.connected = True
            await bose.async_setup_entry(hass, entry)
            await asyncio.sleep(0)
            assert await bose.async_unload_entry(hass, entry)
        assert len(hass.tasks) == 10
        assert all(task.done() for task in hass.tasks)
        assert speaker.disconnections == 5


async def test_monitor_keeps_entity_coordinator_and_callbacks_on_one_client(monkeypatch):
    entry = Entry()
    hass = Hass(entry)
    speaker = Speaker()
    speaker.connected = False
    entity = BoseBaseEntity(speaker)
    coordinator = Coordinator(hass, speaker, "guid-1")
    notifications = []
    speaker.attach_receiver(notifications.append)
    hass.data[bose.DOMAIN] = {entry.entry_id: {
        "speaker": speaker, "coordinator": coordinator,
    }}
    replacement = Speaker()
    real_sleep = asyncio.sleep
    checks = 0

    async def sleep(delay):
        nonlocal checks
        if delay == 30:
            checks += 1
            if checks > 1:
                raise StopMonitor
        await real_sleep(0)

    async def discover(hass):
        return [{"guid": "guid-1", "ip": "new-address.invalid"}]

    async def old_replacement(*args):
        return replacement

    monkeypatch.setattr(bose.asyncio, "sleep", sleep)
    monkeypatch.setattr(bose.config_flow, "Discover_Bose_Devices", discover)
    monkeypatch.setattr(bose, "connect_to_bose", old_replacement)
    with pytest.raises(StopMonitor):
        await bose.reconnection_monitor(hass, entry, None)
    assert hass.data[bose.DOMAIN][entry.entry_id]["speaker"] is entity.speaker
    assert coordinator.speaker is entity.speaker
    assert speaker.reconnects == ["new-address.invalid"]
    assert speaker.receivers == [notifications.append]
    assert speaker.disconnections == 0
    assert entry.data["ip"] == "new-address.invalid"


async def test_monitor_bounds_repeated_discovery_when_device_is_offline(monkeypatch):
    entry = Entry()
    hass = Hass(entry)
    speaker = Speaker()
    speaker.connected = False
    hass.data[bose.DOMAIN] = {entry.entry_id: {"speaker": speaker}}
    clock = [0.0]
    scans = []
    real_sleep = asyncio.sleep

    async def sleep(delay):
        clock[0] += delay
        if clock[0] > 1100:
            raise StopMonitor
        await real_sleep(0)

    async def discover(hass):
        scans.append(clock[0])
        return []

    monkeypatch.setattr(bose, "monotonic", lambda: clock[0], raising=False)
    monkeypatch.setattr(bose.asyncio, "sleep", sleep)
    monkeypatch.setattr(bose.config_flow, "Discover_Bose_Devices", discover)
    with pytest.raises(StopMonitor):
        await bose.reconnection_monitor(hass, entry, None)
    assert len(scans) < 10
    gaps = [b - a for a, b in zip(scans, scans[1:])]
    assert gaps[:4] == [30, 60, 120, 240]
    assert all(gap <= 300 for gap in gaps)


async def test_failed_initial_connect_closes_the_partial_client(monkeypatch):
    entry = Entry()
    speaker = Speaker()

    async def failed_connect():
        raise OSError("offline")

    speaker.connect = failed_connect
    monkeypatch.setattr(bose, "BoseSpeaker", lambda **kwargs: speaker)
    result = await bose.connect_to_bose(Hass(entry), entry, None)
    assert result is None
    assert speaker.disconnections == 1
