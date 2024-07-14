from core import Retriever, DataBaseManager
from models import select_model
from config import Config


config = Config("config/base.yaml")
model = select_model(config)
dbm = DataBaseManager(config)
retriever = Retriever(config)