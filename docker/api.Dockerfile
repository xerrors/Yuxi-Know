# 使用基础镜像
FROM python:3.12
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/

# 设置工作目录
WORKDIR /app

# 设置时区为 UTC+8
ENV TZ=Asia/Shanghai
ENV UV_LINK_MODE=copy

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3-dev \
    ffmpeg \
    libsm6 \
    libxext6

# 安装依赖项
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# 复制代码到容器中
COPY ../src /app/src
COPY ../server /app/server
COPY ../pyproject.toml /app/pyproject.toml
COPY ../.python-version /app/.python-version
COPY ../uv.lock /app/uv.lock

# 同步项目
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen