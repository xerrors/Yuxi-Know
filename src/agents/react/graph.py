import asyncio
import uuid


from src.agents.registry import BaseAgent
from src.agents.react.configuration import ReActConfiguration

class ReActAgent(BaseAgent):
    name = "react"
    description = "A react agent that can answer questions and help with tasks."

    def get_graph(self, **kwargs):
        """构建图"""
        from .workflows import graph
        return graph

def main():
    agent = ReActAgent(ReActConfiguration())

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from src.agents.utils import agent_cli
    asyncio.run(agent_cli(agent, config))


if __name__ == "__main__":
    main()
    # asyncio.run(main())
