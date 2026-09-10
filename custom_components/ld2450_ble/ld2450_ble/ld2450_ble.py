from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from contextlib import suppress

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakError,
    establish_connection,
)

#CONSTANTS FROM CONST FILE
from .const import (
    CHARACTERISTIC_NOTIFY,
    CHARACTERISTIC_WRITE,
    CMD_ENABLE_CONFIG,
    ACK_ENABLE_CONFIG_REGEX,
    CMD_DISABLE_CONFIG,
    ACK_DISABLE_CONFIG_REGEX,
    CMD_QUERY_TARGET_MODE,
    ACK_TARGET_MODE_REGEX,
    CMD_ENABLE_SINGLE_TARGET,
    ACK_SINGLE_TARGET_REGEX,
    CMD_ENABLE_MULTI_TARGET,
    ACK_MULTI_TARGET_REGEX,
    CMD_GET_FW_VER,
    ACK_FW_VER_REGEX,
    CMD_GET_MAC,
    ACK_MAC_REGEX,
    CMD_ZONE,
    ACK_ZONE_REGEX,
    CMD_SET_ZONE_PRE,
    CMD_SET_ZONE_POST,
    ACK_SET_ZONE_REGEX,
    CMD_REBOOT,
    ACK_REBOOT_REGEX,
    CMD_FACTORY_RESET,
    ACK_FACTORY_RESET_REGEX,
    frame_regex
    )
from .models import LD2450BLEState, LD2450BLEConfig

# Write-without-response only queues data on an ESPHome proxy. Give the
# controller time to transmit before submitting the next command.
COMMAND_INTERVAL = 0.1
COMMAND_ATTEMPTS = 3
RECONNECT_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0
REBOOT_DELAY = 5.0
CONNECTION_ERRORS = (BleakError, OSError, EOFError)

__version__ = "0.0.0"

_LOGGER = logging.getLogger(__name__)


