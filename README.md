<h1 style="text-align: center">Project: Athena</h1>


<img src="web/public/home.png" style="border-radius: 16px; margin: 0 auto; max-height: 400px; display: block;"/>

### 准备

1. 提供 API 服务商的 API_KEY，并放置在 `src/.env` 文件中，参考 `src/.env.template`。默认使用的是智谱AI。
2. 配置 python 环境 `pip install -r requirements.txt`

**如果不启用知识库，可以jin**

```
FlagEmbedding==1.2.10
Flask==3.0.3
Flask_Cors==4.0.1
openai==1.35.10
python-dotenv==1.0.1
PyYAML==6.0.1
zhipuai
```


### 启动命令行模式

```bash
python -m src.cli
```

### 启动网页模式

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

