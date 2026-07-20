import sys
import time
import re
from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QCheckBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QListWidget, QListWidgetItem, QInputDialog, QMenu
)
from PySide6.QtGui import QColor, QFont, QIcon, QAction
from app.config.settings import settings_manager
from app.database.db_manager import db_manager
from app.plugins.plugin_manager import plugin_manager

DARK_STYLE = """
QMainWindow {
    background-color: #080c14;
}

QFrame#headerBar {
    background-color: #0c111d;
    border-bottom: 1px solid #1e293b;
    padding: 8px 16px;
}

QLabel#headerTitle {
    color: #ffffff;
    font-weight: bold;
    font-size: 14px;
    font-family: "Segoe UI", sans-serif;
}

QLabel#headerUser {
    color: #94a3b8;
    font-size: 12px;
}

QFrame#chatCard, QFrame#memoryCard, QFrame#tasksCard, QFrame#settingsCard, QFrame#notesCard {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 12px;
}

QLabel.cardTitle {
    color: #00f0ff;
    font-size: 14px;
    font-weight: bold;
}

QLabel.cardSubTitle {
    color: #64748b;
    font-size: 11px;
}

QLineEdit, QTextEdit, QTableWidget, QListWidget {
    background-color: #020617;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 8px;
    color: #f1f5f9;
}

QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #00f0ff;
}

QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d2ff, stop:1 #00f0ff);
    color: #020617;
    border: none;
    border-radius: 6px;
    padding: 9px 18px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33d9ff, stop:1 #33f2ff);
}

QPushButton:pressed {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00b0d4, stop:1 #00c3d4);
}

QPushButton#clearMemBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff3b70, stop:1 #ff5c8a);
    color: white;
    border-radius: 6px;
    padding: 9px 18px;
    font-weight: bold;
}

QPushButton#clearMemBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff5784, stop:1 #ff7a9f);
}

QPushButton#addTaskBtn {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}

QPushButton#addTaskBtn:hover {
    background-color: #334155;
}

QCheckBox {
    color: #f1f5f9;
    spacing: 6px;
}

QComboBox {
    background-color: #020617;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 6px;
    color: #f1f5f9;
}

QComboBox::drop-down {
    border: none;
}

QHeaderView::section {
    background-color: #0f172a;
    color: #94a3b8;
    padding: 6px;
    border: 1px solid #1e293b;
    font-weight: bold;
}

QTableWidget {
    gridline-color: #1e293b;
}
"""

class TodoItemWidget(QWidget):
    def __init__(self, task_text, status):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        self.label_task = QLabel(task_text)
        self.label_task.setStyleSheet("color: #f1f5f9; font-weight: 500;")
        layout.addWidget(self.label_task)
        
        layout.addStretch()
        
        self.label_status = QLabel()
        if status == "completed":
            self.label_status.setText("Complete ✓")
            self.label_status.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.label_status.setText("In Progress •")
            self.label_status.setStyleSheet("color: #f59e0b; font-weight: bold;")
        layout.addWidget(self.label_status)

class NoteItemWidget(QWidget):
    def __init__(self, title, content):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        
        self.label_title = QLabel(title)
        self.label_title.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 12px;")
        
        self.label_content = QLabel(content)
        self.label_content.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        
        layout.addWidget(self.label_title)
        layout.addWidget(self.label_content)

