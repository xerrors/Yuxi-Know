import os
from dotenv import load_dotenv
from core import HistoryManager
from core import PreRetrieval
from config import Config
from models import select_model

load_dotenv()


if __name__ == "__main__":
    config = Config("config/base.yaml")
    model = select_model(config)
    pre_retrieval = PreRetrieval(config)
    # pre_retrieval.add_file("/home/zwj/workspace/ProjectAthena/src/data/file/鉴定工作报告、技术报告-0708.pdf")

    print(f"[{config.model_provider}:{config.get('model_name', 'default')}] Type 'exit' to quit")

    history_manager = HistoryManager()
    while True:
        message = input("\nUser: ")
        if message == "exit":
            break

        external = ""

        if config.enable_knowledge_base:
            kb_res = pre_retrieval.search(message)
            if kb_res:
                kb_res = "\n".join([f"{r['id']}: {r['entity']['text']}" for r in kb_res[0]])
                kb_res = f"知识库信息: {kb_res}"
                external += kb_res

        if len(external) > 0:
            message = f"以下是参考资料：\n\n\n {external} 请根据前面的知识回答：{message}"

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
