import urequests as requests
import json
import time
import ubinascii
import uhashlib
import ssl
import random
from lcd_lib import lcd_st7796, draw_button, hex_to_rgb565
import framebuf
from wifi import connect_wifi

# Configuration
# ============

# Import private configuration
from private import SSID, PASSWORD, TOKEN, SECRET

# SwitchBot API Configuration
API_BASE_URL = "https://api.switch-bot.com/v1.1"

# Display Configuration
HORIZONTAL = True
REVERSE = False

# Colors (Material Design inspired)
BACKGROUND_COLOR = "#F5F5F5"  # Light grey background
METER_BUTTON_COLOR = "#F5F5F5"  # Same as background
METER_BORDER_COLOR = "#2196F3"  # Blue for borders
REFRESH_BUTTON_COLOR = "#F5F5F5"  # Same as background
TEXT_COLOR = "#1565C0"  # Dark blue for text

# Button Layout Configuration
DEVICE_STATUS_Y = 10
BUTTON_HEIGHT = 50
BUTTON_WIDTH = 100
BUTTON_SPACING = 20
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320
REFRESH_BUTTON = (10, SCREEN_HEIGHT - 50, 100, 40)  # Position 50 pixels from bottom
NEXT_PAGE_BUTTON = (120, 400, 100, 40)
PREV_PAGE_BUTTON = (230, 400, 100, 40)

# Device Name Translations
DEVICE_NAMES = {
    "CO2センサー（温湿度計）": "CO2 Meter",
    "寝室のリモートボタン": "Bedroom Remote",
    "寝室のカーテン": "Bedroom Curtain",
    "小部屋のハブミニ": "Small Room Hub",
    "カーテン 0F": "0F Curtain",
    "寝室のハブミニ": "Bedroom Hub",
    "人感センサー キッチン": "Kitchen Motion",
    "換気扇": "Fan",
    "リビングのリモートボタン": "Living Remote",
    "リビングの温湿度計": "Living Meter",
    "リビングのハブミニ": "Living Hub",
    "仕事部屋のカーテン": "Office Curtain",
    "ベランダの防水温湿度計": "Balcony Meter",
    "リビングのカーテン": "Living Curtain",
    "コーヒー": "Coffee Bot",
    "Bath": "Bath Bot",
    "仕事部屋のハブミニ": "Office Hub"
}

# Room Name Translations
ROOM_NAMES = {
    "寝室": "Bedroom",
    "リビング": "Living Room",
    "小部屋": "Small Room",
    "仕事部屋": "Office",
    "キッチン": "Kitchen",
    "ベランダ": "Balcony",
    "その他": "Others"
}

def generate_nonce():
    # Generate 32 random hex characters
    rand_bytes = bytearray(16)  # 16 bytes will give us 32 hex characters
    for i in range(len(rand_bytes)):
        rand_bytes[i] = random.randint(0, 255)
    return ubinascii.hexlify(rand_bytes).decode('utf-8')

def sign(token, secret, nonce, t):
    # Format exactly as in the example
    string_to_sign = '{}{}{}'.format(token, t, nonce)
    message = bytes(string_to_sign, 'utf-8')
    secret_bytes = bytes(secret, 'utf-8')

    # Implementation of HMAC-SHA256
    block_size = 64  # SHA256 block size
    
    # If secret is longer than block size, hash it first
    if len(secret_bytes) > block_size:
        h = uhashlib.sha256()
        h.update(secret_bytes)
        secret_bytes = h.digest()
    
    # Pad secret to block size
    if len(secret_bytes) < block_size:
        secret_bytes = secret_bytes + bytes([0] * (block_size - len(secret_bytes)))
    
    # Prepare inner and outer padding
    inner = bytes([x ^ 0x36 for x in secret_bytes])
    outer = bytes([x ^ 0x5c for x in secret_bytes])
    
    # Inner hash
    h = uhashlib.sha256()
    h.update(inner)
    h.update(message)
    inner_hash = h.digest()
    
    # Outer hash
    h = uhashlib.sha256()
    h.update(outer)
    h.update(inner_hash)
    
    # Base64 encode the result
    return ubinascii.b2a_base64(h.digest()).decode('utf-8').strip()

def get_auth_headers():
    # Get timestamp in milliseconds
    t = str(int(time.time() * 1000))
    nonce = generate_nonce()
    sign_result = sign(TOKEN, SECRET, nonce, t)
    
    # Create headers according to SwitchBot API documentation
    headers = {
        "Authorization": TOKEN,
        "sign": sign_result,
        "t": t,
        "nonce": nonce
    }
    print("Generated sign string:", '{}{}{}'.format(TOKEN, t, nonce))  # Debug print
    return headers

