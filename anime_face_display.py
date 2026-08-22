import math
import random
import threading
import time

import cv2
import numpy as np

from camera.camera_display_control import toggle_camera_display_enabled

WINDOW_NAME = "Robot Face"
WIDTH  = 720
HEIGHT = 1280
FPS    = 30

KEY_MODE_MAP = {
    ord("1"): "neutral",
    ord("2"): "happy",
    ord("3"): "sad",
    ord("4"): "thinking",
    ord("5"): "listening",
    ord("6"): "speaking",
    ord("7"): "laughing",
    ord("8"): "dead",
}

# BGR palette matching the reference blue robot image
BLUE_SHELL  = (212, 176, 49)
BLUE_DARK   = (150, 118, 18)
BLUE_LIGHT  = (240, 210, 90)
SCREEN_BG   = (55, 50, 40)
SCREEN_EDGE = (85, 78, 60)
WHITE       = (242, 242, 242)
ACCENT      = (100, 220, 255)
BG          = (0, 0, 0)
BUTTON_FILL = (70, 70, 70)
BUTTON_EDGE = (160, 160, 160)
BUTTON_TEXT = (245, 245, 245)
BUTTON_BOUNDS = (510, 40, 680, 105)


def _fill_rounded(img, x1, y1, x2, y2, r, color):
    cv2.rectangle(img, (x1+r, y1), (x2-r, y2), color, -1)
    cv2.rectangle(img, (x1, y1+r), (x2, y2-r), color, -1)
    for cx, cy in ((x1+r, y1+r), (x2-r, y1+r), (x1+r, y2-r), (x2-r, y2-r)):
        cv2.circle(img, (cx, cy), r, color, -1, cv2.LINE_AA)


def _outline_rounded(img, x1, y1, x2, y2, r, color, t):
    cv2.line(img, (x1+r, y1),  (x2-r, y1),  color, t, cv2.LINE_AA)
    cv2.line(img, (x1+r, y2),  (x2-r, y2),  color, t, cv2.LINE_AA)
    cv2.line(img, (x1, y1+r),  (x1, y2-r),  color, t, cv2.LINE_AA)
    cv2.line(img, (x2, y1+r),  (x2, y2-r),  color, t, cv2.LINE_AA)
    cv2.ellipse(img, (x1+r, y1+r), (r,r), 0, 180, 270, color, t, cv2.LINE_AA)
    cv2.ellipse(img, (x2-r, y1+r), (r,r), 0, 270, 360, color, t, cv2.LINE_AA)
    cv2.ellipse(img, (x1+r, y2-r), (r,r), 0,  90, 180, color, t, cv2.LINE_AA)
    cv2.ellipse(img, (x2-r, y2-r), (r,r), 0,   0,  90, color, t, cv2.LINE_AA)


def _point_in_toggle_button(x, y):
    x1, y1, x2, y2 = BUTTON_BOUNDS
    return x1 <= x <= x2 and y1 <= y <= y2


def _draw_toggle_button(img, label):
    x1, y1, x2, y2 = BUTTON_BOUNDS
    _fill_rounded(img, x1, y1, x2, y2, 18, BUTTON_FILL)
    _outline_rounded(img, x1, y1, x2, y2, 18, BUTTON_EDGE, 2)
    cv2.putText(img, label, (x1 + 18, y1 + 42),
                cv2.FONT_HERSHEY_SIMPLEX, 0.72, BUTTON_TEXT, 2, cv2.LINE_AA)


