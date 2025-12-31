import socket
import json
import time

ESP_IP = "192.168.1.90"
PORT = 80

# ---------------- POST COMMAND (fire-and-forget) ----------------
def send_cmd(payload):
    body = json.dumps(payload)

    req = (
        "POST /api/set HTTP/1.1\r\n"
        "Host: {}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n\r\n{}"
    ).format(ESP_IP, len(body), body)

    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect((ESP_IP, PORT))
        s.sendall(req.encode())
    except Exception as e:
        pass 
    finally:
        s.close()
    print("Sent:", payload)

# ---------------- GET STATUS ----------------
def get_status():
    req = (
        "GET /api/status HTTP/1.1\r\n"
        "Host: {}\r\n"
        "Connection: close\r\n\r\n"
    ).format(ESP_IP)

    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect((ESP_IP, PORT))
        s.send(req.encode())
        data = s.recv(1024)  
        body = data.decode().split("\r\n\r\n")[-1]
        return json.loads(body)
    except Exception as e:
        print("Ignored:", e)
        return None
    finally:
        s.close()

if __name__ == "__main__":
# ---------------- EXAMPLES ----------------
    send_cmd({"light": True, "fan": False, "zero": False})
    time.sleep(0.5)
    status = get_status()
    print("Current ESP State:", status)
