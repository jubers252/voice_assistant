"""
GPIO Setup for controlling WS2812B pixel LED using SPI
This method works on all Raspberry Pi models including Pi 5
"""
import time
import threading

try:
    import spidev
    HAS_SPI = True
except ImportError:
    HAS_SPI = False
    print("Warning: spidev not available, running in simulation mode")

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False
    print("Warning: RPi.GPIO not available")


class PixelLEDController:
    """Control WS2812B RGB pixel LED using SPI interface"""
    
    def __init__(self, led_count: int = 6, brightness: float = 1.0, simulate: bool = False):
        """
        Initialize the WS2812B pixel LED controller using SPI.
        
        Args:
            led_count: Number of LEDs in the strip (default: 6)
            brightness: Global brightness level 0.0-1.0 (default: 1.0)
            simulate: Force simulation mode
            
        Note:
            Uses SPI0 on Raspberry Pi:
            - MOSI (GPIO 10) = Data pin
            - Connect LED Data -> GPIO 10 (Physical pin 19)
            - Connect LED GND -> GND
            - Connect LED 5V -> 5V power
        """
        self.LED_COUNT = led_count
        self.brightness = max(0.0, min(1.0, brightness))  # Clamp between 0.0 and 1.0
        self.simulation_mode = simulate or not HAS_SPI
        self.pixels = [(0, 0, 0)] * led_count
        
        # Thread control for background animations
        self.animation_thread = None
        self.animation_running = False
        self.animation_lock = threading.Lock()
        
        if self.simulation_mode:
            print(f"Running in SIMULATION mode (LED Count: {led_count})")
            self.spi = None
        else:
            try:
                # Initialize SPI
                self.spi = spidev.SpiDev()
                self.spi.open(0, 0)  # Bus 0, Device 0
                self.spi.max_speed_hz = 6400000  # 6.4MHz for WS2812B timing
                self.spi.mode = 0b00  # CPOL=0, CPHA=0
                print(f"WS2812B initialized using SPI (MOSI = GPIO 10)")
            except Exception as e:
                print(f"Failed to initialize SPI: {e}")
                print("Falling back to simulation mode")
                print("Make sure SPI is enabled: sudo raspi-config -> Interface Options -> SPI")
                self.simulation_mode = True
                self.spi = None
    
    def _encode_byte(self, byte):
        """Encode a single byte into WS2812B SPI format"""
        # WS2812B timing: 0.4us high / 0.85us low for '0', 0.8us high / 0.45us low for '1'
        # At 8MHz SPI: each bit takes 0.125us
        # We need: '1' = 1110 (0.5us high, 0.125us low), '0' = 1000 (0.125us high, 0.375us low)
        result = []
        for i in range(7, -1, -1):
            if (byte >> i) & 1:
                # Bit is 1: send 11100000 (0xE0) for better timing
                result.extend([0b11110000])
            else:
                # Bit is 0: send 10000000 (0x80)
                result.extend([0b11000000])
        return result
    
    def show(self):
        """Update the LED strip with current pixel values"""
        if self.simulation_mode:
            print(f"LED State: {self.pixels}")
            return
        
        # Convert all pixels to SPI format with brightness applied
        spi_data = []
        for r, g, b in self.pixels:
            # Apply brightness scaling
            r = int(r * self.brightness)
            g = int(g * self.brightness)
            b = int(b * self.brightness)
            # WS2812B expects GRB order
            for component in [g, r, b]:
                spi_data.extend(self._encode_byte(component))
        
        # Add reset signal (low for 50+ microseconds = 400 bits at 8MHz)
        reset = [0x00] * 50
        
        # Send to LED strip
        try:
            self.spi.xfer2(spi_data + reset)
        except Exception as e:
            print(f"Error updating LEDs: {e}")
    
    def set_color(self, red: int, green: int, blue: int, led_index: int = 0):
        """Set a single LED color"""
        if 0 <= led_index < self.LED_COUNT:
            self.pixels[led_index] = (red, green, blue)
            self.show()
    
    def set_all_color(self, red: int, green: int, blue: int):
        """Set all LEDs to the same color"""
        self.pixels = [(red, green, blue)] * self.LED_COUNT
        self.show()
    
    def off(self):
        """Turn off all LEDs"""
        self.set_all_color(0, 0, 0)
    
    def set_listening(self):
        """Set blue color for listening state"""
        self.stop_animation()
        self.set_all_color(0, 0, 255)
    
    def set_processing(self):
        """Start multicolor wave animation for processing state in background thread"""
        self.start_animation(self._processing_wave_animation)
    
    def set_speaking(self):
        """Set green color for speaking state"""
        self.stop_animation()
        self.set_all_color(0, 255, 0)
    
    def set_error(self):
        """Set red color for error state"""
        self.stop_animation()
        self.set_all_color(255, 0, 0)
    
    def start_animation(self, animation_func):
        """Start an animation in a background thread"""
        self.stop_animation()
        with self.animation_lock:
            self.animation_running = True
            self.animation_thread = threading.Thread(target=animation_func, daemon=True)
            self.animation_thread.start()
    
    def stop_animation(self):
        """Stop any running animation"""
        with self.animation_lock:
            if self.animation_running:
                self.animation_running = False
                if self.animation_thread and self.animation_thread.is_alive():
                    self.animation_thread.join(timeout=0.5)
    
    def _blink_animation(self):
        """Blinking animation for processing - runs in background thread (fallback)"""
        colors = [(0, 0, 255), (255, 0, 0), (0, 255, 0)]  # Blue, Red, Green
        interval = 0.1

        while self.animation_running:
            for color in colors:
                if not self.animation_running:
                    break
                self.set_all_color(*color)
                time.sleep(interval)
                if not self.animation_running:
                    break
                self.off()
                time.sleep(interval)

    def _processing_wave_animation(self):
        """Multicolor moving wave animation for processing - runs in background thread."""
        # Tuned for 26 LEDs, still works for other lengths.
        # Colors are in RGB space and smoothly interpolated.
        palette = [
            (0, 0, 255),    # Blue
            (0, 255, 255),  # Cyan
            (0, 255, 0),    # Green
            (255, 255, 0),  # Yellow
            (255, 0, 0),    # Red
            (255, 0, 255),  # Magenta
        ]

        def lerp(a, b, t):
            return int(a + (b - a) * t)

        def palette_color(pos):
            """Get interpolated color from repeating palette for float position."""
            n = len(palette)
            pos = pos % n
            i0 = int(pos)
            i1 = (i0 + 1) % n
            t = pos - i0
            r = lerp(palette[i0][0], palette[i1][0], t)
            g = lerp(palette[i0][1], palette[i1][1], t)
            b = lerp(palette[i0][2], palette[i1][2], t)
            return (r, g, b)

        # Wave parameters (good defaults for 26 LEDs)
        speed = 0.35          # Higher = faster motion
        spatial_scale = 0.22  # Color spread across strip
        tail_length = 7       # Brightness falloff tail size
        frame_delay = 0.04    # ~25 FPS

        phase = 0.0
        while self.animation_running:
            new_pixels = []
            for i in range(self.LED_COUNT):
                # Color varies by index + phase to create moving rainbow wave
                base = palette_color((i * spatial_scale) + phase)

                # Create a moving intensity envelope ("wave head + tail")
                dist = (i - int(phase * 3)) % self.LED_COUNT
                if dist < tail_length:
                    intensity = 1.0 - (dist / max(1, tail_length))
                else:
                    intensity = 0.20  # dim background glow

                r = int(base[0] * intensity)
                g = int(base[1] * intensity)
                b = int(base[2] * intensity)
                new_pixels.append((r, g, b))

            self.pixels = new_pixels
            self.show()
            time.sleep(frame_delay)
            phase += speed

        # Clear when animation stops
        self.off()
    
    def cleanup(self):
        """Clean up - turn off all LEDs and stop animations"""
        self.stop_animation()
        self.off()
        if self.spi:
            self.spi.close()

# Example usage
if __name__ == "__main__":
    print("HMMD-mmWave Sensor Motion Detection with Red LED")
    print("=" * 60)
    print("GPIO 27 (Physical pin 13) <- Sensor OUT")
    print()
    obj = PixelLEDController(led_count=26, brightness=0.7, simulate=False)
    obj.set_processing()
    time.sleep(10)

    print("Stop + off + cleanup")
    obj.stop_animation()
    obj.off()
    obj.cleanup()