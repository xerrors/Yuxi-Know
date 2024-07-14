from core.knowledgebase import KnowledgeBase


class DataBaseManager:

    def __init__(self, config=None) -> None:
        self.config = config
        self.knowledge_base = KnowledgeBase(config)

    def get_databases(self):
        kb = self.knowledge_base.get_collections()
        return kb

    def create_database(self, collection_name):
        self.knowledge_base.add_collection(collection_name)
        return self.get_databases()

    def add_file(self, file, collection_name=None):
        self.knowledge_base.add_file(file, collection_name)
        return self.get_databases()

    def add_text(self, text, collection_name=None):
        self.knowledge_base.add_text(text, collection_name)
        return self.get_databases()

    def get_database_info(self, database_name):
        return self.knowledge_base.get_collection_info(database_name)

    def get_document_info(self, database_name, document_id):
        return self.knowledge_base.search_by_id(database_name, document_id)
