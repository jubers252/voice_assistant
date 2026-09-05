# wifi_config.py
import network, socket, ujson, machine, time

CONFIG_FILE = "wifi.json"

# Global WiFi config for reconnection purposes
cfg = {}

HTML_FORM = """<!DOCTYPE html>
<html>
<head><title>ESP WiFi Config</title></head>
<body>
<h2>Configure Wi-Fi</h2>
<form method="POST">
SSID:<br><input name="ssid"><br>
Password:<br><input name="password" type="password"><br><br>
<input type="submit" value="Save">
</form>
</body>
</html>
"""

HTML_OK = """<!DOCTYPE html>
<html>
<body>
<h3>✅ Wi-Fi saved</h3>
<p>Device will reboot now…</p>
</body>
</html>
"""

# -------------------------------------------------
# Try to connect using saved credentials (STA mode)
# -------------------------------------------------
def connect_wifi(static_ip=None, subnet=None, gateway=None, dns=None, timeout=20):
    global cfg
    try:
        with open(CONFIG_FILE) as f:
            cfg = ujson.load(f)
        ssid = cfg["ssid"]
        password = cfg["password"]
    except:
        print("No saved Wi-Fi config")
        return False

    wlan = network.WLAN(network.STA_IF)
    
    # Ensure clean state - disconnect and deactivate first
    try:
        wlan.disconnect()
    except:
        pass
    
    time.sleep(0.5)
    wlan.active(False)
    time.sleep(0.5)
    wlan.active(True)
    time.sleep(1)  # Allow time for interface to activate

    if static_ip:
        wlan.ifconfig((static_ip, subnet, gateway, dns))

    print("Connecting to Wi-Fi:", ssid)
    wlan.connect(ssid, password)

    start = time.time()
    while not wlan.isconnected() and time.time() - start < timeout:
        time.sleep(1)

    if wlan.isconnected():
        print("Wi-Fi connected:", wlan.ifconfig())
        return True
    else:
        print("Wi-Fi connection failed after", timeout, "seconds")
        # Don't deactivate on failure - let it retry
        return False

# -----------------------
# Start Access Point mode
# -----------------------
def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)

    # OPEN AP = most reliable on ESP8266
    ap.config(essid="ESP_Config_1234")
    time.sleep(1)

    print("AP mode started")
    print("Connect to SSID: ESP_Config_1234")
    print("Open: http://192.168.4.1")
    return ap

# -----------------------
# Save Wi-Fi credentials
# -----------------------
def save_wifi(ssid, password):
    print("Saving Wi-Fi:", ssid)
    with open(CONFIG_FILE, "w") as f:
        ujson.dump({"ssid": ssid, "password": password}, f)
    time.sleep(2)
    machine.reset()

def url_decode(s):
    res = ""
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                res += chr(int(s[i+1:i+3], 16))
                i += 3
            except:
                res += s[i]
                i += 1
        elif s[i] == "+":
            res += " "
            i += 1
        else:
            res += s[i]
            i += 1
    return res

# ---------------------------------
# Configuration web server (AP mode)
# ---------------------------------
def start_config_server():
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    s = socket.socket()
    s.bind(addr)
    s.listen(1)

    print("Config portal running")

    while True:
        conn, addr = s.accept()
        print("Client:", addr)

        conn.settimeout(2)
        req = b""

        try:
            while True:
                data = conn.recv(512)
                if not data:
                    break
                req += data
                if b"\r\n\r\n" in req:
                    break
        except:
            pass

        req = req.decode()
        body = ""

        if "\r\n\r\n" in req:
            body = req.split("\r\n\r\n", 1)[1]

        # -------- POST --------
        if req.startswith("POST") and body:
            params = {}
            for pair in body.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = url_decode(v)
                 

            if "ssid" in params and "password" in params:
                conn.send(
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html\r\n"
                    "Connection: close\r\n\r\n"
                    + HTML_OK
                )
                conn.close()
                save_wifi(params["ssid"], params["password"])
                return

        # -------- GET --------
        conn.send(
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n\r\n"
            + HTML_FORM
        )
        conn.close()

