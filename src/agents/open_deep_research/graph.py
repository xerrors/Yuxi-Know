import asyncio
import uuid


from src.utils import logger
from src.agents.registry import BaseAgent
from .configuration import Configuration



class OpenDeepResearchAgent(BaseAgent):
    name = "深度研究（DeepResearch）"
    description = "A deep research agent that can answer questions and help with tasks."
    config_schema = Configuration

    async def get_graph(self, **kwargs):
        from .deep_researcher import deep_researcher
        return deep_researcher


if __name__ == "__main__":
    pass
