import sqlite3
import datetime
from pathlib import Path
from app.utils.logger import get_app_dir, log

class DatabaseManager:
    def __init__(self):
        self.app_dir = get_app_dir()
        self.db_file = self.app_dir / "jarvis.db"
        self.conn = None
        self.init_db()

    def get_connection(self):
        """Get thread-safe connection to the SQLite database."""
        # SQLite doesn't allow cross-thread usage of the same connection object
        # so we open a new connection or run it on demand.
        conn = sqlite3.connect(str(self.db_file))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Create tables if they don't exist."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Conversation History
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    role TEXT,
                    content TEXT
                )
            """)

            # Long-Term Memory (facts about user or preferences)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_key TEXT UNIQUE,
                    memory_value TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # To-Do list
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT,
                    status TEXT DEFAULT 'pending', -- 'pending', 'completed'
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    due_at TEXT
                )
            """)

            # Alarms/Timers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alarms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alarm_time TEXT, -- HH:MM
                    active INTEGER DEFAULT 1, -- 0 or 1
                    label TEXT
                )
            """)

            # Notes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    content TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            conn.close()
            log.info("Database initialized successfully.")
        except Exception as e:
            log.error("Failed to initialize database: %s", e)

    # --- Conversation History APIs ---
    def add_history(self, role: str, content: str):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversation_history (role, content) VALUES (?, ?)",
                (role, content)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("Failed to write to conversation history: %s", e)

    def get_history(self, limit: int = 50):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content, timestamp FROM conversation_history ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            # Return in chronological order
            return [dict(r) for r in reversed(rows)]
        except Exception as e:
            log.error("Failed to fetch conversation history: %s", e)
            return []

    def clear_history(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversation_history")
            conn.commit()
            conn.close()
            log.info("Conversation history cleared.")
        except Exception as e:
            log.error("Failed to clear conversation history: %s", e)

    # --- Long-Term Memory APIs ---
    def add_memory(self, key: str, value: str):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO long_term_memory (memory_key, memory_value)
                VALUES (?, ?)
                ON CONFLICT(memory_key) DO UPDATE SET memory_value=excluded.memory_value, timestamp=CURRENT_TIMESTAMP
                """,
                (key.strip().lower(), value.strip())
            )
            conn.commit()
            conn.close()
            log.info("Memory updated: %s -> %s", key, value)
        except Exception as e:
            log.error("Failed to save memory: %s", e)

    def get_memory(self, key: str) -> str | None:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT memory_value FROM long_term_memory WHERE memory_key = ?",
                (key.strip().lower(),)
            )
            row = cursor.fetchone()
            conn.close()
            return row["memory_value"] if row else None
        except Exception as e:
            log.error("Failed to fetch memory: %s", e)
            return None

    def search_memories(self, query: str):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT memory_key, memory_value FROM long_term_memory WHERE memory_key LIKE ? OR memory_value LIKE ?",
                (f"%{query}%", f"%{query}%")
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("Failed to search memories: %s", e)
            return []

    def get_all_memories(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, memory_key, memory_value, timestamp FROM long_term_memory ORDER BY id DESC")
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("Failed to fetch all memories: %s", e)
            return []

    def delete_memory(self, memory_id: int):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM long_term_memory WHERE id = ?", (memory_id,))
            conn.commit()
            conn.close()
            log.info("Memory ID %d deleted.", memory_id)
        except Exception as e:
            log.error("Failed to delete memory ID %d: %s", memory_id, e)

    # --- To-Do List APIs ---
    def add_todo(self, task: str, due_at: str = None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO todos (task, due_at) VALUES (?, ?)",
                (task, due_at)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("Failed to add todo: %s", e)

    def get_todos(self, status="pending"):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, task, status, created_at, due_at FROM todos WHERE status = ? ORDER BY id DESC",
                (status,)
            )
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("Failed to get todos: %s", e)
            return []

    def update_todo_status(self, todo_id: int, status: str):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE todos SET status = ? WHERE id = ?", (status, todo_id))
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("Failed to update todo: %s", e)

    def delete_todo(self, todo_id: int):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("Failed to delete todo: %s", e)

    # --- Notes APIs ---
    def add_note(self, title: str, content: str):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notes (title, content) VALUES (?, ?)",
                (title, content)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("Failed to add note: %s", e)

    def get_notes(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, content, created_at FROM notes ORDER BY id DESC")
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            log.error("Failed to fetch notes: %s", e)
            return []

    def update_note(self, note_id: int, title: str, content: str):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE notes SET title = ?, content = ? WHERE id = ?", (title, content, note_id))
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("Failed to update note: %s", e)

    def delete_note(self, note_id: int):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            log.error("Failed to delete note: %s", e)

    def get_note_by_title(self, title: str):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, content, created_at FROM notes WHERE title LIKE ? LIMIT 1", (f"%{title}%",))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            log.error("Failed to fetch note by title: %s", e)
            return None

db_manager = DatabaseManager()
