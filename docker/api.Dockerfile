# 使用轻量级Python基础镜像
FROM python:3.12-slim
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
    sed -i 's|http://deb.debian.org/debian|http://mirrors.tuna.tsinghua.edu.cn/debian|g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's|http://security.debian.org/debian-security|http://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources && \
    # sed -i 's|mirrors.aliyun.com|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && \
    # 清理apt缓存并更新，避免空间不足问题
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* && \
    apt-get update && \
    # 安装系统依赖，减少缓存占用
    apt-get install -y --no-install-recommends --fix-missing \
        python3-dev \
        ffmpeg \
        libsm6 \
        libxext6 \
        curl \
        && apt-get autoremove -y && \
        apt-get autoclean && \
        rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* /tmp/* /var/tmp/*

# 复制项目配置文件
COPY ../pyproject.toml /app/pyproject.toml
COPY ../.python-version /app/.python-version

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
    uv sync --no-dev

# 激活虚拟环境并添加到PATH
ENV PATH="/app/.venv/bin:$PATH"

# 复制代码到容器中
COPY ../src /app/src
COPY ../server /app/server
