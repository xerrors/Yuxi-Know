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
    # 细粒度上报至少 8 KiB 的空闲块，重启后由 tmpfiles 恢复；文件缓存仍由内核管理。
    printf '%s\n' 'w /sys/module/page_reporting/parameters/page_reporting_order - - - - 1' \
        > /etc/tmpfiles.d/yuxi-page-reporting.conf
    systemd-tmpfiles --create /etc/tmpfiles.d/yuxi-page-reporting.conf
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
# 嵌套节点采用轻量任务超售；这些逻辑额度不增加物理 CPU 和 RAM。
if [[ ${1:-} == --nested ]]; then
    python3 - <<'PY'
from pathlib import Path
import re

path = Path('/usr/local/services/cubetoolbox/Cubelet/dynamicconf/conf.yaml')
text = path.read_text()
quota = {
    'mcpu_limit': '128000',
    'mem_limit': '"128Gi"',
    'mvm_limit': '512',
    'creation_concurrent_num': '4',
    'paused_resource_release_ratio': '1.0',
}
# 固定发行版的配额字段位于 host.quota；布局变化时显式失败，避免写错层级。
host = re.search(r'^host:[ \t]*\n(?:(?:[ \t].*|)\n)*', text, re.MULTILINE)
if host is None:
    raise RuntimeError('Cubelet 配置缺少 host 段')
quota_section = re.search(r'^  quota:[ \t]*\n(?:(?:    .*|)\n)*', host.group(), re.MULTILINE)
if quota_section is None:
    raise RuntimeError('Cubelet 配置缺少 host.quota 段')
block = quota_section.group()
for key, value in quota.items():
    block, count = re.subn(rf'^    {key}:.*$', f'    {key}: {value}', block, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f'Cubelet 配额字段数量异常：{key}')
start = host.start() + quota_section.start()
end = host.start() + quota_section.end()
path.write_text(text[:start] + block + text[end:])
PY
    systemctl restart cube-sandbox-cubelet.service
fi
curl --fail --silent http://127.0.0.1:3000/health
printf '\nCube v0.7.3 专用节点安装完成\n'
