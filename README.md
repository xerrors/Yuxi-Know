## Project: Athena

### 准备

1. 提供 API 服务商的 API_KEY，并放置在 `src/.env` 文件中，参考 `src/.env.template`。默认使用的是智谱AI。
2. 配置 python 环境 `pip install -r requirements.txt`


### 启动命令行模式

```bash
cd src
python cli.py
```

### 启动网页模式

```bash
cd web
npm install
npm run server

cd src
python api.py
```

