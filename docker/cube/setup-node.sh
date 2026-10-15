#!/usr/bin/env bash
# 在专用 Linux/KVM 执行节点以管理员安装 Cube v0.7.3。
set -euo pipefail
if [[ $(id -u) != 0 || ! -e /dev/kvm ]]; then
    echo '需要专用执行节点的管理员账号和 /dev/kvm' >&2
    exit 1
fi
if command -v setenforce >/dev/null; then
    setenforce 0
fi
# 专用节点重启后仍需允许 Cube 容器读取其 bind mount 配置和证书。
if [[ -f /etc/selinux/config ]]; then
    sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config
fi
mkdir -p /data/shared/yuxi /opt/yuxi-cube
# 嵌套开发节点才需要外层 virtiofs；原生节点直接使用本地共享目录。
if [[ ${1:-} == --nested ]]; then
    if ! mountpoint -q /data/shared/yuxi; then
        mount -t virtiofs yuxi_shared /data/shared/yuxi
    fi
    if ! grep -q '^yuxi_shared ' /etc/fstab; then
        printf '%s\n' 'yuxi_shared /data/shared/yuxi virtiofs defaults 0 0' >> /etc/fstab
    fi
fi
if ! command -v cubemastercli >/dev/null; then
    if [[ ! -f /opt/yuxi-cube/release.tar.gz ]]; then
        curl --fail --silent --show-error --location --retry 3 \
            https://github.com/TencentCloud/CubeSandbox/releases/download/v0.7.3/cube-sandbox-one-click-v0.7.3-amd64.tar.gz \
            -o /opt/yuxi-cube/release.tar.gz.download
        mv /opt/yuxi-cube/release.tar.gz.download /opt/yuxi-cube/release.tar.gz
    fi
    tar -xzf /opt/yuxi-cube/release.tar.gz -C /opt/yuxi-cube
    cube_install=$(find /opt/yuxi-cube -name install.sh -print -quit)
    if [[ -z "$cube_install" ]]; then
        echo '发布包缺少安装入口' >&2
        exit 1
    fi
    MIRROR=cn bash "$cube_install" --yes > /opt/yuxi-cube/install.log 2>&1
fi
curl --fail --silent http://127.0.0.1:3000/health
printf '\nCube v0.7.3 专用节点安装完成\n'
