from core import Retriever, DataBaseManager
from core.graphbase import GraphDatabase
from models import select_model
from config import Config


config = Config("config/base.yaml")
model = select_model(config)
dbm = DataBaseManager(config)
retriever = Retriever(config)

# 启动本地图数据库