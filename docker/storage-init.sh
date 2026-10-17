#!/bin/sh
set -eu

# 只修改挂载根，已有用户文件与索引内部权限由原服务保留。
chown 1000:1000 /app/user-data /app/skill-sources /app/skill-projections
chmod 0700 /app/user-data /app/skill-sources /app/skill-projections
chown 999:999 /var/lib/milvus /var/lib/milvus/logs
chmod 0755 /var/lib/milvus /var/lib/milvus/logs
