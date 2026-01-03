import socket
import json
import time


class HomeAutomation:
    """ESP-based home automation controller for managing lights, fans, and other devices."""
    
    def __init__(self, esp_ip: str = "192.168.1.90", port: int = 80):
        """
        Initialize HomeAutomation controller.
        
        Args:
            esp_ip: IP address of the ESP device
            port: Port number for the ESP device
        """
        self.esp_ip = esp_ip
        self.port = port

    def send_cmd(self, payload: dict) -> None:
        """
        Send command to ESP device (fire-and-forget).
        
        Args:
            payload: Dictionary containing device states (e.g., {"light": True, "fan": False})
        """
        body = json.dumps(payload)

        req = (
            "POST /api/set HTTP/1.1\r\n"
            "Host: {}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n\r\n{}"
        ).format(self.esp_ip, len(body), body)

        s = socket.socket()
        s.settimeout(1)
        try:
            s.connect((self.esp_ip, self.port))
            s.sendall(req.encode())
        except Exception as e:
            pass 
        finally:
            s.close()
        print("Sent:", payload)

    def get_status(self) -> dict:
        """
        Get current status of all devices from ESP.
        
        Returns:
            Dictionary containing device states, or None if request fails
        """
        req = (
            "GET /api/status HTTP/1.1\r\n"
            "Host: {}\r\n"
            "Connection: close\r\n\r\n"
        ).format(self.esp_ip)

        s = socket.socket()
        s.settimeout(2)
        try:
            s.connect((self.esp_ip, self.port))
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
    # Initialize the home automation controller
    home = HomeAutomation()
    
    # Send command to control devices
    home.send_cmd({"light": True, "fan": False, "zero": False})
    time.sleep(0.5)
    
    # Get current device status
    status = home.get_status()
    print("Current ESP State:", status)
