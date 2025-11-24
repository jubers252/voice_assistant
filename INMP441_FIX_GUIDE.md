# INMP441 Microphone - Voice Detection Fix Guide

## Problem
Voice not being detected from 1 foot away with INMP441 I2S microphone on Raspberry Pi.

## Solutions Applied

### 1. **Suppressed ALSA/JACK Error Messages**
   - Added error suppression to prevent console spam
   - Errors are cosmetic - they don't affect functionality

### 2. **Optimized Energy Threshold Settings**
   - **Reduced from 400 to 150** - INMP441 is very sensitive
   - Added dynamic energy adjustment
   - Shorter pause thresholds for faster response

### 3. **Added Ambient Noise Calibration**
   - Automatically adjusts on first listen attempt
   - Calibrates to your specific environment

## Quick Tests

### Test 1: Check Microphone Levels (Real-time)
```bash
python test_inmp441_sensitivity.py
```
This will show real-time audio levels and help you see if the mic is picking up sound.

### Test 2: Check Hardware Configuration
```bash
./check_inmp441.sh
```
This verifies your INMP441 is properly configured at the hardware level.

## Expected Results

### Good Audio Levels
- **RMS > 0.01**: Excellent
- **RMS 0.003-0.01**: Good (should work)
- **RMS < 0.003**: Too quiet (hardware issue)

## If Voice Still Not Detected

### Step 1: Verify Hardware Wiring
```
INMP441 → Raspberry Pi
-----------------------
VDD  → 3.3V (Pin 1)
GND  → Ground (Pin 6)
SCK  → GPIO 18 (Pin 12)
WS   → GPIO 19 (Pin 35)
SD   → GPIO 20 (Pin 38)
L/R  → GND (for left channel)
```

### Step 2: Check /boot/config.txt
```bash
sudo nano /boot/config.txt
# or
sudo nano /boot/firmware/config.txt
```

Add this line:
```
dtoverlay=i2s-mems
```

Then reboot:
```bash
sudo reboot
```

### Step 3: Increase ALSA Capture Volume
```bash
alsamixer
```
- Press **F4** for Capture
- Use **↑** arrow to increase volume
- Press **ESC** to exit

### Step 4: Test with arecord
```bash
# Find your I2S card number
arecord -l

# Record a 5-second test (replace 'X' with your card number)
arecord -D plughw:X,0 -f S32_LE -r 16000 -c 1 -d 5 test.wav

# Play it back
aplay test.wav
```

### Step 5: Adjust Energy Threshold Manually

If the microphone is working but recognition fails, edit:
`speech/speech_recognizer.py`

```python
def _setup_recognizer(self):
    self.recognizer.energy_threshold = 100  # Try even lower (50-150)
```

## Advanced: Find Optimal Threshold

Run the sensitivity test and note the **Max RMS** value:
```bash
python test_inmp441_sensitivity.py
```

Then calculate:
```
optimal_threshold = Max_RMS × 10000 × 0.5
```

Example:
- Max RMS = 0.015
- Threshold = 0.015 × 10000 × 0.5 = **75**

Update in `speech_recognizer.py`:
```python
self.recognizer.energy_threshold = 75  # Your calculated value
```

## Verification

After fixes, test the voice assistant:
```bash
python voice_assistant.py
```

**Expected behavior:**
1. Should show calibration: `Energy threshold adjusted to: XXX`
2. When you speak from 1 foot: Should see `i m listening...`
3. After speaking: Should show `You said: ...`

## Common Issues & Fixes

| Issue | Solution |
|-------|----------|
| No audio detected | Check wiring, verify I2S overlay in config.txt |
| Audio too quiet | Run `alsamixer`, increase Capture volume |
| "Device not found" | Wrong device_index, use None for default |
| Recognition timeout | Lower energy_threshold to 50-100 |
| Words cut off | Increase `pause_threshold` to 1.0 |

## Files Modified
- `audio/audio_processor.py` - Added ALSA error suppression
- `speech/speech_recognizer.py` - Lowered thresholds, added calibration
- `voice_assistant.py` - Added error suppression for audio stream
- `test_inmp441_sensitivity.py` - New diagnostic tool
- `check_inmp441.sh` - New hardware verification script

## Support Commands

```bash
# View current energy threshold while running
# (it will print during calibration)

# List all audio devices
python -c "import speech_recognition as sr; print('\n'.join(f'{i}: {n}' for i, n in enumerate(sr.Microphone.list_microphone_names())))"

# Check sounddevice info
python -c "import sounddevice as sd; print(sd.query_devices())"
```
