# 使用轻量级Python基础镜像
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/
COPY --from=node:20-slim /usr/local/bin /usr/local/bin
COPY --from=node:20-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node:20-slim /usr/local/include /usr/local/include
COPY --from=node:20-slim /usr/local/share /usr/local/share

# 设置工作目录
WORKDIR /app

# 环境变量设置
ENV TZ=Asia/Shanghai \
    UV_PROJECT_ENVIRONMENT="/usr/local" \
    UV_COMPILE_BYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

RUN npm install -g npm@latest && npm cache clean --force

# 设置代理和时区，更换镜像源，安装系统依赖 - 合并为一个RUN减少层数
RUN set -ex \
    # (A) 设置时区
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    # (B) 替换清华源 (针对 Debian Bookworm 的新版格式)
    && sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|security.debian.org/debian-security|mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources \
    # (C) 安装必要的系统库
    && apt-get update \
    && apt-get install -y --no-install-recommends --fix-missing \
        curl \
        ffmpeg \
        libsm6 \
        libxext6 \
    # (D) 清理垃圾，减小体积
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


# 复制项目配置文件
COPY ../pyproject.toml /app/pyproject.toml
COPY ../.python-version /app/.python-version
COPY ../uv.lock /app/uv.lock


# 接收构建参数(如果出现代理错误，则把下面关于环境变量的都注释掉，并注释掉 dock-compose.yml 的 6-8 行)
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""

# 设置环境变量（这些值可能是空的）
ENV HTTP_PROXY=$HTTP_PROXY \
    HTTPS_PROXY=$HTTPS_PROXY \
    http_proxy=$HTTP_PROXY \
    https_proxy=$HTTPS_PROXY

# 如果网络还是不好，可以在后面添加 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen

# 激活虚拟环境并添加到PATH
ENV PATH="/app/.venv/bin:$PATH"

# 复制代码到容器中
COPY ../src /app/src
COPY ../server /app/server
