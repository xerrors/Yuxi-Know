# Select 选项采用中性状态背景

状态：implemented
类型：bug-fix
Owner：frontend/src/shared/model/theme.js

## 问题

Select 下拉选项的默认选中背景由主色算法派生，当前色板得到较深的蓝灰色，弱化了选项内容的层级。

## 决策

### 实现方案

根 ConfigProvider 消费主题 store 的 `components.Select`。Ant Design Vue 4.2.6 的 `controlItemBgActive` 映射到 `--gray-100`，`controlItemBgHover` 映射到 `--gray-50`；主题切换沿用现有的 CSS 色板重新装配。选中状态保留 Ant 的字重及多选勾选标识，禁用状态保留库原有规则。

## 替代方案

较浅的主色背景同样可行；当前使用中性色板统一管理型选择器。逐页覆盖 CSS 需要重复维护浮层选择器，组件主题入口可以覆盖根主题下的所有 Select。

## 后果

修改作用于所有继承根主题的 Select，不修改 Dropdown、Menu 或其他组件的背景。交互、查询与权限保持原有行为；调用方显式设置的独立 ConfigProvider 仍拥有自己的主题。

## 验证

真实 5173 页面回读智能体与评价两个 Select 的 DOM：浅色选中背景为 `rgb(239, 242, 242)`，悬停为 `rgb(245, 247, 247)`；深色选中为 `rgb(30, 31, 31)`，悬停为 `rgb(21, 22, 22)`，与两套 CSS 色板一致。两种主题下选中项保留 600 字重，悬停与选中背景不同，ArrowDown 与 Escape 保持可用。修改前实际选中背景为 `rgb(174, 193, 194)`。检查只切换客户端筛选与主题，不创建业务数据。

前端 `lint:check`、`iconDefaults.test.js` 与 `antEmpty.test.js` 共 7 项单测、`build` 通过。此变更只使用已有主题字段与色板，不新增配置、依赖或行为抽象，直接记录已生效的小范围修复。
