from src.agents.chatbot import ChatbotAgent
from src.agents.react import ReActAgent

class AgentManager:
    def __init__(self):
        self.agents = {}
        self.agent_instances = {}  # 存储已创建的 agent 实例

    def add_agent(self, agent_id, agent_class):
        self.agents[agent_id] = agent_class

    def get_runnable_agent(self, agent_id, **kwargs):
        # 检查是否已经创建了该 agent 的实例
        if agent_id not in self.agent_instances:
            agent_class = self.get_agent(agent_id)
            self.agent_instances[agent_id] = agent_class()
        return self.agent_instances[agent_id]

    def get_agent(self, agent_id):
        return self.agents[agent_id]


agent_manager = AgentManager()
agent_manager.add_agent("chatbot", ChatbotAgent)
agent_manager.add_agent("react", ReActAgent)

__all__ = ["agent_manager"]


if __name__ == "__main__":
    agent = agent_manager.get_agent("chatbot")
    conf = agent_manager.get_configuration("chatbot")
    agent_info = {
        "name": agent.name,
        "description": agent.description,
    }
    print(agent_info)
