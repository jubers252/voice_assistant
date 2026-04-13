#!/usr/bin/env python3
"""
Simple Serial Data Reader
Just read and print serial data - nothing fancy
"""
import serial
import sys


def read_serial(port='/dev/ttyAMA0', baudrate=115200, timeout=1.0):
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


if __name__ == "__main__":
    # Optional: accept port and baud rate as arguments
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyAMA0'
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
    
    read_serial(port=port, baudrate=baudrate)
