#!/usr/bin/env bash
set -euo pipefail
: "${CUBE_GUEST_BOOTSTRAP_PASSWORD:?Set the local Guest bootstrap password}"

cube_disk=/cube/vm/node.qcow2
cube_image_url=https://mirrors.tencent.com/opencloudos/9.6/images/qcow2/x86_64/20260514.2/OpenCloudOS-GenericCloud-9.6-20260514.2.x86_64.qcow2
mkdir -p /cube/vm /cube/shared
if [[ ! -f "$cube_disk" ]]; then
    curl --fail --silent --show-error --location --retry 3 "$cube_image_url" -o "$cube_disk.download"
    qemu-img check "$cube_disk.download"
    mv "$cube_disk.download" "$cube_disk"
    qemu-img resize "$cube_disk" 80G
fi

/usr/libexec/virtiofsd --socket-path=/cube/vm/workspace.sock \
    --shared-dir=/cube/shared --sandbox=none --cache=never --no-announce-submounts &
cube_fs_pid=$!
for cube_attempt in {1..50}; do
    [[ -S /cube/vm/workspace.sock ]] && break
    sleep 0.1
done
[[ -S /cube/vm/workspace.sock ]] || { kill "$cube_fs_pid" 2>/dev/null || true; exit 1; }
# 由 guest 上报空闲页归还 memfd，保留节点的 24 GiB 内存容量。
qemu-system-x86_64 \
    -enable-kvm -machine q35,accel=kvm -cpu host -smp 8 -m 24576 \
    -object memory-backend-memfd,id=mem,size=24G,share=on -numa node,memdev=mem \
    -device virtio-rng-pci \
    -device virtio-balloon-pci,free-page-reporting=on \
    -drive "if=virtio,format=qcow2,file=$cube_disk" \
    -nic 'user,model=virtio-net-pci,hostfwd=tcp:0.0.0.0:10022-:22,hostfwd=tcp:0.0.0.0:13000-:3000,hostfwd=tcp:0.0.0.0:18080-:80' \
    -chardev socket,id=fs,path=/cube/vm/workspace.sock \
    -device vhost-user-fs-pci,queue-size=1024,chardev=fs,tag=yuxi_shared \
    -display none -serial file:/cube/vm/serial.log &
cube_qemu_pid=$!

shutdown_vm() {
    # 只关闭开发执行节点；等待 QEMU 正常退出，避免损坏持久磁盘。
    SSHPASS="$CUBE_GUEST_BOOTSTRAP_PASSWORD" sshpass -e ssh -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/cube/vm/known_hosts -o ConnectTimeout=5 \
        -p 10022 opencloudos@127.0.0.1 'sudo poweroff' || true
    wait "$cube_qemu_pid"
    kill "$cube_fs_pid" || true
}
trap shutdown_vm TERM INT
wait "$cube_qemu_pid"
kill "$cube_fs_pid" || true
