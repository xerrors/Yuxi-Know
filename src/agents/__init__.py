from src.agents.registry import BaseAgent
from src.agents.chatbot.graph import ChatbotAgent
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessageChunk, ToolMessage


class AgentManager:
    def __init__(self):
        self.agents = {}

    def add_agent(self, agent_id, agent):
        self.agents[agent_id] = {
            "agent": agent,
            "configuration": agent.configuration
        }

def agent_cli(agent: BaseAgent, config: RunnableConfig = None):
    config = config or {}
    if "configurable" not in config:
        config["configurable"] = {}

    while True:
        user_input = input("\nUser: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        stream_flag = False
        for msg, metadata in agent.stream_messages([{"role": "user", "content": user_input}], config):
            if isinstance(msg, AIMessageChunk):
                content = msg.content or msg.tool_calls

                if not content:
                    if stream_flag == True:
                        print()
                        stream_flag = False
                    continue

                if stream_flag == False and content:
                    print(f"AI: {content}", end="", flush=True)
                    stream_flag = True
                    continue

                elif content:
                    print(f"{content}", end="", flush=True)

            if isinstance(msg, ToolMessage):
                print(f"Tool: {msg.content}")

def get_agents():
    agent_manager = AgentManager()
    agent_manager.add_agent("chatbot", ChatbotAgent())
    return agent_manager.agents
