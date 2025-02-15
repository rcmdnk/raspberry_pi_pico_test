import urequests as requests
import json
import time
import ubinascii
import uhashlib
import ssl
import random
from lcd_lib import lcd_st7796, draw_button, hex_to_rgb565, update_button_text
import framebuf
from wifi import connect_wifi
from machine import Pin

# Configuration
# ============

# Import private configuration
from private import SSID, PASSWORD, TOKEN, SECRET

# SwitchBot API Configuration
API_BASE_URL = "https://api.switch-bot.com/v1.1"

# Display Configuration
HORIZONTAL = True
REVERSE = False

# LED Configuration
LED = Pin("LED", Pin.OUT)

# Colors (Material Design inspired, all in RGB565 format)
BACKGROUND_COLOR = hex_to_rgb565("#F5F5F5")  # Light grey background
METER_BUTTON_COLOR = BACKGROUND_COLOR  # Same as background
METER_BORDER_COLOR = hex_to_rgb565("#2196F3")  # Blue for borders
REFRESH_BUTTON_COLOR = BACKGROUND_COLOR  # Same as background
REFRESH_BUTTON_ACTIVE_COLOR = hex_to_rgb565("#81C784")  # Green color when pressed
TEXT_COLOR = hex_to_rgb565("#1565C0")  # Dark blue for text
WHITE_COLOR = hex_to_rgb565("#FFFFFF")  # White for graph background

# Graph Colors (Material Design inspired, all in RGB565 format)
TEMPERATURE_COLOR = hex_to_rgb565("#1E88E5")  # Blue 600 - より落ち着いた青
HUMIDITY_COLOR = hex_to_rgb565("#E53935")    # Red 600 - より落ち着いた赤
CO2_COLOR = hex_to_rgb565("#43A047")        # Green 600 - より落ち着いた緑

# Button Layout Configuration
DEVICE_STATUS_Y = 10
BUTTON_HEIGHT = 50
BUTTON_WIDTH = 100
BUTTON_SPACING = 20
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320
REFRESH_BUTTON = (10, SCREEN_HEIGHT - 30, 60, 20)  # Smaller refresh button
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

