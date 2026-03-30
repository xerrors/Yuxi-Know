# 测试规范与工作流

本文档用于指导 Yuxi 后续如何创建测试文件、修改测试文件，以及如何验证项目功能。目标是务实、稳定、可执行，不追求过度设计。

## 1. 测试分层

当前测试统一分为三层：

- `backend/test/unit`
  - 纯单元测试
  - 不依赖运行中的 Docker 服务
  - 优先使用 `monkeypatch`、fake repo、stub、`tmp_path`

- `backend/test/integration`
  - 真实 API 集成测试
  - 依赖 `docker compose up -d` 后的运行环境
  - 统一通过真实 HTTP 接口验证认证、权限、参数和副作用

- `backend/test/e2e`
  - 关键链路端到端测试
  - 覆盖 run、viewer、附件、文件落盘等完整流程
  - 默认数量少、执行更慢

## 2. 新增测试时怎么选目录

新增测试前先判断：

1. 只测 Python 逻辑，不需要真实服务
   放到 `unit`

2. 需要请求真实接口
   放到 `integration/api`

3. 需要验证从入口到最终结果的完整链路
   放到 `e2e`

不要再默认把测试直接丢到 `backend/test/` 根目录。

## 3. 文件和命名规范

文件名：

- 使用 `test_<domain>_<target>.py`
- 一个文件只测一个明确主题

函数名：

- 使用 `test_<行为>_<预期结果>`
- 名称直接表达业务语义

示例：

- `test_create_agent_run_commits_before_enqueue`
- `test_viewer_download_returns_attachment_response`
- `test_agent_bubble_sort_run_creates_expected_artifacts`

## 4. 写测试的基本要求

每个测试尽量保持三段式：

1. Arrange：准备数据、打桩、创建资源
2. Act：调用被测行为
3. Assert：断言结果

要求：

- 不要只断言 `status_code == 200`
- 要断言关键业务字段和副作用
- 失败信息要能帮助定位问题

## 5. fixture 规范

原则：

- 同一个文件内复用，优先写本地 helper
- 多个文件复用，再提取到对应层级的 `conftest.py`
- 根 `backend/test/conftest.py` 只保留通用 marker，不绑定真实环境

当前约定：

- `backend/test/integration/conftest.py`
  - 管理 `test_client`、`admin_headers`、`standard_user`、`knowledge_database`

- `backend/test/e2e/conftest.py`
  - 管理 `e2e_client`、`e2e_headers`、`e2e_agent_context`

## 6. 允许与禁止

允许：

- 在单元测试里使用 `monkeypatch`
- 在集成测试里通过 fixture 创建测试资源
- 在 E2E 中使用轮询等待最终状态

禁止：

- 在测试文件里硬编码真实账号密码
- 在单元测试里请求真实 HTTP 服务
- 在根 `conftest.py` 里继续添加重环境依赖
- 写 `if __name__ == "__main__":` 作为测试入口
- 用 `print` 作为通过/失败判断手段
- 因为系统里没有默认数据就直接 `skip`

## 7. skip 的使用规则

只在下面两类场景允许 `pytest.skip`：

1. 外部可选能力不可用
   例如 OCR 服务、外部模型服务未启动

2. E2E 环境变量未配置
   例如没有配置专用测试账号

不允许把“系统里没有 agent / config / 预置数据”当成正常 skip 条件。
这类情况应优先改为 fixture 显式准备资源，或者直接 fail 暴露环境问题。

## 8. 修改测试文件时的规则

如果是修 bug：

1. 先补一个能稳定复现 bug 的测试
2. 再修代码
3. 先跑最小相关测试集
4. 再跑相关层级回归

如果是改已有功能：

- 行为变了，就更新断言
- 文件职责混乱，就顺手拆分或迁移目录
- 依赖现成系统状态的测试，优先改成 fixture 建资源

## 9. 运行方式

启动环境：

```bash
docker compose up -d
docker ps
docker logs api-dev --tail 100
```

运行单元测试：

```bash
docker compose exec api uv run --group test pytest test/unit -m "not slow"
```

运行集成测试：

```bash
docker compose exec api uv run --group test pytest test/integration
```

运行 E2E：

```bash
docker compose exec api uv run --group test pytest test/e2e -m e2e
```

运行全部测试：

```bash
docker compose exec api uv run --group test pytest test
```

也可以使用：

```bash
backend/test/run_tests.sh unit
backend/test/run_tests.sh integration
backend/test/run_tests.sh e2e
backend/test/run_tests.sh all
```

## 10. 推荐的日常开发流程

建议顺序：

1. 本地改代码
2. 先跑相关单元测试
3. 涉及接口时跑相关集成测试
4. 涉及关键主链路时补跑对应 E2E
5. 提交前至少完成“检查 -> 测试 -> Lint”

## 11. 当前落地原则

这套规范的重点不是一步到位重写所有旧测试，而是：

- 新增测试必须按新目录落位
- 改到旧测试时顺手迁移
- 优先保持测试可执行和可信
- 优先减少假绿和环境耦合

对当前 Yuxi 来说，这就是最务实、也最容易持续执行的测试标准。
