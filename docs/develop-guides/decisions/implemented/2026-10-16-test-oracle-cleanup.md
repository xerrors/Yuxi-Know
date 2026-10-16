# 测试断言与真实观察边界收敛

状态：implemented
类型：testing
Owner：backend/test/unit/agents/test_chatbot_prompt.py

## 问题

Prompt 的逐句文案断言限制等价改写，却不能证明工具选择；部分 UI 测试只搜索模板声明。分块测试用不完整的模块替身加载真实代码，单独执行失败，长度断言无法发现内容损坏。重排连通性探针通过带 fallback 的计算入口判断成功，API Key 自动绑定断言只判断用户非空。

## 决策

### 实现方案

Prompt 测试只保护动态拼装、Workdir 与必需上下文失败。删除详情与共享权限中四项仅锁定插槽、图标和操作文案的源码检查，保留内容保存和编辑态边界检查；既有重组脚本与异步守卫测试保留到有行为替代证据时再精简。分块测试直接导入真实模块，以输入内容与顺序为独立 oracle。重排探针改用现有无 fallback 的 `test_connection`，API Key 测试通过真实 HTTP 读取创建者和保存的 Key 确认归属，仅管理并清理本例创建的 Key，不依赖会清理其他会话的共享 fixture。Ruff 只对 CI 管辖的 `backend/yuxi` 排序 import，并修复已有一个格式错误，不修改生产逻辑或 gate。

## 替代方案

- 保留全部断言：继续锁死文案与源码布局，且假通过仍存在。
- 按静态扫描命中数批量删除测试：会丢失当前唯一的边界检查，不采用。
- 为所有组件建立新测试框架或重构生产组件：超过测试冗余清理范围，不采用。
- 收窄低价值检查并修正已证实的 oracle 缺陷：采用。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| Prompt 动态输入完整保留 | 固定文案存在但上下文丢失 | Prompt 拼装 unit | focused pytest | 丢失 Workdir 或自定义输入应失败 | Passed |
| 分块可独立执行且保留内容顺序 | 先加载其他测试掩盖导入错误或反转内容 | 分块 unit | 单文件 pytest 与故障注入 | 逐块倒序应失败 | Passed |
| 连通性与 Key 归属由实际结果证明 | fallback 或绑定其他用户仍通过 | provider probe、API Key integration | focused pytest 与真实 HTTP | 网络失败、错误用户应失败 | Passed |
| CI Ruff 三项检查通过 | import 排序失败 | backend/pyproject.toml、ruff workflow | check、format --check、check --select I | 原 98 项排序错误被拒绝 | Passed |

旧能力不存在：逐句 Prompt 风格/浏览规则断言、不完整分块模块替身及四项纯模板声明检查从测试中移除，以 diff 与符号搜索确认。

重新引入条件：具体生产契约确实依赖精确文本或静态结构，且已有能恢复目标缺陷的负向证明；关键 UI 行为优先使用真实组件或浏览器证据。

## 后果

源码检查的删除不增加运行时交互覆盖；现存组件重组测试与手动浏览器入口的系统改进留待独立评估。真实外部 provider 探针依赖环境显式开启，未执行时不计为通过。

实际执行：

```bash
cd backend
.venv/bin/ruff check --select I --fix yuxi
.venv/bin/ruff format yuxi/modules/agents/models/definitions.py
.venv/bin/ruff check yuxi
.venv/bin/ruff format yuxi --check
.venv/bin/ruff check --select I yuxi
.venv/bin/python -m pytest test/unit/config -m "not slow" -q
cd ..
docker compose exec -T api uv run --group test pytest test/unit/knowledge/test_chunking_token_limit.py -q
docker compose exec -T api uv run --group test pytest test/unit -m "not slow" -q
docker compose exec -T api uv run --group test pytest test/integration/api/test_apikey_router.py::test_api_key_auto_binds_to_current_user -q
docker compose exec -T frontend pnpm run lint:check
docker compose exec -T frontend pnpm run test:unit
docker compose exec -T frontend pnpm run build
python3 scripts/verify_engineering_contracts.py
python3 -m unittest scripts.test_verify_engineering_contracts
pnpm --dir docs run build
git diff --check
```

Ruff 三项检查通过；生产代码仅排序 import 和修正空行，独立 Reviewer 比较 import 名称及 alias 集合、去除 import 后的 AST 均相同。后端 unit 2665 通过、61 跳过，容器缺少仓库根目录的配置测试在宿主补跑 103 项通过；分块单文件 18 项通过。前端 lint、625 项 unit、类型检查和构建通过。API Key 真实 HTTP 单例通过并清理创建的 Key；工程检查与检查器 66 项 unit、文档构建通过。

内存故障注入不写入生产源码：反转每块内容让三项分块测试在内容相等断言失败；丢弃自定义 Prompt 让拼装测试在末尾断言失败；重排传输错误让真实连通性测试函数拒绝成功；API Key 响应及回读各自绑定错误用户时，相同测试函数均在归属断言失败且执行清理。真实外部 provider 探针、完整 HTTP integration 和 E2E 未执行；上述注入只证明测试可以拒绝目标错误，不证明远端模型可用。
