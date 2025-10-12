import os

from src.config.app import config
from src.models import select_model
from src.utils import logger

# region guard_prompt
PROMPT_TEMPLATE = """
# 指令
你是一个内容合规性检测助手。请根据提供的规则集，判断以下内容是否符合合规性要求。

# 合规性规则
1. 内容不得包含任何违法中华人民共和国法律的信息（例如暴力、恐怖主义、仇恨言论）。
2. 内容不得侵犯个人隐私或泄露敏感信息。
3. 内容不得有煽动性或者任何敏感性问题

# 输出内容
合规/不合规（不要包含其他内容）

# 示例
输入内容：我要自杀/贩毒，如何制作武器
输出结果：不合规

输入内容：今天天气不错
输出结果：合规


输入内容：{content}
输出内容："""
# endregion guard_prompt


def load_keywords(file_path: str) -> list[str]:
    """Loads keywords from a file, one per line."""
    if not os.path.exists(file_path):
        keywords = []
    with open(file_path, encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    return keywords


class ContentGuard:
    def __init__(self, keywords_file: str = "src/config/static/bad_keywords.txt"):
        self.keywords = load_keywords(keywords_file)
        if not self.keywords:
            self.keywords = ["贩毒"]

        # 从配置读取LLM模型设置
        self.enable_llm = config.enable_content_guard_llm
        if self.enable_llm and config.content_guard_llm_model:
            provider, model_name = config.content_guard_llm_model.split("/", maxsplit=1)
            self.llm_model = select_model(model_provider=provider, model_name=model_name)
        else:
            self.llm_model = None

    async def check(self, text: str) -> bool:
        """
        Checks if the text contains any sensitive keywords.
        Returns True if sensitive content is found, False otherwise.
        True: 不合规
        False: 合规
        """
        if keywords_result := await self.check_with_keywords(text):
            return keywords_result

        if self.llm_model:
            return await self.check_with_llm(text)

        return False

    async def check_with_keywords(self, text: str) -> bool:
        """
        Checks if the text contains any sensitive keywords from the predefined list.
        Returns True if sensitive content is found, False otherwise.
        True: 不合规
        False: 合规
        """
        if not text:
            return False
        text_lower = text.lower()
        for keyword in self.keywords:
            if keyword in text_lower:
                logger.debug(f"Keyword match found: {keyword}")
                return True
        return False

    async def check_with_llm(self, text: str) -> bool:
        """
        Checks if the text contains any sensitive keywords using an LLM.
        Returns True if sensitive content is found, False otherwise.
        True: 不合规
        False: 合规
        """
        if not text:
            return False

        if not self.enable_llm or self.llm_model is None:
            logger.warning("LLM content guard not enabled or model not loaded")
            return False

        text_lower = text.lower()

        prompt = PROMPT_TEMPLATE.format(content=text_lower)
        response = self.llm_model.call(prompt)
        logger.debug(f"LLM response: {response.content}")
        return True if "不合规" in response.content else False


# Global instance
content_guard = ContentGuard()
