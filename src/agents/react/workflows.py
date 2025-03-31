import os

from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="glm-4-plus",
                   api_key=os.getenv("ZHIPUAI_API_KEY"),
                   base_url="https://open.bigmodel.cn/api/paas/v4/",
                   temperature=0)


# For this tutorial we will use custom tool that returns pre-defined values for weather in two cities (NYC & SF)

from typing import Literal

from langchain_core.tools import tool


@tool
def get_weather(city: Literal["nyc", "sf"]):
    """Use this to get weather information."""
    if city == "nyc":
        return "It might be cloudy in nyc"
    elif city == "sf":
        return "It's always sunny in sf"
    else:
        raise AssertionError("Unknown city")


tools = [get_weather]


# Define the graph

from langgraph.prebuilt import create_react_agent

graph = create_react_agent(model, tools=tools)
