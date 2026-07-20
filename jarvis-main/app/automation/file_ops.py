import os
import shutil
from pathlib import Path
from app.utils.logger import log
from app.ai.tool_calls import tool_registry

@tool_registry.register("create_file")
def create_file(filepath: str, content: str = "") -> str:
    """Create a file with optional content."""
    try:
        path = Path(filepath).resolve()
        # Create directories if missing
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        log.info("Created file: %s", path)
        return f"File created successfully at {path}."
    except Exception as e:
        log.error("Failed to create file %s: %s", filepath, e)
        return f"Failed to create file: {e}"

@tool_registry.register("delete_file")
def delete_file(filepath: str) -> str:
    """Delete a file or folder."""
    try:
        path = Path(filepath).resolve()
        if path.is_file():
            path.unlink()
            log.info("Deleted file: %s", path)
            return f"File deleted successfully."
        elif path.is_dir():
            shutil.rmtree(path)
            log.info("Deleted directory: %s", path)
            return f"Directory deleted successfully."
        else:
            return "File or folder not found."
    except Exception as e:
        log.error("Failed to delete file %s: %s", filepath, e)
        return f"Failed to delete: {e}"

@tool_registry.register("search_files")
def search_files(query: str, search_path: str = ".") -> str:
    """Search for files matching a query string in a directory."""
    try:
        base_path = Path(search_path).resolve()
        if not base_path.exists():
            return f"Search path {search_path} does not exist."

        results = []
        # Walk up to depth 3 to avoid infinite loops or slow runs
        for root, dirs, files in os.walk(base_path):
            # Restrict depth
            depth = len(Path(root).relative_to(base_path).parts)
            if depth > 3:
                continue
            for file in files:
                if query.lower() in file.lower():
                    results.append(str(Path(root) / file))
                    if len(results) >= 10: # limit to top 10
                        break
            if len(results) >= 10:
                break

        if results:
            return "Found files:\n" + "\n".join(results)
        return "No matching files found."
    except Exception as e:
        log.error("Failed to search files for query %s: %s", query, e)
        return f"Error searching files: {e}"
