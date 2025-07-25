import asyncio

from .chatbot import ChatbotAgent
from .react.graph import ReActAgent
from .open_deep_research.graph import OpenDeepResearchAgent

class AgentManager:
    def __init__(self):
        self._classes = {}
        self._instances = {}  # 存储已创建的 agent 实例

    def register_agent(self, agent_class):
        self._classes[agent_class.__name__] = agent_class

    def init_all_agents(self):
        for agent_id in self._classes.keys():
            self.get_agent(agent_id)

    def get_agent(self, agent_id, reload=False, **kwargs):
        # 检查是否已经创建了该 agent 的实例
        if reload or agent_id not in self._instances:
            agent_class = self._classes[agent_id]
            self._instances[agent_id] = agent_class()

        return self._instances[agent_id]

    def get_agents(self):
        return list(self._instances.values())

    async def reload_all(self):
        for agent_id in self._classes.keys():
            self.get_agent(agent_id, reload=True)

    async def get_agents_info(self):
        agents = self.get_agents()
        return await asyncio.gather(*[a.get_info() for a in agents])


agent_manager = AgentManager()
agent_manager.register_agent(ChatbotAgent)
agent_manager.register_agent(ReActAgent)
agent_manager.register_agent(OpenDeepResearchAgent)
agent_manager.init_all_agents()

__all__ = ["agent_manager"]


if __name__ == "__main__":
    pass
