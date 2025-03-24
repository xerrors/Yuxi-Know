from src.utils.prompts import get_system_prompt
from src.utils.logging_config import logger

class HistoryManager():
    def __init__(self, history=None, system_prompt=None):
        self.messages = history or []

        system_prompt = system_prompt or get_system_prompt()
        self.add_system(system_prompt)

    def add(self, role, content):
        self.messages.append({"role": role, "content": content})
        return self.messages

    def add_user(self, content):
        return self.add("user", content)

    def add_system(self, content):
        return self.add("system", content)

    def add_ai(self, content):
        return self.add("assistant", content)

    def update_ai(self, content):
        if self.messages[-1]["role"] == "assistant":
            self.messages[-1]["content"] = content
            return self.messages
        else:
            self.add_ai(content)
            return self.messages

    def get_history_with_msg(self, msg, role="user", max_rounds=None):
        """Get history with new message, but not append it to history."""
        if max_rounds is None:
            history = self.messages[:]
        else:
            history = self.messages[-(2*max_rounds):]

        history.append({"role": role, "content": msg})
        return history

    def __str__(self):
        history_str = ""
        for message in self.messages:
            msg = message["content"].replace('\n', ' ')
            history_str += f"\n{message['role']}: {msg}"
        return history_str