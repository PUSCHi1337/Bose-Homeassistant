"""The Bose component."""

import asyncio
import json
from time import monotonic

from pybose.BoseAuth import BoseAuth, BoseAuthRejectedError
from pybose.BoseResponse import Accessories, NetworkStateEnum
from pybose.BoseSpeaker import BoseRequestException, BoseSpeaker

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv, device_registry as dr

from . import config_flow
from .const import (
    _LOGGER,
    DOMAIN,
    is_offline_error,
    REQUEST_TIMEOUT,
    TOKEN_REFRESH_DELAY,
    TOKEN_RETRY_DELAY,
)
from .coordinator import BoseCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@callback
def async_migrate_unique_id(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Give entries created before 1.2.3 the unique id newer entries carry.

    Without it Home Assistant cannot tell that the speaker is already set up, so discovery keeps offering it and adding it again creates a duplicate.
    """
    guid = config_entry.data.get("guid")
    if config_entry.unique_id is not None or not guid:
        return

    owner = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, guid)
    if owner is not None and owner.entry_id != config_entry.entry_id:
        _LOGGER.warning(
            "Config entry %s is a duplicate of %s (same speaker %s), remove one of them",
            config_entry.title,
            owner.title,
            guid,
        )
        return

    _LOGGER.info(
        "Adopting %s as unique id of config entry %s", guid, config_entry.title
    )
    hass.config_entries.async_update_entry(config_entry, unique_id=guid)


PLATFORMS = [
    "media_player", "select", "number", "sensor", "binary_sensor", "switch", "button"
]
RECONNECT_CHECK_INTERVAL = 30
RECONNECT_MAX_DELAY = 300


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up an entry and close partial resources on failure or cancellation."""
    try:
        result = await _async_setup_entry(hass, config_entry)
        if not result:
            await _async_stop_entry(hass, config_entry)
        return result
    except BaseException:
        try:
            await _async_stop_entry(hass, config_entry)
        except Exception:
            _LOGGER.exception("Failed to clean up a partial Bose setup")
        raise


async def _async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Bose integration from a config entry."""
    async_migrate_unique_id(hass, config_entry)

    auth = BoseAuth()

    hass.data.setdefault(DOMAIN, {})

    # Store device data in a separate dict (instead of modifying config_entry.data)
    hass.data[DOMAIN][config_entry.entry_id] = {
        "config": config_entry.data  # Store configuration data
    }

    if (
        config_entry.data.get("access_token") is not None
        and config_entry.data.get("refresh_token") is not None
        and config_entry.data.get("bose_person_id") is not None
        and config_entry.data.get("azure_refresh_token") is not None
    ):
        # Using existing access token
        _LOGGER.debug("Using existing access token for %s", config_entry.data["mail"])
        auth.set_access_token(
            config_entry.data["access_token"],
            config_entry.data["refresh_token"],
            config_entry.data["bose_person_id"],
        )
        # Set Azure refresh token which is required for token refresh
        auth.set_azure_refresh_token(config_entry.data["azure_refresh_token"])

        # The speaker rejects an expired token, and the periodic refresh only
        # starts after a successful setup, so refresh an expired token first.
        if not auth.is_token_valid():
            _LOGGER.info(
                "Access token for %s has expired, refreshing it",
                config_entry.data["mail"],
            )
            # refresh_token raises ConfigEntryAuthFailed if the refresh token
            # was rejected; any other failure is retried later.
            if not await refresh_token(hass, config_entry, auth):
                raise ConfigEntryNotReady(
                    f"Could not refresh the expired access token for {config_entry.data['mail']}"
                )
    else:
        # Missing tokens - trigger reauthentication
        _LOGGER.warning(
            "Missing authentication tokens for %s, triggering reauthentication",
            config_entry.data.get("mail"),
        )
        raise ConfigEntryAuthFailed(
            f"Authentication required for {config_entry.data.get('mail')}"
        )

    speaker = await connect_to_bose(hass, config_entry, auth)

    if not speaker:
        discovered = await config_flow.Discover_Bose_Devices(hass)
        found = False

        # find the devce with the same GUID
        for device in discovered:
            if device["guid"] == config_entry.data["guid"]:
                _LOGGER.info(
                    "Found device with same GUID, updating IP to: %s", device["ip"]
                )
                hass.config_entries.async_update_entry(
                    config_entry,
                    data={**config_entry.data, "ip": device["ip"]},
                )
                found = True
                break

        if not found:
            raise ConfigEntryNotReady(
                f"Cannot reach the Bose speaker at {config_entry.data['ip']} and it was not discovered under another address"
            )

        new_entry = hass.config_entries.async_get_entry(config_entry.entry_id)
        if new_entry is None:
            _LOGGER.error("Config entry not found after updating IP, aborting setup")
            return False
        config_entry = new_entry
        speaker = await connect_to_bose(hass, config_entry, auth)

    if speaker is None:
        raise ConfigEntryNotReady(
            f"Cannot reach the Bose speaker at {config_entry.data['ip']}"
        )

    hass.data[DOMAIN][config_entry.entry_id]["speaker"] = speaker
    try:
        system_info = await speaker.get_system_info()
        capabilities = await speaker.get_capabilities()
        await speaker.subscribe()
    except Exception as err:
        raise ConfigEntryNotReady(
            f"The Bose speaker at {config_entry.data['ip']} did not answer during setup: {err}"
        ) from err

    # Register device in Home Assistant
    device_registry = dr.async_get(hass)

    identifiers = {(DOMAIN, config_entry.data["guid"])}
    connections = set()

    if speaker.has_capability("/network/status"):
        try:
            network_status = await speaker.get_network_status()
        except BoseRequestException as err:
            # Some speakers refuse this to some accounts ("User not authorized
            # for LAN"). It only provides the MAC address, so carry on without.
            _LOGGER.warning(
                "Cannot read the network status of the Bose speaker at %s, "
                "registering it without its MAC address: %s",
                config_entry.data["ip"],
                err,
            )
            network_status = {}

        primary_name = network_status.get("primary")
        for interface in network_status.get("interfaces", []):
            if (
                interface.get("type") == primary_name
                and interface.get("state", NetworkStateEnum.DOWN) == NetworkStateEnum.UP
            ):
                mac_address = interface.get("macAddress", "")
                if mac_address:
                    formatted_mac = dr.format_mac(mac_address)
                    connections.add((dr.CONNECTION_NETWORK_MAC, formatted_mac))
                break

    speaker_device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers=identifiers,
        connections=connections,
        manufacturer="Bose",
        name=system_info["name"],
        model=system_info["productName"],
        serial_number=system_info["serialNumber"],
        sw_version=system_info["softwareVersion"],
    )

    # Store the speaker object separately
    hass.data[DOMAIN][config_entry.entry_id]["speaker"] = speaker
    hass.data[DOMAIN][config_entry.entry_id]["system_info"] = system_info
    hass.data[DOMAIN][config_entry.entry_id]["capabilities"] = capabilities
    hass.data[DOMAIN][config_entry.entry_id]["auth"] = auth

    coordinator = BoseCoordinator(
        hass,
        speaker,
        config_entry.data["guid"],
    )
    hass.data[DOMAIN][config_entry.entry_id]["coordinator"] = coordinator
    await coordinator.async_config_entry_first_refresh()

    try:
        # Not all Devices have accessories like "Bose Portable Smart Speaker"
        accessories = await speaker.get_accessories()
        await registerAccessories(
            hass, config_entry, accessories, speaker_device.id
        )
    except Exception:  # noqa: BLE001
        accessories = []
    hass.data[DOMAIN][config_entry.entry_id]["accessories"] = accessories

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Fork change, 2026-10-29: entry ownership plus explicit awaited cleanup.
    tasks = hass.data[DOMAIN][config_entry.entry_id].setdefault("tasks", [])
    tasks.append(config_entry.async_create_background_task(
        hass, refresh_token_thread(hass, config_entry, auth),
        "Bose token refresh", eager_start=False,
    ))
    tasks.append(config_entry.async_create_background_task(
        hass, reconnection_monitor(hass, config_entry, auth),
        "Bose reconnection monitor", eager_start=False,
    ))
    return True


async def refresh_token_thread(
    hass: HomeAssistant, config_entry: ConfigEntry, auth: BoseAuth
):
    """Refresh the token periodically."""
    while True:
        if (
            auth.get_token_validity_time() > 2 * TOKEN_REFRESH_DELAY
        ):  # when token is valid for more than 2 * refresh-delay ...
            _LOGGER.debug(
                "Token still valid, checking again in %s seconds", TOKEN_REFRESH_DELAY
            )  # wait for 1 x refresh-delay before checking again
            await asyncio.sleep(TOKEN_REFRESH_DELAY)
            continue
        _LOGGER.info("Refreshing token for %s", config_entry.data["mail"])
        try:
            if not await refresh_token(hass, config_entry, auth):
                _LOGGER.error(
                    "Failed to refresh token for %s. Trying again in %s seconds",
                    config_entry.data["mail"],
                    TOKEN_RETRY_DELAY,
                )
            else:
                _LOGGER.info(
                    "Token refreshed successfully for %s. New token valid for %s seconds",
                    config_entry.data["mail"],
                    auth.get_token_validity_time(),
                )
        except ConfigEntryAuthFailed:
            # Token refresh failed due to authentication issue - trigger reauth flow
            _LOGGER.warning(
                "Authentication failed for %s, starting reauthentication flow",
                config_entry.data["mail"],
            )
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "reauth", "entry_id": config_entry.entry_id},
                data=config_entry.data,
            )
            # Stop the refresh loop after triggering reauth
            break
        await asyncio.sleep(TOKEN_RETRY_DELAY)


async def refresh_token(hass: HomeAssistant, config_entry: ConfigEntry, auth: BoseAuth):
    """Refresh the token."""
    try:
        new_token = await hass.async_add_executor_job(auth.do_token_refresh)
        if new_token:
            # Get the updated Azure refresh token from auth object
            azure_refresh_token = auth.get_azure_refresh_token()

            update_data = {
                **config_entry.data,
                "access_token": new_token["access_token"],
                "refresh_token": new_token["refresh_token"],
            }

            # Update Azure refresh token if available
            if azure_refresh_token:
                update_data["azure_refresh_token"] = azure_refresh_token

            hass.config_entries.async_update_entry(
                config_entry,
                data=update_data,
            )
            _LOGGER.info(
                "Token is valid for %s seconds", auth.get_token_validity_time()
            )
            return True
    except BoseAuthRejectedError as e:
        _LOGGER.warning(
            "Refresh token invalid for %s, triggering reauthentication flow: %s",
            config_entry.data["mail"],
            e,
        )
        raise ConfigEntryAuthFailed(
            f"Refresh token invalid for {config_entry.data['mail']}"
        ) from e
    except Exception as e:  # noqa: BLE001
        # Bose unreachable or failing; the caller retries later.
        _LOGGER.error(
            "Failed to refresh token for %s: %s", config_entry.data["mail"], e
        )
    return False


async def reconnection_monitor(
    hass: HomeAssistant, config_entry: ConfigEntry, auth: BoseAuth
):
    """Recover the same client, with bounded mDNS discovery attempts."""
    runtime = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    retry_at = 0.0
    retry_delay = RECONNECT_CHECK_INTERVAL
    while runtime and not runtime.get("stopping"):
        await asyncio.sleep(RECONNECT_CHECK_INTERVAL)
        if (hass.data.get(DOMAIN, {}).get(config_entry.entry_id) is not runtime
                or runtime.get("stopping")):
            return
        speaker = runtime.get("speaker")
        if speaker is None:
            return
        if speaker.is_connected():
            retry_at = 0.0
            retry_delay = RECONNECT_CHECK_INTERVAL
            continue
        if monotonic() < retry_at:
            continue
        try:
            discovered = await config_flow.Discover_Bose_Devices(hass)
            device = next(
                (item for item in discovered
                 if item["guid"] == config_entry.data["guid"]), None
            )
            if device is None:
                # An intentionally powered-off speaker is a normal absence.
                retry_at = monotonic() + retry_delay
                _LOGGER.debug(
                    "Bose speaker offline; next discovery in %s seconds",
                    retry_delay,
                )
                retry_delay = min(retry_delay * 2, RECONNECT_MAX_DELAY)
                continue
            # Never replace the client retained by entities/coordinator/callbacks.
            await speaker.reconnect(host=device["ip"])
            if device["ip"] != config_entry.data.get("ip"):
                hass.config_entries.async_update_entry(
                    config_entry, data={**config_entry.data, "ip": device["ip"]}
                )
            retry_at = 0.0
            retry_delay = RECONNECT_CHECK_INTERVAL
            _LOGGER.info("Bose speaker connection recovered")
        except Exception as err:
            retry_at = monotonic() + retry_delay
            if is_offline_error(err):
                _LOGGER.debug(
                    "Bose speaker not ready; next discovery in %s seconds: %s",
                    retry_delay, err,
                )
            else:
                _LOGGER.warning(
                    "Bose recovery failed; next discovery in %s seconds: %s",
                    retry_delay, err,
                )
            retry_delay = min(retry_delay * 2, RECONNECT_MAX_DELAY)


async def _async_stop_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Await every owned task before closing the client and removing runtime."""
    runtime = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    if runtime is None:
        return
    runtime["stopping"] = True
    current = asyncio.current_task()
    tasks = [task for task in runtime.get("tasks", [])
             if task is not current]
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    coordinator = runtime.get("coordinator")
    if coordinator is not None:
        await coordinator.async_shutdown()
    speaker = runtime.get("speaker")
    if speaker is not None:
        await speaker.disconnect()
    hass.data[DOMAIN].pop(config_entry.entry_id, None)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload platforms first; retain runtime if unloading is refused."""
    if not await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        return False
    await _async_stop_entry(hass, config_entry)
    return True


def setup(hass: HomeAssistant, config: ConfigEntry) -> bool:
    """Set up the Bose component."""

    async def handle_custom_request(call: ServiceCall) -> ServiceResponse:
        raw_device_id = call.data.get("device_id")
        _LOGGER.debug(
            "send_custom_request: device_id=%r (type=%s), all data keys=%s",
            raw_device_id,
            type(raw_device_id).__name__,
            list(call.data.keys()),
        )
        if not raw_device_id:
            raise ValueError("No valid target device provided.")

        if isinstance(raw_device_id, list):
            ha_device_id = raw_device_id[0]
        else:
            ha_device_id = str(raw_device_id)

        resource = call.data["resource"]
        method = call.data["method"]
        body = call.data.get("body", {})

        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get(ha_device_id)
        if device_entry is None or device_entry.primary_config_entry is None:
            raise ValueError(
                f"No valid config entry found for Home Assistant device_id: {ha_device_id}"
            )
        speaker = hass.data[DOMAIN][device_entry.primary_config_entry]["speaker"]

        if not speaker:
            raise ValueError(
                f"No speaker found for Home Assistant device_id: {ha_device_id}"
            )

        try:
            response = await speaker._request(resource, method, body)  # noqa: SLF001
            return {
                "summary": "Successfully sent request to Bose speaker",
                "description": json.dumps(response, indent=2),
            }
        except Exception as e:  # noqa: BLE001
            return {
                "summary": "Failed to send request to Bose speaker",
                "description": str(e),
            }

    async def handle_remove_bluetooth_device(call: ServiceCall) -> None:
        """Handle remove Bluetooth device service call."""
        ha_device_id = call.data["device_id"]
        mac_address = call.data["mac_address"]

        # Find the matching speaker instance
        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get(ha_device_id)
        if device_entry is None or device_entry.primary_config_entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="config_entry_not_found",
                translation_placeholders={"device_id": ha_device_id},
            )
        speaker = hass.data[DOMAIN][device_entry.primary_config_entry]["speaker"]

        if not speaker:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="speaker_not_found",
                translation_placeholders={"device_id": ha_device_id},
            )

        await speaker.remove_bluetooth_sink_device(mac_address)

    hass.services.register(
        DOMAIN,
        "remove_bluetooth_device",
        handle_remove_bluetooth_device,
    )
    hass.services.register(
        DOMAIN,
        "send_custom_request",
        handle_custom_request,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def registerAccessories(
    hass: HomeAssistant,
    config_entry,
    accessories: Accessories,
    speaker_device_id: str,
):
    """Register accessories in Home Assistant, linked to the speaker's device."""
    device_registry = dr.async_get(hass)

    subs = accessories.get("subs") or []
    rears_raw = accessories.get("rears") or []

    rears: list = []
    if isinstance(rears_raw, dict):
        for v in rears_raw.values():
            if isinstance(v, list):
                rears.extend(v)
            else:
                rears.append(v)
    elif isinstance(rears_raw, list):
        rears = list(rears_raw)
    else:
        rears = [rears_raw]

    # Linked with async_update_device: the via_device parameter of
    # async_get_or_create is deprecated, and its via_device_id replacement
    # only exists since Home Assistant 2026.8.
    for accessory in list(subs) + rears:
        device = device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, accessory.get("serialnum", "N/A"))},
            serial_number=accessory.get("serialnum", "N/A"),
            manufacturer="Bose",
            name=accessory.get("type", "").replace("_", " "),
            model=accessory.get("type", "").replace("_", " "),
            sw_version=accessory.get("version", "N/A"),
        )
        if device.via_device_id != speaker_device_id:
            device_registry.async_update_device(
                device.id, via_device_id=speaker_device_id
            )


async def connect_to_bose(
    hass: HomeAssistant, config_entry: ConfigEntry, auth: BoseAuth
):
    """Connect to the Bose speaker."""
    data = config_entry.data

    speaker = BoseSpeaker(
        host=data["ip"], device_id=data["guid"],
        bose_auth=auth, request_timeout=REQUEST_TIMEOUT
    )

    try:
        await speaker.connect()
    except asyncio.CancelledError:
        await speaker.disconnect()
        raise
    except Exception as e:  # noqa: BLE001
        await speaker.disconnect()
        if is_offline_error(e):
            _LOGGER.debug("Bose speaker is offline during setup: %s", e)
        else:
            _LOGGER.warning("Failed to connect to Bose speaker: %s", e)
        return None

    return speaker
