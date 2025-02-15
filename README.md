# raspberry_pi_pico_test

MicroPython examples for Raspberry Pi Pico W.

## Simple Examples

* blink.py: Blink the LED on the board
* network.py: Connect to a Wi-Fi network and get the IP address


## With [3.5inch Capacitive Touch LCD (Waveshare)](https://www.waveshare.com/wiki/3.5inch_Capacitive_Touch_LCD)

* lcd_lib.py: Library for [3.5inch Capacitive Touch LCD (Waveshare)](https://www.waveshare.com/wiki/3.5inch_Capacitive_Touch_LCD), based on [3.5inch_Capacitive_Touch_LCD.py](https://files.waveshare.com/wiki/3.5inch%20Capacitive%20Touch%20LCD/3.5inch_Capacitive_Touch_LCD_Demo_Pico.zip)
* lcd_led.py: Example to make on/off buttons on the LCD screen to control the LED
* lcd_slack.py: Example to send a message to Slack with the LCD screen

# SwitchBot Display Controller

This project implements a touch display interface for controlling SwitchBot devices using a Raspberry Pi Pico and a 3.5inch Capacitive Touch LCD.

## Requirements

### Hardware
- Raspberry Pi Pico
- Waveshare 3.5inch Capacitive Touch LCD
- WiFi connection

### Software Dependencies
- MicroPython with `urequests` library
- SwitchBot API credentials (token and secret key)

## Setup

1. Install MicroPython on your Raspberry Pi Pico
2. Install required libraries:
   ```python
   import upip
   upip.install('urequests')
   ```

3. Configure your SwitchBot API credentials:
   - Open `switchbot_display.py`
   - Replace `YOUR_TOKEN` with your SwitchBot API token
   - Replace `YOUR_SECRET` with your SwitchBot API secret key

   You can obtain these credentials from your SwitchBot app:
   1. Open the SwitchBot app
   2. Go to Profile > Preferences > Developer Options
   3. Generate your token and secret key

4. Connect the LCD display to your Raspberry Pi Pico according to the pin configuration in the Waveshare documentation.

## Usage

1. Run the program:
   ```python
   import switchbot_display
   ```

2. The display will show:
   - List of your SwitchBot devices
   - ON/OFF buttons for each device
   - Refresh button at the bottom

3. Touch controls:
   - Touch ON/OFF buttons to control devices
   - Touch the Refresh button to update the device list

## Features

- Display and control multiple SwitchBot devices
- Real-time device control
- Easy-to-use touch interface
- Secure API authentication
- Device list refresh capability

## Troubleshooting

If you encounter any issues:

1. Check your WiFi connection
2. Verify your API credentials
3. Ensure all required libraries are installed
4. Check the serial output for error messages

## References

- [SwitchBot API Documentation](https://github.com/OpenWonderLabs/SwitchBotAPI)
- [Waveshare 3.5inch LCD Documentation](https://www.waveshare.com/wiki/3.5inch_Capacitive_Touch_LCD)


