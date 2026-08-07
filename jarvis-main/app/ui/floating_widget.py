import math
from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QBrush, QPen
from PySide6.QtWidgets import QWidget

class FloatingAssistant(QWidget):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        # Frameless, stays on top, tool window (doesn't show in taskbar)
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(90, 90)

        # Drag position variables
        self.drag_position = QPoint()

        # Animation state variables
        # state can be: "idle" (static slow breath), "listening" (active fast pulse), "thinking" (spin/rapid pulse), "speaking" (sound wave)
        self.state = "idle"
        self.anim_time = 0.0
        self.pulse_radius = 35.0

        # Animation timer: 60 FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(16) # ~60fps

    def set_state(self, state: str):
        if state in ("idle", "listening", "thinking", "speaking"):
            self.state = state

    def update_animation(self):
        self.anim_time += 0.06
        
        # Determine pulse parameters based on state
        if self.state == "idle":
            # Slow breath: oscillates between 30 and 35
            self.pulse_radius = 32.5 + 2.5 * math.sin(self.anim_time * 0.5)
        elif self.state == "listening":
            # Fast pulse: oscillates between 30 and 38
            self.pulse_radius = 34.0 + 4.0 * math.sin(self.anim_time * 2.0)
        elif self.state == "thinking":
            # Shivering/rapid shimmer
            self.pulse_radius = 33.0 + 2.0 * math.sin(self.anim_time * 4.0) + 1.0 * math.cos(self.anim_time * 7.0)
        elif self.state == "speaking":
            # Voice waves (large rapid oscillations)
            self.pulse_radius = 33.0 + 6.0 * abs(math.sin(self.anim_time * 1.5))
            
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center_x = self.width() / 2
        center_y = self.height() / 2
        
        # Color mapping based on state
        # Idle = Cyan, Listening = Red/Magenta, Thinking = Orange/Gold, Speaking = Purple/Blue
        if self.state == "idle":
            core_color = QColor(0, 191, 255)      # Deep Sky Blue
            glow_color = QColor(0, 191, 255, 60)
        elif self.state == "listening":
            core_color = QColor(255, 20, 147)     # Deep Pink
            glow_color = QColor(255, 20, 147, 60)
        elif self.state == "thinking":
            core_color = QColor(255, 140, 0)      # Dark Orange
            glow_color = QColor(255, 140, 0, 60)
        elif self.state == "speaking":
            core_color = QColor(138, 43, 226)     # Blue Violet
            glow_color = QColor(138, 43, 226, 60)

        # Draw outer glowing ring
        gradient = QRadialGradient(center_x, center_y, self.pulse_radius + 10)
        gradient.setColorAt(0.0, core_color)
        gradient.setColorAt(0.6, glow_color)
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            center_x - (self.pulse_radius + 10),
            center_y - (self.pulse_radius + 10),
            (self.pulse_radius + 10) * 2,
            (self.pulse_radius + 10) * 2
        )

        # Draw core solid circle
        core_radius = 20.0
        painter.setBrush(QBrush(core_color))
        painter.drawEllipse(
            center_x - core_radius,
            center_y - core_radius,
            core_radius * 2,
            core_radius * 2
        )

        # Draw neat inner white core details
        painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
        painter.drawEllipse(
            center_x - 5,
            center_y - 5,
            10,
            10
        )

    # --- Mouse Drag Handling ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
