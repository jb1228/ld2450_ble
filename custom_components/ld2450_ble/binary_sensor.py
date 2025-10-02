"""LD2450 BLE integration sensor platform."""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory

from . import LD2450BLE, LD2450BLECoordinator
from .const import DOMAIN
from .models import LD2450BLEData

_LOGGER = logging.getLogger(__name__)


ANY_PRESENCE = BinarySensorEntityDescription(
    key="any_presence",
    translation_key="any_presence",
    device_class=BinarySensorDeviceClass.OCCUPANCY,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    icon="mdi:target-account",
)
TARGET_1 = BinarySensorEntityDescription(
    key="target_1",
    translation_key="target_1",
    device_class=BinarySensorDeviceClass.OCCUPANCY,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    icon="mdi:target-account",
)
TARGET_2 = BinarySensorEntityDescription(
    key="target_2",
    translation_key="target_2",
    device_class=BinarySensorDeviceClass.OCCUPANCY,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    icon="mdi:target-account",
)
TARGET_3 = BinarySensorEntityDescription(
    key="target_3",
    translation_key="target_3",
    device_class=BinarySensorDeviceClass.OCCUPANCY,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    icon="mdi:target-account",
)

TARGET_1_MOVING = BinarySensorEntityDescription(
    key="target_1_moving",
    translation_key="target_1_moving",
    device_class=BinarySensorDeviceClass.MOVING,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
)
TARGET_2_MOVING = BinarySensorEntityDescription(
    key="target_2_moving",
    translation_key="target_2_moving",
    device_class=BinarySensorDeviceClass.MOVING,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
)
TARGET_3_MOVING = BinarySensorEntityDescription(
    key="target_3_moving",
    translation_key="target_3_moving",
    device_class=BinarySensorDeviceClass.MOVING,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
)

MOVING_TARGET = BinarySensorEntityDescription(
    key="moving_target",
    translation_key="moving_target",
    device_class=BinarySensorDeviceClass.MOVING,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    icon="mdi:run",
)

STILL_TARGET = BinarySensorEntityDescription(
    key="still_target",
    translation_key="still_target",
    device_class=BinarySensorDeviceClass.OCCUPANCY,
    entity_registry_enabled_default=True,
    entity_registry_visible_default=True,
    icon="mdi:meditation",
)

SENSOR_DESCRIPTIONS = (
    [
        ANY_PRESENCE,
        MOVING_TARGET,
        STILL_TARGET,
        TARGET_1,
        TARGET_2,
        TARGET_3,
        
        TARGET_1_MOVING,
        TARGET_2_MOVING,
        TARGET_3_MOVING,
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
        LD2450BLEBinary(
            data.coordinator,
            data.device,
            entry.title,
            description,
        )
        for description in SENSOR_DESCRIPTIONS
    )


class LD2450BLEBinary(CoordinatorEntity[LD2450BLECoordinator], BinarySensorEntity):
    """Generic sensor for LD2450BLE."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LD2450BLECoordinator,
        device: LD2450BLE,
        name: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._device = device
        self._key = description.key
        self.entity_description = description
        self._attr_unique_id = f"{device.name}_{self._key}"
        self._attr_device_info = DeviceInfo(
            name=name,
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
            manufacturer="HiLink",
            model="LD2450",
            sw_version=getattr(self._device, "fw_ver"),
        )
        self._attr_native_value = False

    #@property
    #def name(self):
    #    """Return name."""
    #    return self._name

    @property
    def unique_id(self):
        """Return unique id."""
        return self._attr_unique_id
        
    #@property
    #def entity_category(self):
    #    """Return the entity category of the switch."""
    #    return EntityCategory.SENSOR
        
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Helper functions to check target states
        def has_target(target_num):
            return getattr(self._device, f"target_{target_num}_y") > 0
        
        def is_moving(target_num):
            return abs(getattr(self._device, f"target_{target_num}_speed")) > 0
        
        match self._key:
            case "moving_target":
                # Any target is detected AND moving
                moving = any(has_target(i) and is_moving(i) for i in [1, 2, 3])
                self._attr_native_value = moving
                
            case "still_target":
                # Any target is detected BUT not moving
                still = any(has_target(i) and not is_moving(i) for i in [1, 2, 3])
                self._attr_native_value = still
                
            case "any_presence":
                # Any target detected (moving OR still)
                present = any(has_target(i) for i in [1, 2, 3])
                self._attr_native_value = present
                
            case "target_1":
                self._attr_native_value = has_target(1)
            case "target_2":
                self._attr_native_value = has_target(2)
            case "target_3":
                self._attr_native_value = has_target(3)
                
            case "target_1_moving":
                self._attr_native_value = has_target(1) and is_moving(1)
            case "target_2_moving":
                self._attr_native_value = has_target(2) and is_moving(2)
            case "target_3_moving":
                self._attr_native_value = has_target(3) and is_moving(3)
                
            case _:
                _LOGGER.error("Wrong KEY for binary sensor: %s", self._key)

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Unavailable if coordinator isn't connected."""
        return self._coordinator.connected and super().available

    @property
    def is_on(self):
        """Return if multitarget mode is on."""
        return self._attr_native_value