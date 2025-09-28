"""LD2450 BLE integration sensor platform."""

import logging
import math
from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LD2450BLE, LD2450BLECoordinator
from .const import DOMAIN
from .models import LD2450BLEData

_LOGGER = logging.getLogger(__name__)

ZONE_1_X1_DESCRIPTION = NumberEntityDescription(
    key="zone_1_x1",
    translation_key="zone_1_x1",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=-5000,
    native_max_value=5000,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_1_Y1_DESCRIPTION = NumberEntityDescription(
    key="zone_1_y1",
    translation_key="zone_1_y1",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=0,
    native_max_value=7300,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_1_X2_DESCRIPTION = NumberEntityDescription(
    key="zone_1_x2",
    translation_key="zone_1_x2",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=-5000,
    native_max_value=5000,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_1_Y2_DESCRIPTION = NumberEntityDescription(
    key="zone_1_y2",
    translation_key="zone_1_y2",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=0,
    native_max_value=7300,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)

ZONE_2_X1_DESCRIPTION = NumberEntityDescription(
    key="zone_2_x1",
    translation_key="zone_2_x1",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=-5000,
    native_max_value=5000,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_2_Y1_DESCRIPTION = NumberEntityDescription(
    key="zone_2_y1",
    translation_key="zone_2_y1",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=0,
    native_max_value=7300,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_2_X2_DESCRIPTION = NumberEntityDescription(
    key="zone_2_x2",
    translation_key="zone_2_x2",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=-5000,
    native_max_value=5000,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_2_Y2_DESCRIPTION = NumberEntityDescription(
    key="zone_2_y2",
    translation_key="zone_2_y2",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=0,
    native_max_value=7300,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)

ZONE_3_X1_DESCRIPTION = NumberEntityDescription(
    key="zone_3_x1",
    translation_key="zone_3_x1",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=-5000,
    native_max_value=5000,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_3_Y1_DESCRIPTION = NumberEntityDescription(
    key="zone_3_y1",
    translation_key="zone_3_y1",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=0,
    native_max_value=7300,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_3_X2_DESCRIPTION = NumberEntityDescription(
    key="zone_3_x2",
    translation_key="zone_3_x2",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=-5000,
    native_max_value=5000,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)
ZONE_3_Y2_DESCRIPTION = NumberEntityDescription(
    key="zone_3_y2",
    translation_key="zone_3_y2",
    device_class=NumberDeviceClass.DISTANCE,
    mode="slider",
    native_min_value=0,
    native_max_value=7300,
    native_step=100,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
)

SENSOR_DESCRIPTIONS = (
    [
        ZONE_1_X1_DESCRIPTION,
        ZONE_1_Y1_DESCRIPTION,
        ZONE_1_X2_DESCRIPTION,
        ZONE_1_Y2_DESCRIPTION,
        
        ZONE_2_X1_DESCRIPTION,
        ZONE_2_Y1_DESCRIPTION,
        ZONE_2_X2_DESCRIPTION,
        ZONE_2_Y2_DESCRIPTION,
        
        ZONE_3_X1_DESCRIPTION,
        ZONE_3_Y1_DESCRIPTION,
        ZONE_3_X2_DESCRIPTION,
        ZONE_3_Y2_DESCRIPTION,
    ]
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the platform for LD2450BLE."""
    data: LD2450BLEData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        LD2450BLENumber(
            data.coordinator,
            data.device,
            entry.title,
            description,
        )
        for description in SENSOR_DESCRIPTIONS
    )


class LD2450BLENumber(CoordinatorEntity[LD2450BLECoordinator], NumberEntity):
    """Generic sensor for LD2450BLE."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LD2450BLECoordinator,
        device: LD2450BLE,
        name: str,
        description: NumberEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._device = device
        self._key = description.key
        self.entity_description = description
        self._attr_unique_id = f"{name}_{self._key}"
        self._attr_device_info = DeviceInfo(
            name=name,
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
            manufacturer="HiLink",
            model="LD2450",
            sw_version=getattr(self._device, "fw_ver"),
        )
        self._attr_native_value = 0

    @property
    def unique_id(self):
        """Return unique id."""
        return self._attr_unique_id
        
    @property
    def entity_category(self):
        """Return the entity category of the switch."""
        return EntityCategory.CONFIG
        
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = getattr(self._device, self._key)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Unavailable if coordinator isn't connected."""
        return self._coordinator.connected and super().available

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self._device._set_zone(
            getattr(self._device, "zone_type"), 
            int(value) if self._key == "zone_1_x1" else getattr(self._device, "zone_1_x1"), 
            int(value) if self._key == "zone_1_y1" else getattr(self._device, "zone_1_y1"), 
            int(value) if self._key == "zone_1_x2" else getattr(self._device, "zone_1_x2"), 
            int(value) if self._key == "zone_1_y2" else getattr(self._device, "zone_1_y2"), 
            int(value) if self._key == "zone_2_x1" else getattr(self._device, "zone_2_x1"), 
            int(value) if self._key == "zone_2_y1" else getattr(self._device, "zone_2_y1"), 
            int(value) if self._key == "zone_2_x2" else getattr(self._device, "zone_2_x2"), 
            int(value) if self._key == "zone_2_y2" else getattr(self._device, "zone_2_y2"), 
            int(value) if self._key == "zone_3_x1" else getattr(self._device, "zone_3_x1"), 
            int(value) if self._key == "zone_3_y1" else getattr(self._device, "zone_3_y1"), 
            int(value) if self._key == "zone_3_x2" else getattr(self._device, "zone_3_x2"), 
            int(value) if self._key == "zone_3_y2" else getattr(self._device, "zone_3_y2"))