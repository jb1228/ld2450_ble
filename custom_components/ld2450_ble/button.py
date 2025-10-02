"""LD2450 BLE integration button platform."""

import logging
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory

from . import LD2450BLE, LD2450BLECoordinator
from .const import DOMAIN
from .models import LD2450BLEData

_LOGGER = logging.getLogger(__name__)


@dataclass
class LD2450BLEButtonDescription(ButtonEntityDescription):
    """Describes LD2450 BLE button entity."""

    press_fn: str | None = None


BUTTON_DESCRIPTIONS: tuple[LD2450BLEButtonDescription, ...] = (
    LD2450BLEButtonDescription(
        key="restart",
        translation_key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_fn="_reboot",
    ),
    LD2450BLEButtonDescription(
        key="factory_reset",
        translation_key="factory_reset",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        entity_registry_visible_default=False,
        icon="mdi:restart-alert",
        press_fn="_factory_reset",
        
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the platform for LD2450BLE."""
    data: LD2450BLEData = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        LD2450BLEButton(data.coordinator, data.device, entry.title, description)
        for description in BUTTON_DESCRIPTIONS
    ]

    async_add_entities(entities)


class LD2450BLEButton(CoordinatorEntity[LD2450BLECoordinator], ButtonEntity):
    """LD2450 BLE button entity."""

    entity_description: LD2450BLEButtonDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LD2450BLECoordinator,
        device: LD2450BLE,
        name: str,
        description: LD2450BLEButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._coordinator = coordinator
        self._device = device
        self._attr_unique_id = f"{device.name}_{description.key}"
        self._attr_device_info = DeviceInfo(
            name=name,
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
            manufacturer="HiLink",
            model="LD2450",
            sw_version=getattr(self._device, "fw_ver"),
        )

    @property
    def available(self) -> bool:
        """Unavailable if coordinator isn't connected."""
        return self._coordinator.connected and super().available

    async def async_press(self) -> None:
        """Handle the button press."""
        press_method = getattr(self._device, self.entity_description.press_fn)
        await press_method()        
       