#!/bin/bash
# Auto-launch browser for Voice Assistant Dashboard
# This script waits for the Flask server to be ready, then opens Chromium in kiosk mode

BROWSER_READY_FILE="/tmp/browser_launched"
MAX_WAIT=30
WAIT_TIME=0

echo "[BROWSER] Waiting for centralized_ui server to be ready..."

# Wait for port 5000 to be listening
while [ $WAIT_TIME -lt $MAX_WAIT ]; do
    if timeout 2 bash -c "</dev/tcp/localhost/5000" 2>/dev/null; then
        echo "[BROWSER] Server is ready on port 5000"
        break
    fi
    sleep 1
    WAIT_TIME=$((WAIT_TIME + 1))
done

if [ $WAIT_TIME -eq $MAX_WAIT ]; then
    echo "[BROWSER] Timeout waiting for server. Giving up."
    exit 1
fi

# Check if browser already launched (avoid multiple instances)
if [ -f "$BROWSER_READY_FILE" ]; then
    echo "[BROWSER] Browser already launched, skipping."
    exit 0
fi

# Wait a bit more to ensure Flask is fully ready
sleep 2

echo "[BROWSER] Launching Chromium..."

# Export DISPLAY for the user
export DISPLAY=:0
export XAUTHORITY=/home/pi/.Xauthority

# Try to launch Chromium (try multiple browser names)
for browser in chromium-browser chromium google-chrome; do
    if command -v "$browser" &> /dev/null; then
        echo "[BROWSER] Found $browser, launching..."
        nohup "$browser" \
            --kiosk \
            --start-fullscreen \
            --noerrdialogs \
            --disable-infobars \
            --no-first-run \
            --disable-session-crashed-bubble \
            --disable-translate \
            --check-for-update-interval=31536000 \
            --overscroll-history-navigation=0 \
            http://localhost:5000 > /tmp/browser.log 2>&1 &
        break
    fi
done

# Mark that browser has been launched
touch "$BROWSER_READY_FILE"

echo "[BROWSER] Browser launch command executed"
exit 0