class LD2450BLE:
    def __init__(
        self,
        ble_device: BLEDevice,
        advertisement_data: AdvertisementData | None = None,
    ) -> None:
        """Init the LD2450BLE."""
        self._ble_device = ble_device
        self._advertisement_data = advertisement_data
        self._operation_lock = asyncio.Lock()
        self._state = LD2450BLEState()
        self._config = LD2450BLEConfig()
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._expected_disconnect = False
        self._stopped = False
        self._reconnect_enabled = False
        self._reconnect_task: asyncio.Task[None] | None = None
        self._initialized_client: BleakClientWithServiceCache | None = None
        self.loop = asyncio.get_running_loop()
        self._callbacks: list[Callable[[LD2450BLEState, LD2450BLEConfig], None]] = []
        self._disconnected_callbacks: list[Callable[[], None]] = []
        self._buf = b""
        self._received_data = False

    def set_ble_device_and_advertisement_data(
        self, ble_device: BLEDevice, advertisement_data: AdvertisementData
    ) -> None:
        """Set the ble device."""
        self._ble_device = ble_device
        self._advertisement_data = advertisement_data

    @property
    def address(self) -> str:
        """Return the address."""
        return self._ble_device.address

    @property
    def name(self) -> str:
        """Get the name of the device."""
        return self._ble_device.name or self._ble_device.address

    @property
    def rssi(self) -> int | None:
        """Get the rssi of the device."""
        if self._advertisement_data:
            return self._advertisement_data.rssi
        return None

    @property
    def state(self) -> LD2450BLEState:
        """Return the state."""
        return self._state
    @property
    def config(self) -> LD2450BLEConfig:
        """Return the config."""
        return self._config

    def get_target_counts(self, zone: int | None = None) -> dict[str, int]:
        """Count reported targets using ESPHome's LD2450 counting rules.

        Zone bounds are strict and are not reordered. Zone mode is applied by
        the radar to its reports, not by this calculation. Like ESPHome, empty
        slots are at (0, 0) and still; keep the zone's lower Y bound at least 0
        so they cannot fall strictly inside the rectangle.
        """
        state = self._state
        config = self._config
        if zone is not None:
            if zone not in (1, 2, 3):
                raise ValueError("Zone must be 1, 2, or 3")
            x1 = getattr(config, f"zone_{zone}_x1")
            y1 = getattr(config, f"zone_{zone}_y1")
            x2 = getattr(config, f"zone_{zone}_x2")
            y2 = getattr(config, f"zone_{zone}_y2")

        total = moving = 0
        for target in (1, 2, 3):
            x = getattr(state, f"target_{target}_x")
            y = getattr(state, f"target_{target}_y")
            speed = getattr(state, f"target_{target}_speed")
            present = x != 0 or y != 0
            if zone is None:
                total += int(present)
                moving += int(speed != 0)
            elif x1 < x < x2 and y1 < y < y2:
                total += 1
                moving += int(present and speed != 0)

        return {
            "target_count": total,
            "moving_target_count": moving,
            "still_target_count": total - moving,
        }

    @property
    def target_1_x(self) -> int:
        return self._state.target_1_x
    @property
    def target_1_y(self) -> int:
        return self._state.target_1_y
    @property
    def target_1_speed(self) -> int:
        return self._state.target_1_speed
    @property
    def target_1_resolution(self) -> int:
        return self._state.target_1_resolution

    @property
    def target_2_x(self) -> int:
        return self._state.target_2_x
    @property
    def target_2_y(self) -> int:
        return self._state.target_2_y
    @property
    def target_2_speed(self) -> int:
        return self._state.target_2_speed
    @property
    def target_2_resolution(self) -> int:
        return self._state.target_2_resolution

    @property
    def target_3_x(self) -> int:
        return self._state.target_3_x
    @property
    def target_3_y(self) -> int:
        return self._state.target_3_y
    @property
    def target_3_speed(self) -> int:
        return self._state.target_3_speed
    @property
    def target_3_resolution(self) -> int:
        return self._state.target_3_resolution

    @property
    def target_mode(self) -> int:
        return self._config.target_mode

    @property
    def fw_ver(self) -> str:
        return self._config.fw_ver

    @property
    def mac_addr(self) -> str:
        return self._config.mac_addr

    @property
    def zone_type(self) -> int:
        return self._config.zone_type
    @property
    def zone_1_x1(self) -> int:
        return self._config.zone_1_x1
    @property
    def zone_1_y1(self) -> int:
        return self._config.zone_1_y1
    @property
    def zone_1_x2(self) -> int:
        return self._config.zone_1_x2
    @property
    def zone_1_y2(self) -> int:
        return self._config.zone_1_y2
    @property
    def zone_2_x1(self) -> int:
        return self._config.zone_2_x1
    @property
    def zone_2_y1(self) -> int:
        return self._config.zone_2_y1
    @property
    def zone_2_x2(self) -> int:
        return self._config.zone_2_x2
    @property
    def zone_2_y2(self) -> int:
        return self._config.zone_2_y2
    @property
    def zone_3_x1(self) -> int:
        return self._config.zone_3_x1
    @property
    def zone_3_y1(self) -> int:
        return self._config.zone_3_y1
    @property
    def zone_3_x2(self) -> int:
        return self._config.zone_3_x2
    @property
    def zone_3_y2(self) -> int:
        return self._config.zone_3_y2

    async def stop(self) -> None:
        """Stop recovery and release the Bluetooth connection."""
        _LOGGER.debug("%s: Stop", self.name)
        self._stopped = True
        await self._cancel_reconnect()
        async with self._operation_lock:
            await self._execute_disconnect()

    async def _cancel_reconnect(self) -> None:
        task = self._reconnect_task
        self._reconnect_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def _fire_callbacks(self) -> None:
        """Fire the callbacks."""
        for callback in self._callbacks:
            callback(self._state)
            callback(self._config)

    def register_callback(
        self, callback: Callable[[LD2450BLEState, LD2450BLEConfig], None]
    ) -> Callable[[], None]:
        """Register a callback to be called when the state changes."""

        def unregister_callback() -> None:
            self._callbacks.remove(callback)

        self._callbacks.append(callback)
        return unregister_callback

    def _fire_disconnected_callbacks(self) -> None:
        """Fire the callbacks."""
        for callback in self._disconnected_callbacks:
            callback()

    def register_disconnected_callback(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Register a callback to be called when the state changes."""

        def unregister_callback() -> None:
            self._disconnected_callbacks.remove(callback)

        self._disconnected_callbacks.append(callback)
        return unregister_callback

    async def initialise(self) -> None:
        """Subscribe and fetch startup settings as one serialized operation."""
        async with self._operation_lock:
            if self._stopped:
                raise BleakError("LD2450 device has been stopped")
            if (
                self._client is not None
                and self._client.is_connected
                and self._initialized_client is self._client
            ):
                return
            await self._send_command_locked(
                [
                    CMD_ENABLE_CONFIG, CMD_QUERY_TARGET_MODE, CMD_DISABLE_CONFIG,
                    CMD_ENABLE_CONFIG, CMD_GET_FW_VER, CMD_DISABLE_CONFIG,
                    CMD_ENABLE_CONFIG, CMD_GET_MAC, CMD_DISABLE_CONFIG,
                    CMD_ENABLE_CONFIG, CMD_ZONE, CMD_DISABLE_CONFIG,
                ]
            )
            self._initialized_client = self._client
            self._reconnect_enabled = True
            _LOGGER.debug("%s: Startup commands sent; awaiting sensor updates", self.name)

    async def _ensure_connected(self) -> None:
        """Establish a connection and restore notifications before any writes."""
        async with self._connect_lock:
            if self._stopped:
                raise BleakError("LD2450 device has been stopped")
            if self._client is not None and self._client.is_connected:
                return
            _LOGGER.debug("%s: Connecting; RSSI: %s", self.name, self.rssi)
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self.name,
                self._disconnected,
                use_services_cache=True,
                ble_device_callback=lambda: self._ble_device,
            )
            self._client = client
            self._expected_disconnect = False
            self._initialized_client = None
            self._buf = b""
            self._received_data = False
            if self._stopped or not client.is_connected:
                raise BleakError("LD2450 connection closed during setup")
            _LOGGER.debug("%s: Connected; subscribing to notifications", self.name)
            await client.start_notify(CHARACTERISTIC_NOTIFY, self._notification_handler)

    def _schedule_reconnect(self, delay: float = RECONNECT_DELAY) -> None:
        """Keep one recovery task per device, only after successful setup."""
        if self._stopped or not self._reconnect_enabled:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = self.loop.create_task(self._reconnect(delay))

    async def _reconnect(self, delay: float = RECONNECT_DELAY) -> None:
        """Retry connection and initialization with bounded backoff."""
        try:
            while not self._stopped:
                _LOGGER.debug("%s: Reconnecting in %.1fs", self.name, delay)
                await asyncio.sleep(delay)
                try:
                    await self.initialise()
                except CONNECTION_ERRORS as ex:
                    if self._stopped:
                        return
                    _LOGGER.warning("%s: Reinitialization failed: %s", self.name, ex)
                    delay = min(delay * 2, RECONNECT_MAX_DELAY)
                else:
                    _LOGGER.info("%s: BLE connection restored; startup commands sent", self.name)
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("%s: Unexpected error during Bluetooth recovery", self.name)
        finally:
            if self._reconnect_task is asyncio.current_task():
                self._reconnect_task = None

    def intify(self, state: bytes) -> int:
        return int.from_bytes(state, byteorder="little")

    async def _notification_handler(self, _sender: int, data: bytearray) -> None:
        """Handle notification responses."""
        _LOGGER.debug("%s: Notification received: %s", self.name, data.hex())
        self._buf += data

        msg = re.search(ACK_ENABLE_CONFIG_REGEX, self._buf)
        if msg:
            #ACK to enable config. Check if command is good
            if ( int.from_bytes(msg.group("ACK_ENABLE_CONFIG_RESULT"),"little") > 0 ):
                _LOGGER.error("Enable config failed")
            else:
                _LOGGER.debug("Enable config success")
            msg = None

        msg = re.search(ACK_DISABLE_CONFIG_REGEX, self._buf)
        if msg:
            #ACK to disable config. Check if command is good
            if ( int.from_bytes(msg.group("ACK_DISABLE_CONFIG_RESULT"),"little") > 0 ):
                _LOGGER.error("Disable config failed")
            else:
                _LOGGER.debug("Disable config success")
            msg = None
        
        msg = re.search(ACK_REBOOT_REGEX, self._buf)
        if msg:
            #ACK to reboot. Check if command is good
            if ( int.from_bytes(msg.group("ACK_REBOOT_RESULT"),"little") > 0 ):
                _LOGGER.error("Reboot failed")
            else:
                _LOGGER.debug("Reboot success")
            msg = None
        
        msg = re.search(ACK_FACTORY_RESET_REGEX, self._buf)
        if msg:
            #ACK to factory reset. Check if command is good
            if ( int.from_bytes(msg.group("ACK_FACTORY_RESET_RESULT"),"little") > 0 ):
                _LOGGER.error("Factory reset failed")
            else:
                _LOGGER.debug("Factory reset success")
            msg = None
        
        msg = re.search(ACK_TARGET_MODE_REGEX, self._buf)
        if msg:
            #ACK to target mode. Check if command is good
            if ( int.from_bytes(msg.group("ACK_TARGET_MODE_RESULT"),"little") > 0 ):
                _LOGGER.error("Target mode query failed")
            else:
                _LOGGER.debug("Target mode query success")
                target_mode = msg.group("ACK_TARGET_MODE_VAL")[0]
                self._config = LD2450BLEConfig(
                    target_mode = target_mode,
                    fw_ver = self._config.fw_ver,
                    mac_addr = self._config.mac_addr,
                    zone_type = self._config.zone_type,
                    zone_1_x1 = self._config.zone_1_x1,
                    zone_1_y1 = self._config.zone_1_y1,
                    zone_1_x2 = self._config.zone_1_x2,
                    zone_1_y2 = self._config.zone_1_y2,
                    zone_2_x1 = self._config.zone_2_x1,
                    zone_2_y1 = self._config.zone_2_y1,
                    zone_2_x2 = self._config.zone_2_x2,
                    zone_2_y2 = self._config.zone_2_y2,
                    zone_3_x1 = self._config.zone_3_x1,
                    zone_3_y1 = self._config.zone_3_y1,
                    zone_3_x2 = self._config.zone_3_x2,
                    zone_3_y2 = self._config.zone_3_y2,
                )
            msg = None
        
        msg = re.search(ACK_FW_VER_REGEX, self._buf)
        if msg:
            #ACK to fw ver. Check if command is good
            if ( int.from_bytes(msg.group("ACK_FW_VER_RESULT"),"little") > 0 ):
                _LOGGER.error("FW ver query failed")
            else:
                _LOGGER.debug("FW ver query success")
                fw_ver = format(msg.group("ACK_FW_VER_VAL")[1], '1X') + "." + format(msg.group("ACK_FW_VER_VAL")[0], '02X') + "." + format(msg.group("ACK_FW_VER_VAL")[5], '02X') + format(msg.group("ACK_FW_VER_VAL")[4], '02X') + format(msg.group("ACK_FW_VER_VAL")[3], '02X') + format(msg.group("ACK_FW_VER_VAL")[2], '02X')
                self._config = LD2450BLEConfig(
                    target_mode = self._config.target_mode,
                    fw_ver = fw_ver,
                    mac_addr = self._config.mac_addr,
                    zone_type = self._config.zone_type,
                    zone_1_x1 = self._config.zone_1_x1,
                    zone_1_y1 = self._config.zone_1_y1,
                    zone_1_x2 = self._config.zone_1_x2,
                    zone_1_y2 = self._config.zone_1_y2,
                    zone_2_x1 = self._config.zone_2_x1,
                    zone_2_y1 = self._config.zone_2_y1,
                    zone_2_x2 = self._config.zone_2_x2,
                    zone_2_y2 = self._config.zone_2_y2,
                    zone_3_x1 = self._config.zone_3_x1,
                    zone_3_y1 = self._config.zone_3_y1,
                    zone_3_x2 = self._config.zone_3_x2,
                    zone_3_y2 = self._config.zone_3_y2,
                )
            msg = None
 
        msg = re.search(ACK_MAC_REGEX, self._buf)
        if msg:
            #ACK to mac. Check if command is good
            if ( int.from_bytes(msg.group("ACK_MAC_RESULT"),"little") > 0 ):
                _LOGGER.error("MAC query failed")
            else:
                _LOGGER.debug("MAC query success")
                mac_addr = format(msg.group("ACK_MAC_VAL")[0], '02X') + ":" + format(msg.group("ACK_MAC_VAL")[1], '02X') + ":" + format(msg.group("ACK_MAC_VAL")[2], '02X') + ":" + format(msg.group("ACK_MAC_VAL")[3], '02X') + ":" + format(msg.group("ACK_MAC_VAL")[4], '02X') + ":" + format(msg.group("ACK_MAC_VAL")[5], '02X')
                self._config = LD2450BLEConfig(
                    target_mode = self._config.target_mode,
                    fw_ver = self._config.fw_ver,
                    mac_addr = mac_addr,
                    zone_type = self._config.zone_type,
                    zone_1_x1 = self._config.zone_1_x1,
                    zone_1_y1 = self._config.zone_1_y1,
                    zone_1_x2 = self._config.zone_1_x2,
                    zone_1_y2 = self._config.zone_1_y2,
                    zone_2_x1 = self._config.zone_2_x1,
                    zone_2_y1 = self._config.zone_2_y1,
                    zone_2_x2 = self._config.zone_2_x2,
                    zone_2_y2 = self._config.zone_2_y2,
                    zone_3_x1 = self._config.zone_3_x1,
                    zone_3_y1 = self._config.zone_3_y1,
                    zone_3_x2 = self._config.zone_3_x2,
                    zone_3_y2 = self._config.zone_3_y2,
                )
            msg = None

        msg = re.search(ACK_MULTI_TARGET_REGEX, self._buf)
        if msg:
            #SET_MULTI_TARGET. Check if command is good
            if ( int.from_bytes(msg.group("ACK_MULTI_TARGET_RESULT"),"little") > 0 ):
                _LOGGER.error("SET_MULTI_TARGET query failed")
            else:
                _LOGGER.debug("SET_MULTI_TARGET query success")
                #calling update
                await self._get_target_mode()
            msg = None
           
        msg = re.search(ACK_SINGLE_TARGET_REGEX, self._buf)
        if msg:
            #SET_SINGLE_TARGET. Check if command is good
            if ( int.from_bytes(msg.group("ACK_SINGLE_TARGET_RESULT"),"little") > 0 ):
                _LOGGER.error("SET_SINGLE_TARGET query failed")
            else:
                _LOGGER.debug("SET_SINGLE_TARGET query success")
                #calling update
                await self._get_target_mode()
            msg = None
            
        msg = re.search(ACK_SET_ZONE_REGEX, self._buf)
        if msg:
            #SET_ZONE. Check if command is good
            if ( int.from_bytes(msg.group("ACK_SET_ZONE_RESULT"),"little") > 0 ):
                _LOGGER.error("SET_ZONE query failed")
            else:
                _LOGGER.debug("SET_ZONE query success")
                #calling update
                await self._get_zone()
            msg = None
            
        msg = re.search(ACK_ZONE_REGEX, self._buf)
        if msg:
            #ACK to zone query. Check if command is good
            if ( int.from_bytes(msg.group("ACK_ZONE_RESULT"),"little") > 0 ):
                _LOGGER.error("Zone query failed")
            else:
                _LOGGER.debug("Zone query success")
                zone_type = int.from_bytes(msg.group("ACK_ZONE_TYPE"),"little")

                #first zone
                zone_1_x1 = int.from_bytes(msg.group("ACK_ZONE_ONE")[0:2],"little",signed=True)
                zone_1_y1 = int.from_bytes(msg.group("ACK_ZONE_ONE")[2:4],"little",signed=True)
                zone_1_x2 = int.from_bytes(msg.group("ACK_ZONE_ONE")[4:6],"little",signed=True)
                zone_1_y2 = int.from_bytes(msg.group("ACK_ZONE_ONE")[6:8],"little",signed=True)

                #second zone
                zone_2_x1 = int.from_bytes(msg.group("ACK_ZONE_TWO")[0:2],"little",signed=True)
                zone_2_y1 = int.from_bytes(msg.group("ACK_ZONE_TWO")[2:4],"little",signed=True)
                zone_2_x2 = int.from_bytes(msg.group("ACK_ZONE_TWO")[4:6],"little",signed=True)
                zone_2_y2 = int.from_bytes(msg.group("ACK_ZONE_TWO")[6:8],"little",signed=True)

                #third zone
                zone_3_x1 = int.from_bytes(msg.group("ACK_ZONE_THREE")[0:2],"little",signed=True)
                zone_3_y1 = int.from_bytes(msg.group("ACK_ZONE_THREE")[2:4],"little",signed=True)
                zone_3_x2 = int.from_bytes(msg.group("ACK_ZONE_THREE")[4:6],"little",signed=True)
                zone_3_y2 = int.from_bytes(msg.group("ACK_ZONE_THREE")[6:8],"little",signed=True)

                self._config = LD2450BLEConfig(
                    target_mode = self._config.target_mode,
                    fw_ver = self._config.fw_ver,
                    mac_addr = self._config.mac_addr,
                    zone_type = zone_type,
                    zone_1_x1 = zone_1_x1,
                    zone_1_y1 = zone_1_y1,
                    zone_1_x2 = zone_1_x2,
                    zone_1_y2 = zone_1_y2,
                    zone_2_x1 = zone_2_x1,
                    zone_2_y1 = zone_2_y1,
                    zone_2_x2 = zone_2_x2,
                    zone_2_y2 = zone_2_y2,
                    zone_3_x1 = zone_3_x1,
                    zone_3_y1 = zone_3_y1,
                    zone_3_x2 = zone_3_x2,
                    zone_3_y2 = zone_3_y2,
                )
                self._fire_callbacks()
            msg = None            

        msg = re.search(frame_regex, self._buf)
        if msg:
            #sensor data received
            self._buf = self._buf[msg.end() :]  # noqa: E203

            target_1_x = int.from_bytes(msg.group("target_1_x"),"little")
            if target_1_x >= 2**15:
                target_1_x = target_1_x - 2**15
            else:
                target_1_x = - target_1_x
            target_1_y = int.from_bytes(msg.group("target_1_y"),"little")
            if target_1_y >= 2**15:
                target_1_y = target_1_y - 2**15
            else:
                target_1_y = - target_1_y
            target_1_speed = int.from_bytes(msg.group("target_1_s"),"little")
            if target_1_speed >= 2**15:
                target_1_speed = target_1_speed - 2**15
            else:
                target_1_speed = - target_1_speed
            target_1_resolution = int.from_bytes(msg.group("target_1_r"),"little")

            target_2_x = int.from_bytes(msg.group("target_2_x"),"little")
            if target_2_x >= 2**15:
                target_2_x = target_2_x - 2**15
            else:
                target_2_x = - target_2_x
            target_2_y = int.from_bytes(msg.group("target_2_y"),"little")
            if target_2_y >= 2**15:
                target_2_y = target_2_y - 2**15
            else:
                target_2_y = - target_2_y
            target_2_speed = int.from_bytes(msg.group("target_2_s"),"little")
            if target_2_speed >= 2**15:
                target_2_speed = target_2_speed - 2**15
            else:
                target_2_speed = - target_2_speed
            target_2_resolution = int.from_bytes(msg.group("target_2_r"),"little")

            target_3_x = int.from_bytes(msg.group("target_3_x"),"little")
            if target_3_x >= 2**15:
                target_3_x = target_3_x - 2**15
            else:
                target_3_x = - target_3_x
            target_3_y = int.from_bytes(msg.group("target_3_y"),"little")
            if target_3_y >= 2**15:
                target_3_y = target_3_y - 2**15
            else:
                target_3_y = - target_3_y
            target_3_speed = int.from_bytes(msg.group("target_3_s"),"little")
            if target_3_speed >= 2**15:
                target_3_speed = target_3_speed - 2**15
            else:
                target_3_speed = - target_3_speed
            target_3_resolution = int.from_bytes(msg.group("target_3_r"),"little")

            self._state = LD2450BLEState(
                target_1_x = target_1_x,
                target_1_y = target_1_y,
                target_1_speed = target_1_speed,
                target_1_resolution = target_1_resolution,

                target_2_x = target_2_x,
                target_2_y = target_2_y,
                target_2_speed = target_2_speed,
                target_2_resolution = target_2_resolution,

                target_3_x = target_3_x,
                target_3_y = target_3_y,
                target_3_speed = target_3_speed,
                target_3_resolution = target_3_resolution,
            )
            msg = None            
            if not self._received_data:
                self._received_data = True
                _LOGGER.info("%s: Receiving radar target updates", self.name)
            self._fire_callbacks()

        _LOGGER.debug(
            "%s: Notification received; RSSI: %s: %s %s",
            self.name,
            self.rssi,
            data.hex(),
            self._state,
        )

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Ignore old sessions and recover an unexpected disconnection."""
        if client is not self._client:
            return
        self._client = None
        self._initialized_client = None
        self._buf = b""
        self._fire_disconnected_callbacks()
        if self._stopped or self._expected_disconnect:
            return
        _LOGGER.warning(
            "%s: Device unexpectedly disconnected; RSSI: %s", self.name, self.rssi
        )
        self._schedule_reconnect()

    async def _execute_disconnect(self) -> None:
        """Clear local state and attempt to close even if stop_notify fails."""
        async with self._connect_lock:
            client = self._client
            self._expected_disconnect = True
            self._client = None
            self._initialized_client = None
            self._buf = b""
            if client is None:
                return
            self._fire_disconnected_callbacks()
            if client.is_connected:
                try:
                    await client.stop_notify(CHARACTERISTIC_NOTIFY)
                except CONNECTION_ERRORS as ex:
                    _LOGGER.debug("%s: Could not stop notifications: %s", self.name, ex)
                finally:
                    try:
                        await client.disconnect()
                    except CONNECTION_ERRORS as ex:
                        _LOGGER.warning("%s: Could not close BLE connection: %s", self.name, ex)

    async def _send_command_locked(
        self,
        commands: list[bytes],
        attempts: int = COMMAND_ATTEMPTS,
        *,
        expect_disconnect: bool = False,
    ) -> None:
        """Reconnect and retry the whole transaction, never a detached write."""
        for attempt in range(1, attempts + 1):
            if self._stopped:
                raise BleakError("LD2450 device has been stopped")
            try:
                await self._ensure_connected()
                await self._execute_command_locked(
                    commands, expect_disconnect=expect_disconnect
                )
                return
            except asyncio.CancelledError:
                await self._execute_disconnect()
                raise
            except CONNECTION_ERRORS as ex:
                _LOGGER.warning(
                    "%s: BLE command attempt %d/%d failed: %s",
                    self.name, attempt, attempts, ex,
                )
                await self._execute_disconnect()
                if self._stopped or attempt == attempts:
                    if not expect_disconnect:
                        self._schedule_reconnect()
                    raise
                await asyncio.sleep(
                    min(RECONNECT_DELAY * 2 ** (attempt - 1), RECONNECT_MAX_DELAY)
                )

    async def _send_command(self, commands: list[bytes] | bytes) -> None:
        """Keep configuration entry, operation, and exit together."""
        if isinstance(commands, bytes):
            commands = [commands]
        async with self._operation_lock:
            await self._send_command_locked(commands)

    async def _execute_command_locked(
        self, commands: list[bytes], *, expect_disconnect: bool = False
    ) -> None:
        """Pace writes without changing the radar's write-without-response mode."""
        client = self._client
        for index, command in enumerate(commands):
            if (
                self._stopped
                or client is None
                or client is not self._client
                or not client.is_connected
            ):
                raise BleakError("LD2450 disconnected during command transaction")
            last_command = index == len(commands) - 1
            if expect_disconnect and last_command:
                self._expected_disconnect = True
            await client.write_gatt_char(CHARACTERISTIC_WRITE, command, response=False)
            await asyncio.sleep(COMMAND_INTERVAL)
            if not (expect_disconnect and last_command):
                if client is not self._client or not client.is_connected:
                    raise BleakError("LD2450 disconnected during command transaction")

    # Sensor commands are complete configuration transactions so concurrent
    # entity actions and retries cannot interleave or lose config mode.
    async def _get_target_mode(self) -> None:
        await self._send_command([CMD_ENABLE_CONFIG, CMD_QUERY_TARGET_MODE, CMD_DISABLE_CONFIG])

    async def _get_fw_ver(self) -> None:
        await self._send_command([CMD_ENABLE_CONFIG, CMD_GET_FW_VER, CMD_DISABLE_CONFIG])

    async def _get_mac(self) -> None:
        await self._send_command([CMD_ENABLE_CONFIG, CMD_GET_MAC, CMD_DISABLE_CONFIG])

    async def _get_zone(self) -> None:
        await self._send_command([CMD_ENABLE_CONFIG, CMD_ZONE, CMD_DISABLE_CONFIG])

    async def _reboot(self) -> None:
        await self._send_restart_command(CMD_REBOOT)

    async def _factory_reset(self) -> None:
        await self._send_restart_command(CMD_FACTORY_RESET)

    async def _send_restart_command(self, command: bytes) -> None:
        """Do not replay a restart or send config-exit to a rebooting radar."""
        await self._cancel_reconnect()
        async with self._operation_lock:
            try:
                await self._send_command_locked(
                    [CMD_ENABLE_CONFIG, command], attempts=1, expect_disconnect=True
                )
            finally:
                await self._execute_disconnect()
                self._schedule_reconnect(REBOOT_DELAY)

    async def _set_target_mode(self, mode: int) -> None:
        if mode in (1, 2):
            command = CMD_ENABLE_SINGLE_TARGET if mode == 1 else CMD_ENABLE_MULTI_TARGET
            await self._send_command([CMD_ENABLE_CONFIG, command, CMD_DISABLE_CONFIG])

    async def _set_zone(self, zone_type: int, 
        zone_1_x1: int | 0, 
        zone_1_y1: int | 0, 
        zone_1_x2: int | 0, 
        zone_1_y2: int | 0, 
        zone_2_x1: int | 0, 
        zone_2_y1: int | 0, 
        zone_2_x2: int | 0, 
        zone_2_y2: int | 0, 
        zone_3_x1: int | 0, 
        zone_3_y1: int | 0, 
        zone_3_x2: int | 0, 
        zone_3_y2: int | 0) -> None:
        """Execute command."""
        await self._send_command([CMD_ENABLE_CONFIG, CMD_SET_ZONE_PRE +
            zone_type.to_bytes(2,"little") + 
            self._num2hex(zone_1_x1) + 
            self._num2hex(zone_1_y1) + 
            self._num2hex(zone_1_x2) + 
            self._num2hex(zone_1_y2) +  
            self._num2hex(zone_2_x1) + 
            self._num2hex(zone_2_y1) + 
            self._num2hex(zone_2_x2) +  
            self._num2hex(zone_2_y2) + 
            self._num2hex(zone_3_x1) + 
            self._num2hex(zone_3_y1) + 
            self._num2hex(zone_3_x2) + 
            self._num2hex(zone_3_y2) +
            CMD_SET_ZONE_POST, CMD_DISABLE_CONFIG])
            
    def _num2hex(self, num: int) -> bytes:
        return num.to_bytes(2, byteorder='little', signed=True)
