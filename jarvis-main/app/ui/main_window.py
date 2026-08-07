import sys
import time
import re
from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QCheckBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QListWidget, QListWidgetItem, QInputDialog, QMenu, QStackedWidget,
    QScrollArea
)
from PySide6.QtGui import QColor, QFont, QIcon, QAction
from app.config.settings import settings_manager
from app.database.db_manager import db_manager
from app.plugins.plugin_manager import plugin_manager
from app.ui.jarvis_orb import JarvisOrbWidget

DARK_SCI_FI_STYLE = """
QMainWindow {
    background-color: #050811;
}

/* Sidebar Navigation */
QFrame#sidebarFrame {
    background-color: #04060d;
    border-right: 1px solid #101827;
}

QPushButton.navBtn {
    background-color: transparent;
    color: #64748b;
    border: none;
    border-left: 3px solid transparent;
    padding: 12px 6px;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}

QPushButton.navBtn:hover {
    color: #94a3b8;
    background-color: rgba(0, 240, 255, 0.04);
}

QPushButton.navBtnActive {
    background-color: rgba(0, 240, 255, 0.08);
    color: #00f0ff;
    border-left: 3px solid #00f0ff;
    font-weight: bold;
}

/* Top Header */
QFrame#headerFrame {
    background-color: #050811;
    padding: 14px 24px;
}

QLabel#headerTitle {
    color: #ffffff;
    font-weight: 800;
    font-size: 18px;
    font-family: "Georgia", "Segoe UI", serif;
    letter-spacing: 2px;
}

QLabel#statusTag {
    color: #00f0ff;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1.5px;
}

/* Briefing Card */
QFrame#briefingCard {
    background-color: #090f1d;
    border: 1px solid #16243b;
    border-radius: 14px;
}

QLabel#briefingTitle {
    color: #00f0ff;
    font-size: 18px;
    font-weight: bold;
    font-family: "Georgia", "Segoe UI", serif;
}

QLabel#briefingDesc {
    color: #94a3b8;
    font-size: 12px;
    line-height: 1.5;
}

QPushButton#btnBriefing {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00e5ff, stop:1 #00a8ff);
    color: #040710;
    border: none;
    border-radius: 6px;
    padding: 10px 18px;
    font-weight: 800;
    font-size: 11px;
    letter-spacing: 1px;
}

QPushButton#btnBriefing:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33ecff, stop:1 #33b8ff);
}

QPushButton#btnReconcile {
    background-color: #0d1526;
    color: #e2e8f0;
    border: 1px solid #1e2d4a;
    border-radius: 6px;
    padding: 10px 18px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 1px;
}

QPushButton#btnReconcile:hover {
    background-color: #16233b;
    color: #00f0ff;
    border-color: #00f0ff;
}

/* Bottom Command Bar */
QFrame#commandBar {
    background-color: #080d1a;
    border: 1px solid #16243c;
    border-radius: 12px;
    padding: 4px 12px;
}

QFrame#commandBar:focus-within {
    border: 1px solid #00f0ff;
}

QLineEdit#commandInput {
    background-color: transparent;
    border: none;
    color: #f8fafc;
    font-size: 12.5px;
}

QLabel#execHint {
    color: #00f0ff;
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 1px;
}

/* Cards & Lists */
QFrame#tasksCard, QFrame#notesCard, QFrame#memoryCard, QFrame#settingsCard {
    background-color: #090f1d;
    border: 1px solid #16243b;
    border-radius: 14px;
}

QLineEdit, QTextEdit, QTableWidget, QListWidget {
    background-color: #040710;
    border: 1px solid #16243c;
    border-radius: 10px;
    padding: 10px;
    color: #f8fafc;
    font-size: 12px;
}

QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #00f0ff;
}

QPushButton.actionBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00e5ff, stop:1 #00a8ff);
    color: #040710;
    border: none;
    border-radius: 6px;
    padding: 9px 18px;
    font-weight: bold;
    font-size: 11px;
}

QPushButton.actionBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33ecff, stop:1 #33b8ff);
}

QPushButton#clearMemBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff4b2b, stop:1 #ff416c);
    color: white;
    border-radius: 6px;
    padding: 9px 18px;
    font-weight: bold;
}

QCheckBox {
    color: #f8fafc;
    spacing: 8px;
}

QComboBox {
    background-color: #040710;
    border: 1px solid #16243c;
    border-radius: 8px;
    padding: 8px 12px;
    color: #f8fafc;
}

QHeaderView::section {
    background-color: #090f1d;
    color: #00f0ff;
    padding: 8px;
    border: 1px solid #16243c;
    font-weight: bold;
    font-size: 11px;
}

QTableWidget {
    gridline-color: #16243c;
    selection-background-color: #16243c;
}
"""

