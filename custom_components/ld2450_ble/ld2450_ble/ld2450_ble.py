from __future__ import annotations

import asyncio
import logging
import re
import sys
from collections.abc import Callable
from typing import Any, TypeVar

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakDBusError
from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakError,
    BleakNotFoundError,
    establish_connection,
    retry_bluetooth_connection_error,
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
from .exceptions import CharacteristicMissingError
from .models import LD2450BLEState, LD2450BLEConfig

BLEAK_BACKOFF_TIME = 0.25

__version__ = "0.0.0"


WrapFuncType = TypeVar("WrapFuncType", bound=Callable[..., Any])

RETRY_BACKOFF_EXCEPTIONS = (BleakDBusError,)

_LOGGER = logging.getLogger(__name__)

DEFAULT_ATTEMPTS = sys.maxsize


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
        self.loop = asyncio.get_running_loop()
        self._callbacks: list[Callable[[LD2450BLEState, LD2450BLEConfig], None]] = []
        self._disconnected_callbacks: list[Callable[[], None]] = []
        self._buf = b""

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
        """Stop the LD2410BLE."""
        _LOGGER.debug("%s: Stop", self.name)
        await self._execute_disconnect()

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
        await self._ensure_connected()

        _LOGGER.debug("%s: Subscribe to notifications; RSSI: %s", self.name, self.rssi)
        if self._client is not None:
            _LOGGER.debug(self._client)
        
            await self._client.start_notify(
                CHARACTERISTIC_NOTIFY, self._notification_handler
            )
            
            #get startup values from sensor
            await self._get_target_mode()
            await self._get_fw_ver()
            await self._get_mac()
            await self._get_zone()
           
        else:
            _LOGGER.debug("Client is unexpectedly None")

    async def _ensure_connected(self) -> None:
        """Ensure connection to device is established."""
        if self._connect_lock.locked():
            _LOGGER.debug(
                "%s: Connection already in progress, waiting for it to complete; RSSI: %s",
                self.name,
                self.rssi,
            )
        if self._client and self._client.is_connected:
            return
        async with self._connect_lock:
            # Check again while holding the lock
            if self._client and self._client.is_connected:
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
            _LOGGER.debug("%s: Connected; RSSI: %s", self.name, self.rssi)

            self._client = client

    async def _reconnect(self) -> None:
        """Attempt a reconnect"""
        _LOGGER.debug("ensuring connection")
        try:
            await self._ensure_connected()
            _LOGGER.debug("ensured connection - initialising")
            await self.initialise()
        except BleakNotFoundError:
            _LOGGER.debug("failed to ensure connection - backing off")
            await asyncio.sleep(BLEAK_BACKOFF_TIME)
            _LOGGER.debug("reconnecting again")
            asyncio.create_task(self._reconnect())

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
            if target_1_x > 2**15:
                target_1_x = target_1_x - 2**15
            else:
                target_1_x = - target_1_x
            target_1_y = int.from_bytes(msg.group("target_1_y"),"little")
            if target_1_y > 2**15:
                target_1_y = target_1_y - 2**15
            else:
                target_1_y = - target_1_y
            target_1_speed = int.from_bytes(msg.group("target_1_s"),"little")
            if target_1_speed > 2**15:
                target_1_speed = target_1_speed - 2**15
            else:
                target_1_speed = - target_1_speed
            target_1_resolution = int.from_bytes(msg.group("target_1_r"),"little")

            target_2_x = int.from_bytes(msg.group("target_2_x"),"little")
            if target_2_x > 2**15:
                target_2_x = target_2_x - 2**15
            else:
                target_2_x = - target_2_x
            target_2_y = int.from_bytes(msg.group("target_2_y"),"little")
            if target_2_y > 2**15:
                target_2_y = target_2_y - 2**15
            else:
                target_2_y = - target_2_y
            target_2_speed = int.from_bytes(msg.group("target_2_s"),"little")
            if target_2_speed > 2**15:
                target_2_speed = target_2_speed - 2**15
            else:
                target_2_speed = - target_2_speed
            target_2_resolution = int.from_bytes(msg.group("target_2_r"),"little")

            target_3_x = int.from_bytes(msg.group("target_3_x"),"little")
            if target_3_x > 2**15:
                target_3_x = target_3_x - 2**15
            else:
                target_3_x = - target_3_x
            target_3_y = int.from_bytes(msg.group("target_3_y"),"little")
            if target_3_y > 2**15:
                target_3_y = target_3_y - 2**15
            else:
                target_3_y = - target_3_y
            target_3_speed = int.from_bytes(msg.group("target_3_s"),"little")
            if target_3_speed > 2**15:
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
            self._fire_callbacks()

        _LOGGER.debug(
            "%s: Notification received; RSSI: %s: %s %s",
            self.name,
            self.rssi,
            data.hex(),
            self._state,
        )

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Disconnected callback."""
        self._fire_disconnected_callbacks()
        if self._expected_disconnect:
            _LOGGER.debug(
                "%s: Disconnected from device; RSSI: %s", self.name, self.rssi
            )
            return
        _LOGGER.warning(
            "%s: Device unexpectedly disconnected; RSSI: %s",
            self.name,
            self.rssi,
        )
        asyncio.create_task(self._reconnect())

    def _disconnect(self) -> None:
        """Disconnect from device."""
        asyncio.create_task(self._execute_timed_disconnect())

    async def _execute_timed_disconnect(self) -> None:
        """Execute timed disconnection."""
        _LOGGER.debug(
            "%s: Disconnecting",
            self.name,
        )
        await self._execute_disconnect()

    async def _execute_disconnect(self) -> None:
        """Execute disconnection."""
        async with self._connect_lock:
            client = self._client
            self._expected_disconnect = True
            self._client = None
            if client and client.is_connected:
                await client.stop_notify(CHARACTERISTIC_NOTIFY)
                await client.disconnect()

    @retry_bluetooth_connection_error(DEFAULT_ATTEMPTS)
    async def _send_command_locked(self, commands: list[bytes]) -> None:
        """Send command to device and read response."""
        try:
            await self._execute_command_locked(commands)
        except BleakDBusError as ex:
            # Disconnect so we can reset state and try again
            await asyncio.sleep(BLEAK_BACKOFF_TIME)
            _LOGGER.debug(
                "%s: RSSI: %s; Backing off %ss; Disconnecting due to error: %s",
                self.name,
                self.rssi,
                BLEAK_BACKOFF_TIME,
                ex,
            )
            await self._execute_disconnect()
            raise
        except BleakError as ex:
            # Disconnect so we can reset state and try again
            _LOGGER.debug(
                "%s: RSSI: %s; Disconnecting due to error: %s", self.name, self.rssi, ex
            )
            await self._execute_disconnect()
            raise

    async def _send_command(
        self, commands: list[bytes] | bytes, retry: int | None = None
    ) -> None:
        """Send command to device and read response."""
        await self._ensure_connected()
        if not isinstance(commands, list):
            commands = [commands]
        await self._send_command_while_connected(commands, retry)

    async def _send_command_while_connected(
        self, commands: list[bytes], retry: int | None = None
    ) -> None:
        """Send command to device and read response."""
        _LOGGER.debug(
            "%s: Sending commands %s",
            self.name,
            [command.hex() for command in commands],
        )
        if self._operation_lock.locked():
            _LOGGER.debug(
                "%s: Operation already in progress, waiting for it to complete; RSSI: %s",
                self.name,
                self.rssi,
            )
        async with self._operation_lock:
            try:
                await self._send_command_locked(commands)
                return
            except BleakNotFoundError:
                _LOGGER.error(
                    "%s: device not found, no longer in range, or poor RSSI: %s",
                    self.name,
                    self.rssi,
                    exc_info=True,
                )
                raise
            except CharacteristicMissingError as ex:
                _LOGGER.debug(
                    "%s: characteristic missing: %s; RSSI: %s",
                    self.name,
                    ex,
                    self.rssi,
                    exc_info=True,
                )
                raise
            except BLEAK_EXCEPTIONS:
                _LOGGER.debug("%s: communication failed", self.name, exc_info=True)
                raise

        raise RuntimeError("Unreachable")

    async def _execute_command_locked(self, commands: list[bytes]) -> None:
        """Execute command and read response."""
        assert self._client is not None  # nosec
        for command in commands:
            await self._client.write_gatt_char(CHARACTERISTIC_WRITE, command, False)          

    #sensor commands
    async def _get_target_mode(self) -> None:
        """Execute command."""
        assert self._client is not None  # nosec
        await self._send_command(CMD_ENABLE_CONFIG)
        await self._send_command(CMD_QUERY_TARGET_MODE)
        await self._send_command(CMD_DISABLE_CONFIG)
            
    async def _get_fw_ver(self) -> None:
        """Execute command."""
        assert self._client is not None  # nosec
        await self._send_command(CMD_ENABLE_CONFIG)
        await self._send_command(CMD_GET_FW_VER)
        await self._send_command(CMD_DISABLE_CONFIG)

    async def _get_mac(self) -> None:
        """Execute command."""
        assert self._client is not None  # nosec
        await self._send_command(CMD_ENABLE_CONFIG)
        await self._send_command(CMD_GET_MAC)
        await self._send_command(CMD_DISABLE_CONFIG)

    async def _get_zone(self) -> None:
        """Query zone config."""
        assert self._client is not None  # nosec
        await self._send_command(CMD_ENABLE_CONFIG)
        await self._send_command(CMD_ZONE)
        await self._send_command(CMD_DISABLE_CONFIG)

    async def _reboot(self) -> None:
        """Execute reboot command."""
        assert self._client is not None  # nosec
        await self._send_command(CMD_ENABLE_CONFIG)
        await self._send_command(CMD_REBOOT)
        await self._send_command(CMD_DISABLE_CONFIG)
        # Device will reboot and disconnect, schedule reconnection
        await self._schedule_reconnect_after_reboot()

    async def _factory_reset(self) -> None:
        """Execute factory reset command."""
        assert self._client is not None  # nosec
        await self._send_command(CMD_ENABLE_CONFIG)
        await self._send_command(CMD_FACTORY_RESET)
        await self._send_command(CMD_DISABLE_CONFIG)
        # Device will factory reset and reboot, schedule reconnection
        await self._schedule_reconnect_after_reboot()

    async def _schedule_reconnect_after_reboot(self) -> None:
        """Schedule reconnection after device reboot with appropriate delay."""
        
        async def delayed_reconnect():
            # Wait for device to complete reboot (typically 3-5 seconds)
            await asyncio.sleep(5)
            # Reset expected disconnect flag to allow reconnection
            self._expected_disconnect = False
            # Attempt reconnection
            _LOGGER.debug("Initiating reconnection after reboot")
            await self._reconnect()
        
        # Start the delayed reconnection task
        asyncio.create_task(delayed_reconnect())

    async def _set_target_mode(self, mode: int) -> None:
        """Execute command."""
        if mode in [1,2]:
            assert self._client is not None  # nosec
            await self._send_command(CMD_ENABLE_CONFIG)
            if mode == 1:
                #single target mode
                await self._send_command(CMD_ENABLE_SINGLE_TARGET)
            else:
                #multi target mode
                await self._send_command(CMD_ENABLE_MULTI_TARGET)
            await self._send_command(CMD_DISABLE_CONFIG)

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
        assert self._client is not None  # nosec
        await self._send_command(CMD_ENABLE_CONFIG)
        await self._send_command(CMD_SET_ZONE_PRE + 
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
            CMD_SET_ZONE_POST)
        await self._send_command(CMD_DISABLE_CONFIG)
            
    def _num2hex(self, num: int) -> bytes:
        return num.to_bytes(2, byteorder='little', signed=True)