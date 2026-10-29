"""Tests for the Bose switch platform."""

from bose.switch import BoseAccessorySwitch, BoseStandbySettingSwitch

from .conftest import FakeHass, FakeSpeaker


def _accessory_switch(speaker):
    entity = BoseAccessorySwitch(
        speaker,
        {"productName": "Test"},
        {"enabled": {"subs": True}},
        None,
        "Subwoofers",
        "subs",
    )
    entity.async_write_ha_state = lambda: None
    return entity


async def _no_answer():
    raise TimeoutError("no response from the speaker within 10 seconds")


async def test_failed_update_goes_unavailable_instead_of_raising():
    """A speaker that does not answer must not break the poll (issue #82)."""
    speaker = FakeSpeaker()
    speaker.get_accessories = _no_answer
    entity = _accessory_switch(speaker)

    await entity.async_update()

    assert not entity.available


async def test_update_recovers_when_the_speaker_answers_again():
    """Availability comes back with the first successful read."""
    speaker = FakeSpeaker()

    async def answers():
        return {"enabled": {"subs": False}}

    speaker.get_accessories = answers
    entity = _accessory_switch(speaker)
    entity._attr_available = False  # noqa: SLF001

    await entity.async_update()

    assert entity.available
    assert entity.is_on is False


async def test_push_restores_availability():
    """A notification proves the speaker is alive again."""
    speaker = FakeSpeaker()
    entity = _accessory_switch(speaker)
    entity._attr_available = False  # noqa: SLF001

    speaker.notify("/accessories", {"enabled": {"subs": True}})

    assert entity.available
    assert entity.is_on is True


async def test_standby_switch_survives_a_failed_update():
    """The standby switch gets the same protection."""
    speaker = FakeSpeaker()
    speaker.get_system_timeout = _no_answer
    entity = BoseStandbySettingSwitch(
        speaker, {"productName": "Test"}, None, FakeHass()
    )
    entity.async_write_ha_state = lambda: None

    await entity.async_update()

    assert not entity.available


# Reproduce entities left as restored placeholders when setup happens in standby.
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bose import switch as switch_platform
from bose.const import DOMAIN

_ACCESSORIES = {
    "controllable": {"subs": True, "rears": True},
    "enabled": {"subs": True, "rears": True},
}


class _DiscoveryEntry:
    entry_id = "accessory-entry"

    def __init__(self):
        self.tasks = []
        self.unload_callbacks = []

    def async_on_unload(self, callback):
        self.unload_callbacks.append(callback)

    def async_create_background_task(self, hass, coro, name, **kwargs):
        task = asyncio.create_task(coro, name=name)
        self.tasks.append(task)
        return task

    def unload(self):
        for callback in self.unload_callbacks:
            callback()


async def _discovery_setup(monkeypatch, initial, *, supported=True):
    speaker = FakeSpeaker(capabilities=("/accessories",) if supported else ())
    speaker.is_connected = lambda: True
    speaker.get_accessories = AsyncMock(return_value=_ACCESSORIES)
    speaker.put_accessories = AsyncMock(
        side_effect=AssertionError("Discovery must never change accessory settings")
    )
    entry = _DiscoveryEntry()
    hass = FakeHass()
    runtime = {
        "speaker": speaker,
        "system_info": {"productName": "Test"},
        "accessories": initial,
    }
    hass.data = {DOMAIN: {entry.entry_id: runtime}}
    timers = []
    entities = []

    def add_entities(new_entities, update_before_add=False):
        for entity in new_entities:
            entity.async_write_ha_state = lambda: None
        entities.extend(new_entities)

    def track_interval(hass, callback, interval):
        timer = SimpleNamespace(
            callback=callback, interval=interval, cancelled=False
        )
        timers.append(timer)

        def cancel():
            timer.cancelled = True

        return cancel

    monkeypatch.setattr(
        switch_platform, "async_track_time_interval", track_interval, raising=False
    )
    await switch_platform.async_setup_entry(hass, entry, add_entities)
    return SimpleNamespace(
        speaker=speaker, entry=entry, runtime=runtime, timers=timers, entities=entities
    )