class MainWindow(QMainWindow):
    text_submitted = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis Assistant - Dashboard")
        self.resize(960, 800)
        self.setStyleSheet(DARK_STYLE)

        # Central Widget & Base Vertical Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        base_layout = QVBoxLayout(central_widget)
        base_layout.setContentsMargins(0, 0, 0, 0)
        base_layout.setSpacing(0)

        # 1. Custom Header Bar
        header = QFrame()
        header.setObjectName("headerBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)

        # macOS style window buttons
        dots_layout = QHBoxLayout()
        dots_layout.setSpacing(6)
        for color in ("#ff5f56", "#ffbd2e", "#27c93f"):
            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
            dots_layout.addWidget(dot)
        header_layout.addLayout(dots_layout)
        header_layout.addStretch()

        # Center Title
        self.title_label = QLabel("Jarvis Assistant - Dashboard")
        self.title_label.setObjectName("headerTitle")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        # Right User Label
        user_name = db_manager.get_memory("user_name") or "Alex R."
        self.user_label = QLabel(f"User: {user_name}")
        self.user_label.setObjectName("headerUser")
        header_layout.addWidget(self.user_label)
        
        base_layout.addWidget(header)

        # 2. Main 3-row Grid Body Layout
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(16, 16, 16, 16)
        grid_layout.setSpacing(16)

        # Initialize cards
        self.chat_card = self.create_chat_card()
        self.mem_card = self.create_memory_card()
        self.tasks_card = self.create_tasks_card()
        self.notes_card = self.create_notes_card()
        self.settings_card = self.create_settings_card()

        # Add to grid
        grid_layout.addWidget(self.chat_card, 0, 0)
        grid_layout.addWidget(self.mem_card, 0, 1)
        grid_layout.addWidget(self.tasks_card, 1, 0)
        grid_layout.addWidget(self.notes_card, 1, 1)
        grid_layout.addWidget(self.settings_card, 2, 0, 1, 2) # spanning wide at the bottom

        # Set stretch factors for equal spacing
        grid_layout.setRowStretch(0, 2)
        grid_layout.setRowStretch(1, 2)
        grid_layout.setRowStretch(2, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)

        base_layout.addWidget(grid_widget)

    def show_event(self, event):
        # Refresh all values when dashboard is shown
        self.refresh_todos()
        self.refresh_memories()
        self.refresh_notes()
        self.refresh_plugins()
        self.refresh_user_label()

    def refresh_user_label(self):
        user_name = db_manager.get_memory("user_name") or "Alex R."
        self.user_label.setText(f"User: {user_name}")

    # --- Chat Card ---
    def create_chat_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("chatCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header Title
        title_layout = QHBoxLayout()
        title = QLabel("Chat")
        title.setObjectName("chatTitle")
        title.setProperty("class", "cardTitle")
        title.setStyleSheet("color: #00f0ff; font-size: 14px; font-weight: bold;")
        sub = QLabel("(Live)")
        sub.setStyleSheet("color: #64748b; font-size: 11px;")
        title_layout.addWidget(title)
        title_layout.addWidget(sub)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a command or ask Jarvis...")
        self.chat_input.returnPressed.connect(self.submit_text)
        
        self.send_btn = QPushButton("SEND")
        self.send_btn.clicked.connect(self.submit_text)

        input_layout.addWidget(self.chat_input)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        return card

    def submit_text(self):
        text = self.chat_input.text().strip()
        if text:
            self.append_message("You", text)
            self.text_submitted.emit(text)
            self.chat_input.clear()

    def append_message(self, sender: str, message: str):
        color = "#00e5ff" if sender == "Jarvis" else "#a0aec0"
        bubble = f"<p style='margin: 4px 0;'><b style='color: {color};'>{sender}:</b> {message}</p>"
        self.chat_display.append(bubble)

    # --- Memory Card ---
    def create_memory_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("memoryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header Title
        title_layout = QHBoxLayout()
        title = QLabel("Memory")
        title.setStyleSheet("color: #00f0ff; font-size: 14px; font-weight: bold;")
        
        # Display current date and time in subtitle
        self.time_sub = QLabel()
        self.time_sub.setStyleSheet("color: #64748b; font-size: 11px;")
        self.update_memory_time_subtitle()
        
        title_layout.addWidget(title)
        title_layout.addWidget(self.time_sub)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        self.memory_table = QTableWidget(0, 3)
        self.memory_table.setHorizontalHeaderLabels(["ID", "Key", "Value"])
        self.memory_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.memory_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.memory_table)

        self.mem_clear_btn = QPushButton("Clear Memory")
        self.mem_clear_btn.setObjectName("clearMemBtn")
        self.mem_clear_btn.clicked.connect(self.clear_all_memories)
        layout.addWidget(self.mem_clear_btn)

        return card

    def update_memory_time_subtitle(self):
        current_time = time.strftime("%m/%d/%y, %H:%M")
        self.time_sub.setText(f"({current_time})")

    def refresh_memories(self):
        self.memory_table.setRowCount(0)
        self.update_memory_time_subtitle()
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

    # --- Tasks Card ---
    def create_tasks_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("tasksCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header Title
        title_layout = QHBoxLayout()
        title = QLabel("Tasks")
        title.setStyleSheet("color: #00f0ff; font-size: 14px; font-weight: bold;")
        sub = QLabel("(Active)")
        sub.setStyleSheet("color: #64748b; font-size: 11px;")
        title_layout.addWidget(title)
        title_layout.addWidget(sub)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # Custom Tasks List
        self.todo_list = QListWidget()
        self.todo_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.todo_list.customContextMenuRequested.connect(self.show_todo_context_menu)
        layout.addWidget(self.todo_list)

        self.todo_add_btn = QPushButton("+ Add New Task")
        self.todo_add_btn.setObjectName("addTaskBtn")
        self.todo_add_btn.clicked.connect(self.add_todo)
        layout.addWidget(self.todo_add_btn)

        return card

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
            item.setSizeHint(QSize(100, 36))
            
            task_label = f"{idx}. {t['task']}"
            widget = TodoItemWidget(task_label, t['status'])
            
            self.todo_list.addItem(item)
            self.todo_list.setItemWidget(item, widget)

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

    # --- Notes Card ---
    def create_notes_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("notesCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header Title
        title_layout = QHBoxLayout()
        title = QLabel("Notes")
        title.setStyleSheet("color: #00f0ff; font-size: 14px; font-weight: bold;")
        sub = QLabel("(Saved)")
        sub.setStyleSheet("color: #64748b; font-size: 11px;")
        title_layout.addWidget(title)
        title_layout.addWidget(sub)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # Custom Notes List
        self.notes_list = QListWidget()
        self.notes_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.notes_list.customContextMenuRequested.connect(self.show_notes_context_menu)
        layout.addWidget(self.notes_list)

        self.note_add_btn = QPushButton("+ Create New Note")
        self.note_add_btn.setObjectName("addTaskBtn")
        self.note_add_btn.clicked.connect(self.add_note_ui)
        layout.addWidget(self.note_add_btn)

        return card

    def refresh_notes(self):
        self.notes_list.clear()
        notes = db_manager.get_notes()
        for n in notes:
            item = QListWidgetItem(self.notes_list)
            item.setData(Qt.UserRole, n['id'])
            item.setSizeHint(QSize(100, 48))
            
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

    # --- Settings Card ---
    def create_settings_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header Title
        title_layout = QHBoxLayout()
        title = QLabel("Settings")
        title.setStyleSheet("color: #00f0ff; font-size: 14px; font-weight: bold;")
        sub = QLabel("(Configured)")
        sub.setStyleSheet("color: #64748b; font-size: 11px;")
        title_layout.addWidget(title)
        title_layout.addWidget(sub)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # Side by side check boxes
        chk_layout = QHBoxLayout()
        self.chk_autostart = QCheckBox("Run at Startup")
        self.chk_autostart.setChecked(settings_manager.get("auto_start", False))
        self.chk_autostart.stateChanged.connect(self.save_general_settings)
        
        self.chk_lightmode = QCheckBox("Light Mode")
        self.chk_lightmode.setChecked(settings_manager.get("theme", "dark") == "light")
        self.chk_lightmode.stateChanged.connect(self.toggle_theme_visual)

        chk_layout.addWidget(self.chk_autostart)
        chk_layout.addWidget(self.chk_lightmode)
        layout.addLayout(chk_layout)

        # Forms
        form_layout = QVBoxLayout()
        form_layout.setSpacing(12)

        # Wake Mode
        lbl_wake = QLabel("Wake Mode")
        lbl_wake.setStyleSheet("color: #94a3b8; font-weight: 500;")
        self.cmb_wake_mode = QComboBox()
        self.cmb_wake_mode.addItems(["voice", "typed", "double_clap"])
        self.cmb_wake_mode.setCurrentText(settings_manager.get("wake_mode", "voice"))
        self.cmb_wake_mode.currentIndexChanged.connect(self.save_general_settings)
        form_layout.addWidget(lbl_wake)
        form_layout.addWidget(self.cmb_wake_mode)

        # Ollama AI Connection
        lbl_ollama = QLabel("Ollama AI")
        lbl_ollama.setStyleSheet("color: #94a3b8; font-weight: 500;")
        self.txt_ollama_ai = QLineEdit()
        
        # Display as model@url
        url = settings_manager.get("ollama_api_url", "http://localhost:11434")
        display_url = url.replace("http://", "").replace("https://", "").rstrip("/")
        model = settings_manager.get("ollama_model", "mistral")
        self.txt_ollama_ai.setText(f"{model}@{display_url}")
        self.txt_ollama_ai.editingFinished.connect(self.save_ai_settings_unified)
        
        form_layout.addWidget(lbl_ollama)
        form_layout.addWidget(self.txt_ollama_ai)

        # Dynamic Plugin Information
        self.lbl_plugins = QLabel("Plugins: None")
        self.lbl_plugins.setStyleSheet("color: #64748b; font-size: 11px;")
        form_layout.addWidget(self.lbl_plugins)

        layout.addLayout(form_layout)
        layout.addStretch()

        return card

    def toggle_theme_visual(self):
        theme_val = "light" if self.chk_lightmode.isChecked() else "dark"
        settings_manager.set("theme", theme_val)

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
