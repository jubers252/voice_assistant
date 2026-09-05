# boot.py - Runs on every startup before main.py
import wifi_config
import webrepl
import time

# Auto-start WebREPL on boot (before main.py)
print("Enabling WebREPL on boot...")
try:
    webrepl.start(password="esp32repl")
    print("WebREPL enabled - ready for remote connection")
except Exception as e:
    print("WebREPL init error:", e)

# Give WebREPL time to start
time.sleep(1)
