# main.py
import network
import socket
import time
import json
import machine
from machine import Pin, freq

from ir_rx.nec import NEC_16
from ir_rx.print_error import print_error
import wifi_config

# WebREPL for remote programming
try:
    import webrepl
except ImportError:
    print("WebREPL not available")
    webrepl = None

# ===== CPU SPEED =====
freq(160000000)

# ===== STATIC IP CONFIG =====
STATIC_IP = "192.168.1.90"
SUBNET    = "255.255.255.0"
GATEWAY   = "192.168.1.1"
DNS       = "8.8.8.8"

# ===== PINS =====
IR_PIN    = 13   # D7
LIGHT_PIN = 12    # D2
FAN_PIN   = 4    # D1
ZERO_PIN  = 5    # D6

# Active LOW relays
light = Pin(LIGHT_PIN, Pin.OUT, value=1)
fan   = Pin(FAN_PIN,   Pin.OUT, value=1)
zero  = Pin(ZERO_PIN,  Pin.OUT, value=1)

# ===== STATE =====
state = {
    "light": False,
    "fan": False,
    "zero": False
}

def apply_state():
    # active-low logic
    light.value(1 if state["light"] else 0)
    fan.value(1 if state["fan"] else 0)
    zero.value(1 if state["zero"] else 0)

apply_state()

# ===== IR CALLBACK =====
last_time = 0

def ir_cb(data, addr, ctrl):
    global last_time

    if data < 0:
        return  # ignore repeat

    now = time.ticks_ms()
    if time.ticks_diff(now, last_time) < 300:
        return
    last_time = now

    print("NEC16:", hex(data), "ADDR:", hex(addr))

    if data == 0x0A:
        state["light"] = not state["light"]
    elif data == 0x1B:
        state["fan"] = not state["fan"]
    elif data == 0x1F:
        state["zero"] = not state["zero"]

    apply_state()

# ===== IR INIT =====
ir = NEC_16(Pin(IR_PIN, Pin.IN), ir_cb)
ir.error_function(print_error)
print("NEC16 IR ready")

# ===== WIFI CONNECT =====
wlan = network.WLAN(network.STA_IF)
wifi_connected = False
last_wifi_check = 0
wifi_reconnect_delay = 5  # seconds between reconnection attempts
wifi_retry_count = 0
MAX_WIFI_RETRIES = 3

# Attempt WiFi connection with retries
for attempt in range(MAX_WIFI_RETRIES):
    print(f"WiFi connection attempt {attempt + 1}/{MAX_WIFI_RETRIES}...")
    if wifi_config.connect_wifi(
            STATIC_IP,
            SUBNET,
            GATEWAY,
            DNS,
            timeout=30  # Increased timeout for post-reset stability
        ):
        wifi_connected = True
        print("Wi-Fi connected:", wlan.ifconfig()[0])
        break
    else:
        if attempt < MAX_WIFI_RETRIES - 1:
            print(f"Retry {attempt + 1} failed, waiting 2s before retry...")
            time.sleep(2)
else:
    # All retries exhausted
    print("Wi-Fi failed → starting AP mode")
    wifi_config.start_ap()
    wifi_config.start_config_server()
    
    # ===== WEBREPL INIT =====
    if webrepl:
        try:
            # Start WebREPL on port 8266 with password
            # Password is stored in webrepl_cfg.py if it exists
            webrepl.start(password="esp32repl")
            print("WebREPL started on port 8266")
            print("Connect with: webrepl-cli.py ws://192.168.1.90:8266")
        except Exception as e:
            print("WebREPL error:", e)

# ===== WEB SERVER =====
addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
s = socket.socket()
s.bind(addr)
s.listen(1)
s.settimeout(1)

print("Web server running")

# ===== WIFI HEALTH CHECK =====
def check_and_maintain_wifi():
    global wifi_connected, last_wifi_check, wifi_reconnect_delay
    
    now = time.ticks_ms()
    # Check WiFi status every 10 seconds
    if time.ticks_diff(now, last_wifi_check) < 10000:
        return
    
    last_wifi_check = now
    
    if not wlan.isconnected():
        if wifi_connected:
            print("WiFi disconnected!")
            wifi_connected = False
        
        # Try to reconnect
        print("Attempting WiFi reconnection...")
        try:
            # Ensure clean state before reconnection
            wlan.disconnect()
            time.sleep(0.5)
            wlan.connect(wifi_config.cfg["ssid"], wifi_config.cfg["password"])
            time.sleep(3)
            if wlan.isconnected():
                wifi_connected = True
                print("WiFi reconnected:", wlan.ifconfig()[0])
            else:
                print("WiFi reconnection attempt failed")
        except Exception as e:
            print("Reconnection failed:", e)
    else:
        if not wifi_connected:
            wifi_connected = True
            print("WiFi restored:", wlan.ifconfig()[0])

# ===== MAIN LOOP =====
while True:
    try:
        # Check WiFi health periodically
        check_and_maintain_wifi()
        
        conn, addr = s.accept()
        req = conn.recv(1024).decode()
        handled = False  # Track if request was handled

        if "\r\n\r\n" in req:
            headers, body = req.split("\r\n\r\n", 1)
        else:
            headers = req
            body = ""

        # ---------- JSON API ----------
        if headers.startswith("GET /api/status"):
            pass

        elif headers.startswith("GET /api/reset"):
            # Send reset confirmation response
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                "Connection: close\r\n\r\n" +
                json.dumps({"status": "resetting"})
            )
            conn.send(response)
            conn.close()
            handled = True
            print("Reset request received - rebooting device...")
            time.sleep(1)  # Give time for response to be sent
            machine.reset()
            # Code won't reach here after reset()


        elif headers.startswith("POST /api/set") and body:
            try:
                data = json.loads(body)
                for k in state:
                    if k in data:
                        state[k] = bool(data[k])
            except Exception as e:
                print("JSON error:", e)

        # ---------- Legacy query ----------
        else:
            if "light=on" in req:
                state["light"] = True
            elif "light=off" in req:
                state["light"] = False

            if "fan=on" in req:
                state["fan"] = True
            elif "fan=off" in req:
                state["fan"] = False

            if "zero=on" in req:
                state["zero"] = True
            elif "zero=off" in req:
                state["zero"] = False

        apply_state()

        # Don't send response if already handled (e.g., reset)
        if not handled:
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                "Connection: close\r\n\r\n" +
                json.dumps(state)
            )

            conn.send(response)
            conn.close()

    except OSError:
        pass
    except Exception as e:
        print("ERR:", e)

