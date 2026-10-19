#!/usr/bin/env bash
# 仅在一次性的 GitHub 托管机器安装固定版本 Cube。
set -euo pipefail
if [[ ${GITHUB_ACTIONS:-} != true || ${RUNNER_ENVIRONMENT:-} != github-hosted ]]; then
    echo '安装探针仅允许在 GitHub 临时托管执行器运行' >&2
    exit 1
fi
sudo mkdir -p /opt/yuxi-cube /sys/fs/bpf
sudo install -d -o "$(id -u)" -g "$(id -g)" -m 0755 /data/shared/yuxi-hosted-probe
# Cubelet 要求 XFS；只格式化本探针的新文件，保留 runner 原有磁盘。
sudo mkdir -p /data/cubelet
truncate -s 24G "$RUNNER_TEMP/cubelet.xfs"
sudo mkfs.xfs -f -m reflink=1 "$RUNNER_TEMP/cubelet.xfs"
sudo mount -o loop "$RUNNER_TEMP/cubelet.xfs" /data/cubelet
if ! mountpoint -q /sys/fs/bpf; then
    sudo mount -t bpf bpf /sys/fs/bpf
fi
curl --fail --silent --show-error --location --retry 3 \
    https://github.com/TencentCloud/CubeSandbox/releases/download/v0.7.3/cube-sandbox-one-click-v0.7.3-amd64.tar.gz \
    -o "$RUNNER_TEMP/cube.tar.gz"
sudo tar -xzf "$RUNNER_TEMP/cube.tar.gz" -C /opt/yuxi-cube
cube_install=$(find /opt/yuxi-cube -name install.sh -print -quit)
test -n "$cube_install"
# 冷拉取曾超过 Cube 的 30 秒 DNS 启动探针；先准备同一镜像，保留真实就绪检查。
cube_dns_image=cube-sandbox-image.tencentcloudcr.com/opensource/coredns/coredns:1.14.2
sudo docker pull "$cube_dns_image" > "$RUNNER_TEMP/cube-coredns-image.log" 2>&1 || {
    tail -30 "$RUNNER_TEMP/cube-coredns-image.log"
    exit 1
}
# 使用发布包支持的默认镜像选择，完整安装日志留在临时执行器。
sudo env MIRROR= CUBE_PROXY_COREDNS_IMAGE="$cube_dns_image" bash "$cube_install" --yes > "$RUNNER_TEMP/cube-install.log" 2>&1 || {
    grep -iE 'error|fatal|failed|unsupported|must be|not found' "$RUNNER_TEMP/cube-install.log" | tail -30 || true
    # DNS 日志不读取安装环境文件，可区分镜像、端口和宿主路由失败。
    sudo journalctl --no-pager -n 80 -u cube-sandbox-dns.service -u cube-sandbox-coredns.service
    sudo ss -lntup '( sport = :53 )'
    exit 1
}
curl --fail --silent --show-error http://127.0.0.1:3000/health
sudo cp docker/cube/Dockerfile.user /opt/yuxi-cube/Dockerfile.user
sudo bash docker/cube/build-template.sh
