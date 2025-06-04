# 使用基础镜像
FROM python:3.12

# 设置工作目录
WORKDIR /app

# 环境变量设置
ARG http_proxy
ARG https_proxy
ENV http_proxy=$http_proxy \
    https_proxy=$https_proxy \
    TZ=Asia/Shanghai

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3-dev \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip
RUN pip install --upgrade pip

# 复制项目配置文件
COPY ../pyproject.toml /app/pyproject.toml

# 安装依赖项
RUN pip install -e .

# 复制代码到容器中
COPY ../src /app/src
COPY ../server /app/server