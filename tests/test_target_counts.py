"""ESPHome count parity using real BLE frames and a minimal HA sensor harness."""

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bleak.backends.device import BLEDevice

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ld2450_ble"
SPEC = importlib.util.spec_from_file_location(
    "ld2450_count_driver", ROOT / "ld2450_ble/__init__.py",
    submodule_search_locations=[str(ROOT / "ld2450_ble")],
)
PACKAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACKAGE
SPEC.loader.exec_module(PACKAGE)
driver = sys.modules[f"{SPEC.name}.ld2450_ble"]


def load_sensor_platform():
    """Load the actual sensor platform without installing Home Assistant."""
    class CoordinatorEntity:
        def __class_getitem__(cls, _item):
            return cls

        def __init__(self, coordinator):
            self.coordinator = coordinator
            self.async_write_ha_state = Mock()

        @property
        def available(self):
            return self.coordinator.last_update_success

    attrs = {
        "homeassistant": {},
        "homeassistant.components": {},
        "homeassistant.components.sensor": {
            "SensorDeviceClass": SimpleNamespace(DISTANCE="distance"),
            "SensorEntity": type("SensorEntity", (), {}),
            "SensorEntityDescription": SimpleNamespace,
            "SensorStateClass": SimpleNamespace(MEASUREMENT="measurement"),
        },
        "homeassistant.config_entries": {"ConfigEntry": SimpleNamespace},
        "homeassistant.const": {
            "EntityCategory": SimpleNamespace(DIAGNOSTIC="diagnostic"),
            "UnitOfLength": SimpleNamespace(MILLIMETERS="mm"),
        },
        "homeassistant.core": {"HomeAssistant": SimpleNamespace, "callback": lambda f: f},
        "homeassistant.helpers": {},
        "homeassistant.helpers.device_registry": {
            "DeviceInfo": dict, "CONNECTION_BLUETOOTH": "bluetooth",
        },
        "homeassistant.helpers.entity_platform": {"AddEntitiesCallback": object},
        "homeassistant.helpers.update_coordinator": {"CoordinatorEntity": CoordinatorEntity},
        "ld2450_sensor_test": {
            "LD2450BLE": driver.LD2450BLE, "LD2450BLECoordinator": SimpleNamespace,
        },
        "ld2450_sensor_test.const": {"DOMAIN": "ld2450_ble"},
        "ld2450_sensor_test.models": {"LD2450BLEData": SimpleNamespace},
    }
    modules = {}
    for name, values in attrs.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        modules[name] = module
    spec = importlib.util.spec_from_file_location("ld2450_sensor_test.sensor", ROOT / "sensor.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


sensor = load_sensor_platform()


def signed_word(value):
    """Radar sign-magnitude encoding, including positive zero (0x8000)."""
    return (abs(value) | (0x8000 if value >= 0 else 0)).to_bytes(2, "little")


def report(*targets):
    payload = b""
    for x, y, speed in (*targets, *((0, 0, 0),) * (3 - len(targets))):
        payload += signed_word(x) + signed_word(y) + signed_word(speed) + b"\x40\x01"
    return bytearray(b"\xaa\xff\x03\x00" + payload + b"\x55\xcc")


class TargetCountTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.device = driver.LD2450BLE(BLEDevice("AA:BB:CC:DD:EE:FF", "Radar", {}))
        self.device._config = driver.LD2450BLEConfig(
            zone_1_x1=-1000, zone_1_y1=0, zone_1_x2=1000, zone_1_y2=2000,
            zone_2_x1=0, zone_2_y1=0, zone_2_x2=2000, zone_2_y2=2000,
            zone_3_x1=-2000, zone_3_y1=0, zone_3_x2=2000, zone_3_y2=3000,
        )

    async def send(self, *targets):
        await self.device._notification_handler(1, report(*targets))

    def assert_counts(self, zone, total, moving, still):
        self.assertEqual(self.device.get_target_counts(zone), {
            "target_count": total, "moving_target_count": moving,
            "still_target_count": still,
        })

    async def test_mixed_targets_and_overlapping_zones(self):
        await self.send((-500, 1000, 0), (500, 1000, 1), (1500, 1000, -1))
        self.assert_counts(None, 3, 2, 1)
        self.assert_counts(1, 2, 1, 1)
        self.assert_counts(2, 2, 2, 0)
        self.assert_counts(3, 3, 2, 1)

    async def test_all_four_edges_and_corners_are_excluded(self):
        for x, y in ((-1000, 1000), (1000, 1000), (0, 0), (0, 2000),
                     (-1000, 0), (1000, 2000)):
            with self.subTest(x=x, y=y):
                await self.send((x, y, 0))
                self.assert_counts(1, 0, 0, 0)
        await self.send((-999, 1, 0), (999, 1999, -1))
        self.assert_counts(1, 2, 1, 1)

    async def test_empty_report_clears_previous_counts(self):
        await self.send((100, 1000, 1), (200, 1000, 0))
        self.assert_counts(1, 2, 1, 1)
        await self.send()
        for zone in (None, 1, 2, 3):
            self.assert_counts(zone, 0, 0, 0)

    async def test_both_zero_encodings_and_both_speed_signs(self):
        for raw_zero in (b"\x00\x00", b"\x00\x80"):
            with self.subTest(raw_zero=raw_zero):
                target = raw_zero * 3 + b"\x00\x00"  # Resolution is unsigned.
                frame = bytearray(b"\xaa\xff\x03\x00" + target * 3 + b"\x55\xcc")
                await self.device._notification_handler(1, frame)
                self.assertEqual(self.device.state, driver.LD2450BLEState())
                self.assert_counts(None, 0, 0, 0)
        await self.send((0, 1000, 0), (-100, 1000, -1), (100, 1000, 1))
        self.assertEqual(self.device.target_1_x, 0)
        self.assertEqual(self.device.target_1_speed, 0)
        self.assertEqual(self.device.target_2_speed, -1)
        self.assertEqual(self.device.target_3_speed, 1)
        self.assert_counts(1, 3, 2, 1)

    async def test_global_presence_uses_distance_not_positive_y(self):
        await self.send((100, 0, 0), (100, -100, -1))
        self.assert_counts(None, 2, 1, 1)
        self.assert_counts(1, 0, 0, 0)

    async def test_zone_mode_does_not_apply_additional_software_filtering(self):
        await self.send((100, 1000, 1))
        for mode in (0, 1, 2):
            with self.subTest(mode=mode):
                self.device._config = replace(self.device.config, zone_type=mode)
                self.assert_counts(1, 1, 1, 0)

    async def test_degenerate_and_reversed_zones_count_zero(self):
        await self.send((100, 1000, 1))
        for changes in ({"zone_1_x2": -1000}, {"zone_1_x1": 1000, "zone_1_x2": -1000},
                        {"zone_1_y2": 0}, {"zone_1_y1": 2000, "zone_1_y2": 0}):
            with self.subTest(changes=changes):
                original = self.device.config
                self.device._config = replace(original, **changes)
                self.assert_counts(1, 0, 0, 0)
                self.device._config = original

    async def test_origin_containing_zone_preserves_esphome_empty_slot_behavior(self):
        self.device._config = replace(self.device.config, zone_1_y1=-1000)
        await self.send()
        self.assert_counts(None, 0, 0, 0)
        self.assert_counts(1, 3, 0, 3)

    async def test_sensor_registration_values_translations_and_availability(self):
        coordinator = SimpleNamespace(connected=True, last_update_success=True)
        data = SimpleNamespace(coordinator=coordinator, device=self.device)
        hass = SimpleNamespace(data={"ld2450_ble": {"entry": data}})
        entities = []
        await sensor.async_setup_entry(
            hass, SimpleNamespace(entry_id="entry", title="Radar"), entities.extend,
        )
        counts = {e._key: e for e in entities if e._key.endswith("target_count")}
        self.assertEqual(len(counts), 12)
        self.assertEqual(len({e._attr_unique_id for e in entities}), len(entities))
        self.device.register_callback(lambda _state: [
            e._handle_coordinator_update() for e in counts.values()
        ])
        await self.send((-500, 1000, 0), (500, 1000, 1), (1500, 1000, -1))
        for prefix, expected in (("", (3, 2, 1)), ("zone_1_", (2, 1, 1)),
                                 ("zone_2_", (2, 2, 0)), ("zone_3_", (3, 2, 1))):
            for suffix, value in zip(("target_count", "moving_target_count", "still_target_count"), expected):
                entity = counts[prefix + suffix]
                self.assertEqual(entity._attr_native_value, value)
                entity.async_write_ha_state.assert_called()
                self.assertTrue(entity.available)
                self.assertTrue(entity.entity_description.entity_registry_enabled_default)
                self.assertTrue(entity.entity_description.entity_registry_visible_default)
        for filename in ("strings.json", "translations/en.json"):
            translations = json.loads((ROOT / filename).read_text())["entity"]["sensor"]
            for key in counts:
                self.assertIn("name", translations[key])
        coordinator.connected = False
        self.assertTrue(all(not e.available for e in counts.values()))
        coordinator.connected = True
        coordinator.last_update_success = False
        self.assertTrue(all(not e.available for e in counts.values()))

    async def test_zone_ack_updates_counts_without_waiting_for_another_report(self):
        await self.send((100, 1000, 0))
        updates = []
        self.device.register_callback(lambda _state: updates.append(self.device.get_target_counts(1)))
        # Successful query response: move zone 1 beyond the current target.
        coordinates = (200, 0, 1000, 2000, 0, 0, 0, 0, 0, 0, 0, 0)
        payload = b"".join(v.to_bytes(2, "little", signed=True) for v in coordinates)
        ack = b"\xfd\xfc\xfb\xfa\x1e\x00\xc1\x01\x00\x00\x00\x00" + payload + b"\x04\x03\x02\x01"
        await self.device._notification_handler(1, bytearray(ack))
        self.assertTrue(updates)
        self.assertEqual(updates[-1]["target_count"], 0)
        self.assert_counts(1, 0, 0, 0)

    async def test_direction_matches_nonzero_speed_count_classification(self):
        entity = sensor.LD2450BLESensor(
            SimpleNamespace(), self.device, "Radar", sensor.TARGET_1_DIRECTION_DESCRIPTION,
        )
        for speed, expected in ((0, "Stationary"), (1, "Moving away"), (-1, "Approaching")):
            await self.send((100, 1000, speed))
            entity._handle_coordinator_update()
            self.assertEqual(entity._attr_native_value, expected)
        await self.send()
        entity._handle_coordinator_update()
        self.assertEqual(entity._attr_native_value, "NA")


if __name__ == "__main__":
    unittest.main()