class SwitchBotDisplay:
    def __init__(self, pseudo_mode=False):
        self.lcd = lcd_st7796(horizontal=HORIZONTAL, reverse=REVERSE)
        self.lcd.clear_display(BACKGROUND_COLOR)  # Set background color
        self.devices = []
        self.meters = []  # List to store meter devices
        self.current_page = 0
        self.items_per_page = 3
        # Data storage for graphs
        self.meter_history = {}  # {device_id: [(timestamp, temp, humidity, co2), ...]}
        self.last_update = 0
        self.update_interval = 10 if pseudo_mode else 60  # 10 seconds in pseudo mode, 1 minute in normal mode
        self.need_refresh = True  # Flag to control display refresh
        self.initialized = False  # Flag to track if initial screen has been drawn
        self.pseudo_mode = pseudo_mode
        # Initialize LED
        self.led = LED
        self.led.off()  # Ensure LED is off initially
        # Ensure WiFi connection if not in pseudo mode
        if not pseudo_mode:
            try:
                connect_wifi(SSID, PASSWORD)
            except Exception as e:
                print(f"WiFi connection error: {e}")
                raise

    def generate_pseudo_data(self):
        """Generate pseudo data for testing"""
        # Create sample devices if not exists
        if not self.meters:
            self.meters = [
                {"deviceId": "meter1", "deviceName": "リビングの温湿度計", "deviceType": "Meter"},
                {"deviceId": "meter2", "deviceName": "CO2センサー（温湿度計）", "deviceType": "MeterPro(CO2)"},
                {"deviceId": "meter3", "deviceName": "ベランダの防水温湿度計", "deviceType": "Meter"}
            ]

        current_time = time.time()
        
        # Generate or update data for each meter
        for meter in self.meters:
            device_id = meter.get("deviceId")
            if device_id not in self.meter_history:
                # Initialize with 60 minutes of historical data
                self.meter_history[device_id] = []
                # Start with base values
                base_temp = 25.0
                base_humidity = 50.0
                base_co2 = 800.0 if meter.get("deviceType") == "MeterPro(CO2)" else None
                
                for i in range(60):
                    timestamp = current_time - (59 - i) * 60  # Start from 59 minutes ago
                    # Add small random changes to create continuous data
                    base_temp += random.uniform(-0.1, 0.1)
                    base_humidity += random.uniform(-0.5, 0.5)
                    if base_co2 is not None:
                        base_co2 += random.uniform(-5, 5)
                    
                    # Keep values within reasonable ranges
                    base_temp = max(20, min(30, base_temp))
                    base_humidity = max(30, min(70, base_humidity))
                    if base_co2 is not None:
                        base_co2 = max(400, min(1200, base_co2))
                    
                    self.meter_history[device_id].append((
                        timestamp,
                        base_temp,
                        base_humidity,
                        base_co2
                    ))
            else:
                # Add new data point with small random changes from last value
                last_data = self.meter_history[device_id][-1]
                _, last_temp, last_humidity, last_co2 = last_data
                
                # Add small random changes
                new_temp = last_temp + random.uniform(-0.1, 0.1)
                new_humidity = last_humidity + random.uniform(-0.5, 0.5)
                
                # Keep values within reasonable ranges
                new_temp = max(20, min(30, new_temp))
                new_humidity = max(30, min(70, new_humidity))
                
                if last_co2 is not None:
                    new_co2 = last_co2 + random.uniform(-5, 5)
                    new_co2 = max(400, min(1200, new_co2))
                else:
                    new_co2 = None
                
                new_data = (current_time, new_temp, new_humidity, new_co2)
                self.meter_history[device_id].append(new_data)
                if len(self.meter_history[device_id]) > 60:
                    self.meter_history[device_id].pop(0)

        return True

    def get_devices(self):
        if self.pseudo_mode:
            return self.generate_pseudo_data()
            
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

        if self.pseudo_mode:
            success = self.generate_pseudo_data()
        else:
            success = self.get_devices()
            if success:
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
        
        if success:
            self.last_update = current_time
            self.need_refresh = True
        return success

    def draw_initial_screen(self):
        """Draw the complete screen including static elements"""
        if not self.initialized:
            # Only clear the display on first draw
            self.lcd.clear_display(BACKGROUND_COLOR)
            self.initialized = True
            
        # Draw refresh button at the bottom
        draw_button(self.lcd, REFRESH_BUTTON, REFRESH_BUTTON_COLOR, "Refresh", TEXT_COLOR)
        
        # Create button backgrounds for meter values
        y_pos = DEVICE_STATUS_Y
        for meter in self.meters:
            device_name = self.get_device_display_name(meter)
            status_button = (10, y_pos, SCREEN_WIDTH - 20, 30)
            draw_button(self.lcd, status_button, METER_BUTTON_COLOR, "", TEXT_COLOR)
            y_pos += 40
        
        # Draw initial meter values
        self.update_meter_display()

    def draw_last_update_time(self):
        """Draw the last update time in the bottom right corner"""
        update_time = time.localtime(self.last_update)
        # Format: YYYY/MM/DD HH:MM:SS
        time_str = "{:04d}/{:02d}/{:02d} {:02d}:{:02d}:{:02d}".format(
            update_time[0],  # Year
            update_time[1],  # Month
            update_time[2],  # Day
            update_time[3],  # Hour
            update_time[4],  # Minute
            update_time[5]   # Second
        )
        # Draw with a small background rectangle to ensure clean display
        self.lcd.draw_text(SCREEN_WIDTH - 160, SCREEN_HEIGHT - 20, time_str, TEXT_COLOR, BACKGROUND_COLOR)

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
                
                # Draw button with text
                status_button = (10, y_pos, SCREEN_WIDTH - 20, 30)
                draw_button(self.lcd, status_button, METER_BUTTON_COLOR, status_text, TEXT_COLOR)
                y_pos += 40
        
        # Draw last update time
        self.draw_last_update_time()

    def draw_graph(self, history_data, title):
        """Draw a graph of temperature, humidity, and CO2 history"""
        # Clear the screen with background color
        self.lcd.clear_display(BACKGROUND_COLOR)
        
        # Get current values from the latest data point
        if history_data:
            _, current_temp, current_humidity, current_co2 = history_data[-1]
            # Create title with current values
            if current_co2 is not None:
                value_text = f"{title}: {current_temp:.1f}C {current_humidity:.0f}% {current_co2:.0f}ppm"
            else:
                value_text = f"{title}: {current_temp:.1f}C {current_humidity:.0f}%"
        else:
            value_text = title
        
        # Draw title directly without using draw_button
        title_x = 10
        title_y = 10
        title_w = SCREEN_WIDTH - 20
        title_h = 30
        self.lcd.fill_rectangle(title_x, title_y, title_w, title_h, METER_BUTTON_COLOR)
        text_x = title_x + (title_w - len(value_text) * 8) // 2  # Center text (8 pixels per character)
        text_y = title_y + (title_h - 8) // 2  # Center text vertically (8 pixels height)
        self.lcd.draw_text(text_x, text_y, value_text, TEXT_COLOR, BACKGROUND_COLOR)
        
        # Graph area dimensions
        GRAPH_X = 40
        GRAPH_Y = 60
        GRAPH_WIDTH = SCREEN_WIDTH - 120
        GRAPH_HEIGHT = 180
        
        # Draw graph background
        self.lcd.fill_rectangle(GRAPH_X, GRAPH_Y, GRAPH_WIDTH, GRAPH_HEIGHT, WHITE_COLOR)
        
        # Draw axes
        self.lcd.fill_rectangle(GRAPH_X, GRAPH_Y, 2, GRAPH_HEIGHT, TEXT_COLOR)  # Y axis
        self.lcd.fill_rectangle(GRAPH_X, GRAPH_Y + GRAPH_HEIGHT - 2, GRAPH_WIDTH, 2, TEXT_COLOR)  # X axis
        
        if not history_data:
            draw_button(self.lcd, (GRAPH_X, GRAPH_Y + GRAPH_HEIGHT//2 - 15, GRAPH_WIDTH, 30),
                       BACKGROUND_COLOR, "No data available", TEXT_COLOR)
            return
        
        # Draw time ticks on x-axis
        if len(history_data) > 1:
            latest_time = history_data[-1][0]
            for i in range(7):  # Draw 7 ticks (0, 10, 20, 30, 40, 50, 60 minutes ago)
                minutes_ago = i * 10
                x = GRAPH_X + GRAPH_WIDTH - (minutes_ago * GRAPH_WIDTH // 60)
                # Draw tick mark
                self.lcd.fill_rectangle(x, GRAPH_Y + GRAPH_HEIGHT - 5, 1, 5, TEXT_COLOR)
                # Draw time label
                tick_time = time.localtime(latest_time - minutes_ago * 60)
                time_str = "{:02d}:{:02d}".format(tick_time[3], tick_time[4])
                self.lcd.draw_text(x - 20, GRAPH_Y + GRAPH_HEIGHT + 5, time_str, TEXT_COLOR, BACKGROUND_COLOR)
        
        # Get min/max values for scaling
        temps = [data[1] for data in history_data if data[1] is not None]
        humids = [data[2] for data in history_data if data[2] is not None]
        co2s = [data[3] for data in history_data if data[3] is not None]
        
        if not temps or not humids:
            return
            
        temp_min, temp_max = min(temps), max(temps)
        humid_min, humid_max = min(humids), max(humids)
        
        # Add some padding to min/max
        temp_range = max(1, temp_max - temp_min)
        humid_range = max(1, humid_max - humid_min)
        temp_min -= temp_range * 0.1
        temp_max += temp_range * 0.1
        humid_min -= humid_range * 0.1
        humid_max += humid_range * 0.1
        
        # CO2 scaling if available
        if co2s:
            co2_min, co2_max = min(co2s), max(co2s)
            co2_range = max(1, co2_max - co2_min)
            co2_min -= co2_range * 0.1
            co2_max += co2_range * 0.1

        # Draw data points
        for i in range(len(history_data)):
            x = GRAPH_X + i * GRAPH_WIDTH // (len(history_data)-1)
            
            # Temperature
            if history_data[i][1] is not None:
                y = GRAPH_Y + GRAPH_HEIGHT - int((history_data[i][1] - temp_min) * GRAPH_HEIGHT / (temp_max - temp_min))
                self.lcd.fill_rectangle(x-1, y-1, 3, 3, TEMPERATURE_COLOR)
            
            # Humidity
            if history_data[i][2] is not None:
                y = GRAPH_Y + GRAPH_HEIGHT - int((history_data[i][2] - humid_min) * GRAPH_HEIGHT / (humid_max - humid_min))
                self.lcd.fill_rectangle(x-1, y-1, 3, 3, HUMIDITY_COLOR)
            
            # CO2
            if co2s and history_data[i][3] is not None:
                y = GRAPH_Y + GRAPH_HEIGHT - int((history_data[i][3] - co2_min) * GRAPH_HEIGHT / (co2_max - co2_min))
                self.lcd.fill_rectangle(x-1, y-1, 3, 3, CO2_COLOR)
        
        # Draw legend
        legend_y = GRAPH_Y + GRAPH_HEIGHT + 20
        # Temperature
        self.lcd.fill_rectangle(GRAPH_X, legend_y, 20, 2, TEMPERATURE_COLOR)
        self.lcd.draw_text(GRAPH_X + 30, legend_y - 3, "Temp", TEMPERATURE_COLOR, BACKGROUND_COLOR)
        # Humidity
        self.lcd.fill_rectangle(GRAPH_X + 100, legend_y, 20, 2, HUMIDITY_COLOR)
        self.lcd.draw_text(GRAPH_X + 130, legend_y - 3, "Humidity", HUMIDITY_COLOR, BACKGROUND_COLOR)
        # CO2
        if co2s:
            self.lcd.fill_rectangle(GRAPH_X + 220, legend_y, 20, 2, CO2_COLOR) 
            self.lcd.draw_text(GRAPH_X + 250, legend_y - 3, "CO2", CO2_COLOR, BACKGROUND_COLOR)
        
        # Draw min/max values
        self.lcd.draw_text(5, GRAPH_Y - 4, f"{temp_max:.1f}C", TEMPERATURE_COLOR, BACKGROUND_COLOR)
        self.lcd.draw_text(5, GRAPH_Y + GRAPH_HEIGHT - 8, f"{temp_min:.1f}C", TEMPERATURE_COLOR, BACKGROUND_COLOR)
        self.lcd.draw_text(GRAPH_X + GRAPH_WIDTH + 5, GRAPH_Y - 4, f"{humid_max:.0f}%", HUMIDITY_COLOR, BACKGROUND_COLOR) 
        self.lcd.draw_text(GRAPH_X + GRAPH_WIDTH + 5, GRAPH_Y + GRAPH_HEIGHT - 8, f"{humid_min:.0f}%", HUMIDITY_COLOR, BACKGROUND_COLOR)
        if co2s:
            self.lcd.draw_text(GRAPH_X + GRAPH_WIDTH + 5, GRAPH_Y - 16, f"{co2_max:.0f}ppm", CO2_COLOR, BACKGROUND_COLOR) 
            self.lcd.draw_text(GRAPH_X + GRAPH_WIDTH + 5, GRAPH_Y + GRAPH_HEIGHT - 20, f"{co2_min:.0f}ppm", CO2_COLOR, BACKGROUND_COLOR)
        
        # Draw back button
        draw_button(self.lcd, (10, SCREEN_HEIGHT - 30, 60, 20), REFRESH_BUTTON_COLOR, "Back", TEXT_COLOR)
        
        # Draw last update time
        self.draw_last_update_time()

    def handle_touch(self):
        for x, y in self.lcd.get_touch_xy():
            # Check if we're in graph view
            if hasattr(self, 'showing_graph') and self.showing_graph:
                # Check back button
                bx, by, bw, bh = (10, SCREEN_HEIGHT - 30, 60, 20)
                if (bx <= x < bx + bw) and (by <= y < by + bh):
                    self.showing_graph = False
                    # Clear the screen before redrawing
                    self.lcd.clear_display(BACKGROUND_COLOR)
                    self.initialized = False  # Force complete redraw
                    self.draw_initial_screen()
                    time.sleep_ms(100)
                    self.lcd.clear_touch()
                    return
                continue
            
            # Check refresh button
            bx, by, bw, bh = REFRESH_BUTTON
            if (bx <= x < bx + bw) and (by <= y < by + bh):
                # Visual feedback - change button color and turn on LED
                draw_button(self.lcd, REFRESH_BUTTON, REFRESH_BUTTON_ACTIVE_COLOR, "Refresh", TEXT_COLOR)
                self.led.on()  # Turn on LED
                
                if self.get_devices():
                    self.update_meter_display()  # Only update the values
                
                # Return to original color and turn off LED
                draw_button(self.lcd, REFRESH_BUTTON, REFRESH_BUTTON_COLOR, "Refresh", TEXT_COLOR)
                self.led.off()  # Turn off LED
                time.sleep_ms(100)
                self.lcd.clear_touch()
                return
            
            # Check meter buttons
            y_pos = DEVICE_STATUS_Y
            for meter in self.meters:
                status_button = (10, y_pos, SCREEN_WIDTH - 20, 30)
                bx, by, bw, bh = status_button
                if (bx <= x < bx + bw) and (by <= y < by + bh):
                    device_id = meter.get("deviceId")
                    if device_id in self.meter_history:
                        self.showing_graph = True
                        device_name = self.get_device_display_name(meter)
                        self.draw_graph(self.meter_history[device_id], device_name)
                        time.sleep_ms(100)
                        self.lcd.clear_touch()
                        return
                y_pos += 40

    def run(self):
        if self.get_devices():
            # Initial data collection and complete draw
            self.update_meter_history()
            self.draw_initial_screen()
            
            # Keep track of current device being viewed
            current_device_id = None
            current_device_name = None
            
            while True:
                # Update data if needed
                if self.update_meter_history():
                    if hasattr(self, 'showing_graph') and self.showing_graph and current_device_id:
                        # Redraw graph with updated data
                        self.draw_graph(self.meter_history[current_device_id], current_device_name)
                    else:
                        self.update_meter_display()  # Only update the values
                
                # Check touch events
                for x, y in self.lcd.get_touch_xy():
                    # Check if we're in graph view
                    if hasattr(self, 'showing_graph') and self.showing_graph:
                        # Check back button
                        bx, by, bw, bh = (10, SCREEN_HEIGHT - 30, 60, 20)
                        if (bx <= x < bx + bw) and (by <= y < by + bh):
                            self.showing_graph = False
                            current_device_id = None
                            current_device_name = None
                            # Clear the screen before redrawing
                            self.lcd.clear_display(BACKGROUND_COLOR)
                            self.initialized = False  # Force complete redraw
                            self.draw_initial_screen()
                            time.sleep_ms(100)
                            self.lcd.clear_touch()
                            continue
                        continue
                    
                    # Check refresh button
                    bx, by, bw, bh = REFRESH_BUTTON
                    if (bx <= x < bx + bw) and (by <= y < by + bh):
                        # Visual feedback - change button color and turn on LED
                        draw_button(self.lcd, REFRESH_BUTTON, REFRESH_BUTTON_ACTIVE_COLOR, "Refresh", TEXT_COLOR)
                        self.led.on()  # Turn on LED
                        
                        if self.get_devices():
                            self.update_meter_display()  # Only update the values
                        
                        # Return to original color and turn off LED
                        draw_button(self.lcd, REFRESH_BUTTON, REFRESH_BUTTON_COLOR, "Refresh", TEXT_COLOR)
                        self.led.off()  # Turn off LED
                        time.sleep_ms(100)
                        self.lcd.clear_touch()
                        continue
                    
                    # Check meter buttons
                    y_pos = DEVICE_STATUS_Y
                    for meter in self.meters:
                        status_button = (10, y_pos, SCREEN_WIDTH - 20, 30)
                        bx, by, bw, bh = status_button
                        if (bx <= x < bx + bw) and (by <= y < by + bh):
                            device_id = meter.get("deviceId")
                            if device_id in self.meter_history:
                                self.showing_graph = True
                                current_device_id = device_id
                                current_device_name = self.get_device_display_name(meter)
                                self.draw_graph(self.meter_history[device_id], current_device_name)
                                time.sleep_ms(100)
                                self.lcd.clear_touch()
                            break
                        y_pos += 40
                
                time.sleep_ms(10)

if __name__ == "__main__":
    # Use pseudo_mode=True for testing without actual API calls
    display = SwitchBotDisplay(pseudo_mode=True)
    display.run() 