"""WiFi helper mixin for Bose integration.

This module provides a small helper mixin used by WiFi-related
entities. It intentionally does not inherit from Home Assistant
Entity classes to avoid multiple-inheritance conflicts.
"""

from pybose.BoseResponse import WifiStatus
from pybose.BoseSpeaker import BoseSpeaker

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import _LOGGER, DOMAIN
from ..coordinator import BoseCoordinator


class BoseWifiBase:
    """Helper mixin for Bose WiFi sensors."""

    def __init__(
        self,
        speaker: BoseSpeaker,
        config_entry: ConfigEntry,
        hass: HomeAssistant,
        coordinator: BoseCoordinator,
    ) -> None:
        """Initialize the WiFi helper on the entity instance."""
        self.speaker = speaker
        self.config_entry = config_entry
        self.coordinator = coordinator
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.data["guid"])},
        }

        self.speaker.attach_receiver(self._parse_message)
        self.hass = hass

    def _parse_message(self, data):
        """Parse real-time messages from the speaker."""
        if data.get("header", {}).get("resource") == "/network/wifi/status":
            self.update_from_wifi_status(WifiStatus(data.get("body")))
            self._attr_available = True
            if self.hass and hasattr(self, "async_write_ha_state"):
                self.async_write_ha_state()

    def update_from_wifi_status(self, wifi_status: WifiStatus):
        """Implemented in sensor."""
        raise NotImplementedError("update_from_wifi_status not implemented in sensor")

    async def async_update(self) -> None:
        """Fetch the latest WiFi status."""
        if not self.speaker.is_connected():
            return
        try:
            wifi_data = await self.coordinator.get_wifi_status()
            wifi_status = WifiStatus(wifi_data)
            self.update_from_wifi_status(wifi_status)
        except Exception:  # noqa: BLE001
            if self._attr_available and self.speaker.is_connected():
                _LOGGER.exception(
                    "Error updating WiFi status for %s", self.config_entry.data["ip"]
                )
            self._attr_available = False
        else:
            self._attr_available = True