class TodoItemWidget(QWidget):
    def __init__(self, task_text, status):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        
        self.label_task = QLabel(task_text)
        self.label_task.setStyleSheet("font-weight: 600; font-size: 12px; color: #f8fafc;")
        layout.addWidget(self.label_task)
        
        layout.addStretch()
        
        self.label_status = QLabel()
        if status == "completed":
            self.label_status.setText("Complete ✓")
            self.label_status.setStyleSheet("color: #10b981; font-weight: bold; font-size: 11px; background-color: rgba(16, 185, 129, 0.15); padding: 2px 8px; border-radius: 6px;")
        else:
            self.label_status.setText("In Progress •")
            self.label_status.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 11px; background-color: rgba(245, 158, 11, 0.15); padding: 2px 8px; border-radius: 6px;")
        layout.addWidget(self.label_status)

class NoteItemWidget(QWidget):
    def __init__(self, title, content):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)
        
        self.label_title = QLabel(title)
        self.label_title.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 12px;")
        
        self.label_content = QLabel(content)
        self.label_content.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        
        layout.addWidget(self.label_title)
        layout.addWidget(self.label_content)

class MainWindow(QMainWindow):
    text_submitted = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis System - Cyber Control Center")
        self.resize(1080, 850)
        self.setStyleSheet(DARK_SCI_FI_STYLE)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_h_layout = QHBoxLayout(central_widget)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        # 1. Left Vertical Sidebar Navigation
        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar.setFixedWidth(85)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 16, 0, 16)
        sb_layout.setSpacing(12)

        # Top Orb Logo Icon
        logo_label = QLabel("🌀")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("font-size: 24px; color: #00f0ff; margin-bottom: 12px;")
        sb_layout.addWidget(logo_label)

        # Nav Buttons
        self.nav_btns = {}
        nav_items = [
            ("CHAT", "💬", 0),
            ("TASKS", "☑", 1),
            ("NOTES", "📄", 2),
            ("MEMORY", "🧠", 3),
        ]

        for name, icon, page_idx in nav_items:
            btn = QPushButton(f"{icon}\n{name}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("class", "navBtn")
            btn.clicked.connect(lambda _, idx=page_idx: self.switch_page(idx))
            sb_layout.addWidget(btn)
            self.nav_btns[page_idx] = btn

        sb_layout.addStretch()

        # Bottom Settings & Power Buttons
        btn_settings = QPushButton("⚙\nSETTINGS")
        btn_settings.setCursor(Qt.PointingHandCursor)
        btn_settings.setProperty("class", "navBtn")
        btn_settings.clicked.connect(lambda: self.switch_page(4))
        sb_layout.addWidget(btn_settings)
        self.nav_btns[4] = btn_settings

        btn_exit = QPushButton("⏻\nEXIT")
        btn_exit.setCursor(Qt.PointingHandCursor)
        btn_exit.setProperty("class", "navBtn")
        btn_exit.clicked.connect(self.close)
        sb_layout.addWidget(btn_exit)

        main_h_layout.addWidget(sidebar)

        # 2. Main Right Area (Header + Stacked Pages)
        right_widget = QWidget()
        right_v_layout = QVBoxLayout(right_widget)
        right_v_layout.setContentsMargins(0, 0, 0, 0)
        right_v_layout.setSpacing(0)

        # Header Bar
        header = QFrame()
        header.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 16)

        title_label = QLabel("JARVIS SYSTEM")
        title_label.setObjectName("headerTitle")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_tag = QLabel("● NEURAL LINK: ACTIVE")
        self.status_tag.setObjectName("statusTag")
        header_layout.addWidget(self.status_tag)

        right_v_layout.addWidget(header)

        # QStackedWidget for Views
        self.stack = QStackedWidget()
        self.page_chat = self.create_chat_view()
        self.page_tasks = self.create_tasks_view()
        self.page_notes = self.create_notes_view()
        self.page_memory = self.create_memory_view()
        self.page_settings = self.create_settings_view()

        self.stack.addWidget(self.page_chat)
        self.stack.addWidget(self.page_tasks)
        self.stack.addWidget(self.page_notes)
        self.stack.addWidget(self.page_memory)
        self.stack.addWidget(self.page_settings)

        right_v_layout.addWidget(self.stack)
        main_h_layout.addWidget(right_widget)

        # Default active page = CHAT
        self.switch_page(0)

    def switch_page(self, idx: int):
        self.stack.setCurrentIndex(idx)
        for p_idx, btn in self.nav_btns.items():
            if p_idx == idx:
                btn.setStyleSheet("background-color: rgba(0, 240, 255, 0.1); color: #00f0ff; border-left: 3px solid #00f0ff; font-weight: bold;")
            else:
                btn.setStyleSheet("background-color: transparent; color: #64748b; border-left: 3px solid transparent;")

    def show_event(self, event):
        self.refresh_todos()
        self.refresh_memories()
        self.refresh_notes()
        self.refresh_plugins()
        self.refresh_briefing_card()

    # --- TAB 0: CHAT VIEW (Reference Screenshot replica) ---
    def create_chat_view(self) -> QWidget:
        view = QWidget()
        v_layout = QVBoxLayout(view)
        v_layout.setContentsMargins(32, 10, 32, 24)
        v_layout.setSpacing(16)

        # 1. Central AI Orb Visualizer
        self.orb = JarvisOrbWidget()
        v_layout.addWidget(self.orb, 0, Qt.AlignCenter)

        # 2. Central Briefing Card
        self.briefing_card = QFrame()
        self.briefing_card.setObjectName("briefingCard")
        b_layout = QVBoxLayout(self.briefing_card)
        b_layout.setContentsMargins(24, 20, 24, 20)
        b_layout.setSpacing(12)

        user_name = db_manager.get_memory("user_name") or "Aditya"
        self.briefing_title = QLabel(f"Jarvis online. Welcome back, {user_name}!")
        self.briefing_title.setObjectName("briefingTitle")
        b_layout.addWidget(self.briefing_title)

        self.briefing_desc = QLabel()
        self.briefing_desc.setObjectName("briefingDesc")
        self.briefing_desc.setWordWrap(True)
        b_layout.addWidget(self.briefing_desc)

        # Briefing Card Action Buttons
        b_btn_layout = QHBoxLayout()
        b_btn_layout.setSpacing(14)
        
        self.btn_gen_briefing = QPushButton("GENERATE BRIEFING")
        self.btn_gen_briefing.setObjectName("btnBriefing")
        self.btn_gen_briefing.setCursor(Qt.PointingHandCursor)
        self.btn_gen_briefing.clicked.connect(self.generate_briefing_action)
        
        self.btn_reconcile = QPushButton("⚡ RECONCILE TASKS")
        self.btn_reconcile.setObjectName("btnReconcile")
        self.btn_reconcile.setCursor(Qt.PointingHandCursor)
        self.btn_reconcile.clicked.connect(self.reconcile_tasks_action)

        b_btn_layout.addWidget(self.btn_gen_briefing)
        b_btn_layout.addWidget(self.btn_reconcile)
        b_btn_layout.addStretch()
        b_layout.addLayout(b_btn_layout)

        v_layout.addWidget(self.briefing_card)

        # 3. Live Chat Log Stream
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("background-color: transparent; border: none; font-size: 12px;")
        v_layout.addWidget(self.chat_display)

        # 4. Bottom Command Input Bar
        cmd_bar = QFrame()
        cmd_bar.setObjectName("commandBar")
        cmd_layout = QHBoxLayout(cmd_bar)
        cmd_layout.setContentsMargins(16, 6, 16, 6)
        cmd_layout.setSpacing(10)

        prompt_lbl = QLabel(">")
        prompt_lbl.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 14px;")
        cmd_layout.addWidget(prompt_lbl)

        self.cmd_input = QLineEdit()
        self.cmd_input.setObjectName("commandInput")
        self.cmd_input.setPlaceholderText("Specify command...")
        self.cmd_input.returnPressed.connect(self.submit_command)
        cmd_layout.addWidget(self.cmd_input)

        exec_hint = QLabel("RETURN TO EXECUTE")
        exec_hint.setObjectName("execHint")
        cmd_layout.addWidget(exec_hint)

        mic_btn = QPushButton("🎙")
        mic_btn.setCursor(Qt.PointingHandCursor)
        mic_btn.setStyleSheet("background: transparent; color: #00f0ff; font-size: 16px; border: none; padding: 2px 6px;")
        mic_btn.clicked.connect(self.trigger_mic_record)
        cmd_layout.addWidget(mic_btn)

        v_layout.addWidget(cmd_bar)

        return view

    def refresh_briefing_card(self):
        user_name = db_manager.get_memory("user_name") or "Aditya"
        self.briefing_title.setText(f"Jarvis online. Welcome back, {user_name}!")
        
        pending_count = len(db_manager.get_todos(status="pending"))
        self.briefing_desc.setText(
            f"Systems optimized. I've prepared your daily briefing and flagged {pending_count} urgent tasks "
            f"in the Neural Link queue. How can I assist you this afternoon?"
        )

    def generate_briefing_action(self):
        user_name = db_manager.get_memory("user_name") or "Aditya"
        pending_todos = db_manager.get_todos(status="pending")
        notes = db_manager.get_notes()
        
        task_str = f"{len(pending_todos)} pending tasks" if pending_todos else "no pending tasks"
        note_str = f"{len(notes)} saved notes" if notes else "no notes"
        briefing_text = f"Daily Briefing for {user_name}: All systems operational. You have {task_str} and {note_str} stored in memory."
        
        self.append_message("Jarvis", briefing_text)
        self.text_submitted.emit(briefing_text)

    def reconcile_tasks_action(self):
        self.switch_page(1)

    def trigger_mic_record(self):
        self.append_message("System", "Voice listener active...")

    def submit_command(self):
        text = self.cmd_input.text().strip()
        if text:
            self.append_message("You", text)
            self.text_submitted.emit(text)
            self.cmd_input.clear()

    def append_message(self, sender: str, message: str):
        color = "#00f0ff" if sender == "Jarvis" else "#94a3b8"
        bg_color = "rgba(0, 240, 255, 0.06)" if sender == "Jarvis" else "rgba(148, 163, 184, 0.06)"
        bubble = (
            f"<div style='margin: 4px 0; padding: 6px 12px; border-radius: 8px; background-color: {bg_color};'>"
            f"<b style='color: {color}; font-size: 11.5px;'>{sender}:</b> "
            f"<span style='color: #f8fafc; font-size: 11.5px;'>{message}</span>"
            f"</div>"
        )
        self.chat_display.append(bubble)

    # --- TAB 1: TASKS VIEW ---
    def create_tasks_view(self) -> QWidget:
        view = QWidget()
        v_layout = QVBoxLayout(view)
        v_layout.setContentsMargins(28, 20, 28, 24)
        v_layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("tasksCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(12)

        title = QLabel("Neural Link Task Queue")
        title.setStyleSheet("color: #00f0ff; font-size: 16px; font-weight: bold;")
        c_layout.addWidget(title)

        self.todo_list = QListWidget()
        self.todo_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.todo_list.customContextMenuRequested.connect(self.show_todo_context_menu)
        c_layout.addWidget(self.todo_list)

        btn_add = QPushButton("+ Add New Task")
        btn_add.setProperty("class", "actionBtn")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self.add_todo)
        c_layout.addWidget(btn_add)

        v_layout.addWidget(card)
        return view

    def refresh_todos(self):
        self.todo_list.clear()
        todos_pending = db_manager.get_todos(status="pending")
        todos_completed = db_manager.get_todos(status="completed")
        todos = todos_pending + todos_completed
        todos.sort(key=lambda x: x['id'])

        for idx, t in enumerate(todos, start=1):
            item = QListWidgetItem(self.todo_list)
            item.setData(Qt.UserRole, t['id'])
            item.setData(Qt.UserRole + 1, t['status'])
            item.setSizeHint(QSize(100, 38))
            
            task_label = f"{idx}. {t['task']}"
            widget = TodoItemWidget(task_label, t['status'])
            
            self.todo_list.addItem(item)
            self.todo_list.setItemWidget(item, widget)
        
        self.refresh_briefing_card()

    def add_todo(self):
        text, ok = QInputDialog.getText(self, "Add Task", "Enter new task description:")
        if ok and text.strip():
            db_manager.add_todo(text.strip())
            self.refresh_todos()

    def toggle_todo_status(self, todo_id: int, current_status: str):
        new_status = "completed" if current_status == "pending" else "pending"
        db_manager.update_todo_status(todo_id, new_status)
        self.refresh_todos()

    def delete_todo_by_id(self, todo_id: int):
        db_manager.delete_todo(todo_id)
        self.refresh_todos()

    def show_todo_context_menu(self, pos):
        item = self.todo_list.itemAt(pos)
        if not item:
            return
        todo_id = item.data(Qt.UserRole)
        todo_status = item.data(Qt.UserRole + 1)
        
        menu = QMenu(self)
        toggle_action = QAction("Mark Completed" if todo_status == "pending" else "Mark In Progress", self)
        toggle_action.triggered.connect(lambda: self.toggle_todo_status(todo_id, todo_status))
        delete_action = QAction("Delete Task", self)
        delete_action.triggered.connect(lambda: self.delete_todo_by_id(todo_id))
        
        menu.addAction(toggle_action)
        menu.addAction(delete_action)
        menu.exec(self.todo_list.mapToGlobal(pos))

    # --- TAB 2: NOTES VIEW ---
    def create_notes_view(self) -> QWidget:
        view = QWidget()
        v_layout = QVBoxLayout(view)
        v_layout.setContentsMargins(28, 20, 28, 24)
        v_layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("notesCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(12)

        title = QLabel("Saved Notes & Snippets")
        title.setStyleSheet("color: #00f0ff; font-size: 16px; font-weight: bold;")
        c_layout.addWidget(title)

        self.notes_list = QListWidget()
        self.notes_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.notes_list.customContextMenuRequested.connect(self.show_notes_context_menu)
        c_layout.addWidget(self.notes_list)

        btn_add = QPushButton("+ Create New Note")
        btn_add.setProperty("class", "actionBtn")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self.add_note_ui)
        c_layout.addWidget(btn_add)

        v_layout.addWidget(card)
        return view

    def refresh_notes(self):
        self.notes_list.clear()
        notes = db_manager.get_notes()
        for n in notes:
            item = QListWidgetItem(self.notes_list)
            item.setData(Qt.UserRole, n['id'])
            item.setSizeHint(QSize(100, 50))
            
            widget = NoteItemWidget(n['title'], n['content'])
            self.notes_list.addItem(item)
            self.notes_list.setItemWidget(item, widget)

    def add_note_ui(self):
        title, ok1 = QInputDialog.getText(self, "Create Note", "Enter note title:")
        if ok1 and title.strip():
            content, ok2 = QInputDialog.getText(self, "Create Note", "Enter note content:")
            if ok2 and content.strip():
                db_manager.add_note(title.strip(), content.strip())
                self.refresh_notes()

    def delete_note_by_id(self, note_id: int):
        db_manager.delete_note(note_id)
        self.refresh_notes()

    def show_notes_context_menu(self, pos):
        item = self.notes_list.itemAt(pos)
        if not item:
            return
        note_id = item.data(Qt.UserRole)
        menu = QMenu(self)
        delete_action = QAction("Delete Note", self)
        delete_action.triggered.connect(lambda: self.delete_note_by_id(note_id))
        menu.addAction(delete_action)
        menu.exec(self.notes_list.mapToGlobal(pos))

    # --- TAB 3: MEMORY VIEW ---
    def create_memory_view(self) -> QWidget:
        view = QWidget()
        v_layout = QVBoxLayout(view)
        v_layout.setContentsMargins(28, 20, 28, 24)
        v_layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("memoryCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(12)

        title = QLabel("Semantic Long-Term Memory")
        title.setStyleSheet("color: #00f0ff; font-size: 16px; font-weight: bold;")
        c_layout.addWidget(title)

        self.memory_table = QTableWidget(0, 3)
        self.memory_table.setHorizontalHeaderLabels(["ID", "Key", "Value"])
        self.memory_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.memory_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.memory_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.memory_table.customContextMenuRequested.connect(self.show_memory_context_menu)
        c_layout.addWidget(self.memory_table)

        btn_layout = QHBoxLayout()
        btn_add = QPushButton("+ Add Memory")
        btn_add.setProperty("class", "actionBtn")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self.add_memory_ui)
        
        btn_clear = QPushButton("Clear Memory")
        btn_clear.setObjectName("clearMemBtn")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self.clear_all_memories)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_clear)
        c_layout.addLayout(btn_layout)

        v_layout.addWidget(card)
        return view

    def refresh_memories(self):
        self.memory_table.setRowCount(0)
        memories = db_manager.get_all_memories()
        for m in memories:
            row = self.memory_table.rowCount()
            self.memory_table.insertRow(row)
            
            id_item = QTableWidgetItem(f"{m['id']:03d}")
            id_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            key_item = QTableWidgetItem(m["memory_key"])
            val_item = QTableWidgetItem(m["memory_value"])
            
            self.memory_table.setItem(row, 0, id_item)
            self.memory_table.setItem(row, 1, key_item)
            self.memory_table.setItem(row, 2, val_item)

    def add_memory_ui(self):
        key, ok1 = QInputDialog.getText(self, "Add Memory", "Enter memory key/fact name:")
        if ok1 and key.strip():
            val, ok2 = QInputDialog.getText(self, "Add Memory", f"Enter value for '{key.strip()}':")
            if ok2 and val.strip():
                db_manager.add_memory(key.strip(), val.strip())
                self.refresh_memories()

    def show_memory_context_menu(self, pos):
        item = self.memory_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        id_item = self.memory_table.item(row, 0)
        if not id_item:
            return
        try:
            mem_id = int(id_item.text())
        except ValueError:
            return
            
        menu = QMenu(self)
        delete_action = QAction("Delete Memory", self)
        delete_action.triggered.connect(lambda: self.delete_memory_by_id(mem_id))
        menu.addAction(delete_action)
        menu.exec(self.memory_table.mapToGlobal(pos))

    def delete_memory_by_id(self, mem_id: int):
        db_manager.delete_memory(mem_id)
        self.refresh_memories()

    def clear_all_memories(self):
        try:
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM long_term_memory")
            conn.commit()
            conn.close()
            self.refresh_memories()
        except Exception as e:
            pass

    # --- TAB 4: SETTINGS VIEW ---
    def create_settings_view(self) -> QWidget:
        view = QWidget()
        v_layout = QVBoxLayout(view)
        v_layout.setContentsMargins(28, 20, 28, 24)
        v_layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("settingsCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(14)

        title = QLabel("System & AI Configuration")
        title.setStyleSheet("color: #00f0ff; font-size: 16px; font-weight: bold;")
        c_layout.addWidget(title)

        self.chk_autostart = QCheckBox("Run at Windows Startup")
        self.chk_autostart.setChecked(settings_manager.get("auto_start", False))
        self.chk_autostart.stateChanged.connect(self.save_general_settings)
        c_layout.addWidget(self.chk_autostart)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(16)

        # Wake Mode
        v1 = QVBoxLayout()
        lbl_wake = QLabel("Wake Mode")
        lbl_wake.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 11px;")
        self.cmb_wake_mode = QComboBox()
        self.cmb_wake_mode.addItems(["voice", "typed", "double_clap"])
        self.cmb_wake_mode.setCurrentText(settings_manager.get("wake_mode", "voice"))
        self.cmb_wake_mode.currentIndexChanged.connect(self.save_general_settings)
        v1.addWidget(lbl_wake)
        v1.addWidget(self.cmb_wake_mode)

        # Local Ollama Connection
        v2 = QVBoxLayout()
        lbl_ollama = QLabel("Local LLM (model@url)")
        lbl_ollama.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 11px;")
        self.txt_ollama_ai = QLineEdit()
        url = settings_manager.get("ollama_api_url", "http://localhost:11434")
        display_url = url.replace("http://", "").replace("https://", "").rstrip("/")
        model = settings_manager.get("ollama_model", "mistral")
        self.txt_ollama_ai.setText(f"{model}@{display_url}")
        self.txt_ollama_ai.editingFinished.connect(self.save_ai_settings_unified)
        v2.addWidget(lbl_ollama)
        v2.addWidget(self.txt_ollama_ai)

        form_layout.addLayout(v1)
        form_layout.addLayout(v2)
        c_layout.addLayout(form_layout)

        self.lbl_plugins = QLabel("Plugins: None")
        self.lbl_plugins.setStyleSheet("color: #64748b; font-size: 11px;")
        c_layout.addWidget(self.lbl_plugins)

        v_layout.addWidget(card)
        return view

    def save_general_settings(self):
        settings_manager.set("auto_start", self.chk_autostart.isChecked())
        settings_manager.set("wake_mode", self.cmb_wake_mode.currentText())

    def save_ai_settings_unified(self):
        text = self.txt_ollama_ai.text().strip()
        if "@" in text:
            model, raw_url = text.split("@", 1)
            url = raw_url.strip()
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "http://" + url
            settings_manager.set("ollama_model", model.strip())
            settings_manager.set("ollama_api_url", url)

    def refresh_plugins(self):
        plugin_manager.load_plugins()
        names = list(plugin_manager.loaded_plugins.keys())
        if names:
            self.lbl_plugins.setText(f"Active Plugins: {', '.join(names)}")
        else:
            self.lbl_plugins.setText("Active Plugins: None")
