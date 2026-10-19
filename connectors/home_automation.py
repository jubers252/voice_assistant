import socket
import json

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

        
    def send_cmd(self, payload: dict) -> bool:
        """
        Send command to ESP device.
        
        Args:
            payload: Dictionary containing device states (e.g., {"light": True, "fan": False})
            
        Returns:
            True if sent successfully, False otherwise
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
            print(f"Sent: {payload}")
            return True
        except Exception as e:
            print(f"Failed to send {payload}: {e}")
            return False
        finally:
            s.close()

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
