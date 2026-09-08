Run the Bluetooth recovery tests from the repository root:

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

The tests load the integration's BLE driver directly and simulate connections,
notifications, write failures, timing, and cancellation. They do not connect to
Bluetooth hardware or require Home Assistant. Delays use a virtual clock.
