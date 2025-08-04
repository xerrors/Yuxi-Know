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

# 安装依赖项，如果无法成功安装，则尝试是设置此处的代理
# ENV HTTP_PROXY=http://172.19.13.5:7890 \
#     HTTPS_PROXY=http://172.19.13.5:7890 \
#     http_proxy=http://172.19.13.5:7890 \
#     https_proxy=http://172.19.13.5:7890

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

# 复制代码到容器中
COPY ../src /app/src
COPY ../server /app/server

# 同步项目
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync

# 取消代理
RUN unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy