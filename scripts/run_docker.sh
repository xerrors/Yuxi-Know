#!/bin/bash

# 检查是否提供了命令行参数
if [ $# -eq 0 ]; then
    echo "请提供命令参数，例如：up -d 或 down"
    exit 1
fi

# 将所有命令行参数传递给 docker compose 命令
docker compose -f docker/docker-compose.dev.yml --env-file src/.env "$@"