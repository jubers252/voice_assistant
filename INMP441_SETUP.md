# INMP441 I2S Microphone Setup Guide for Raspberry Pi

This guide will help you configure your INMP441 I2S MEMS microphone with the voice assistant on Raspberry Pi.

## Hardware Connection

The INMP441 connects to Raspberry Pi via I2S interface:

| INMP441 Pin | Raspberry Pi Pin | Description |
|-------------|------------------|-------------|
| VDD         | 3.3V (Pin 1)     | Power |
| GND         | GND (Pin 6)      | Ground |
| SD          | GPIO 18 (Pin 12) | Serial Data |
| WS          | GPIO 19 (Pin 35) | Word Select (LRCLK) |
| SCK         | GPIO 20 (Pin 38) | Serial Clock (BCLK) |
| L/R         | GND              | Left/Right channel select (GND = Left) |

## Software Setup

### 1. Enable I2S on Raspberry Pi

Edit `/boot/config.txt`:
```bash
sudo nano /boot/config.txt
```

Add or uncomment:
```
dtparam=i2s=on
```

Reboot:
```bash
sudo reboot
```

### 2. Install Required Packages

```bash
# Install ALSA utilities
sudo apt-get update
sudo apt-get install -y libasound2-dev alsa-utils

# Test I2S device is detected
arecord -l
```

You should see an I2S device listed (e.g., "simple-card" or "bcm2835-i2s").

### 3. Configure ALSA

Create or edit `~/.asoundrc`:
```bash
nano ~/.asoundrc
```

Add the following configuration:
```
pcm.!default {
    type asym
    playback.pcm {
        type plug
        slave.pcm "hw:0,0"
    }
    capture.pcm {
        type plug
        slave.pcm "hw:1,0"
    }
}

ctl.!default {
    type hw
    card 0
}
```

**Note:** Adjust `hw:1,0` to match your I2S card number from `arecord -l`.

### 4. Test the Microphone

Test recording with ALSA:
```bash
# Record 5 seconds of audio
arecord -D hw:1,0 -f S32_LE -r 16000 -c 1 -d 5 test.wav

# Play it back
aplay test.wav
```

## Voice Assistant Configuration

### Step 1: Test INMP441 with the Test Script

Run the comprehensive test script:
```bash
python test_inmp441.py
```

This will:
- List all available audio devices
- Auto-detect your INMP441
- Test recording quality
- Monitor real-time audio levels
- Save test recordings

**Important:** Note the device index number shown for your INMP441.

### Step 2: Configure the Voice Assistant

The voice assistant now has **automatic I2S device detection**. It will:
1. Auto-detect your INMP441 on startup
2. Configure optimal settings (16000 Hz sample rate)
3. Use the detected device for both wake word detection and speech recognition

**No manual configuration needed** in most cases!

### Step 3: Manual Configuration (if auto-detection fails)

If auto-detection doesn't work, you can manually set the device:

Edit `audio/audio_processor.py` and modify the `__init__` method:
```python
# Find this line in AudioProcessors.__init__:
self.mic_device_id = self._auto_detect_mic_device()

# Replace with:
self.mic_device_id = X  # Replace X with your device index from test_inmp441.py
```

Or create a configuration file `mic_config.py`:
```python
# mic_config.py
INMP441_DEVICE_ID = 1  # Your device index
SAMPLE_RATE = 16000     # Hz
MIC_GAIN = 1.0          # Adjust if too loud/quiet
```

### Step 4: Run the Voice Assistant

```bash
# Activate your virtual environment
source /home/jubers/ENV/test/bin/activate

# Run the assistant
python voice_assistant.py
```

You should see:
```
Initializing Voice Assistant...
Auto-detected I2S microphone: Device X - [your INMP441 name]
AudioProcessor initialized with microphone device X
Using microphone device: X
Sample rate: 16000 Hz
```

## Troubleshooting

### Issue: No audio detected
**Solution:**
1. Check hardware connections
2. Verify I2S is enabled: `lsmod | grep snd`
3. Check ALSA configuration: `arecord -l`
4. Test with: `arecord -D hw:1,0 -f S32_LE -r 16000 -c 1 -d 3 test.wav`

### Issue: Audio too quiet
**Solution:**
Adjust the gain in `audio/audio_processor.py`:
```python
self.mic_gain_factor = 2.0  # Increase for louder audio
```

### Issue: Audio too loud/distorted
**Solution:**
```python
self.mic_gain_factor = 0.5  # Decrease for quieter audio
```

### Issue: Wrong device detected
**Solution:**
1. Run `python test_inmp441.py` to find correct device
2. Manually set device ID as shown in Step 3 above

### Issue: Wake word not detected
**Solution:**
1. Check sample rate matches between wake word model and INMP441 (16000 Hz)
2. Test audio quality: `python test_inmp441.py`
3. Adjust wake word detection thresholds in `audio/wake_word_detector.py`:
   ```python
   # Lower these for more sensitive detection
   energy_threshold=0.040      # Default: 0.060
   confidence_threshold=0.95   # Default: 0.997
   ```

## Optimal Settings for INMP441

The system is pre-configured with optimal settings for INMP441:

| Parameter | Value | Reason |
|-----------|-------|--------|
| Sample Rate | 16000 Hz | Best for speech recognition |
| Channels | 1 (Mono) | INMP441 is mono |
| Gain | 1.0 | Adjust if needed |
| Energy Threshold | 300 | Optimized for sensitive mics |
| Pause Threshold | 1.2s | Good responsiveness |

## Advanced Configuration

### Change Sample Rate

If you want to use a different sample rate:

1. Edit `audio/audio_processor.py`:
```python
self.sample_rate = 22050  # or 44100, 48000
```

2. Ensure wake word model is compatible with the new rate

### Multi-Microphone Setup

If you have multiple microphones:
```python
# In audio/audio_processor.py
def _auto_detect_mic_device(self):
    # Add priority logic
    preferred_devices = ['inmp441', 'i2s']
    # ... implement priority selection
```

## Testing Checklist

- [ ] I2S enabled in `/boot/config.txt`
- [ ] INMP441 visible in `arecord -l`
- [ ] Test recording with `arecord` works
- [ ] `python test_inmp441.py` detects INMP441
- [ ] Audio levels good in real-time monitoring
- [ ] Voice assistant auto-detects device
- [ ] Wake word detection works
- [ ] Speech recognition works

## Additional Resources

- [INMP441 Datasheet](https://invensense.tdk.com/products/digital/inmp441/)
- [Raspberry Pi I2S Setup](https://learn.adafruit.com/adafruit-i2s-mems-microphone-breakout)
- [ALSA Configuration Guide](https://www.alsa-project.org/wiki/Asoundrc)

## Support

If you encounter issues:
1. Check connections
2. Run `python test_inmp441.py`
3. Check system logs: `dmesg | grep i2s`
4. Verify ALSA: `aplay -l` and `arecord -l`