def update_button_text(lcd, button_rect, text, text_color):
    """Update only the text part of a button without redrawing the background"""
    x, y, w, h = button_rect
    # Draw new text centered in the button without modifying the background
    lcd.draw_centered_text(x, y, w, h, text, hex_to_rgb565(TEXT_COLOR), hex_to_rgb565(BACKGROUND_COLOR))

def draw_button(lcd, button, bg_color, label="", text_color=0xFFFF):
    x, y, w, h = button

    # RGB565 requires 2 bytes per pixel
    buf = bytearray(w * h * 2)
    fb = framebuf.FrameBuffer(buf, w, h, framebuf.RGB565)
    fb.fill(bg_color)

    if label:
        # built in font is 8x8 pixel
        text_width = len(label) * 8
        text_height = 8
        text_x = (w - text_width) // 2
        text_y = (h - text_height) // 2
        fb.text(label, text_x, text_y, text_color)

    # draw
    lcd.set_windows(x, y, x + w - 1, y + h - 1)
    lcd.dc(1)
    lcd.cs(0)
    lcd.bus.write(buf)
    lcd.cs(1)

class SwitchBotDisplay:
    def __init__(self):
        self.lcd = lcd_st7796(horizontal=HORIZONTAL, reverse=REVERSE)
        self.lcd.clear_display(hex_to_rgb565(BACKGROUND_COLOR))  # Set background color
        self.devices = []
        self.meters = []  # List to store meter devices
        self.current_page = 0
        self.items_per_page = 3
        # Data storage for graphs
        self.meter_history = {}  # {device_id: [(timestamp, temp, humidity, co2), ...]}
        self.last_update = 0
        self.update_interval = 60  # 1 minute in seconds
        self.need_refresh = True  # Flag to control display refresh
        self.initialized = False  # Flag to track if initial screen has been drawn
        # Ensure WiFi connection
        try:
            connect_wifi(SSID, PASSWORD)
        except Exception as e:
            print(f"WiFi connection error: {e}")
            raise

    def get_devices(self):
        try:
            headers = get_auth_headers()
            response = requests.get(
                f"{API_BASE_URL}/devices",
                headers=headers
            )
            data = response.json()
            if data.get("statusCode") == 100:
                self.devices = data["body"]["deviceList"]
                # Filter devices that contain "Meter" or "WoIOSensor" in their type
                self.meters = [d for d in self.devices if 
                             any(t in str(d.get("deviceType", "")) 
                                 for t in ["Meter", "WoIOSensor"])]
                print(f"Found {len(self.meters)} meter devices:")
                for meter in self.meters:
                    print(f"- {meter.get('deviceName')} (Type: {meter.get('deviceType')})")
                return True
            return False
        except Exception as e:
            print(f"Error getting devices: {e}")
            return False

    def get_meter_status(self, device_id):
        try:
            headers = get_auth_headers()
            response = requests.get(
                f"{API_BASE_URL}/devices/{device_id}/status",
                headers=headers
            )
            data = response.json()
            if data.get("statusCode") == 100:
                return data["body"]
            return None
        except Exception as e:
            print(f"Error getting meter status: {e}")
            return None

    def control_device(self, device_id, command):
        try:
            url = f"{API_BASE_URL}/devices/{device_id}/commands"
            data = {
                "command": command,
                "parameter": "default",
                "commandType": "command"
            }
            response = requests.post(
                url, 
                headers=get_auth_headers(), 
                data=json.dumps(data)
            )
            return response.json()["statusCode"] == 100
        except Exception as e:
            print(f"Error controlling device: {e}")
            return False

    def get_device_display_name(self, device):
        # Get device name and type
        device_name = device.get("deviceName", "")
        device_type = device.get("deviceType", "Unknown")

        # Return translated name if available, otherwise return device type
        return DEVICE_NAMES.get(device_name, device_type)

    def update_meter_history(self):
        current_time = time.time()
        if current_time - self.last_update < self.update_interval:
            return False
        
        for meter in self.meters:
            device_id = meter.get("deviceId")
            if device_id not in self.meter_history:
                self.meter_history[device_id] = []
            
            status = self.get_meter_status(device_id)
            if status:
                temp = status.get("temperature")
                humidity = status.get("humidity")
                co2 = status.get("CO2") if meter.get("deviceType") == "MeterPro(CO2)" else None
                
                # Keep last 60 minutes of data
                history = self.meter_history[device_id]
                history.append((current_time, temp, humidity, co2))
                if len(history) > 60:
                    history.pop(0)
        
        self.last_update = current_time
        self.need_refresh = True  # Set refresh flag when data is updated
        return True

    def draw_initial_screen(self):
        """Draw the complete screen including static elements"""
        if not self.initialized:
            # Only clear the display on first draw
            self.lcd.clear_display(hex_to_rgb565(BACKGROUND_COLOR))
            self.initialized = True
            
        # Draw refresh button at the bottom
        draw_button(self.lcd, REFRESH_BUTTON, hex_to_rgb565(REFRESH_BUTTON_COLOR), "Refresh", hex_to_rgb565(TEXT_COLOR))
        
        # Create button backgrounds for meter values
        y_pos = DEVICE_STATUS_Y
        for meter in self.meters:
            device_name = self.get_device_display_name(meter)
            status_button = (10, y_pos, SCREEN_WIDTH - 20, 30)
            draw_button(self.lcd, status_button, hex_to_rgb565(METER_BUTTON_COLOR), "", hex_to_rgb565(TEXT_COLOR))
            y_pos += 40
        
        # Draw initial meter values
        self.update_meter_display()

    def update_meter_display(self):
        """Update only the meter values without redrawing buttons"""
        y_pos = DEVICE_STATUS_Y
        for meter in self.meters:
            device_name = self.get_device_display_name(meter)
            device_id = meter.get("deviceId")
            
            # Get latest values from history
            if device_id in self.meter_history and self.meter_history[device_id]:
                latest = self.meter_history[device_id][-1]
                _, temp, humidity, co2 = latest
                
                if meter.get("deviceType") == "MeterPro(CO2)" and co2 is not None:
                    status_text = f"{device_name}: {temp}C {humidity}% {co2}ppm"
                else:
                    status_text = f"{device_name}: {temp}C {humidity}%"
                
                # Update only the text
                status_button = (10, y_pos, SCREEN_WIDTH - 20, 30)
                update_button_text(self.lcd, status_button, status_text, hex_to_rgb565(TEXT_COLOR), hex_to_rgb565(BACKGROUND_COLOR))
                y_pos += 40

    def handle_touch(self):
        for x, y in self.lcd.get_touch_xy():
            # Check refresh button
            bx, by, bw, bh = REFRESH_BUTTON
            if (bx <= x < bx + bw) and (by <= y < by + bh):
                if self.get_devices():
                    self.update_meter_display()  # Only update the values
                time.sleep_ms(100)
                self.lcd.clear_touch()
                return

            # Check navigation buttons
            if len(self.devices) > self.items_per_page:
                # Previous page
                bx, by, bw, bh = PREV_PAGE_BUTTON
                if (bx <= x < bx + bw) and (by <= y < by + bh):
                    self.current_page = (self.current_page - 1) % ((len(self.devices) - 1) // self.items_per_page + 1)
                    self.draw_initial_screen()
                    time.sleep_ms(100)
                    self.lcd.clear_touch()
                    return

                # Next page
                bx, by, bw, bh = NEXT_PAGE_BUTTON
                if (bx <= x < bx + bw) and (by <= y < by + bh):
                    self.current_page = (self.current_page + 1) % ((len(self.devices) - 1) // self.items_per_page + 1)
                    self.draw_initial_screen()
                    time.sleep_ms(100)
                    self.lcd.clear_touch()
                    return

            # Check device buttons
            start_idx = self.current_page * self.items_per_page
            end_idx = min(start_idx + self.items_per_page, len(self.devices))
            
            for i, device in enumerate(self.devices[start_idx:end_idx]):
                y_pos = DEVICE_STATUS_Y + i * (BUTTON_HEIGHT + BUTTON_SPACING)
                
                # Check ON button
                if (220 <= x < 300) and (y_pos <= y < y_pos + BUTTON_HEIGHT):
                    device_id = device.get("deviceId")
                    if device_id and self.control_device(device_id, "turnOn"):
                        print(f"Turned ON {device.get('deviceName', 'Unknown')}")
                    time.sleep_ms(100)
                    self.lcd.clear_touch()
                    return
                
                # Check OFF button
                if (310 <= x < 390) and (y_pos <= y < y_pos + BUTTON_HEIGHT):
                    device_id = device.get("deviceId")
                    if device_id and self.control_device(device_id, "turnOff"):
                        print(f"Turned OFF {device.get('deviceName', 'Unknown')}")
                    time.sleep_ms(100)
                    self.lcd.clear_touch()
                    return

    def run(self):
        if self.get_devices():
            # Initial data collection and complete draw
            self.update_meter_history()
            self.draw_initial_screen()
            
            while True:
                # Update data if needed
                if self.update_meter_history():
                    self.update_meter_display()  # Only update the values
                
                self.handle_touch()
                time.sleep_ms(10)

if __name__ == "__main__":
    display = SwitchBotDisplay()
    display.run() 