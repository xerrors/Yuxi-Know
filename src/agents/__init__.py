

class AgentManager:
    def __init__(self):
        self.agents = {}

    def add_agent(self, agent_id, agent):
        self.agents[agent_id] = agent
