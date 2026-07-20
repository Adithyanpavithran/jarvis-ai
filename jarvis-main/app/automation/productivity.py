from app.database.db_manager import db_manager
from app.utils.logger import log, get_app_dir
from app.ai.tool_calls import tool_registry

@tool_registry.register("add_todo")
def add_todo_tool(task: str, due: str = None) -> str:
    """Add a task to the user's To-Do list."""
    try:
        db_manager.add_todo(task, due)
        log.info("Todo added: %s (due: %s)", task, due)
        return f"Added task to your todo list: '{task}'."
    except Exception as e:
        log.error("Failed to add todo tool: %s", e)
        return f"Failed to add task: {e}"

@tool_registry.register("add_note")
def add_note_tool(title: str, content: str) -> str:
    """Create a new note with a title and content."""
    try:
        db_manager.add_note(title, content)
        log.info("Note created: %s", title)
        return f"Saved note: '{title}'."
    except Exception as e:
        log.error("Failed to save note tool: %s", e)
        return f"Failed to save note: {e}"

@tool_registry.register("list_todos")
def list_todos_tool() -> str:
    """List pending to-do tasks."""
    try:
        todos = db_manager.get_todos(status="pending")
        if not todos:
            return "You have no pending tasks on your To-Do list!"
        
        lines = []
        for t in todos:
            due_str = f" (Due: {t['due_at']})" if t['due_at'] else ""
            lines.append(f"- [{t['id']}] {t['task']}{due_str}")
        return "Your Pending Tasks:\n" + "\n".join(lines)
    except Exception as e:
        log.error("Failed to list todos tool: %s", e)
        return "Failed to fetch todo list."

@tool_registry.register("list_notes")
def list_notes_tool() -> str:
    """List all saved notes."""
    try:
        notes = db_manager.get_notes()
        if not notes:
            return "You haven't saved any notes yet."
        
        lines = [f"- [{n['id']}] {n['title']} (Saved: {n['created_at']})" for n in notes]
        return "Your Saved Notes:\n" + "\n".join(lines)
    except Exception as e:
        log.error("Failed to list notes tool: %s", e)
        return "Failed to fetch notes."

@tool_registry.register("read_note")
def read_note(title: str) -> str:
    """Read the content of a specific note by title."""
    try:
        note = db_manager.get_note_by_title(title)
        if note:
            return f"Note: {note['title']}\nSaved on: {note['created_at']}\nContent: {note['content']}"
        return f"Could not find a note with title matching '{title}'."
    except Exception as e:
        log.error("Failed to read note tool: %s", e)
        return f"Failed to retrieve note: {e}"

@tool_registry.register("add_calendar_reminder")
def add_calendar_reminder(title: str, when_text: str = None) -> str:
    """Save a calendar reminder to the reminders list."""
    import time
    from pathlib import Path
    try:
        reminder_path = get_app_dir() / "session_state" / "reminders.txt"
        reminder_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {title}"
        if when_text:
            line += f" | when: {when_text}"
        line += "\n"
        with reminder_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        log.info("Saved reminder to %s", reminder_path)
        return f"Saved your reminder for {title} (time: {when_text or 'not specified'})."
    except Exception as e:
        log.error("Failed to add calendar reminder tool: %s", e)
        return f"Failed to save reminder: {e}"

