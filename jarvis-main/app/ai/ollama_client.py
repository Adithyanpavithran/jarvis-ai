import json
import urllib.request
from app.utils.logger import log
from app.config.settings import settings_manager
from app.database.db_manager import db_manager
from app.ai.tool_calls import tool_registry

SYSTEM_INSTRUCTIONS = """
You are Jarvis, a sophisticated, helpful, and highly interactive AI desktop assistant.
You run locally on the user's Windows PC.

You have access to the following tools to interact with the system or perform tasks. To run a tool, you MUST append its exact tag [TOOL: tool_name(arguments)] at the very end of your response. Do not output more than one tool call.

Available Tools:
1. open_app(app_name: str) - Open a program (e.g. [TOOL: open_app("notepad")])
2. close_app(app_name: str) - Close a program by process name (e.g. [TOOL: close_app("notepad")])
3. open_url(url: str) - Open any website in the browser (e.g. [TOOL: open_url("https://google.com")])
4. screenshot() - Capture a desktop screenshot (e.g. [TOOL: screenshot()])
5. lock_pc() - Lock the computer screen (e.g. [TOOL: lock_pc()])
6. sleep_pc() - Put the PC to sleep (e.g. [TOOL: sleep_pc()])
7. set_volume(level: int) - Set volume from 0 to 100 (e.g. [TOOL: set_volume(50)])
8. add_todo(task: str, due: str = None) - Add a task to To-Do list (e.g. [TOOL: add_todo("Buy milk")])
9. add_note(title: str, content: str) - Create a quick text note (e.g. [TOOL: add_note("Meeting", "At 3 PM")])
10. web_search(query: str) - Query Google or Wikipedia (e.g. [TOOL: web_search("Ollama release date")])
11. play_media(action: str) - Control playback: "play", "pause", "next", "prev" (e.g. [TOOL: play_media("pause")])
12. open_spotify(query: str = None) - Open Spotify app or search (e.g. [TOOL: open_spotify("pink floyd")])
13. open_youtube(query: str = None) - Open YouTube or search (e.g. [TOOL: open_youtube("lofi beats")])
14. play_song(uri: str = None) - Play a song URI link (e.g. [TOOL: play_song()])
15. read_note(title: str) - Read a specific note content by title (e.g. [TOOL: read_note("shopping list")])
16. add_calendar_reminder(title: str, when_text: str = None) - Save a calendar reminder (e.g. [TOOL: add_calendar_reminder("call doctor", "tomorrow at 10 AM")])
17. stop_youtube() - Close any open YouTube browser windows or tabs (e.g. [TOOL: stop_youtube()])
18. git_status() - Check current git repository status (e.g. [TOOL: git_status()])
19. git_commit(message: str) - Stage and commit code changes (e.g. [TOOL: git_commit("Updated Jarvis features")])
20. git_push(branch: str = "main") - Push local commits to remote GitHub repository (e.g. [TOOL: git_push("main")])
21. git_pull(branch: str = "main") - Pull latest code from GitHub (e.g. [TOOL: git_pull("main")])

Important Guidelines:
- Speak naturally and conversationally. Keep spoken replies very brief and concise (1-2 sentences maximum) unless the user explicitly asks for more detail. This minimizes generation latency and makes the conversation feel fast and real-time.
- If the user asks you to perform a system action or commit/push code to GitHub, explain what you are doing and ALWAYS append the [TOOL: ...] command at the very end of your text response.
- Do not make up tools. Only use the listed ones.
"""

class OllamaClient:
    def __init__(self):
        pass

    def query(self, prompt: str, conversation_history: list = None) -> tuple[str, str | None]:
        """
        Send a query to the local Ollama instance.
        Returns:
            (response_text, tool_call_string_or_none)
        """
        if not settings_manager.get("ollama_enabled", True):
            return "Ollama is disabled in settings.", None

        api_url = settings_manager.get("ollama_api_url", "http://localhost:11434")
        model = settings_manager.get("ollama_model", "mistral")
        temp = settings_manager.get("ollama_temperature", 0.7)

        # Retrieve relevant memories to enrich system context
        memories = db_manager.get_all_memories()
        memory_context = ""
        if memories:
            memory_context = "Facts known about the user:\n" + "\n".join(
                [f"- {m['memory_key']}: {m['memory_value']}" for m in memories]
            )

        # Build message history payload
        messages = [
            {"role": "system", "content": f"{SYSTEM_INSTRUCTIONS}\n\n{memory_context}"}
        ]

        if conversation_history:
            # Map history to Ollama API role expectations (system, user, assistant)
            for h in conversation_history[-10:]: # last 10 turns
                role = "assistant" if h["role"] == "assistant" else "user"
                messages.append({"role": role, "content": h["content"]})

        messages.append({"role": "user", "content": prompt})

        # Query Ollama via REST API
        url = f"{api_url.rstrip('/')}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "options": {
                "temperature": temp
            },
            "stream": False
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                res_data = json.load(response)
                full_reply = res_data["message"]["content"].strip()
                
                # Check for tool call tags in the reply
                tool_call = None
                tool_match = re.search(r"(\[TOOL:\s*\w+\s*\(.*\)\s*\])", full_reply)
                if tool_match:
                    tool_call = tool_match.group(1)
                    # Clean the response text by removing the tool call tag
                    reply_clean = full_reply.replace(tool_call, "").strip()
                else:
                    reply_clean = full_reply

                return reply_clean, tool_call

        except Exception as e:
            log.error("Failed to query local Ollama server: %s", e)
            return f"I'm sorry, I had trouble reaching my local AI server. Please make sure Ollama is running and has the '{model}' model installed.", None

import re # needed for search
ollama_client = OllamaClient()
