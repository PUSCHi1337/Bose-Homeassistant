"""Base entity for Bose integration."""

from typing import cast

from propcache.api import cached_property
from pybose.BoseSpeaker import BoseSpeaker

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class BoseBaseEntity(Entity):
    """Base entity for Bose integration."""

    _cf_unique_id: str | None = None

    def __init__(self, speaker: BoseSpeaker) -> None:
        """Initialize the entity."""
        self.speaker = speaker

        self._attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Transport loss is unavailable, including for push-only entities."""
        return self.speaker.is_connected() and super().available

    async def async_added_to_hass(self) -> None:
        """Follow one shared connection watcher, removed with this entity."""
        await super().async_added_to_hass()
        entry = self.platform.config_entry
        coordinator = self.hass.data[DOMAIN][entry.entry_id]["coordinator"]
        self._bose_connected = self.speaker.is_connected()
        self.async_on_remove(
            coordinator.async_add_listener(self._async_connection_updated)
        )

    @callback
    def _async_connection_updated(self) -> None:
        """Publish disconnection and request fresh data once after reconnect."""
        connected = self.speaker.is_connected()
        if connected == self._bose_connected:
            return
        self._bose_connected = connected
        if connected:
            self.async_schedule_update_ha_state(force_refresh=True)
        else:
            self.async_write_ha_state()

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Return the device info of the entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, cast(str, self.speaker.get_device_id()))},
        )

    @cached_property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        base_id = cast(str, self.speaker.get_device_id())

        if (
            hasattr(self, "_cf_unique_id")
            and self._cf_unique_id is not None
            and self._cf_unique_id.strip()
        ):
            name_part = self._cf_unique_id.strip()
        elif (
            hasattr(self, "_attr_translation_key")
            and self._attr_translation_key is not None
            and self._attr_translation_key.strip()
        ):
            name_part = self._attr_translation_key.strip()
        elif (
            hasattr(self, "_attr_name")
            and self._attr_name is not None
            and self._attr_name.strip()
        ):
            name_part = self._attr_name.strip()
        else:
            name_part = "error"

        if not name_part:
            return base_id
        name_part = name_part.lower().replace(" ", "_")
        return f"{base_id}_{name_part}"
