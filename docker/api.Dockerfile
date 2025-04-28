# 使用基础镜像
FROM python:3.12

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3-dev \
    ffmpeg \
    libsm6 \
    libxext6

# 复制 requirements.txt 文件（这一步如果文件没变，Docker 会使用缓存）
# COPY../requirements.txt /app/requirements.txt
COPY ../pyproject.toml /app/pyproject.toml
COPY ../.python-version /app/.python-version

# 安装依赖（Docker 会缓存这一步，除非 requirements.txt 发生变化）
RUN pip install uv
RUN uv sync

# 复制代码到容器中
COPY ../src /app/src
COPY ../server /app/server

