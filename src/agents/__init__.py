import asyncio
from src.agents.chatbot import ChatbotAgent
from src.agents.react import ReActAgent

class AgentManager:
    def __init__(self):
        self._classes = {}
        self._instances = {}  # 存储已创建的 agent 实例

    def register_agent(self, agent_class):
        self._classes[agent_class.name] = agent_class

    def init_all_agents(self):
        for agent_class in self._classes.values():
            self.get_agent(agent_class.name)

    def get_agent(self, agent_name, **kwargs):
        # 检查是否已经创建了该 agent 的实例
        if agent_name not in self._instances:
            agent_class = self._classes[agent_name]
            self._instances[agent_name] = agent_class()

        return self._instances[agent_name]

    def get_agents(self):
        return list(self._instances.values())

    async def get_agents_info(self):
        agents = self.get_agents()
        return await asyncio.gather(*[a.get_info() for a in agents])


agent_manager = AgentManager()
agent_manager.register_agent(ChatbotAgent)
agent_manager.register_agent(ReActAgent)  # 暂时屏蔽 ReActAgent
agent_manager.init_all_agents()

__all__ = ["agent_manager"]


if __name__ == "__main__":
    pass
