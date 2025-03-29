from src.agents.chatbot import ChatbotAgent
from src.agents.react import ReActAgent

class AgentManager:
    def __init__(self):
        self.agents = {}

    def add_agent(self, agent_id, agent_class):
        self.agents[agent_id] = agent_class

    def get_runnable_agent(self, agent_id, **kwargs):
        agent_class = self.get_agent(agent_id)
        return agent_class()

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
