# Compose 长格式 bind 自动创建宿主目录

状态：implemented
类型：bug-fix
Owner：docker-compose.yml

## 问题

Issue #1089：新克隆仓库后 `docker compose up` 因长格式 bind 的宿主路径不存在而失败（例如 `docker/volumes/yuxi/skill-sources`）。短格式会创建缺失目录，长格式走 mount API 时默认不会。

## 决策

### 实现方案

开发 Compose 中所有 `type: bind` 状态挂载显式设置 `bind.create_host_path: true`，由 Compose 在启动前创建缺失宿主目录。生产 Compose 继续使用短格式，行为不变。不在 `init.sh` 预创建目录，避免与 Compose 契约双写。

## 替代方案

在 init 脚本中 `mkdir`：增加第二 Owner，且跳过 init 的直接 `compose up` 仍会失败。把开发配置改回短格式：能创建目录，但失去与现有长格式挂载声明的一致性，且不解决后续再引入长格式时的同类缺陷。

## 后果

首次启动会在 `YUXI_STATE_DIR`（默认 `./docker/volumes`）下自动创建空状态目录。生产短格式路径不受影响。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 开发 Compose 每个长格式 bind 开启 create_host_path | 漏改某一挂载 | docker-compose.yml | unit：`test_dev_compose_long_binds_set_create_host_path`；`docker compose config` 回读 21 个默认 profile 长格式 bind 均含 `create_host_path: true` | 去掉 skill-sources 的 bind 选项后 guard 失败 | Passed |
| 契约回归不被静默绕过 | 只改 YAML 不改测试 | test_docker_compose_service_boundaries.py | 负向 unit | 同上 | Passed |

- Passed：`python -m pytest backend/test/unit/config/test_docker_compose_service_boundaries.py -k create_host_path --noconftest -q`（2 项）；临时 `YUXI_STATE_DIR` 下 `docker compose config --format json` 回读默认 profile 21 个长格式状态 bind 均含 `create_host_path: true`；YAML 静态计数 22 个长格式 bind（含 `paddlex` profile）均设置该选项；临时空 `YUXI_STATE_DIR` 执行 `docker compose up -d redis` 退出码 0 且宿主 `redis/` 目录被创建；`python scripts/verify_engineering_contracts.py`；`git diff --check`。
- Not run：`docker compose exec api … pytest` 因本地重建 API 镜像时清华 apt 源不可达而失败。
