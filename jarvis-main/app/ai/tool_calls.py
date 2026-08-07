import re
from app.utils.logger import log

class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name):
        def decorator(func):
            self.tools[name] = func
            return func
        return decorator

    def execute(self, tool_tag: str) -> str:
        """
        Parse and execute a tool tag like: [TOOL: tool_name("arg1", 123)]
        Returns a string representation of the result or error.
        """
        match = re.search(r"\[TOOL:\s*(\w+)\s*\((.*?)\)\s*\]", tool_tag.strip(), re.DOTALL)
        if not match:
            return "Error: Invalid tool tag format."

        func_name = match.group(1)
        args_str = match.group(2)

        if func_name not in self.tools:
            return f"Error: Tool '{func_name}' not registered."

        # Parse args (simple comma-split with string/int conversion)
        args = []
        kwargs = {}
        if args_str.strip():
            # Basic parsing of arguments (comma-separated, stripping quotes)
            raw_args = re.split(r",\s*(?=(?:[^'\"]|'[^']*'|\"[^\"]*\")*$)", args_str)
            for ra in raw_args:
                ra = ra.strip()
                if ra.startswith('"') and ra.endswith('"'):
                    args.append(ra[1:-1])
                elif ra.startswith("'") and ra.endswith("'"):
                    args.append(ra[1:-1])
                elif ra.lower() in ("true", "false"):
                    args.append(ra.lower() == "true")
                else:
                    try:
                        if "." in ra:
                            args.append(float(ra))
                        else:
                            args.append(int(ra))
                    except ValueError:
                        args.append(ra)

        try:
            log.info("Executing tool: %s with args %s", func_name, args)
            res = self.tools[func_name](*args, **kwargs)
            return str(res) if res is not None else f"Tool '{func_name}' executed successfully."
        except Exception as e:
            log.error("Failed to execute tool %s: %s", func_name, e)
            return f"Error: Failed to execute tool '{func_name}': {e}"

tool_registry = ToolRegistry()
