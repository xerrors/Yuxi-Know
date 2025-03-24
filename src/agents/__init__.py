from src.agents.chatbot import ChatbotAgent, ChatbotConfiguration

class AgentManager:
    def __init__(self):
        self.agents = {}

    def add_agent(self, agent_id, agent_class, configuration_class):
        self.agents[agent_id] = {
            "agent_class": agent_class,
            "configuration_class": configuration_class
        }

    def get_runnable_agent(self, agent_id, **kwargs):
        agent_class = self.get_agent(agent_id)
        configuration_class = self.get_configuration(agent_id)
        configuration = configuration_class(**kwargs)
        return agent_class(configuration)

    def get_agent(self, agent_id):
        return self.agents[agent_id]["agent_class"]

    def get_configuration(self, agent_id):
        return self.agents[agent_id]["configuration_class"]


agent_manager = AgentManager()
agent_manager.add_agent("chatbot", ChatbotAgent, ChatbotConfiguration)

__all__ = ["agent_manager"]


if __name__ == "__main__":
    agent = agent_manager.get_agent("chatbot")
    conf = agent_manager.get_configuration("chatbot")
    agent_info = {
        "name": agent.name,
        "description": agent.description,
    }
    print(agent_info)
