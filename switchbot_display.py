import urequests as requests
import json
import time
import ubinascii
import uhashlib
import ssl
import random
import os
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
BUTTON_COLOR = hex_to_rgb565("#E3F2FD")  # Blue 50 - Very light blue for buttons
BUTTON_ACTIVE_COLOR = hex_to_rgb565("#90CAF9")  # Blue 200 - Lighter blue when pressed
TEXT_COLOR = hex_to_rgb565("#1565C0")  # Blue 800 - Dark blue for text
WHITE_COLOR = hex_to_rgb565("#FFFFFF")  # White for graph background

# Graph Colors (Material Design inspired, all in RGB565 format)
TEMPERATURE_COLOR = hex_to_rgb565("#1E88E5")  # Blue 600 - より落ち着いた青
HUMIDITY_COLOR = hex_to_rgb565("#E53935")    # Red 600 - より落ち着いた赤
CO2_COLOR = hex_to_rgb565("#43A047")        # Green 600 - より落ち着いた緑

# Button Layout Configuration
DEVICE_STATUS_Y = 10
BUTTON_HEIGHT = 120  # Increased height for room buttons
BUTTON_WIDTH = 150   # Width for room buttons
BUTTON_SPACING = 10  # Spacing between buttons
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320
REFRESH_BUTTON = (10, SCREEN_HEIGHT - 30, 60, 20)  # Smaller refresh button

# Room button positions (3x2 grid)
ROOM_BUTTONS = {
    "Living Room": (10, 10),
    "Office": (170, 10),
    "Play Room": (330, 10),
    "Bedroom": (10, 140),
    "Kitchen": (170, 140),
    "Balcony": (330, 140),
}

# Device Name Translations
DEVICE_NAMES = {
    # Living Room
    "リビングのカーテン": "Living Curtain",
    "リビングのハブミニ": "Living Hub", 
    "リビングのリモートボタン": "Living Remote",
    "カーテン 0F": "0F Curtain",

    # Office
    "仕事部屋のカーテン": "Office Curtain",
    "仕事部屋のハブミニ": "Office Hub",

    # Play Room
    "小部屋のハブミニ": "Play Room Hub",
    "小部屋の温湿度計": "Play Room Meter",
    
    # Bedroom
    "CO2センサー": "CO2 Meter",
    "寝室のカーテン": "Bedroom Curtain", 
    "寝室のハブミニ": "Bedroom Hub",
    "寝室のリモートボタン": "Bedroom Remote",

    # Kitchen
    "人感センサー キッチン": "Kitchen Motion",
    "コーヒー": "Coffee Bot",
    "換気扇": "Fan", 
    "Bath": "Bath Bot",


    # Balcony
    "ベランダの防水温湿度計": "Balcony Meter",
}

# Device place
DEVICE_PLACES = {
    "Living Room": ["Living Curtain", "Living Hub", "Living Remote", "0F Curtain"],
    "Office": ["Office Curtain", "Office Hub"],
    "Play Room": ["Play Room Hub", "Play Room Meter"],
    "Bedroom": ["CO2 Meter", "Bedroom Curtain", "Bedroom Hub", "Bedroom Remote"],
    "Kitchen": ["Kitchen Motion", "Bath Bot", "Coffee Bot", "Fan"],
    "Balcony": ["Balcony Meter"]
}

