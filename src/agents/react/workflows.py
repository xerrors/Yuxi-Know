import os

from langchain_openai import ChatOpenAI

from src import graph_base

model = ChatOpenAI(model="glm-4-plus",
                   api_key=os.getenv("ZHIPUAI_API_KEY"),
                   base_url="https://open.bigmodel.cn/api/paas/v4/",
                   temperature=0)


# For this tutorial we will use custom tool that returns pre-defined values for weather in two cities (NYC & SF)

from typing import Literal, Annotated

from langchain_core.tools import tool, StructuredTool



tools = []


from langgraph.prebuilt import create_react_agent

graph = create_react_agent(model, tools=tools)
