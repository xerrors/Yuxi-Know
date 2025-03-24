from pydantic import BaseModel, Field
from langchain_core.tools import Tool, StructuredTool

from src.utils.web_search import WebSearcher

class SearchArgsSchema(BaseModel):
    query: str = Field(..., description="The query to search the web for")

search_tool = Tool(
    name="search",
    description="Search the web for information",
    func=WebSearcher().search,
    args_schema=SearchArgsSchema,
    return_direct=True,
)

