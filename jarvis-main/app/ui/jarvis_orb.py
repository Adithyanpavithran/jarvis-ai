import math
from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QBrush, QPen, QFont
from PySide6.QtWidgets import QWidget

class JarvisOrbWidget(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.state = "listening" # "idle", "listening", "thinking", "speaking"
        self.anim_time = 0.0
        self.eq_heights = [12, 18, 28, 20, 30, 16, 10]

        # Animation timer ~60 FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(16)

    def set_state(self, state: str):
        if state in ("idle", "listening", "thinking", "speaking"):
            self.state = state
            self.update()

    def update_animation(self):
        self.anim_time += 0.05
        
        # Calculate dynamic equalizer bar heights based on state
        speed = 2.0 if self.state in ("listening", "speaking") else (3.5 if self.state == "thinking" else 0.8)
        base_h = 24.0 if self.state == "speaking" else (18.0 if self.state == "listening" else 10.0)
        
        for i in range(7):
            phase = i * 0.7
            h = base_h + 12.0 * math.sin(self.anim_time * speed + phase)
            self.eq_heights[i] = max(6.0, h)
            
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0 - 15.0 # slightly offset up for equalizer below

        # Colors based on state
        if self.state == "idle":
            cyan_core = QColor(0, 229, 255)
            glow_alpha = 50
            status_text = "IDLE"
        elif self.state == "listening":
            cyan_core = QColor(0, 240, 255)
            glow_alpha = 90
            status_text = "LISTENING"
        elif self.state == "thinking":
            cyan_core = QColor(255, 140, 0)
            glow_alpha = 100
            status_text = "THINKING"
        else: # speaking
            cyan_core = QColor(168, 85, 247)
            glow_alpha = 100
            status_text = "SPEAKING"

        # 1. Draw Concentric Background Orbit Rings
        pen_ring = QPen(QColor(0, 240, 255, 25))
        pen_ring.setWidth(1)
        painter.setPen(pen_ring)
        painter.setBrush(Qt.NoBrush)
        
        r1 = 110.0 + 3.0 * math.sin(self.anim_time * 0.6)
        r2 = 145.0 + 4.0 * math.cos(self.anim_time * 0.4)
        painter.drawEllipse(cx - r1, cy - r1, r1 * 2, r1 * 2)
        painter.drawEllipse(cx - r2, cy - r2, r2 * 2, r2 * 2)

        # 2. Draw Outer Halo Glow
        glow_r = 90.0 + 6.0 * math.sin(self.anim_time * 1.5)
        grad = QRadialGradient(cx, cy, glow_r + 25.0)
        grad.setColorAt(0.0, QColor(cyan_core.red(), cyan_core.green(), cyan_core.blue(), glow_alpha))
        grad.setColorAt(0.65, QColor(cyan_core.red(), cyan_core.green(), cyan_core.blue(), int(glow_alpha * 0.3)))
        grad.setColorAt(1.0, QColor(7, 11, 20, 0))
        
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx - (glow_r + 25.0), cy - (glow_r + 25.0), (glow_r + 25.0) * 2, (glow_r + 25.0) * 2)

        # 3. Draw Dark Sphere Core
        sphere_r = 72.0
        grad_sphere = QRadialGradient(cx - 15, cy - 15, sphere_r + 10)
        grad_sphere.setColorAt(0.0, QColor(20, 30, 50))
        grad_sphere.setColorAt(0.7, QColor(8, 12, 22))
        grad_sphere.setColorAt(1.0, QColor(4, 7, 14))
        
        painter.setBrush(QBrush(grad_sphere))
        painter.setPen(QPen(QColor(cyan_core.red(), cyan_core.green(), cyan_core.blue(), 120), 1.5))
        painter.drawEllipse(cx - sphere_r, cy - sphere_r, sphere_r * 2, sphere_r * 2)

        # 4. Draw Glowing White Capsule Eyes (||)
        eye_w = 6.0
        eye_h = 16.0 + 2.0 * math.sin(self.anim_time * 2.0)
        eye_spacing = 10.0
        
        painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
        painter.setPen(Qt.NoPen)
        
        # Left Eye
        painter.drawRoundedRect(QRectF(cx - eye_spacing - eye_w, cy - eye_h / 2.0, eye_w, eye_h), 3.0, 3.0)
        # Right Eye
        painter.drawRoundedRect(QRectF(cx + eye_spacing, cy - eye_h / 2.0, eye_w, eye_h), 3.0, 3.0)

        # 5. Draw Status Pill Badge Below Orb ("● LISTENING")
        pill_w = 94.0
        pill_h = 22.0
        pill_y = cy + sphere_r - 12.0
        
        painter.setBrush(QBrush(QColor(8, 18, 32, 220)))
        painter.setPen(QPen(QColor(0, 240, 255, 100), 1))
        painter.drawRoundedRect(QRectF(cx - pill_w / 2.0, pill_y, pill_w, pill_h), 11.0, 11.0)
        
        # Dot
        painter.setBrush(QBrush(cyan_core))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx - pill_w / 2.0 + 10.0, pill_y + 7.0, 7.0, 7.0)
        
        # Text
        painter.setPen(QColor(0, 240, 255))
        font = QFont("Segoe UI", 8, QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        painter.setFont(font)
        painter.drawText(QRectF(cx - pill_w / 2.0 + 22.0, pill_y, pill_w - 24.0, pill_h), Qt.AlignVCenter | Qt.AlignLeft, status_text)

        # 6. Draw Audio Equalizer Visualizer Bars Below Status Pill
        eq_y = pill_y + pill_h + 18.0
        bar_w = 4.0
        bar_gap = 5.0
        total_eq_w = 7 * bar_w + 6 * bar_gap
        start_x = cx - total_eq_w / 2.0
        
        painter.setBrush(QBrush(QColor(0, 240, 255, 220)))
        for i in range(7):
            bx = start_x + i * (bar_w + bar_gap)
            bh = self.eq_heights[i]
            by = eq_y - bh / 2.0
            painter.drawRoundedRect(QRectF(bx, by, bar_w, bh), 2.0, 2.0)
