import time
import network

ssid = "<SSID>"
password = "<PASSWORD>"

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(ssid, password)

max_wait = 10
while max_wait > 0:
    if wlan.status() < 0 or wlan.status() >= 3:
        break
    max_wait -= 1
    print("waiting for connection...")
    time.sleep(1)

if wlan.status() != 3:
    raise RuntimeError("network connection failed")
else:
    print("connected")


ifconfig = wlan.ifconfig()
print('IP address   :', ifconfig[0])
print('Subnet mask  :', ifconfig[1])
print('Gateway      :', ifconfig[2])
print('DNS server   :', ifconfig[3])
mac = ubinascii.hexlify(wlan.config('mac'), ':').decode()
print('MAC address  :', mac)
print('SSID         :', wlan.config('ssid'))
print('Channel      :', wlan.config('channel'))
print('Security     :', wlan.config('security'))
print('Hostname     :', wlan.config('hostname'))
print('TX Power     :', wlan.config('txpower'))
print('PM           :', wlan.config('pm'))
