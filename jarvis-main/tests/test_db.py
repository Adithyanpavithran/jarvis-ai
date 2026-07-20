import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database.db_manager import db_manager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        # The database manager initializes jarvis.db in %APPDATA%/Jarvis
        # We can clean/reset the test data or just write temporary records
        db_manager.clear_history()

    def test_history_logging(self):
        """Test that conversation history can be successfully logged and retrieved."""
        db_manager.add_history("user", "Hello Jarvis")
        db_manager.add_history("assistant", "Hello User, how can I help you today?")
        
        history = db_manager.get_history(limit=5)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Hello Jarvis")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[1]["content"], "Hello User, how can I help you today?")

    def test_memory_crud(self):
        """Test long-term memory key-value updates."""
        key = "favorite_color"
        val = "Ocean Cyan"
        
        db_manager.add_memory(key, val)
        stored_val = db_manager.get_memory(key)
        self.assertEqual(stored_val, val)

    def test_todo_management(self):
        """Test adding and retrieving tasks from the To-Do database table."""
        task = "Rebuild Jarvis GUI in PySide6"
        db_manager.add_todo(task)
        
        todos = db_manager.get_todos(status="pending")
        self.assertTrue(any(t["task"] == task for t in todos))

if __name__ == "__main__":
    unittest.main()
