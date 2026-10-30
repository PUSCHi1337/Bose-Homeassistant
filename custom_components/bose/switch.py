"""Support for Bose power switch."""

from asyncio import Task, current_task
from datetime import datetime, timedelta
from typing import Any

from pybose.BoseResponse import Accessories, SystemInfo, SystemTimeout
from pybose.BoseSpeaker import BoseSpeaker

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import _LOGGER, DOMAIN
from .entity import BoseBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Bose switch."""
    speaker: BoseSpeaker = hass.data[DOMAIN][config_entry.entry_id]["speaker"]

    # Fetch system info
    system_info = hass.data[DOMAIN][config_entry.entry_id]["system_info"]
    accessories = hass.data[DOMAIN][config_entry.entry_id]["accessories"]

    entities: list[SwitchEntity] = []
    if speaker.has_capability("/system/power/timeouts"):
        entities.append(
            BoseStandbySettingSwitch(speaker, system_info, config_entry, hass)
        )
    else:
        _LOGGER.debug("Speaker does not support system timeouts")

    added_accessories: set[str] = set()

    def _create_accessory_switches(data: Accessories) -> list[SwitchEntity]:
        """Create each supported switch once, including after late discovery."""
        if not data:
            return []
        controllable = data.get("controllable") or {}
        new_entities: list[SwitchEntity] = []
        for attribute, entity_class in (
            ("subs", BoseSubwooferSwitch),
            ("rears", BoseRearSpeakerSwitch),
        ):
            if controllable.get(attribute) and attribute not in added_accessories:
                new_entities.append(
                    entity_class(speaker, system_info, data, config_entry)
                )
                added_accessories.add(attribute)
        return new_entities

    entities.extend(_create_accessory_switches(accessories))
    async_add_entities(entities, update_before_add=False)

    # A standby response (or failed first read) can omit controllable accessories.
    # Restored registry entries cannot poll themselves until their entities exist.
    if len(added_accessories) == 2 or not speaker.has_capability("/accessories"):
        return

    runtime = hass.data[DOMAIN][config_entry.entry_id]
    refresh_task: Task[None] | None = None
    cancel_interval = None
    stopped = False

    @callback
    def _stop_discovery() -> None:
        nonlocal stopped
        stopped = True
        if cancel_interval is not None:
            cancel_interval()
        if refresh_task is not None and refresh_task is not current_task():
            refresh_task.cancel()

    async def _async_refresh_accessories() -> None:
        if not speaker.is_connected():
            return
        try:
            data = await speaker.get_accessories()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Accessories not ready for discovery", exc_info=True)
            return
        if stopped:
            return
        runtime["accessories"] = data
        new_entities = _create_accessory_switches(data)
        if new_entities:
            async_add_entities(new_entities, update_before_add=False)
        if len(added_accessories) == 2:
            _stop_discovery()

    @callback
    def _schedule_refresh(_now: datetime) -> None:
        nonlocal refresh_task
        if stopped or (refresh_task is not None and not refresh_task.done()):
            return
        refresh_task = config_entry.async_create_background_task(
            hass, _async_refresh_accessories(), "Bose accessory discovery",
            eager_start=False,
        )

    cancel_interval = async_track_time_interval(
        hass, _schedule_refresh, timedelta(seconds=60)
    )
    config_entry.async_on_unload(_stop_discovery)

class BoseAccessorySwitch(BoseBaseEntity, SwitchEntity):
    """Generic accessory switch for Bose speakers."""

    def __init__(
        self,
        speaker: BoseSpeaker,
        speaker_info: SystemInfo,
        accessories: Accessories,
        config_entry,
        name: str,
        attribute: str,
    ) -> None:
        """Initialize the switch."""
        BoseBaseEntity.__init__(self, speaker)
        self.speaker = speaker
        self._attribute = attribute
        self._attr_is_on = (
            accessories.get("enabled", {}).get(attribute) if accessories else False
        )
        self.speaker_info = speaker_info
        self.config_entry = config_entry
        self._attr_translation_key = attribute
        self.icon = "mdi:speaker"

        self.speaker.attach_receiver(self._parse_message)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the speaker feature."""
        await self.speaker.put_accessories(**{f"{self._attribute}_enabled": True})
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the speaker feature."""
        await self.speaker.put_accessories(**{f"{self._attribute}_enabled": False})
        self.async_write_ha_state()

    def _parse_message(self, data):
        """Parse the message from the speaker."""
        if data.get("header", {}).get("resource") == "/accessories":
            self._parse_accessories(Accessories(data.get("body")))

    def _parse_accessories(self, data: Accessories):
        """Parse the accessories data."""
        enabled = data.get("enabled", {}) if data else {}
        self._attr_is_on = enabled.get(self._attribute, False) if enabled else False
        self._attr_available = True
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the switch state."""
        if not self.speaker.is_connected():
            return
        try:
            accessories = await self.speaker.get_accessories()
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Cannot read the accessory state from the speaker", exc_info=True
            )
            if self._attr_available:
                self._attr_available = False
                self.async_write_ha_state()
            return
        self._parse_accessories(accessories)


class BoseSubwooferSwitch(BoseAccessorySwitch):
    """Switch to turn on/off subwoofers."""

    def __init__(
        self,
        speaker: BoseSpeaker,
        speaker_info: SystemInfo,
        accessories: Accessories,
        config_entry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            speaker, speaker_info, accessories, config_entry, "Subwoofers", "subs"
        )


class BoseRearSpeakerSwitch(BoseAccessorySwitch):
    """Switch to turn on/off rear speakers."""

    def __init__(
        self,
        speaker: BoseSpeaker,
        speaker_info: SystemInfo,
        accessories: Accessories,
        config_entry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            speaker, speaker_info, accessories, config_entry, "Rear Speakers", "rears"
        )


class BoseStandbySettingSwitch(BoseBaseEntity, SwitchEntity):
    """Switch to turn on/off standby setting."""

    def __init__(
        self,
        speaker: BoseSpeaker,
        speaker_info: SystemInfo,
        config_entry,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the switch."""
        BoseBaseEntity.__init__(self, speaker)
        self.speaker = speaker
        self._attr_is_on = None
        self.speaker_info = speaker_info
        self.config_entry = config_entry
        self.icon = "mdi:power-standby"
        self._attr_translation_key = "auto_standby"

        self._attr_entity_category = EntityCategory.CONFIG

        self.speaker.attach_receiver(self._parse_message)
        hass.async_create_task(self.async_update())

    def _parse_message(self, data):
        """Parse the message from the speaker."""
        if data.get("header", {}).get("resource") == "/system/power/timeouts":
            result: SystemTimeout = data.get("body")
            self._attr_is_on = result.get("noAudio", False)
            self._attr_available = True
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the speaker feature."""
        await self.speaker.set_system_timeout(True, False)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the speaker feature."""
        await self.speaker.set_system_timeout(False, False)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the switch state."""
        if not self.speaker.is_connected():
            return
        try:
            timeouts = await self.speaker.get_system_timeout()
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Cannot read the standby setting from the speaker", exc_info=True
            )
            if self._attr_available:
                self._attr_available = False
                self.async_write_ha_state()
            return
        self._attr_is_on = timeouts.get("noAudio", False)
        self._attr_available = True
        self.async_write_ha_state()
