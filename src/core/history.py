from utils.logging_config import logger

class HistoryManager():
    def __init__(self, history=None):
        self.messages = history or []

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

    def get_history_with_msg(self, msg, role="user"):
        """Get history with new message, but not append it to history."""
        history = self.messages[:]
        history.append({"role": role, "content": msg})
        return history

    def __str__(self):
        history_str = ""
        for message in self.messages:
            history_str += f"{message['role']}: {message['content']}"
        return history_str