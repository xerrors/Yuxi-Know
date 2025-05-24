import os

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

model = ChatOpenAI(model="glm-4-plus",
                   api_key=os.getenv("ZHIPUAI_API_KEY"),
                   base_url="https://open.bigmodel.cn/api/paas/v4/",
                   temperature=0)

tools = []
graph = create_react_agent(model, tools=tools, checkpointer=InMemorySaver())