# Data storage configuration
DATA_FILE = "meter_data.json"
UPDATE_INTERVAL = 300  # 5 minutes in seconds
HOURLY_INTERVAL = 3600  # 1 hour in seconds
MAX_5MIN_SAMPLES = 12  # 1 hour worth of 5-minute samples
MAX_HOURLY_SAMPLES = 24  # 24 hours worth of hourly samples

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
        self.last_hourly_update = 0
        self.update_interval = UPDATE_INTERVAL if not pseudo_mode else 10
        self.need_refresh = True
        self.initialized = False
        self.pseudo_mode = pseudo_mode
        # Initialize LED
        self.led = LED
        self.led.off()  # Ensure LED is off initially
        
        # Load saved data if exists
        self.load_data()
        
        # Ensure WiFi connection if not in pseudo mode
        if not pseudo_mode:
            try:
                connect_wifi(SSID, PASSWORD)
            except Exception as e:
                print(f"WiFi connection error: {e}")
                raise

    def load_data(self):
        """Load saved meter data from file"""
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                self.meter_history = data.get('devices', {})
        except (OSError, ValueError):
            self.meter_history = {}

    def save_data(self):
        """Save meter data to file"""
        try:
            data = {'devices': self.meter_history}
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving data: {e}")

    def cleanup_old_data(self, device_id):
        """Remove data older than the retention period"""
        current_time = time.time()
        
        if device_id not in self.meter_history:
            self.meter_history[device_id] = {'5min_data': [], 'hourly_data': []}
            
        device_data = self.meter_history[device_id]
        
        # Cleanup 5-minute data (keep last hour)
        five_min_data = device_data.get('5min_data', [])
        five_min_data = [
            d for d in five_min_data
            if current_time - d['timestamp'] <= HOURLY_INTERVAL
        ][-MAX_5MIN_SAMPLES:]
        device_data['5min_data'] = five_min_data
        
        # Cleanup hourly data (keep last 24 hours)
        hourly_data = device_data.get('hourly_data', [])
        hourly_data = [
            d for d in hourly_data
            if current_time - d['timestamp'] <= HOURLY_INTERVAL * 24
        ][-MAX_HOURLY_SAMPLES:]
        device_data['hourly_data'] = hourly_data

    def generate_pseudo_data(self):
        """Generate pseudo data for testing"""
        # Create sample devices if not exists
        if not self.meters:
            self.meters = [
                {"deviceId": "meter1", "deviceName": "小部屋の温湿度計", "deviceType": "Meter"},
                {"deviceId": "meter2", "deviceName": "CO2センサー", "deviceType": "MeterPro(CO2)"},
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
            # Force garbage collection before API call
            import gc
            gc.collect()
            
            headers = get_auth_headers()
            response = requests.get(
                f"{API_BASE_URL}/devices",
                headers=headers
            )
            data = response.json()
            # Clean up response object to free memory
            response.close()
            
            if data.get("statusCode") == 100:
                self.devices = data["body"]["deviceList"]
                
                # Filter devices that contain "Meter" or "WoIOSensor" in their type
                self.meters = [d for d in self.devices if 
                             any(t in str(d.get("deviceType", "")) 
                                 for t in ["Meter", "WoIOSensor"])]
                # Clear devices list to free memory
                self.devices = []
                
                # Force garbage collection
                gc.collect()
                return True
            return False
        except Exception as e:
            print(f"Error getting devices: {e}")
            return False
        finally:
            # Force garbage collection
            gc.collect()

    def get_meter_status(self, device_id):
        try:
            # Force garbage collection before API call
            import gc
            gc.collect()
            
            headers = get_auth_headers()
            response = requests.get(
                f"{API_BASE_URL}/devices/{device_id}/status",
                headers=headers
            )
            data = response.json()
            # Clean up response object to free memory
            response.close()
            
            if data.get("statusCode") == 100:
                return data["body"]
            return None
        except Exception as e:
            print(f"Error getting meter status: {e}")
            return None
        finally:
            # Force garbage collection
            gc.collect()

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
                    status = self.get_meter_status(device_id)
                    
                    if status:
                        temp = status.get("temperature")
                        humidity = status.get("humidity")
                        co2 = status.get("CO2") if meter.get("deviceType") == "MeterPro(CO2)" else None
                        
                        # Create new data point
                        data_point = {
                            'timestamp': current_time,
                            'temperature': temp,
                            'humidity': humidity,
                            'co2': co2
                        }
                        
                        # Initialize device data if not exists
                        if device_id not in self.meter_history:
                            self.meter_history[device_id] = {'5min_data': [], 'hourly_data': []}
                        
                        # Add 5-minute data
                        self.meter_history[device_id]['5min_data'].append(data_point)
                        
                        # Check if it's time for hourly update
                        if current_time - self.last_hourly_update >= HOURLY_INTERVAL:
                            # Calculate hourly average from 5-minute data
                            five_min_data = self.meter_history[device_id]['5min_data']
                            if five_min_data:
                                hourly_avg = {
                                    'timestamp': current_time,
                                    'temperature': sum(d['temperature'] for d in five_min_data) / len(five_min_data),
                                    'humidity': sum(d['humidity'] for d in five_min_data) / len(five_min_data),
                                    'co2': sum(d['co2'] for d in five_min_data) / len(five_min_data) if co2 is not None else None
                                }
                                self.meter_history[device_id]['hourly_data'].append(hourly_avg)
                        
                        # Cleanup old data
                        self.cleanup_old_data(device_id)
                    
                    # Force garbage collection after each meter
                    import gc
                    gc.collect()
                
                # Update hourly timestamp if needed
                if current_time - self.last_hourly_update >= HOURLY_INTERVAL:
                    self.last_hourly_update = current_time
                
                # Save data to file
                self.save_data()
        
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
        draw_button(self.lcd, REFRESH_BUTTON, BUTTON_COLOR, "Refresh", TEXT_COLOR)
                
        # Draw room buttons
        for room_name, (x, y) in ROOM_BUTTONS.items():
            button = (x, y, BUTTON_WIDTH, BUTTON_HEIGHT)
            self.lcd.fill_rectangle(x, y, BUTTON_WIDTH, BUTTON_HEIGHT, BUTTON_COLOR)
            
            # Draw room name at the top of the button
            name_y = y + 10
            text_x = x + (BUTTON_WIDTH - len(room_name) * 8) // 2
            self.lcd.draw_text(text_x, name_y, room_name, TEXT_COLOR, BUTTON_COLOR)
            
            # Find meters in this room
            room_devices = DEVICE_PLACES.get(room_name, [])
            meter_values = []
            
            # Get meter values for the room
            for device_name in room_devices:
                for meter in self.meters:
                    if DEVICE_NAMES.get(meter.get("deviceName", "")) == device_name:
                        device_id = meter.get("deviceId")
                        if device_id in self.meter_history:
                            device_data = self.meter_history[device_id]
                            five_min_data = device_data.get('5min_data', [])
                            if five_min_data:
                                latest = five_min_data[-1]
                                temp = latest['temperature']
                                humidity = latest['humidity']
                                co2 = latest.get('co2')
                                meter_values.append((temp, humidity, co2))
            
            # Display meter values if available
            if meter_values:
                y_offset = 35  # Start values lower in the button
                for temp, humidity, co2 in meter_values:
                    # Temperature
                    temp_text = f"{temp:.1f}C"
                    temp_x = x + (BUTTON_WIDTH - len(temp_text) * 8) // 2
                    self.lcd.draw_text(temp_x, y + y_offset, temp_text,
                                     TEMPERATURE_COLOR, BUTTON_COLOR)
                    
                    # Humidity
                    humid_text = f"{humidity:.0f}%"
                    humid_x = x + (BUTTON_WIDTH - len(humid_text) * 8) // 2
                    self.lcd.draw_text(humid_x, y + y_offset + 20, humid_text,
                                     HUMIDITY_COLOR, BUTTON_COLOR)
                    
                    # CO2 if available
                    if co2 is not None:
                        co2_text = f"{co2:.0f}ppm"
                        co2_x = x + (BUTTON_WIDTH - len(co2_text) * 8) // 2
                        self.lcd.draw_text(co2_x, y + y_offset + 40, co2_text,
                                         CO2_COLOR, BUTTON_COLOR)
                    y_offset += 70  # Increase offset for next meter if any

        
        # Draw last update time
        self.draw_last_update_time()

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
        # Redraw the entire screen as we need to update all room buttons
        self.draw_initial_screen()

    def draw_graph(self, device_data, title, view_mode='5min'):
        """Draw a graph of temperature, humidity, and CO2 history
        
        Args:
            device_data (dict): Dictionary containing '5min_data' and 'hourly_data'
            title (str): Title to display
            view_mode (str): Either '5min' or 'hourly'
        """
        # Clear the screen with background color
        self.lcd.clear_display(BACKGROUND_COLOR)
        
        # Get the appropriate data based on view mode
        history_data = device_data.get(f'{view_mode}_data', [])
        
        # Filter data to show only the desired time range
        current_time = time.time()
        if view_mode == '5min':
            time_range = HOURLY_INTERVAL  # 1 hour
        else:
            time_range = HOURLY_INTERVAL * 24  # 24 hours
            
        history_data = [
            d for d in history_data
            if current_time - d['timestamp'] <= time_range
        ]
        
        # Get current values from the latest data point
        if history_data:
            latest = history_data[-1]
            current_temp = latest['temperature']
            current_humidity = latest['humidity']
            current_co2 = latest.get('co2')
            # Create title with current values
            if current_co2 is not None:
                value_text = f"{title}: {current_temp:.1f}C {current_humidity:.0f}% {current_co2:.0f}ppm"
            else:
                value_text = f"{title}: {current_temp:.1f}C {current_humidity:.0f}%"
        else:
            value_text = title
        
        # Draw title
        title_x = 10
        title_y = 10
        title_w = SCREEN_WIDTH - 20
        title_h = 30
        self.lcd.fill_rectangle(title_x, title_y, title_w, title_h, BUTTON_COLOR)
        text_x = title_x + (title_w - len(value_text) * 8) // 2
        text_y = title_y + (title_h - 8) // 2
        self.lcd.draw_text(text_x, text_y, value_text, TEXT_COLOR, BUTTON_COLOR)
        
        # Graph area dimensions
        GRAPH_X = 50
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
        if view_mode == '5min':
            # Draw ticks every 10 minutes for 1-hour view
            tick_interval = 10  # minutes
            num_ticks = 6  # 0, 10, 20, 30, 40, 50, 60 minutes
        else:
            # Draw ticks every 4 hours for 24-hour view
            tick_interval = 4  # hours
            num_ticks = 6  # 0, 4, 8, 12, 16, 20, 24 hours
        
        for i in range(num_ticks + 1):
            minutes_ago = i * tick_interval * (60 if view_mode == 'hourly' else 1)
            x = GRAPH_X + GRAPH_WIDTH - (minutes_ago * GRAPH_WIDTH // time_range)
            # Draw tick mark
            self.lcd.fill_rectangle(x, GRAPH_Y + GRAPH_HEIGHT - 5, 1, 5, TEXT_COLOR)
            # Draw time label
            tick_time = time.localtime(current_time - minutes_ago * 60)
            time_str = "{:02d}:{:02d}".format(tick_time[3], tick_time[4])
            self.lcd.draw_text(x - 20, GRAPH_Y + GRAPH_HEIGHT + 5, time_str, TEXT_COLOR, BACKGROUND_COLOR)
        
        # Get min/max values for scaling
        temps = [data['temperature'] for data in history_data if data['temperature'] is not None]
        humids = [data['humidity'] for data in history_data if data['humidity'] is not None]
        co2s = [data['co2'] for data in history_data if data.get('co2') is not None]
        
        if not temps or not humids:
            return
            
        temp_min, temp_max = min(temps), max(temps)
        humid_min, humid_max = min(humids), max(humids)
        
        # Add some padding to min/max and ensure non-zero range
        temp_range = max(1, temp_max - temp_min)
        humid_range = max(1, humid_max - humid_min)
        
        # Adjust min/max with padding
        temp_padding = temp_range * 0.1
        humid_padding = humid_range * 0.1
        temp_min -= temp_padding
        temp_max += temp_padding
        humid_min -= humid_padding
        humid_max += humid_padding
        
        # CO2 scaling if available
        if co2s:
            co2_min, co2_max = min(co2s), max(co2s)
            co2_range = max(1, co2_max - co2_min)
            co2_padding = co2_range * 0.1
            co2_min -= co2_padding
            co2_max += co2_padding

        # Draw data points and connect them with lines
        for i in range(len(history_data)):
            # Calculate x position based on timestamp
            data = history_data[i]
            time_diff = current_time - data['timestamp']
            x = GRAPH_X + GRAPH_WIDTH - int(time_diff * GRAPH_WIDTH / time_range)
            
            # Temperature
            if data['temperature'] is not None:
                if temp_max == temp_min:
                    y = GRAPH_Y + GRAPH_HEIGHT // 2
                else:
                    y = GRAPH_Y + GRAPH_HEIGHT - int((data['temperature'] - temp_min) * GRAPH_HEIGHT / (temp_max - temp_min))
                self.lcd.fill_rectangle(x-1, y-1, 3, 3, TEMPERATURE_COLOR)
                
                # Draw line to next point if exists
                if i < len(history_data) - 1:
                    next_data = history_data[i + 1]
                    next_time_diff = current_time - next_data['timestamp']
                    next_x = GRAPH_X + GRAPH_WIDTH - int(next_time_diff * GRAPH_WIDTH / time_range)
                    if next_data['temperature'] is not None:
                        if temp_max == temp_min:
                            next_y = GRAPH_Y + GRAPH_HEIGHT // 2
                        else:
                            next_y = GRAPH_Y + GRAPH_HEIGHT - int((next_data['temperature'] - temp_min) * GRAPH_HEIGHT / (temp_max - temp_min))
                        # Draw diagonal line
                        dx = abs(next_x - x)
                        dy = abs(next_y - y)
                        if dx > dy:
                            steps = dx
                        else:
                            steps = dy
                        if steps > 0:
                            x_inc = (next_x - x) / steps
                            y_inc = (next_y - y) / steps
                            curr_x = x
                            curr_y = y
                            for _ in range(int(steps)):
                                self.lcd.fill_rectangle(int(curr_x), int(curr_y), 2, 2, TEMPERATURE_COLOR)
                                curr_x += x_inc
                                curr_y += y_inc
            
            # Humidity
            if data['humidity'] is not None:
                if humid_max == humid_min:
                    y = GRAPH_Y + GRAPH_HEIGHT // 2
                else:
                    y = GRAPH_Y + GRAPH_HEIGHT - int((data['humidity'] - humid_min) * GRAPH_HEIGHT / (humid_max - humid_min))
                self.lcd.fill_rectangle(x-1, y-1, 3, 3, HUMIDITY_COLOR)
                
                # Draw line to next point if exists
                if i < len(history_data) - 1:
                    next_data = history_data[i + 1]
                    next_time_diff = current_time - next_data['timestamp']
                    next_x = GRAPH_X + GRAPH_WIDTH - int(next_time_diff * GRAPH_WIDTH / time_range)
                    if next_data['humidity'] is not None:
                        if humid_max == humid_min:
                            next_y = GRAPH_Y + GRAPH_HEIGHT // 2
                        else:
                            next_y = GRAPH_Y + GRAPH_HEIGHT - int((next_data['humidity'] - humid_min) * GRAPH_HEIGHT / (humid_max - humid_min))
                        # Draw diagonal line
                        dx = abs(next_x - x)
                        dy = abs(next_y - y)
                        if dx > dy:
                            steps = dx
                        else:
                            steps = dy
                        if steps > 0:
                            x_inc = (next_x - x) / steps
                            y_inc = (next_y - y) / steps
                            curr_x = x
                            curr_y = y
                            for _ in range(int(steps)):
                                self.lcd.fill_rectangle(int(curr_x), int(curr_y), 2, 2, HUMIDITY_COLOR)
                                curr_x += x_inc
                                curr_y += y_inc
            
            # CO2
            if data.get('co2') is not None:
                if co2_max == co2_min:
                    y = GRAPH_Y + GRAPH_HEIGHT // 2
                else:
                    y = GRAPH_Y + GRAPH_HEIGHT - int((data['co2'] - co2_min) * GRAPH_HEIGHT / (co2_max - co2_min))
                self.lcd.fill_rectangle(x-1, y-1, 3, 3, CO2_COLOR)
                
                # Draw line to next point if exists
                if i < len(history_data) - 1:
                    next_data = history_data[i + 1]
                    next_time_diff = current_time - next_data['timestamp']
                    next_x = GRAPH_X + GRAPH_WIDTH - int(next_time_diff * GRAPH_WIDTH / time_range)
                    if next_data.get('co2') is not None:
                        if co2_max == co2_min:
                            next_y = GRAPH_Y + GRAPH_HEIGHT // 2
                        else:
                            next_y = GRAPH_Y + GRAPH_HEIGHT - int((next_data['co2'] - co2_min) * GRAPH_HEIGHT / (co2_max - co2_min))
                        # Draw diagonal line
                        dx = abs(next_x - x)
                        dy = abs(next_y - y)
                        if dx > dy:
                            steps = dx
                        else:
                            steps = dy
                        if steps > 0:
                            x_inc = (next_x - x) / steps
                            y_inc = (next_y - y) / steps
                            curr_x = x
                            curr_y = y
                            for _ in range(int(steps)):
                                self.lcd.fill_rectangle(int(curr_x), int(curr_y), 2, 2, CO2_COLOR)
                                curr_x += x_inc
                                curr_y += y_inc
        
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
        draw_button(self.lcd, (10, SCREEN_HEIGHT - 30, 60, 20), BUTTON_COLOR, "Back", TEXT_COLOR)
        
        # Draw view mode toggle button
        toggle_text = "24h" if view_mode == '5min' else "1h"
        draw_button(self.lcd, (80, SCREEN_HEIGHT - 30, 60, 20), BUTTON_COLOR, toggle_text, TEXT_COLOR)
        
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

                # Check view mode toggle button
                bx, by, bw, bh = (80, SCREEN_HEIGHT - 30, 60, 20)
                if (bx <= x < bx + bw) and (by <= y < by + bh):
                    # Toggle view mode
                    self.current_view_mode = 'hourly' if self.current_view_mode == '5min' else '5min'
                    # Redraw graph with new view mode
                    self.draw_graph(self.meter_history[self.current_device_id], 
                                  self.current_device_name,
                                  self.current_view_mode)
                    time.sleep_ms(100)
                    self.lcd.clear_touch()
                    return
                continue
            
            # Check refresh button
            bx, by, bw, bh = REFRESH_BUTTON
            if (bx <= x < bx + bw) and (by <= y < by + bh):
                # Visual feedback - change button color and turn on LED
                draw_button(self.lcd, REFRESH_BUTTON, BUTTON_ACTIVE_COLOR, "Refresh", TEXT_COLOR)
                self.led.on()  # Turn on LED
                
                if self.get_devices():
                    self.update_meter_display()  # Only update the values
                
                # Return to original color and turn off LED
                draw_button(self.lcd, REFRESH_BUTTON, BUTTON_COLOR, "Refresh", TEXT_COLOR)
                self.led.off()  # Turn off LED
                time.sleep_ms(100)
                self.lcd.clear_touch()
                return
            
            # Check room buttons
            for room_name, (bx, by) in ROOM_BUTTONS.items():
                if (bx <= x < bx + BUTTON_WIDTH) and (by <= y < by + BUTTON_HEIGHT):
                    # Find meter in this room
                    room_devices = DEVICE_PLACES.get(room_name, [])
                    for device_name in room_devices:
                        for meter in self.meters:
                            if DEVICE_NAMES.get(meter.get("deviceName", "")) == device_name:
                                device_id = meter.get("deviceId")
                                if device_id in self.meter_history:
                                    self.showing_graph = True
                                    self.current_device_id = device_id
                                    self.current_device_name = device_name
                                    self.current_view_mode = '5min'  # Reset to 5-minute view
                                    self.draw_graph(self.meter_history[device_id], device_name, self.current_view_mode)
                    time.sleep_ms(100)
                    self.lcd.clear_touch()
                    return
                    break

    def run(self):
        if self.get_devices():
            # Initial data collection and complete draw
            self.update_meter_history()
            self.draw_initial_screen()
            
            # Keep track of current device and view mode
            self.current_device_id = None
            self.current_device_name = None
            self.current_view_mode = '5min'  # Default to 5-minute view
            
            while True:
                # Update data if needed
                if self.update_meter_history():
                    if hasattr(self, 'showing_graph') and self.showing_graph and self.current_device_id:
                        # Redraw graph with updated data
                        self.draw_graph(self.meter_history[self.current_device_id],
                                      self.current_device_name,
                                      self.current_view_mode)
                    else:
                        self.update_meter_display()
                
                # Handle touch events
                self.handle_touch()
                
                time.sleep_ms(10)

if __name__ == "__main__":
    # Use pseudo_mode=True for testing without actual API calls
    display = SwitchBotDisplay(pseudo_mode=False)
    display.run() 