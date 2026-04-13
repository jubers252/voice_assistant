import socket
import json
import time
import serial
import sys
import threading

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

        
    def read_serial(self, port='/dev/ttyAMA0', baudrate=115200, timeout=1.0):
        """
        Read serial data and print it.
        
        Args:
            port: Serial port (default: /dev/ttyAMA0 for Pi GPIO UART)
            baudrate: Baud rate (default: 115200 for HMMD-mmWave)
            timeout: Read timeout in seconds
        """
        try:
            # Open serial port
            ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
            print(f"Connected to {port} at {baudrate} baud")
            
            # Read and print
            while True:
                if ser.in_waiting > 0:
                    data = ser.readline()
                    raw_str = data.decode('utf-8', errors='ignore').strip()
                    print(raw_str)
                    if "OFF" in raw_str:
                        status = self.get_status()
                        self.send_cmd({"light": False, "fan": False, "zero": False})
                        print(f"Motion not detected: {raw_str}")
                        break
                
                    
        except KeyboardInterrupt:
            print("\n\nStopped by user")
        except serial.SerialException as e:
            print(f"Error: {e}")
            print(f"Check: port exists (ls /dev/ttyAMA0) and UART is enabled (sudo raspi-config)")
        finally:
            if 'ser' in locals() and ser.is_open:
                ser.close()
                print("Serial port closed")


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


class MotionControlThread(threading.Thread):
    """Motion monitor: Turn ON/OFF based on range with state saving"""
    
    def __init__(self, home_automation, port='/dev/ttyAMA0', baudrate=115200, 
                 min_range=100, max_range=250, timeout=15):
        super().__init__(daemon=True)
        self.home = home_automation
        self.port = port
        self.baudrate = baudrate
        self.min_range = min_range      # Turn ON if range < min_range
        self.max_range = max_range      # Turn OFF if range > max_range
        self.timeout = timeout
        self.running = False
        self.last_motion_time = None
        self.devices_on = False
        self.saved_state = None         # Save device state before turning off
    
    def run(self):
        self.running = True
        print(f"Motion monitor started")
        print(f"  Turn ON if: range < {self.min_range}cm")
        print(f"  Turn OFF if: range > {self.max_range}cm for {self.timeout}s\n")
        
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
            print(f"Connected to {self.port}\n")
            
            while self.running:
                # Check timeout: turn OFF if out of range for X seconds
                if self.last_motion_time and (time.time() - self.last_motion_time) >= self.timeout:
                    if self.devices_on:
                        print(f"Timeout reached - Turning OFF devices")
                        self.saved_state = self.home.get_status()
                        self.home.send_cmd({"light": False, "fan": False, "zero": False})
                        self.devices_on = False
                    self.last_motion_time = None
                
                # Read serial data
                if ser.in_waiting > 0:
                    data = ser.readline()
                    msg = data.decode('utf-8', errors='ignore').strip()
                    
                    if msg:
                        print(f"[RAW] '{msg}'")
                        
                        # Try to extract range from message
                        current_range = None
                        try:
                            # Split message and find "Range"
                            words = msg.split()
                            for i, word in enumerate(words):
                                if "range" in word.lower():
                                    # Next word should be the number
                                    if i + 1 < len(words):
                                        current_range = int(words[i + 1])
                                    break
                            
                            # If not found, try last word as number
                            if current_range is None:
                                current_range = int(words[-1])
                        except:
                            current_range = None
                        
                        if current_range is not None:
                            if current_range < self.min_range:
                                # Motion detected - turn ON
                                self.last_motion_time = None
                                if not self.devices_on:
                                    if self.saved_state:
                                        self.home.send_cmd(self.saved_state)
                    
                                    self.devices_on = True
                                    print(f"Motion detected - Turning ON")
                            elif current_range > self.max_range:
                                # Out of range - start timer
                                if not self.last_motion_time:
                                    self.last_motion_time = time.time()
                                    print(f"Out of range - Timer started ({self.timeout}s)")
                            else:
                                # In between range - keep ON if already ON
                                if self.devices_on:
                                    self.last_motion_time = None
                
                time.sleep(0.05)
        
        except Exception as e:
            print(f"Error: {e}")
        finally:
            try:
                ser.close()
            except:
                pass
    
    def stop(self):
        self.running = False



if __name__ == "__main__":
    home = HomeAutomation()
    
    motion = MotionControlThread(
        home, 
        port='/dev/ttyAMA0', 
        baudrate=115200, 
        min_range=200,      # Turn ON if range < 150cm
        max_range=400,      # Turn OFF if range > 350cm
        timeout=60         # Turn OFF after 10s out of range
    )
    motion.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        motion.stop()
        print("Done")
