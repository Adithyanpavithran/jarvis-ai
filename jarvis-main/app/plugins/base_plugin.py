class JarvisPlugin:
    """Base class for all Jarvis plugins."""
    def __init__(self):
        self.name = "BasePlugin"
        self.description = "Base class for Jarvis plugins."
        self.version = "1.0.0"

    def on_load(self):
        """Called when the plugin is loaded."""
        pass

    def on_unload(self):
        """Called when the plugin is unloaded."""
        pass

    def get_tools(self) -> dict:
        """
        Return a dictionary of tools defined by this plugin to be registered.
        Example format:
        {
            "tool_name": self.my_tool_function
        }
        """
        return {}
