#!/bin/bash

# 检查是否提供了 API_KEY 参数
if [ -z "$1" ]; then
    echo "请提供 API_KEY。"
    exit 1
fi

# 获取当前目录路径
CURRENT_DIR=$(pwd)

# 如果 src 目录不存在则创建
if [! -d "${CURRENT_DIR}/src" ]; then
    mkdir -p "${CURRENT_DIR}/src"
fi

# 如果.env 文件不存在，则从.env.template 复制一份创建
if [! -f "${CURRENT_DIR}/src/.env" ]; then
    cp "${CURRENT_DIR}/src/.env.template" "${CURRENT_DIR}/src/.env"
fi

# 将 API_KEY 写入.env 文件
echo "ZHIPUAI_API_KEY=$1" > "${CURRENT_DIR}/src/.env"

echo "API_KEY 已成功写入 src/.env 文件。"