import os
import sys
import importlib.util
from pathlib import Path
from app.utils.logger import get_app_dir, log
from app.plugins.base_plugin import JarvisPlugin
from app.ai.tool_calls import tool_registry

class PluginManager:
    def __init__(self):
        self.app_dir = get_app_dir()
        self.plugins_dir = self.app_dir / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.loaded_plugins = {}
        if not list(self.plugins_dir.glob("*.py")):
            self._create_sample_plugin()

    def _create_sample_plugin(self):
        sample_path = self.plugins_dir / "sample_plugin.py"
        code = """from app.plugins.base_plugin import JarvisPlugin

class HelloPlugin(JarvisPlugin):
    def __init__(self):
        super().__init__()
        self.name = "HelloPlugin"
        self.description = "A simple plugin that says hello."
        self.version = "1.0.0"

    def on_load(self):
        pass

    def get_tools(self) -> dict:
        return {
            "plugin_hello": self.hello_tool
        }

    def hello_tool(self, name: str) -> str:
        return f"Hello, {name}! This response is generated from HelloPlugin."
"""
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write(code)

    def load_plugins(self):
        """Scan the plugins directory and dynamically load Jarvis plugins."""
        log.info("Scanning for plugins in %s...", self.plugins_dir)
        
        # Add plugins directory to sys.path to allow imports within plugins
        if str(self.plugins_dir) not in sys.path:
            sys.path.append(str(self.plugins_dir))

        for file in self.plugins_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            
            try:
                module_name = file.stem
                spec = importlib.util.spec_from_file_location(module_name, file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Look for subclasses of JarvisPlugin in the loaded module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type) 
                        and issubclass(attr, JarvisPlugin) 
                        and attr is not JarvisPlugin
                    ):
                        plugin_instance = attr()
                        plugin_instance.on_load()
                        self.loaded_plugins[plugin_instance.name] = plugin_instance
                        
                        # Register plugin tools to the main tool registry
                        tools = plugin_instance.get_tools()
                        for tool_name, tool_func in tools.items():
                            tool_registry.tools[tool_name] = tool_func
                            log.info("Registered plugin tool: %s", tool_name)

                        log.info("Successfully loaded plugin: %s (%s)", plugin_instance.name, plugin_instance.version)
            except Exception as e:
                log.error("Failed to load plugin from file %s: %s", file.name, e)

    def unload_all(self):
        for name, plugin in list(self.loaded_plugins.items()):
            try:
                plugin.on_unload()
                log.info("Unloaded plugin: %s", name)
            except Exception as e:
                log.error("Failed to unload plugin %s: %s", name, e)
        self.loaded_plugins.clear()

plugin_manager = PluginManager()
