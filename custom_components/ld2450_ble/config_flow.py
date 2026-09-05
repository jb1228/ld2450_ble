"""Config flow for LD2450BLE integration."""

from __future__ import annotations

import logging
from typing import Any

from bluetooth_data_tools import human_readable_name
from .ld2450_ble import BLEAK_EXCEPTIONS, LD2450BLE
import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, LOCAL_NAMES, SERVICE_UUID, MANUFACTURER_ID

_LOGGER = logging.getLogger(__name__)


def _is_supported_device(discovery_info: BluetoothServiceInfoBleak) -> bool:
    """Check if device is supported based on multiple criteria."""
    # Check if name starts with any of the known prefixes (case-insensitive)
    if discovery_info.name:
        name_upper = discovery_info.name.upper()
        if any(name_upper.startswith(local_name.upper()) for local_name in LOCAL_NAMES):
            _LOGGER.debug(
                "Device %s (%s) matched by name",
                discovery_info.name,
                discovery_info.address,
            )
            return True
    
    # Check if device advertises the LD2450 service UUID
    if SERVICE_UUID.lower() in [uuid.lower() for uuid in discovery_info.service_uuids]:
        _LOGGER.debug(
            "Device %s (%s) matched by service UUID",
            discovery_info.name,
            discovery_info.address,
        )
        return True
    
    # Check manufacturer data
    if MANUFACTURER_ID in discovery_info.manufacturer_data:
        _LOGGER.debug(
            "Device %s (%s) matched by manufacturer ID",
            discovery_info.name,
            discovery_info.address,
        )
        return True
    
    _LOGGER.debug(
        "Device %s (%s) did not match any criteria - Name: %s, UUIDs: %s, Manufacturer: %s",
        discovery_info.name,
        discovery_info.address,
        discovery_info.name,
        discovery_info.service_uuids,
        list(discovery_info.manufacturer_data.keys()),
    )
    return False


class Ld2450BleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LD2450 BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> config_entries.ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.info(
            "Bluetooth discovery triggered for device: %s (%s)",
            discovery_info.name,
            discovery_info.address,
        )
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": human_readable_name(
                None, discovery_info.name, discovery_info.address
            )
        }
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            local_name = discovery_info.name
            await self.async_set_unique_id(
                discovery_info.address, raise_on_progress=False
            )
            self._abort_if_unique_id_configured()
            ld2450_ble = LD2450BLE(discovery_info.device)
            try:
                await ld2450_ble.initialise()
            except BLEAK_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"
            else:
                await ld2450_ble.stop()
                return self.async_create_entry(
                    title=local_name,
                    data={
                        CONF_ADDRESS: discovery_info.address,
                    },
                )

        if discovery := self._discovery_info:
            self._discovered_devices[discovery.address] = discovery
        else:
            current_addresses = self._async_current_ids()
            for discovery in async_discovered_service_info(self.hass):
                # Skip if already configured or in the list
                if (
                    discovery.address in current_addresses
                    or discovery.address in self._discovered_devices
                ):
                    continue
                
                # Check if device is supported using multiple criteria
                if not _is_supported_device(discovery):
                    continue
                    
                self._discovered_devices[discovery.address] = discovery
                _LOGGER.info(
                    "Discovered LD2450 device: %s (%s)",
                    discovery.name,
                    discovery.address,
                )

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        service_info.address: f"{service_info.name} ({service_info.address})"
                        for service_info in self._discovered_devices.values()
                    }
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
