# Mipow Playbulb integration
This component has been created to be used with Home Assistant 2022.9 and above.

It allows to integrate with MiPow Playbulbs - bluetooth, battery controlled LED candles.

## Verified devices:
 - BTL300
 - BTL305ES

## Version 3.0 - ALPHA
This version is not backward compatible.
We recommend to remove the entites and configuration that was configured for lower versions.

## Supported domains
### Light
TBD

### Battery sensor
TBD

## Installation
This integration is not (yet) part of the official Home Assistant integrations.
You have to install it manually or install it via HACS. 
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
This integration requires [Home Assistant Bluetooth](https://www.home-assistant.io/integrations/bluetooth/) integration.
The devices are discovered automatically or you can use MiPow integration from the integration list.

## Supported features
After restart, when the integration successfully connects to your device, you can control your device directly from Lovelace card or by sending a service command:

```yaml
entity_id: light.name_your_device
rgb_color:
  - 255
  - 255
  - 0
brightness: 0..255
effect: light | flash | pulse | rainbow | colorloop | candle
white_value: 0..255
flash: short | long
```

### Color mode
In color mode you can control both white value and color separately.
When color is selected, the brigthness of the color is only changed, in this case the white value is controlled separately.
When no color is selected, then brightness represents white value.
![Color palette](doc/color_palette.png "Example color palette")

### White mode
In this mode only white value is changed - any colors are removed.
![White mode](doc/white_mode.png)

### Effects
Mipow candles come with a predefined list of effects that are represented in HA by:
- light - no effects applied at all
- flash
- pulse
- rainbow - change the light color
- colorloop - is a combination of rainbow and pulse
- candle - blink the lightusing a candle effect

### Battery sensor
When the device is battery powered, you can check the level using battery sensor.