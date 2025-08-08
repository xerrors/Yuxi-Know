# 使用轻量级Python基础镜像
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/

# 设置工作目录
WORKDIR /app

# 环境变量设置
ENV TZ=Asia/Shanghai \
    UV_LINK_MODE=copy \
    DEBIAN_FRONTEND=noninteractive

# 设置代理和时区，更换镜像源，安装系统依赖 - 合并为一个RUN减少层数
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    # 更换为阿里云镜像源加速下载
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    # 安装系统依赖
    apt-get update && apt-get install -y --no-install-recommends \
        python3-dev \
        ffmpeg \
        libsm6 \
        libxext6 \
        curl \
        && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# 复制项目配置文件
COPY ../pyproject.toml /app/pyproject.toml
COPY ../.python-version /app/.python-version

# 接收构建参数
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""

# 设置环境变量（这些值可能是空的）
ENV HTTP_PROXY=$HTTP_PROXY \
    HTTPS_PROXY=$HTTPS_PROXY \
    http_proxy=$HTTP_PROXY \
    https_proxy=$HTTPS_PROXY

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

# 复制代码到容器中
COPY ../src /app/src
COPY ../server /app/server
