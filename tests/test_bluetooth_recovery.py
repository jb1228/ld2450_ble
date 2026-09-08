"""Exercise the real driver with simulated BLE connections, without Home Assistant."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components/ld2450_ble/ld2450_ble"
SPEC = importlib.util.spec_from_file_location(
    "ld2450_driver", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
)
PACKAGE_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACKAGE_MODULE
SPEC.loader.exec_module(PACKAGE_MODULE)
driver = sys.modules["ld2450_driver.ld2450_ble"]


class FakeClient:
    def __init__(self, test, callback):
        self.test = test
        self.callback = callback
        self.is_connected = True
        self.writes = []
        self.write_times = []
        self.fail_on = None
        self.drop_on = None
        self.start_notify = AsyncMock()
        self.stop_notify = AsyncMock()
        self.disconnect = AsyncMock(side_effect=self.drop)
        self.write_gatt_char = AsyncMock(side_effect=self.write)

    def drop(self):
        self.is_connected = False
        self.callback(self)

    async def write(self, characteristic, command, *, response):
        self.test.assertEqual(characteristic, driver.CHARACTERISTIC_WRITE)
        self.test.assertFalse(response)
        self.test.assertTrue(self.is_connected)
        self.start_notify.assert_awaited_once()
        self.writes.append(command)
        self.write_times.append(self.test.elapsed)
        if command == self.fail_on:
            raise BleakError("simulated write failure")
        if command == self.drop_on:
            self.drop()


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.elapsed = 0.0
        self.delays = []
        self.clients = []
        self.connection_failures = []
        self.real_sleep = asyncio.sleep
        self.device = driver.LD2450BLE(BLEDevice("AA:BB:CC:DD:EE:FF", "LD2450 test", {}))
        self.connect = AsyncMock(side_effect=self.make_client)
        self.connect_patch = patch.object(driver, "establish_connection", self.connect)
        self.connect_patch.start()
        # Replace only the driver's asyncio reference, leaving unittest's loop alone.
        self.asyncio_patch = patch.object(driver, "asyncio", SimpleNamespace(
            sleep=self.sleep, current_task=asyncio.current_task,
            CancelledError=asyncio.CancelledError,
        ))
        self.asyncio_patch.start()
        self.log_patch = patch.object(driver, "_LOGGER")
        self.log_patch.start()

    async def asyncTearDown(self):
        await self.device.stop()
        self.log_patch.stop()
        self.asyncio_patch.stop()
        self.connect_patch.stop()

    async def sleep(self, delay):
        self.delays.append(delay)
        self.elapsed += delay
        await self.real_sleep(0)

    async def make_client(self, *args, **kwargs):
        if self.connection_failures:
            raise self.connection_failures.pop(0)
        client = FakeClient(self, args[3])
        self.clients.append(client)
        return client

    async def test_startup_is_paced_and_concurrent_initialization_is_not_duplicated(self):
        await asyncio.gather(self.device.initialise(), self.device.initialise())
        self.assertEqual(len(self.clients), 1)
        client = self.clients[0]
        self.assertEqual(len(client.writes), 12)
        self.assertEqual(self.delays, [0.1] * 12)
        for before, after in zip(client.write_times, client.write_times[1:]):
            self.assertAlmostEqual(after - before, 0.1)
        self.assertEqual(client.writes[:3], [
            driver.CMD_ENABLE_CONFIG, driver.CMD_QUERY_TARGET_MODE, driver.CMD_DISABLE_CONFIG
        ])

    async def test_write_failure_reconnects_and_replays_the_whole_transaction(self):
        first = await self.make_client(None, None, None, self.device._disconnected)
        first.fail_on = driver.CMD_QUERY_TARGET_MODE
        self.connect.side_effect = [first, await self.make_client(None, None, None, self.device._disconnected)]
        await self.device._get_target_mode()
        self.assertEqual(first.writes, [driver.CMD_ENABLE_CONFIG, driver.CMD_QUERY_TARGET_MODE])
        self.assertEqual(self.clients[1].writes, [
            driver.CMD_ENABLE_CONFIG, driver.CMD_QUERY_TARGET_MODE, driver.CMD_DISABLE_CONFIG
        ])
        first.disconnect.assert_awaited_once()
        self.assertFalse(self.device._expected_disconnect)

    async def test_mid_transaction_disconnect_retries_with_notifications(self):
        first = await self.make_client(None, None, None, self.device._disconnected)
        first.drop_on = driver.CMD_GET_FW_VER
        second = await self.make_client(None, None, None, self.device._disconnected)
        self.connect.side_effect = [first, second]
        await self.device._get_fw_ver()
        self.assertEqual(second.writes, [
            driver.CMD_ENABLE_CONFIG, driver.CMD_GET_FW_VER, driver.CMD_DISABLE_CONFIG
        ])
        second.start_notify.assert_awaited_once()

    async def test_repeated_disconnects_recover_and_old_callbacks_are_ignored(self):
        await self.device.initialise()
        first = self.clients[0]
        self.device._buf = b"partial old frame"
        first.drop()
        task = self.device._reconnect_task
        self.device._schedule_reconnect()
        self.assertIs(self.device._reconnect_task, task)
        await task
        second = self.clients[1]
        self.assertEqual(self.device._buf, b"")
        self.assertFalse(self.device._expected_disconnect)
        first.callback(first)
        self.assertIs(self.device._client, second)
        self.assertIsNone(self.device._reconnect_task)
        second.drop()
        await self.device._reconnect_task
        self.assertEqual(len(self.clients), 3)
        self.assertEqual(len(self.clients[-1].writes), 12)
        updates = []
        self.device.register_callback(updates.append)
        callback = self.clients[-1].start_notify.call_args.args[1]
        await callback(None, bytearray(b"\xaa\xff\x03\x00" + b"\x00" * 24 + b"\x55\xcc"))
        self.assertTrue(updates, "new session must deliver parsed radar updates")

    async def test_reconnect_survives_generic_errors_and_backs_off(self):
        self.connection_failures = [BleakError("busy"), TimeoutError(), OSError("closed")]
        self.device._reconnect_enabled = True
        self.device._schedule_reconnect()
        task = self.device._reconnect_task
        self.device._schedule_reconnect()
        self.assertIs(self.device._reconnect_task, task)
        await task
        self.assertEqual(self.connect.await_count, 4)
        self.assertEqual(self.delays[:4], [1.0, 1.0, 2.0, 2.0])
        self.assertEqual(len(self.clients[0].writes), 12)
        self.assertIsNone(self.device._reconnect_task)

    async def test_foreground_retry_limit_and_failed_setup_does_not_start_recovery(self):
        self.connect.side_effect = BleakError("unavailable")
        with self.assertRaises(BleakError):
            await self.device.initialise()
        self.assertEqual(self.connect.await_count, 3)
        self.assertIsNone(self.device._reconnect_task)
        self.assertIsNone(self.device._client)

    async def test_exhausted_control_retries_schedule_background_recovery(self):
        await self.device.initialise()
        self.clients[0].drop()
        await self.device._cancel_reconnect()
        self.connect.side_effect = BleakError("unavailable")
        with self.assertRaises(BleakError):
            await self.device._get_target_mode()
        self.assertIsNotNone(self.device._reconnect_task)

    async def test_concurrent_controls_do_not_interleave_config_sessions(self):
        await asyncio.gather(self.device._get_fw_ver(), self.device._get_target_mode())
        self.assertEqual(self.clients[0].writes, [
            driver.CMD_ENABLE_CONFIG, driver.CMD_GET_FW_VER, driver.CMD_DISABLE_CONFIG,
            driver.CMD_ENABLE_CONFIG, driver.CMD_QUERY_TARGET_MODE, driver.CMD_DISABLE_CONFIG,
        ])

    async def test_stop_cancels_pending_recovery_and_prevents_new_connections(self):
        entered = asyncio.Event()
        async def blocked_sleep(delay):
            entered.set()
            await asyncio.Event().wait()
        driver.asyncio.sleep = blocked_sleep
        self.device._reconnect_enabled = True
        self.device._schedule_reconnect()
        task = self.device._reconnect_task
        await asyncio.wait_for(entered.wait(), 1)
        await self.device.stop()
        self.assertTrue(task.cancelled())
        self.assertIsNone(self.device._reconnect_task)
        self.device._schedule_reconnect()
        with self.assertRaises(BleakError):
            await self.device._get_target_mode()
        self.connect.assert_not_awaited()

    async def test_stop_during_notification_setup_closes_connection(self):
        entered = asyncio.Event()
        async def make_blocked_client(*args, **kwargs):
            client = await self.make_client(*args, **kwargs)
            async def blocked_notify(*args):
                entered.set()
                await asyncio.Event().wait()
            client.start_notify.side_effect = blocked_notify
            return client
        self.connect.side_effect = make_blocked_client
        self.device._reconnect_enabled = True
        self.device._schedule_reconnect()
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(self.device.stop(), 1)
        self.clients[0].disconnect.assert_awaited_once()
        self.assertIsNone(self.device._client)
        self.assertIsNone(self.device._reconnect_task)

    async def test_notification_setup_failure_releases_client_before_retry(self):
        first = await self.make_client(None, None, None, self.device._disconnected)
        first.start_notify.side_effect = TimeoutError()
        second = await self.make_client(None, None, None, self.device._disconnected)
        self.connect.side_effect = [first, second]
        await self.device.initialise()
        first.disconnect.assert_awaited_once()
        self.assertFalse(first.writes)
        self.assertEqual(len(second.writes), 12)

    async def test_stop_notify_error_does_not_prevent_disconnect(self):
        await self.device.initialise()
        client = self.clients[0]
        client.stop_notify.side_effect = BleakError("already disconnected")
        disconnected = []
        self.device.register_disconnected_callback(lambda: disconnected.append(True))
        await self.device.stop()
        client.disconnect.assert_awaited_once()
        self.assertEqual(disconnected, [True])

    async def test_reboot_accepts_expected_disconnect_and_schedules_one_delayed_recovery(self):
        await self.device.initialise()
        first = self.clients[0]
        first.drop_on = driver.CMD_REBOOT
        initial_writes = len(first.writes)
        await self.device._reboot()
        task = self.device._reconnect_task
        await task
        self.assertEqual(first.writes[initial_writes:], [driver.CMD_ENABLE_CONFIG, driver.CMD_REBOOT])
        self.assertIn(5.0, self.delays)
        self.assertEqual(len(self.clients), 2)
        self.assertFalse(self.device._expected_disconnect)

    async def test_factory_reset_write_failure_is_not_replayed(self):
        await self.device.initialise()
        first = self.clients[0]
        first.fail_on = driver.CMD_FACTORY_RESET
        with self.assertRaises(BleakError):
            await self.device._factory_reset()
        task = self.device._reconnect_task
        await task
        self.assertEqual(first.writes.count(driver.CMD_FACTORY_RESET), 1)
        self.assertNotIn(driver.CMD_FACTORY_RESET, self.clients[1].writes)
        self.assertIn(5.0, self.delays)


if __name__ == "__main__":
    unittest.main()
