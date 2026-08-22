from time import time, sleep

import serial
import struct
import math
from camera.face_track_servo import FaceTrackServo

obj = FaceTrackServo(verbose=True)
obj.initialize()  # Initialize PWM hardware

def decode_coord(raw):
    if raw >= 0x8000:
        return raw - 0x8000
    else:
        return -raw

ser = serial.Serial("/dev/ttyAMA0", 256000, timeout=1)

while True:
    data = ser.read(24)

    if len(data) != 24:
        continue

    if data[0] != 0xAA or data[1] != 0xFF:
        continue

    raw_x = struct.unpack("<H", data[4:6])[0]
    raw_y = struct.unpack("<H", data[6:8])[0]

    x = decode_coord(raw_x)
    y = decode_coord(raw_y)

    if y == 0:
        continue

    angle = math.degrees(math.atan2(x, y))

    obj.move_pan_to_angle(angle)
    # sleep(0.1)
    print(
        f"X={x:5d} "
        f"Y={y:5d} "
        f"Angle={angle:6.2f}"
    )