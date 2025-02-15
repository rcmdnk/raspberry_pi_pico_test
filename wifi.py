import network
import time


def connect_wifi(ssid, password):
    """Connect to WiFi with the given SSID and password.
    
    Args:
        ssid (str): WiFi SSID
        password (str): WiFi password
        
    Returns:
        network.WLAN: The WLAN interface object
        
    Raises:
        RuntimeError: If connection fails
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to WiFi...')
        wlan.connect(ssid, password)
        # Wait for connection with timeout
        max_wait = 10
        while max_wait > 0:
            if wlan.status() < 0 or wlan.status() >= 3:
                break
            max_wait -= 1
            print('Waiting for connection...')
            time.sleep(1)
            
        if wlan.status() != 3:
            raise RuntimeError('Network connection failed')
    print('Connected to WiFi')
    print('IP:', wlan.ifconfig()[0])
    return wlan 