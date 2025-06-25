# 使用基础镜像
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/

# 设置工作目录
WORKDIR /app

# 环境变量设置
ARG http_proxy
ARG https_proxy
ENV TZ=Asia/Shanghai \
    UV_LINK_MODE=copy

# 只有当代理变量不为空时才设置代理
RUN if [ -n "$http_proxy" ]; then echo "export http_proxy=$http_proxy" >> /etc/environment; fi
RUN if [ -n "$https_proxy" ]; then echo "export https_proxy=$https_proxy" >> /etc/environment; fi

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3-dev \
    ffmpeg \
    libsm6 \
    libxext6

# 复制项目配置文件
COPY ../pyproject.toml /app/pyproject.toml
COPY ../.python-version /app/.python-version

# 安装依赖项（不使用lock文件）
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

# 复制代码到容器中
COPY ../src /app/src
COPY ../server /app/server

# 同步项目
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync