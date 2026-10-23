# Cube 部署默认参数归 Compose

状态：implemented
类型：simplification
Owner：docker-compose.yml

## 问题

Quick Start 重复列出固定端口、模板和标准共享目录，生产初始化还要求填写目录，用户无法只配置后端与节点连接。

## 决策

### 实现方案

开发与生产 Compose 统一提供 Cube 的标准共享目录默认值，沿用已有端口和模板默认值；未配置或留空时使用默认，显式路径继续覆盖。`.env.template` 展示这些部署约定，`scripts/init.sh` 的生产 Cube 分支只要求无默认值的节点地址。Quick Start 只填写后端、节点地址及可选认证。

应用仍校验收到的绝对路径，默认值不会建立共享挂载，也不会迁移文件。自定义数据槽位仍需显式指定对应节点目录。

## 替代方案

- 只在教程填写默认值：增加重复配置，拒绝。
- 只改模板：未复制模板的初始化路径仍被脚本阻断，拒绝。
- 在 provider 内补默认值：扩大行为范围且重复部署策略，拒绝。

## 后果

默认目录必须已映射为该部署的同一份 Workspace 与 Skills。Compose 不证明共享关系，也不创建或迁移挂载。真实 Cube VM 执行不属于本次默认值解析验证。

## 验证

- `backend/.venv/bin/python -m pytest backend/test/unit/config -q --tb=short`：172 passed。新增六项通过真实 `init.sh` 和 `docker compose config --format json` 回读开发/生产 API、worker、app-init 的环境，覆盖省略、空值、自定义路径；运行不访问实际部署凭据、不创建容器。
- 修复前，同一组测试的四项默认用例分别因空目录或生产初始化拒绝而失败；两项显式路径用例通过。
- `bash -n scripts/init.sh`、修改测试文件的 Ruff 检查和 `git diff --check` 通过。
- 真实 Cube 共享挂载与 VM E2E 未运行；本次只验证部署配置解析与教程展示，执行节点的共享关系仍由部署者准备。

旧能力不存在：生产脚本不再强制要求共享目录，Quick Start 不再列出四个默认参数。

重新引入条件：实际部署不再有标准目录约定时，重新评估是否要求显式输入。
