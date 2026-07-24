import subprocess
from pathlib import Path
from app.utils.logger import log
from app.ai.tool_calls import tool_registry

def get_repo_root() -> Path:
    """Get the root path of the current repository."""
    return Path(__file__).resolve().parents[2]

@tool_registry.register("git_status")
def git_status_tool() -> str:
    """Check git repository status."""
    try:
        root = get_repo_root()
        res = subprocess.run(["git", "status"], cwd=root, capture_output=True, text=True, check=True)
        return f"Git Status:\n{res.stdout.strip()}"
    except Exception as e:
        log.error("Failed to run git status: %s", e)
        return f"Failed to check git status: {e}"

@tool_registry.register("git_commit")
def git_commit_tool(message: str) -> str:
    """Stage changes and commit them with a commit message."""
    try:
        message = str(message).strip(" '\"")
        root = get_repo_root()
        # Stage all changes
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True, text=True, check=True)
        # Commit
        res = subprocess.run(["git", "commit", "-m", message], cwd=root, capture_output=True, text=True)
        if "nothing to commit" in res.stdout:
            return "Nothing to commit, working tree clean."
        log.info("Git commit created with message: %s", message)
        return f"Git Commit Successful:\n{res.stdout.strip()}"
    except Exception as e:
        log.error("Failed to create git commit: %s", e)
        return f"Failed to commit changes: {e}"

@tool_registry.register("git_push")
def git_push_tool(branch: str = "main") -> str:
    """Push local commits to GitHub origin remote."""
    try:
        import re
        branch = re.sub(r"[^\w\-\/]", "", str(branch)) or "main"
        root = get_repo_root()
        res = subprocess.run(["git", "push", "origin", branch], cwd=root, capture_output=True, text=True)
        if res.returncode == 0:
            log.info("Git push successful to origin/%s", branch)
            return f"Git Push Successful:\n{res.stdout.strip() or 'Pushed commits to origin/' + branch}"
        else:
            err = res.stderr.strip() or res.stdout.strip()
            log.error("Git push failed: %s", err)
            return f"Git Push Failed:\n{err}"
    except Exception as e:
        log.error("Failed to push git repository: %s", e)
        return f"Failed to push: {e}"

@tool_registry.register("git_pull")
def git_pull_tool(branch: str = "main") -> str:
    """Pull latest changes from remote repository."""
    try:
        root = get_repo_root()
        res = subprocess.run(["git", "pull", "origin", branch], cwd=root, capture_output=True, text=True)
        return f"Git Pull:\n{res.stdout.strip() or res.stderr.strip()}"
    except Exception as e:
        log.error("Failed to pull git repository: %s", e)
        return f"Failed to pull: {e}"
