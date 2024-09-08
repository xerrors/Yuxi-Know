<img src="web/public/home.png" style="border-radius: 16px; margin: 0 auto; max-height: 400px; display: block;"/>

<h1 style="text-align: center">Yuxi (语析)</h1>

## 准备

1. 提供 API 服务商的 API_KEY，并放置在 `src/.env` 文件中，参考 `src/.env.template`。默认使用的是智谱AI。
2. 配置 python 环境 `pip install -r requirements.txt`

**如果不启用知识库，可以仅安装下面的依赖**

```
FlagEmbedding==1.2.10
Flask==3.0.3
Flask_Cors==4.0.1
openai==1.35.10
python-dotenv==1.0.1
PyYAML==6.0.1
zhipuai
```

### 【可选】配置图数据库 neo4j

使用 docker 部署 neo4j 服务，配置文件见 [local_neo4j/docker-compose.yml](local_neo4j/docker-compose.yml). 
默认账号密码见最后一行，可以使用 `http://localhost:7474/` 在浏览器可视化访问。

```bash
cd local_neo4j
docker compose up -d
```

可以使用 `python test_neo4j.py` 来测试是否正常启动。使用 `docker compose down` 可停止服务。
如果想要管理 neo4j，也可以使用 `docker ps` 查看容器 id，然后使用 `docker exec -it  <CONTAINER_ID> /bin/bash` 进入容器。
如果想要删除数据库中的文件，可以进入容器并停止 neo4j 后，执行 `rm -rf /data/databases`。


## 启动

```bash
python -m src.api 

cd web
npm install
npm run server
```

或者

```bash
bash run.sh
```

