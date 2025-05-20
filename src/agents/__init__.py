import asyncio
from src.agents.chatbot import ChatbotAgent
from src.agents.react import ReActAgent

class AgentManager:
    def __init__(self):
        self._classes = {}
        self._instances = {}  # 存储已创建的 agent 实例

    def register_agent(self, agent_id, agent_class):
        self._classes[agent_id] = agent_class

    def init_all_agents(self):
        for agent_id, agent_class in self._classes.items():
            self.get_agent(agent_id)

    def get_agent(self, agent_id, **kwargs):
        # 检查是否已经创建了该 agent 的实例
        if agent_id not in self._instances:
            agent_class = self._classes[agent_id]
            self._instances[agent_id] = agent_class()

        return self._instances[agent_id]

    def get_agents(self):
        return list(self._instances.values())

    async def get_agents_info(self):
        agents = self.get_agents()
        return await asyncio.gather(*[a.get_info() for a in agents])


agent_manager = AgentManager()
agent_manager.register_agent("chatbot", ChatbotAgent)
agent_manager.register_agent("react", ReActAgent)  # 暂时屏蔽 ReActAgent
agent_manager.init_all_agents()

__all__ = ["agent_manager"]


if __name__ == "__main__":
    pass