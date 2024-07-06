import os
from dotenv import load_dotenv
from core.history import HistoryManager
from config import Config
from models.chat_model import DeepSeek, Zhipu

load_dotenv()


if __name__ == "__main__":
    config = Config("config/base.yaml")
    model = Zhipu()

    print("[CLI] Type 'exit' to quit")

    history_manager = HistoryManager()
    while True:
        message = input("\nUser: ")
        if message == "exit":
            break

        messages = history_manager.add_user(message)
        response = model.predict(messages, stream=config.stream)

        if config.stream:
            content = ""
            print(f"AI: ", end='', flush=True)
            for chunk in response:
                content += chunk.content
                print(f"{chunk.content}", end='', flush=True)
            print()
        else:
            content = response.content
            print(f"AI: {content}")

        history_manager.add_ai(content)
