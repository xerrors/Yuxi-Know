from src.agents.registry import BaseAgent

class ReActAgent(BaseAgent):
    name = "ReAct"
    description = "A react agent that can answer questions and help with tasks."

    async def get_graph(self, **kwargs):
        from .workflows import graph
        return graph
