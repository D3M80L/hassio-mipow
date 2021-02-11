# Mipow Playbulb integration
This component has been created to be used with Home Assistant.

It allows to integrate with MiPow Playbulbs - bluetooth, battery controlled LED candles.

## Verified devices:
 - BTL300
 - BTL305ES

## Installation

### HACS
 - Ensure HACS is installed
 - Add Custom Repository https://github.com/D3M80L/hassio-mipow
 - Install the integration
 - Restart Home Assistant

### Manual installation
 - Download the latest release
 - Unpack the release and copy *mipow* folder from the *custom_components* folder in this repository, to the folder *custom_components* in your Home Assistant installation
 - Restart Home Assistant

## Configuration
This integration requires manual configuration.
Playbulb candles are not automatically added to Home Assistant.
You need to know the MAC address of your device and use it in the configuration.

```yaml
light:
  - platform: mipow
    devices:
      "AA:BB:CC:DD:EE:FF":
        name: Name Your Device
      "FE:ED:AF:AC:E0:00":
        name: Name Your Second Device
```

## Supported features
After restart, when the integration successfully connects to your device, you can control your candle directly from Lovelace card or by sending a service command:

```yaml
entity_id: light.name_your_device
rgb_color:
  - 255
  - 255
  - 0
brightness: 0..255
effect: Flash | Candle | Fade | Jump RGB | Fade RGB
white_value: 0..255
flash: short | long
```