import asyncio
import traceback
from google.genai import types

class ToolRegistry:
    def __init__(self):
        self.tools = {}
        self.declarations = []

    def register(self, name, func, declaration):
        self.tools[name] = func
        self.declarations.append(declaration)

    async def execute(self, name, args, context):
        if name not in self.tools:
            return f"Error: Tool {name} not found."
        
        func = self.tools[name]
        loop = asyncio.get_running_loop()
        
        try:
            # Special case for vision which is async
            if name == "screen_process":
                return await func(args, context)
            
            # Most tools are sync and run in executor
            result = await loop.run_in_executor(None, lambda: func(parameters=args, player=context.ui))
            return result or "Done."
        except Exception as e:
            traceback.print_exc()
            return f"Error executing {name}: {e}"

tool_registry = ToolRegistry()