async def _tick(context):
    assert len(context.timers) == 1, "Missing retry for late accessory discovery"
    context.timers[0].callback(None)
    if context.entry.tasks:
        await asyncio.gather(*context.entry.tasks)


@pytest.mark.parametrize(
    "initial",
    [
        [],  # the initial accessory read failed during integration setup
        {"controllable": {"subs": False, "rears": False}},
    ],
)
async def test_accessory_switches_appear_after_standby(monkeypatch, initial):
    context = await _discovery_setup(monkeypatch, initial)
    assert not context.entities

    await _tick(context)

    assert {entity.unique_id for entity in context.entities} == {
        "device-1_subs", "device-1_rears"
    }
    assert all(entity.is_on for entity in context.entities)
    assert context.timers[0].interval == timedelta(seconds=60)
    assert context.timers[0].cancelled
    assert context.runtime["accessories"] == _ACCESSORIES
    context.speaker.put_accessories.assert_not_awaited()
    context.entry.unload()


async def test_late_rears_do_not_duplicate_existing_subwoofer(monkeypatch):
    initial = {"controllable": {"subs": True}, "enabled": {"subs": True}}
    context = await _discovery_setup(monkeypatch, initial)
    context.speaker.get_accessories.side_effect = [initial, _ACCESSORIES]
    subwoofer = context.entities[0]

    await _tick(context)
    assert context.entities == [subwoofer]
    assert not context.timers[0].cancelled
    await _tick(context)

    assert len(context.entities) == 2
    assert context.entities[0] is subwoofer
    assert len(context.speaker.receivers) == 2
    assert context.timers[0].cancelled
    context.entry.unload()


async def test_discovery_skips_disconnected_speakers_and_recovers(monkeypatch):
    context = await _discovery_setup(monkeypatch, [])
    context.speaker.is_connected = lambda: False

    await _tick(context)
    context.speaker.get_accessories.assert_not_awaited()
    assert not context.entities

    context.speaker.is_connected = lambda: True
    await _tick(context)
    assert len(context.entities) == 2
    context.entry.unload()


async def test_temporary_discovery_failure_keeps_the_retry(monkeypatch):
    context = await _discovery_setup(monkeypatch, [])
    context.speaker.get_accessories.side_effect = [
        TimeoutError("accessories not ready"), _ACCESSORIES
    ]

    await _tick(context)
    assert not context.entities
    assert not context.timers[0].cancelled
    await _tick(context)

    assert len(context.entities) == 2
    context.entry.unload()


async def test_existing_accessories_need_no_discovery_timer(monkeypatch):
    context = await _discovery_setup(monkeypatch, _ACCESSORIES)
    assert len(context.entities) == 2
    assert not context.timers
    assert not context.entry.tasks


async def test_unsupported_speaker_never_starts_accessory_discovery(monkeypatch):
    context = await _discovery_setup(monkeypatch, [], supported=False)
    assert not context.entities
    assert not context.timers
    context.speaker.get_accessories.assert_not_awaited()


async def test_discovery_is_single_flight_and_cancelled_on_unload(monkeypatch):
    context = await _discovery_setup(monkeypatch, [])
    assert len(context.timers) == 1, "Missing retry for late accessory discovery"
    started = asyncio.Event()
    never_finishes = asyncio.Event()

    async def pending_accessories():
        started.set()
        await never_finishes.wait()

    context.speaker.get_accessories.side_effect = pending_accessories
    context.timers[0].callback(None)
    await started.wait()
    context.timers[0].callback(None)
    assert len(context.entry.tasks) == 1

    context.entry.unload()
    await asyncio.gather(*context.entry.tasks, return_exceptions=True)

    assert context.timers[0].cancelled
    assert context.entry.tasks[0].cancelled()
    assert not context.entities
    context.timers[0].callback(None)
    assert len(context.entry.tasks) == 1
