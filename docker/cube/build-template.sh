#!/usr/bin/env bash
# 在 Cube 执行节点运行，先把 Dockerfile.user 上传到 /opt/yuxi-cube/。
set -euo pipefail
cd /opt/yuxi-cube
cube_template_alias=${CUBE_TEMPLATE_ID:-yuxi-user}
docker build --build-arg CUBE_UID="${CUBE_UID:-1000}" --build-arg CUBE_GID="${CUBE_GID:-1000}" \
    -f Dockerfile.user -t 127.0.0.1:5000/${cube_template_alias}:0.1 . > template-image.log 2>&1
if ! docker inspect yuxi-cube-registry >/dev/null 2>&1; then
    docker run -d --name yuxi-cube-registry --restart unless-stopped \
        -p 127.0.0.1:5000:5000 registry:2 > /dev/null
fi
docker push 127.0.0.1:5000/${cube_template_alias}:0.1 > template-push.log 2>&1
/usr/local/bin/cubemastercli template create-from-image \
    --image http://127.0.0.1:5000/${cube_template_alias}:0.1 \
    --alias "$cube_template_alias" \
    --cpu 1000 --memory 1024 \
    --writable-layer-size 2G --expose-port 49983 --probe 49983 --probe-path /health
