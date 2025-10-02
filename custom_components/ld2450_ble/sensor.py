"""LD2450 BLE integration sensor platform."""

import logging
import math
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
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

TARGET_1_X_DESCRIPTION = SensorEntityDescription(
    key="target_1_x",
    translation_key="target_1_x",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:arrow-left-right",
)
TARGET_1_Y_DESCRIPTION = SensorEntityDescription(
    key="target_1_y",
    translation_key="target_1_y",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:arrow-up-down",
)
TARGET_1_SPEED_DESCRIPTION = SensorEntityDescription(
    key="target_1_speed",
    translation_key="target_1_speed",
    device_class=None,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement="cm/s",
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:speedometer-slow",
)
TARGET_1_RESOLUTION_DESCRIPTION = SensorEntityDescription(
    key="target_1_resolution",
    translation_key="target_1_resolution",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    icon="mdi:map-marker-radius-outline",
)

TARGET_2_X_DESCRIPTION = SensorEntityDescription(
    key="target_2_x",
    translation_key="target_2_x",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:arrow-left-right",
)
TARGET_2_Y_DESCRIPTION = SensorEntityDescription(
    key="target_2_y",
    translation_key="target_2_y",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:arrow-up-down",
)
TARGET_2_SPEED_DESCRIPTION = SensorEntityDescription(
    key="target_2_speed",
    translation_key="target_2_speed",
    device_class=None,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement="cm/s",
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:speedometer-slow",
)
TARGET_2_RESOLUTION_DESCRIPTION = SensorEntityDescription(
    key="target_2_resolution",
    translation_key="target_2_resolution",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    icon="mdi:map-marker-radius-outline",
)

TARGET_3_X_DESCRIPTION = SensorEntityDescription(
    key="target_3_x",
    translation_key="target_3_x",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:arrow-left-right",
)
TARGET_3_Y_DESCRIPTION = SensorEntityDescription(
    key="target_3_y",
    translation_key="target_3_y",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:arrow-up-down",
)
TARGET_3_SPEED_DESCRIPTION = SensorEntityDescription(
    key="target_3_speed",
    translation_key="target_3_speed",
    device_class=None,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement="cm/s",
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:speedometer-slow",
)
TARGET_3_RESOLUTION_DESCRIPTION = SensorEntityDescription(
    key="target_3_resolution",
    translation_key="target_3_resolution",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
    entity_registry_visible_default=False,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    icon="mdi:map-marker-radius-outline",
)

#calculated
TARGET_1_DISTANCE_DESCRIPTION = SensorEntityDescription(
    key="target_1_distance",
    translation_key="target_1_distance",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:map-marker-distance",
)
TARGET_2_DISTANCE_DESCRIPTION = SensorEntityDescription(
    key="target_2_distance",
    translation_key="target_2_distance",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:map-marker-distance",
)
TARGET_3_DISTANCE_DESCRIPTION = SensorEntityDescription(
    key="target_3_distance",
    translation_key="target_3_distance",
    device_class=SensorDeviceClass.DISTANCE,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:map-marker-distance",
)
TARGET_1_ANGLE_DESCRIPTION = SensorEntityDescription(
    key="target_1_angle",
    translation_key="target_1_angle",
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement="°",
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:angle-acute",
)
TARGET_2_ANGLE_DESCRIPTION = SensorEntityDescription(
    key="target_2_angle",
    translation_key="target_2_angle",
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement="°",
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:angle-acute",
)
TARGET_3_ANGLE_DESCRIPTION = SensorEntityDescription(
    key="target_3_angle",
    translation_key="target_3_angle",
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    native_unit_of_measurement="°",
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:angle-acute",
)


SENSOR_DESCRIPTIONS = (
    [
        TARGET_1_X_DESCRIPTION,
        TARGET_1_Y_DESCRIPTION,
        TARGET_1_SPEED_DESCRIPTION,
        TARGET_1_RESOLUTION_DESCRIPTION,
        
        TARGET_2_X_DESCRIPTION,
        TARGET_2_Y_DESCRIPTION,
        TARGET_2_SPEED_DESCRIPTION,
        TARGET_2_RESOLUTION_DESCRIPTION,

        TARGET_3_X_DESCRIPTION,
        TARGET_3_Y_DESCRIPTION,
        TARGET_3_SPEED_DESCRIPTION,
        TARGET_3_RESOLUTION_DESCRIPTION,
        
        TARGET_1_DISTANCE_DESCRIPTION,
        TARGET_2_DISTANCE_DESCRIPTION,
        TARGET_3_DISTANCE_DESCRIPTION,

        TARGET_1_ANGLE_DESCRIPTION,
        TARGET_2_ANGLE_DESCRIPTION,
        TARGET_3_ANGLE_DESCRIPTION        
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
        LD2450BLESensor(
            data.coordinator,
            data.device,
            entry.title,
            description,
        )
        for description in SENSOR_DESCRIPTIONS
    )


class LD2450BLESensor(CoordinatorEntity[LD2450BLECoordinator], SensorEntity):
    """Generic sensor for LD2450BLE."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LD2450BLECoordinator,
        device: LD2450BLE,
        name: str,
        description: SensorEntityDescription,
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        match self._key:
            case "target_1_distance":
                self._attr_native_value = int(math.hypot(getattr(self._device, "target_1_x"), getattr(self._device, "target_1_y")))
            case "target_2_distance":
                self._attr_native_value = int(math.hypot(getattr(self._device, "target_2_x"), getattr(self._device, "target_2_y")))
            case "target_3_distance":
                self._attr_native_value = int(math.hypot(getattr(self._device, "target_3_x"), getattr(self._device, "target_3_y")))
            case "target_1_angle":
                self._attr_native_value = int(math.degrees(math.atan2(getattr(self._device, "target_1_x"), getattr(self._device, "target_1_y"))))
            case "target_2_angle":
                self._attr_native_value = int(math.degrees(math.atan2(getattr(self._device, "target_2_x"), getattr(self._device, "target_2_y"))))
            case "target_3_angle":
                self._attr_native_value = int(math.degrees(math.atan2(getattr(self._device, "target_3_x"), getattr(self._device, "target_3_y"))))
            case _:
                #if not in calculated sensors, just get the value from sensor's state
                self._attr_native_value = getattr(self._device, self._key)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Unavailable if coordinator isn't connected."""
        return self._coordinator.connected and super().available