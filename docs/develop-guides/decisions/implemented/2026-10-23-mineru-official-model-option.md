# MinerU Official 默认解析模型

状态：implemented
类型：feature
Owner：backend/yuxi/modules/documents/options.py

## 问题

管理员不能在现有 OCR 配置中选择 MinerU Official 的默认解析模型。解析器文档提及 model_version，但上传请求没有发送该字段。

## 决策

### 实现方案

现有 mineru_official_api_opts 增加 model_version，choices 仅包含 pipeline / vlm，默认 pipeline。复用已存在的 Options 存储、枚举校验和设置页下拉框，不新增环境变量、接口或 Schema。

documents service 将有效凭据与 model_version 交给 MinerUOfficialParser。解析器发送 /file-urls/batch 请求时使用任务显式 model_version，缺省使用实例配置。API Key 的环境变量回退和脱敏行为保持原有语义。

OCR 设置表单保存空白的脱敏凭据时省略该字段，防止仅修改模型时清除原 Key。数据库凭据通过明确的「清除已保存凭据」选项清除；该保存规则由共用 OCR 表单维护，也适用于同表单的其他服务凭据。

不增加其他官方参数，不升级 MinerU，不改变自托管选项；真实官方服务的质量与性能不由协议测试推断。

## 替代方案

- 继续依赖官方默认值：无法让管理员选择 VLM，也无法证明任务参数被发送。
- 新建独立配置或仅增加上传表单：复制现有配置机制，或无法覆盖统一解析入口的其他使用方。

## 后果

既有记录没有模型字段时继续使用 pipeline，app-init 同步新字段定义，无需 Schema 迁移。API 与 worker 重启后加载代码；管理员保存后对后续解析生效，显式任务参数可以覆盖默认值。

OCR 表单的空白凭据表示保留，纯空格也不提交；明确清除操作才发送空值。该规则防止模型或服务地址修改意外删除同卡片凭据，配置 API 的空值清除语义保持不变。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 模型选项可以保存回读并拒绝非法值 | 仅显示选项或接受不支持的模型 | documents/options.py、system/services/options.py | test_mineru_defaults_round_trip_and_reject_invalid_choices：真实 HTTP/PG，2 passed | hybrid 或空值返回 400，原值和凭据不变 | Passed |
| 默认、已保存选择和单次覆盖到达请求 | model_version 丢失或优先级颠倒 | documents/service.py、engines/mineru_official.py | service/parser unit，检查出站 JSON 和实际 ZIP 解包正文 | 实现前 5 个回归场景因字段未知、默认值缺失或请求缺少 model_version 失败 | Passed |
| 旧记录显示 pipeline，保存后显示 vlm | 默认值空白、重载丢失或空白凭据覆盖原值 | OCRSettingsSection.vue | ocrSettings.test.js；mineruOfficialOptions.js 真实页面保存、刷新及浅深主题 1440/768 宽度截图 | 仅有凭据的记录显示 pipeline；空值和纯空格保留 Key，勾选清除才删除 | Passed |

在挂载当前源码的既有 Compose 测试环境执行，临时账号与配置快照用于隔离验证，不修改预置账号。实际执行：

- `uv run --no-sync --group test pytest test/unit -m 'not slow' -q -p no:cacheprovider`：3119 passed、107 既有 skipped；跳过不计为验证通过。
- `uv run --no-sync --group test pytest test/unit/services/test_ocr_service.py test/unit/knowledge/test_parser_engines.py test/unit/config/test_options.py -q -p no:cacheprovider`：40 passed。
- `uv run --no-sync --group test pytest test/integration/api/test_system_router_api.py -k mineru_defaults -q -p no:cacheprovider`：2 passed，独立回读 PG；清理恢复 value、updated_by、updated_at。
- `pnpm run lint:check`、`pnpm run test:unit`、`pnpm run build`：通过，前端 809 tests passed。纯空格回归先证明请求仍包含空白 Key 而失败，修正过滤后相关 2 tests passed。
- `playwright-cli run-code --filename=frontend/test/browser/mineruOfficialOptions.js`：真实页面验证通过，检查请求省略空白 Key、数据库凭据来源保持、刷新模型、显式清除及截图。
- 后端 `uv run ruff check yuxi`、`uv run ruff format yuxi --check`、`uv run ruff check --select I yuxi`：通过；工程契约及 66 个验证器单测通过。

真实官方云解析探针为 Not run：协议验证不提交文件到外部服务，也不消耗云端额度，不能据此声称模型质量与性能已校准。
