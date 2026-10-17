# 产品品牌配置收敛为单一来源

状态：implemented
类型：simplification
Owner：backend/yuxi/modules/system/static/info.template.yaml

## 问题

站点配置同时定义 organization 与 branding，首页、登录页和侧栏分别读取组织名、产品名与头像，造成重复概念和不一致展示。用户要求只保留产品名称与 Logo，删除无价值的组织头像及全部副标题，并统一品牌文字与首页黑白主按钮。

## 决策

### 实现方案

品牌模板仅保留 branding 与 footer。branding 统一拥有 name、logo，以及仍有当前消费者的 title、login_bg。HomeView、LoginView、AppLayout 从同一 Info Store 的 branding 读取产品名称和 Logo；首页移除副标题投影，登录页移除组织名拼接，侧栏以 Logo 替代独立头像。

Info Store 拥有前端品牌投影；模板与现有 /api/system/info 加载器继续拥有服务端配置读取与版本替换。无配置兼容层或数据迁移逻辑；自定义 YAML 需按新的单一品牌结构调整。当前工作区不存在 info.local.yaml，运行时使用仓库模板。首页与登录页品牌文字沿用原登录页“语析”的字号、字重与中性灰色（gray-700）。首页的输入及按钮样式由[首页单屏输入入口与知识流线](2026-10-16-home-entry-screen.md)拥有。

## 替代方案

- 保留 organization 并更改界面标签：仍存在两份名称和图标事实。
- 为旧字段增加转换与回退：继续维护用户明确删除的概念，当前工作区无此类定制文件消费者。
- 去掉全部可配置展示：名称、Logo、首页标题、登录背景和协议均有当前消费者，保留其自定义能力。

## 验证

| 验收主张 | 失败面 | 语义 Owner | 直接证据 / 命令 | 负向案例 | 当前结果 |
|---|---|---|---|---|---|
| 配置只表达一份产品品牌 | 组织/头像/副标题残留或名称分叉 | 品牌模板 / Info Store | unit、真实 HTTP、残留检索 | 原模板在新契约断言下失败 | Passed：相关 unit 4 项、独立只读真实 GET 新结构断言通过 |
| 首页、登录、侧栏一致读取名称和 Logo | 品牌为空、Logo 用旧头像、登录拼接组织名 | 三个界面 / Info Store | 浏览器自定义名称与 Logo、字体比较、侧栏展开/收起 | 仅提供新结构、不提供组织或头像 | Passed：自定义产品名、Logo、登录背景、两主题字体与侧栏展开/收起均通过 |
| 黑白主按钮与单屏入口成立 | hover 恢复蓝绿、主题反转错误、入口回归 | HomeView | 浅深色与 hover/active DOM 色值、关键尺寸及导航 | 长品牌、短视口、服务失败重试 | Passed：十组布局、两主题三态色值、键盘与登录导航、重试均通过 |

- `playwright-cli -s=product-brand-check --raw run-code --filename=frontend/test/browser/homeEntry.js`：通过；浏览器使用公开品牌与登录协议 fixture，验证实际 DOM、按钮色值和 Canvas 像素，不代替后端授权与持久化证据。
- `docker compose exec -T frontend pnpm run test:unit`：645 项通过；前端 lint 与 build 通过。
- `docker compose exec -T api uv run --group test pytest test/unit -m "not slow"`：2714 项通过、62 项跳过；品牌路由最小集合 4 项通过。
- 工程契约检查、其 66 项 unit、文档 `pnpm run build` 与 `git diff --check`：通过；独立 Reviewer 审查收敛。
- 独立只读 `GET /api/system/info`：真实 HTTP 200、success 及 branding/footer 结构断言通过。
- `docker compose exec -T api uv run --group test pytest test/integration/api/test_system_router_api.py -k info_endpoint_is_public -q`：Not run；session fixture 的已有 Workdir 重叠清理保护阻止进入测试体，未绕过保护或清理共享工作区。

旧能力不存在：organization、独立品牌 avatar、subtitle/subtitles 及副标题展示从当前品牌模板、Store 与界面中移除。

重新引入条件：有明确 consumer 需要组织与产品作为独立实体展示时，重新裁决信息模型。

## 后果

自定义品牌文件须更新结构。后台用户头像、部门和身份信息不属于本次品牌清理。协议配置与登录授权保持现有行为；页面验证不代替真实登录或智能体执行链路。