class RobotFaceRenderer:
    def __init__(self, width=WIDTH, height=HEIGHT):
        self.width  = width
        self.height = height
        self.mode   = "neutral"

        self.next_blink  = time.time() + random.uniform(2.0, 4.5)
        self.blink_dur   = 0.13
        self.blinking    = False
        self.blink_start = 0.0

        self.speak_phase  = 0.0
        self.idle_phase   = 0.0
        self.think_phase  = 0.0
        self.listen_phase = 0.0
        self.laugh_phase  = 0.0
        self.dead_phase   = 0.0
        self.dead_started_at = None
        self.dead_shatter_delay = 0.8

        # pupil gaze — pan (A/D) and tilt (W/S) for servo mapping, reset with R
        self.pupil_pan_angle  = 0.0   # horizontal (left/right)
        self.pupil_tilt_angle = 0.0   # vertical (up/down)
        self.pupil_radius = 20
        self.pupil_travel_radius = 32
        self.override_pan = None      # external pan angle override (e.g., from servo)
        self.override_tilt = None     # external tilt angle override (e.g., from servo)

    def set_pupil_angles(self, pan_angle, tilt_angle):
        """Set pupil pan and tilt angles from external source (e.g., servo feedback)
        
        Args:
            pan_angle: Horizontal angle in radians (-pi to pi, left to right)
            tilt_angle: Vertical angle in radians (-pi to pi, down to up)
        """
        self.override_pan = pan_angle
        self.override_tilt = tilt_angle

    def _pupil_offset(self):
        max_angle = math.pi / 2
        pan_ratio = max(-1.0, min(1.0, self.pupil_pan_angle / max_angle))
        tilt_ratio = max(-1.0, min(1.0, self.pupil_tilt_angle / max_angle))
        return (
            int(pan_ratio * self.pupil_travel_radius),
            int(tilt_ratio * self.pupil_travel_radius),
        )

    def get_pupil_angles(self):
        """Get current pupil pan and tilt angles
        
        Returns:
            tuple: (pan_angle, tilt_angle) in radians
        """
        return (self.pupil_pan_angle, self.pupil_tilt_angle)

    def _draw_music_note(self, img, x, y, size, color):
        """Draw a simple music note symbol"""
        # note head (circle)
        cv2.circle(img, (x, y), int(size * 0.4), color, -1, cv2.LINE_AA)
        # stem (vertical line)
        cv2.line(img, (x + int(size * 0.3), y - int(size * 0.4)), 
                      (x + int(size * 0.3), y - int(size * 1.2)), color, 
                      int(size * 0.15), cv2.LINE_AA)
        # flag (curve at top)
        cv2.ellipse(img, (x + int(size * 0.5), y - int(size * 0.8)), 
                   (int(size * 0.35), int(size * 0.25)), 0, 0, 180, color, -1, cv2.LINE_AA)

    def _render_music_stream(self, frame, sx1, sy1, sx2, sy2):
        """Render music notes streaming from top corners (left and right)"""
        # Right side stream
        start_x_right = self.width - 40
        # Left side stream
        start_x_left = 40
        start_y = 0
        
        # Create multiple notes at different stages from right side
        for i in range(5):
            # Stagger notes with phase offset (increased for slower speed)
            phase = (self.listen_phase - i * 0.6) % (2 * math.pi)
            
            # Calculate note position (moving down and left towards face)
            progress = (phase / (2 * math.pi))  # 0 to 1
            if progress < 0:
                progress += 1
            
            # Vertical movement from top to middle of screen (slower)
            y = int(start_y + progress * (self.height * 0.3))
            # Horizontal drift from right towards center
            x_right = int(start_x_right - progress * 100)
            
            # Only draw if within frame
            if 0 <= x_right < self.width and 0 <= y < self.height:
                # Vary opacity with distance
                opacity = 1.0 - progress * 0.3
                alpha = np.zeros_like(frame)
                self._draw_music_note(alpha, x_right, y, 28, ACCENT)
                frame[:] = cv2.addWeighted(frame, 1.0, alpha, opacity * 0.8, 0.0)

        # Create multiple notes at different stages from left side
        for i in range(5):
            # Stagger notes with phase offset, slightly offset from right side
            phase = (self.listen_phase - i * 0.6 + 0.3) % (2 * math.pi)
            
            # Calculate note position (moving down and right towards face)
            progress = (phase / (2 * math.pi))  # 0 to 1
            if progress < 0:
                progress += 1
            
            # Vertical movement from top to middle of screen (slower)
            y = int(start_y + progress * (self.height * 0.3))
            # Horizontal drift from left towards center
            x_left = int(start_x_left + progress * 100)
            
            # Only draw if within frame
            if 0 <= x_left < self.width and 0 <= y < self.height:
                # Vary opacity with distance
                opacity = 1.0 - progress * 0.3
                alpha = np.zeros_like(frame)
                self._draw_music_note(alpha, x_left, y, 28, ACCENT)
                frame[:] = cv2.addWeighted(frame, 1.0, alpha, opacity * 0.8, 0.0)

    def _blink(self, now):
        if self.blinking:
            t = now - self.blink_start
            if t >= self.blink_dur:
                self.blinking   = False
                self.next_blink = now + random.uniform(2.0, 4.5)
                return 0.0
            h = self.blink_dur / 2.0
            return (t / h) if t < h else (1.0 - (t - h) / h)
        if now >= self.next_blink:
            self.blinking    = True
            self.blink_start = now
        return 0.0

    def _speak(self, dt):
        if self.mode != "speaking":
            return 0.0
        self.speak_phase += dt * 7.0 * 2 * math.pi
        v = (0.6 * (math.sin(self.speak_phase) + 1) * 0.5
           + 0.4 * (math.sin(self.speak_phase * 1.9 + 0.5) + 1) * 0.5)
        return 0.15 + 0.85 * v

    def _shell(self, img, cx, cy):
        hw, hh = 310, 290
        r      = 90
        x1, y1 = cx - hw, cy - hh
        x2, y2 = cx + hw, cy + hh

        # side ears
        for ex in (x1 - 22, x2 + 22):
            cv2.ellipse(img, (ex, cy), (30, 56), 0, 0, 360, BLUE_DARK,  -1, cv2.LINE_AA)
            cv2.ellipse(img, (ex, cy), (22, 44), 0, 0, 360, BLUE_SHELL, -1, cv2.LINE_AA)

        # head shell
        _fill_rounded(img, x1, y1, x2, y2, r, BLUE_SHELL)
        _outline_rounded(img, x1+4, y1+4, x2-4, y2-4, r-2, BLUE_LIGHT, 5)

        # antenna
        ay = y1 - 2
        cv2.line(img,   (cx, ay),     (cx, ay-44),  BLUE_DARK,  12, cv2.LINE_AA)
        cv2.circle(img, (cx, ay-68),  28, BLUE_DARK,  -1, cv2.LINE_AA)
        cv2.circle(img, (cx, ay-68),  21, BLUE_SHELL, -1, cv2.LINE_AA)
        cv2.circle(img, (cx-7, ay-76), 7, BLUE_LIGHT, -1, cv2.LINE_AA)

        # screen inset
        sm = 50
        sx1, sy1 = x1 + sm, y1 + sm
        sx2, sy2 = x2 - sm, y2 - sm
        sr = 54
        _fill_rounded(img, sx1, sy1, sx2, sy2, sr, SCREEN_BG)
        _outline_rounded(img, sx1, sy1, sx2, sy2, sr, SCREEN_EDGE, 4)
        return sx1, sy1, sx2, sy2

    def _eyes(self, img, blink, sx1, sy1, sx2, sy2):
        scx    = (sx1 + sx2) // 2
        ey     = sy1 + 200  # Moved lower to make space above for info
        lx     = scx - 140  # More separation
        rx     = scx + 140  # More separation
        ew, eh = 80, 95  # Bigger eyes!
        closed = blink > 0.68
        eh_now = max(4, int(eh * (1.0 - blink)))
        mode   = self.mode
        pupil_color = (0, 0, 0)

        if mode == "happy":
            # Big happy eyes with multiple sparkles - joyful expression
            for ex in (lx, rx):
                # Main eye white - very large
                cv2.ellipse(img, (ex, ey), (ew, eh_now), 0, 0, 360, WHITE, -1, cv2.LINE_AA)
                # Large happy pupil centered
                cv2.circle(img, (ex, ey), max(22, int(self.pupil_radius * 1.3)), pupil_color, -1, cv2.LINE_AA)
                # Multiple sparkle shines for extra happiness
                cv2.circle(img, (ex - 12, ey - 12), 7, WHITE, -1, cv2.LINE_AA)
                cv2.circle(img, (ex + 8, ey - 10), 5, WHITE, -1, cv2.LINE_AA)
                cv2.circle(img, (ex - 8, ey + 8), 4, WHITE, -1, cv2.LINE_AA)
            return
        if mode == "laughing":
            # Big anime-style laughing eyes - happy closed crescents with animation
            laugh_wave = 0.5 + 0.5 * math.sin(self.laugh_phase)
            laugh_bob = int(3 * math.sin(self.laugh_phase * 1.5))
            thickness = int(8 + 3 * laugh_wave)
            # Draw happy closed eyes as thick curved lines
            for ex in (lx, rx):
                eye_y = ey + laugh_bob
                # Happy crescent: curved smile shape for each eye
                cv2.ellipse(img, (ex, eye_y), (ew, int(eh * 0.5)), 0, 190, 350, WHITE, thickness, cv2.LINE_AA)
                # Add small tear/shine marks below for extra cuteness
                cv2.circle(img, (ex, eye_y + int(eh * 0.35)), 5, WHITE, -1, cv2.LINE_AA)
            return
        if mode == "dead":
            # animated X-eyes (pulse + tiny jitter)
            pulse = 0.5 + 0.5 * math.sin(self.dead_phase * 1.8)
            half = int(16 + 5 * pulse)
            t = int(4 + 2 * pulse)
            jy = int(2 * math.sin(self.dead_phase * 3.2))
            jx = int(2 * math.cos(self.dead_phase * 2.7))
            for ex in (lx, rx):
                cx, cy = ex + jx, ey + jy
                cv2.line(img, (cx-half, cy-half), (cx+half, cy+half), WHITE, t, cv2.LINE_AA)
                cv2.line(img, (cx-half, cy+half), (cx+half, cy-half), WHITE, t, cv2.LINE_AA)
            return
        # shared pupil offset based on pan/tilt angles
        pdx, pdy = self._pupil_offset()

        if mode == "sad":
            for ex in (lx, rx):
                cv2.ellipse(img, (ex, ey+6), (ew-8, max(4, eh_now//3)), 0, 0, 360, WHITE, -1, cv2.LINE_AA)
                cv2.circle(img, (ex + pdx, ey + 6 + pdy), max(6, int(self.pupil_radius * 0.6)), pupil_color, -1, cv2.LINE_AA)
            return
        if mode == "thinking":
            cv2.ellipse(img, (lx, ey), (ew-8, max(5, eh_now//2)), 0, 0, 360, WHITE, -1, cv2.LINE_AA)
            cv2.ellipse(img, (rx, ey), (ew-4, eh_now),            0, 0, 360, WHITE, -1, cv2.LINE_AA)
            for ex in (lx, rx):
                cv2.circle(img, (ex + pdx, ey + pdy), max(7, int(self.pupil_radius * 0.7)), pupil_color, -1, cv2.LINE_AA)
            return
        if mode == "listening":
            # Attentive listening eyes - focused upward with vertical ovals and animated pupils
            if closed:
                for ex in (lx, rx):
                    cv2.line(img, (ex-ew+4, ey), (ex+ew-4, ey), WHITE, 7, cv2.LINE_AA)
            else:
                # Vertical focused eyes (more alert/listening posture)
                for ex in (lx, rx):
                    # Eyes are taller/more vertical for concentrated listening
                    cv2.ellipse(img, (ex, ey), (int(ew * 0.6), eh_now), 0, 0, 360, WHITE, -1, cv2.LINE_AA)
                    # Pupils looking upward - concentrated gaze
                    pupil_y = ey + pdy - 12
                    pupil_x = ex + pdx
                    cv2.circle(img, (pupil_x, pupil_y), self.pupil_radius, pupil_color, -1, cv2.LINE_AA)
                    # Multiple highlights showing active listening
                    cv2.circle(img, (pupil_x - 4, pupil_y - 6), 4, WHITE, -1, cv2.LINE_AA)
                    cv2.circle(img, (pupil_x + 3, pupil_y - 5), 3, ACCENT, -1, cv2.LINE_AA)
            return

        if mode == "speaking":
            # Speaking mode - animated eyes with side-to-side pupil movement
            if closed:
                for ex in (lx, rx):
                    cv2.line(img, (ex-ew+4, ey), (ex+ew-4, ey), WHITE, 7, cv2.LINE_AA)
            else:
                # Eyes slightly narrower when speaking
                speak_narrow = int(eh_now * 0.7)
                for ex in (lx, rx):
                    cv2.ellipse(img, (ex, ey), (ew, speak_narrow), 0, 0, 360, WHITE, -1, cv2.LINE_AA)
                    # Pupils moving side to side (like speaking animation)
                    speak_pupil_x = pdx + int(15 * math.sin(self.speak_phase * 0.8))
                    pr = max(7, int(self.pupil_radius * (speak_narrow / eh)))
                    cv2.circle(img, (ex + speak_pupil_x, ey + pdy), pr, pupil_color, -1, cv2.LINE_AA)
            return

        # neutral  (blink-capable white ovals + pupils)
        if closed:
            for ex in (lx, rx):
                cv2.line(img, (ex-ew+4, ey), (ex+ew-4, ey), WHITE, 7, cv2.LINE_AA)
            return
        for ex in (lx, rx):
            cv2.ellipse(img, (ex, ey), (ew, eh_now), 0, 0, 360, WHITE, -1, cv2.LINE_AA)
            pr = max(7, int(self.pupil_radius * (eh_now / eh)))
            cv2.circle(img, (ex + pdx, ey + pdy), pr, pupil_color, -1, cv2.LINE_AA)

    def _mouth(self, img, speak_level, sx1, sy1, sx2, sy2):
        scx  = (sx1 + sx2) // 2
        my   = sy1 + 290
        T    = 8
        mode = self.mode

        if mode == "happy":
            cv2.ellipse(img, (scx, my-14), (60, 30), 0, 12, 168, WHITE, T, cv2.LINE_AA)
            return
        if mode == "laughing":
            # animated laugh mouth: vertical bob + opening variation
            laugh_wave = 0.5 + 0.5 * math.sin(self.laugh_phase * 1.25)
            mouth_y = my + int(6 * math.sin(self.laugh_phase))
            mouth_w = int(62 + 12 * laugh_wave)
            mouth_h = int(34 + 16 * laugh_wave)
            inner_t = int(4 + 3 * laugh_wave)

            cv2.ellipse(img, (scx, mouth_y), (mouth_w, mouth_h), 0, 8, 172, WHITE, -1, cv2.LINE_AA)
            cv2.ellipse(img, (scx, mouth_y), (mouth_w, mouth_h), 0, 8, 172, SCREEN_BG, inner_t, cv2.LINE_AA)
            cv2.ellipse(img, (scx, mouth_y), (mouth_w, mouth_h), 0, 8, 172, WHITE, T, cv2.LINE_AA)
            return
        if mode == "sad":
            cv2.ellipse(img, (scx, my+22), (52, 22), 0, 192, 348, WHITE, T, cv2.LINE_AA)
            return
        if mode == "dead":
            # animated flat/wobble mouth for "dead" reaction
            wobble = int(4 * math.sin(self.dead_phase * 2.4))
            mx1, mx2 = scx - 52, scx + 52
            myd = my + 18 + wobble
            cv2.line(img, (mx1, myd), (mx2, myd), WHITE, T, cv2.LINE_AA)
            cv2.circle(img, (scx, myd + 8), 4, WHITE, -1, cv2.LINE_AA)
            return
        if mode == "thinking":
            cv2.line(img, (scx-48, my+4), (scx+8, my+4), WHITE, T, cv2.LINE_AA)
            for i, ox in enumerate((40, 60, 80)):
                cv2.circle(img, (scx+ox, my+4), 5+i, WHITE, -1, cv2.LINE_AA)
            return
        if mode == "listening":
            cv2.circle(img, (scx, my), 15, WHITE, T, cv2.LINE_AA)
            return
        if mode == "speaking":
            # thick animated arc mouth for speaking
            arc_h = max(14, int(16 + 20 * speak_level))
            arc_w = max(40, int(44 + 8 * speak_level))
            thickness = max(8, int(8 + 5 * speak_level))
            mouth_y = my + int(2 * math.sin(self.speak_phase * 0.6))
            cv2.ellipse(img, (scx, mouth_y), (arc_w, arc_h), 0, 10, 170, WHITE, thickness, cv2.LINE_AA)
            return
        # neutral
        cv2.ellipse(img, (scx, my-6), (40, 17), 0, 14, 166, WHITE, T, cv2.LINE_AA)

    def _render_dead_shatter(self, frame, now, blink, speak, cx, cy):
        # draw full robot to an offscreen buffer first
        off = np.zeros_like(frame)
        sx1, sy1, sx2, sy2 = self._shell(off, cx, cy)
        self._eyes(off, blink, sx1, sy1, sx2, sy2)
        self._mouth(off, speak, sx1, sy1, sx2, sy2)

        # split head area into tiles and scatter them outward
        tile = 36
        head_w = max(1, sx2 - sx1)
        head_h = max(1, sy2 - sy1)
        center_x = (sx1 + sx2) // 2
        center_y = (sy1 + sy2) // 2

        for y in range(sy1, sy2, tile):
            for x in range(sx1, sx2, tile):
                x2 = min(x + tile, sx2)
                y2 = min(y + tile, sy2)
                piece = off[y:y2, x:x2]
                if piece.size == 0:
                    continue

                # per-piece pseudo-random motion derived from tile index (stable each frame)
                tid = ((x - sx1) // tile) + 37 * ((y - sy1) // tile)
                ang = (tid * 0.73) % (2 * math.pi)
                phase = self.dead_phase * (1.0 + (tid % 5) * 0.06)

                # outward velocity + shake
                vx = math.cos(ang)
                vy = math.sin(ang)
                spread = 18 + 10 * math.sin(phase * 1.9 + tid * 0.11)
                shake_x = 4 * math.sin(phase * 4.1 + tid)
                shake_y = 4 * math.cos(phase * 3.7 + tid * 0.7)

                dx = int((x + x2) * 0.5 - center_x)
                dy = int((y + y2) * 0.5 - center_y)
                dist_boost = 0.012 * (dx * dx + dy * dy) ** 0.5

                ox = int(vx * spread + shake_x + vx * dist_boost * 20)
                oy = int(vy * spread + shake_y + vy * dist_boost * 20)

                nx1, ny1 = x + ox, y + oy
                nx2, ny2 = nx1 + (x2 - x), ny1 + (y2 - y)

                # clip destination to frame bounds
                if nx2 <= 0 or ny2 <= 0 or nx1 >= self.width or ny1 >= self.height:
                    continue
                cx1 = max(0, nx1)
                cy1 = max(0, ny1)
                cx2 = min(self.width, nx2)
                cy2 = min(self.height, ny2)

                px1 = cx1 - nx1
                py1 = cy1 - ny1
                px2 = px1 + (cx2 - cx1)
                py2 = py1 + (cy2 - cy1)

                frag = piece[py1:py2, px1:px2].copy()
                if frag.size == 0:
                    continue

                # slight fade based on pulse
                fade = 0.75 + 0.25 * (0.5 + 0.5 * math.sin(phase * 2.3))
                frag = np.clip(frag.astype(np.float32) * fade, 0, 255).astype(np.uint8)

                mask = cv2.cvtColor(frag, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(mask, 10, 255, cv2.THRESH_BINARY)
                roi = frame[cy1:cy2, cx1:cx2]
                bg_roi = cv2.bitwise_and(roi, roi, mask=cv2.bitwise_not(mask))
                fg_roi = cv2.bitwise_and(frag, frag, mask=mask)
                frame[cy1:cy2, cx1:cx2] = cv2.add(bg_roi, fg_roi)

    def render(self, frame, now, dt):
        frame[:] = BG

        self.idle_phase   += dt * 1.4
        self.think_phase  += dt * 2.2
        self.listen_phase += dt * 4.0
        self.laugh_phase  += dt * 7.0
        self.dead_phase   += dt * 5.5

        blink = self._blink(now)
        speak = self._speak(dt)

        cx = self.width  // 2
        cy = self.height // 2 + 80 + int(2 * math.sin(self.idle_phase))

        # in thinking mode, make pupils move in a circle continuously
        if self.mode == "thinking":
            if self.override_pan is not None:
                self.pupil_pan_angle = self.override_pan
            else:
                self.pupil_pan_angle = math.sin(self.think_phase) * (math.pi / 3)
            if self.override_tilt is not None:
                self.pupil_tilt_angle = self.override_tilt
            else:
                self.pupil_tilt_angle = math.cos(self.think_phase * 0.8) * (math.pi / 6)
        else:
            # use override angles if provided, otherwise use keyboard-controlled angles
            if self.override_pan is not None:
                self.pupil_pan_angle = self.override_pan
            if self.override_tilt is not None:
                self.pupil_tilt_angle = self.override_tilt

        # Only render eyes, no shell or mouth (simple display)
        # Create a dummy screen area for eyes positioning
        sx1, sy1 = cx - 250, cy - 200
        sx2, sy2 = cx + 250, cy + 200
        
        self._eyes(frame, blink, sx1, sy1, sx2, sy2)

        lbl = "1-8:mode  A/D:pan  W/S:tilt  R:reset    mode=" + self.mode
        cv2.putText(frame, lbl, (18, self.height-22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (130,130,130), 1, cv2.LINE_AA)


class FaceDisplayController:
    """Run the robot face continuously in a background thread."""

    def __init__(self, mode="neutral", pan_angle=0.0, tilt_angle=0.0):
        self.mode = mode
        self.pan_angle = pan_angle
        self.tilt_angle = tilt_angle
        self.visible = True
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._toggle_requested = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="anime-face-display", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def is_running(self):
        return bool(self._thread and self._thread.is_alive())

    def set_mode(self, mode):
        with self._lock:
            self.mode = mode

    def set_pupil_angles(self, pan_angle, tilt_angle):
        with self._lock:
            self.pan_angle = pan_angle
            self.tilt_angle = tilt_angle

    def show(self):
        with self._lock:
            self.visible = True

    def hide(self):
        with self._lock:
            self.visible = False

    def _run(self):
        def _mouse_callback(event, x, y, _flags, _param):
            if event == cv2.EVENT_LBUTTONUP and _point_in_toggle_button(x, y):
                self._toggle_requested = True

        renderer = RobotFaceRenderer(WIDTH, HEIGHT)
        last = time.time()
        window_visible = False

        try:
            while not self._stop_event.is_set():
                now = time.time()
                dt = max(0.001, now - last)
                last = now

                with self._lock:
                    renderer.mode = self.mode
                    renderer.pupil_pan_angle = self.pan_angle
                    renderer.pupil_tilt_angle = self.tilt_angle
                    visible = self.visible

                if visible and not window_visible:
                    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(WINDOW_NAME, WIDTH, HEIGHT)
                    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                    cv2.setMouseCallback(WINDOW_NAME, _mouse_callback)
                    window_visible = True

                if not visible and window_visible:
                    try:
                        cv2.destroyWindow(WINDOW_NAME)
                    except cv2.error:
                        pass
                    window_visible = False

                if not visible:
                    time.sleep(0.05)
                    continue

                frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
                renderer.render(frame, now, dt)
                _draw_toggle_button(frame, "Show Cam")
                cv2.imshow(WINDOW_NAME, frame)

                key = cv2.waitKey(max(1, int(1000 / FPS))) & 0xFF
                if key in (27, ord("q")):
                    self._stop_event.set()
                    break
                if key in KEY_MODE_MAP:
                    self.set_mode(KEY_MODE_MAP[key])
                if key == ord("c") or self._toggle_requested:
                    self._toggle_requested = False
                    enabled = toggle_camera_display_enabled(default=False)
                    if enabled:
                        self.hide()
        finally:
            self._thread = None
            if window_visible:
                try:
                    cv2.destroyWindow(WINDOW_NAME)
                except cv2.error:
                    pass


def main(mode="neutral", pan_angle=0.0, tilt_angle=0.0):
    """Run the robot face display
    
    Args:
        mode: Initial face expression (\"neutral\", \"happy\", \"sad\", \"thinking\", 
              \"listening\", \"speaking\", \"laughing\", \"dead\")
        pan_angle: Initial pupil pan angle in radians (horizontal)
        tilt_angle: Initial pupil tilt angle in radians (vertical)
    """
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, WIDTH, HEIGHT)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    renderer = RobotFaceRenderer(WIDTH, HEIGHT)
    renderer.mode = mode
    renderer.pupil_pan_angle = pan_angle
    renderer.pupil_tilt_angle = tilt_angle
    last = time.time()

    while True:
        now  = time.time()
        dt   = max(0.001, now - last)
        last = now

        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        renderer.render(frame, now, dt)
        cv2.imshow(WINDOW_NAME, frame)

        key = cv2.waitKey(max(1, int(1000 / FPS))) & 0xFF
        if key in (27, ord("q")):
            break
        modes = {"1":"neutral","2":"happy","3":"sad",
                 "4":"thinking","5":"listening","6":"speaking","7":"laughing","8":"dead"}
        if chr(key) in modes:
            renderer.mode = modes[chr(key)]
        if key == ord("a"):
            renderer.pupil_pan_angle -= 0.20
        if key == ord("d"):
            renderer.pupil_pan_angle += 0.20
        if key == ord("w"):
            renderer.pupil_tilt_angle -= 0.20
        if key == ord("s"):
            renderer.pupil_tilt_angle += 0.20
        if key == ord("r"):
            renderer.pupil_pan_angle = 0.0
            renderer.pupil_tilt_angle = 0.0

    cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Robot Face Display")
    parser.add_argument("--mode", type=str, default="neutral",
                        choices=["neutral", "happy", "sad", "thinking", "listening", "speaking", "laughing", "dead"],
                        help="Initial face expression mode")
    parser.add_argument("--pan", type=float, default=0.0,
                        help="Initial pupil pan angle in radians (left/right)")
    parser.add_argument("--tilt", type=float, default=0.0,
                        help="Initial pupil tilt angle in radians (up/down)")
    
    args = parser.parse_args()
    main(mode=args.mode, pan_angle=args.pan, tilt_angle=args.tilt)
