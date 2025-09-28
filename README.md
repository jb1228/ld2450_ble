# LD2450 BLE Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant integration for the Hi-Link LD2450 24GHz mmWave Radar Presence Sensor over Bluetooth LE.

This integration extends Home Assistant's native Bluetooth integration capabilities to fully support the LD2450 radar sensor, including all configuration options and sensor data.

## Features

- Automatic discovery and configuration via Bluetooth
- Real-time presence detection with multi-target support
- Zone configuration with up to 3 configurable zones
- Comprehensive sensor data including target coordinates, speed, distance, and angle
- Full control over sensor settings through the Home Assistant interface

## Installation

### HACS Installation (Preferred)

1. Make sure you have [HACS](https://hacs.xyz) installed in your Home Assistant instance
2. Add this repository as a custom repository in HACS:
   - Click the menu icon in the top right of HACS
   - Select "Custom repositories"
   - Add `jb1228/ld2450_ble` as the repository URL
   - Select "Integration" as the category
3. Click "Download" on the LD2450 BLE integration
4. Restart Home Assistant

### Manual Installation

1. Download the latest release from this repository
2. Copy the `custom_components/ld2450_ble` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

The integration supports automatic discovery of LD2450 devices:

1. Go to Settings -> Devices & Services
2. Click "Add Integration"
3. Search for "LD2450 BLE"
4. The integration will automatically discover any LD2450 devices broadcasting over Bluetooth
5. Follow the prompts to complete setup

## Available Entities

### Sensors
- Target coordinates (X,Y) for up to 3 targets
- Target speed
- Calculated distance and angle
- Movement and presence status

### Configuration Entities
- Multi-target mode switch
- Zone mode selector (Off, AND, OR)
- Zone coordinate configuration (up to 3 zones)
- Reboot button

![image](https://github.com/MassiPi/ld2450_ble/assets/2384381/7c8f944a-35a3-4fd5-a7cb-4913463a8ff2)

![image](https://github.com/MassiPi/ld2450_ble/assets/2384381/38e1a29c-66a0-4be3-83dd-ece0a1f10fc4)

## Credits

This integration is based on:
- Home Assistant's official [LD2410 BLE integration](https://www.home-assistant.io/integrations/ld2410_ble/)
- Original Bluetooth protocol implementation from [930913/ld2410-ble](https://github.com/930913/ld2410-ble)
- Modified and extended for LD2450 support by [MassiPI](https://github.com/MassiPI)

As a bonus, there is the 3d model for a sensor case (just print it..) (5 parts: sensor box (with text), back plate, 3-pieces-support to allow solid positioning of the sensor)

![image](https://github.com/user-attachments/assets/d84e66ad-e7e6-463b-be1d-7ceca93e85db)
