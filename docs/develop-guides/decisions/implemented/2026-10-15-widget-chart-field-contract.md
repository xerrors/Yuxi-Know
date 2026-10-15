# 图表字段引用契约与错误定位

状态：implemented
类型：bug-fix
Owner：frontend/src/shared/lib/chatWidgets.js

## 问题

Chart 的 xAxis 容易被理解为坐标轴类型，而实际协议要求它引用每条 data 记录中的字符串列。模型修改数据列名却保留模板值时会产生无效图表；聚合错误提示又把字段不匹配描述为最多 60 行，掩盖实际原因。

## 决策

### 实现方案

前端解析器保持现有接受范围，按 series 和 data 的实际失败位置报告条目、字段与原因。缺失横轴或系列字段优先于额外字段诊断；只有超过记录数上限才显示 60 条限制。

内置 `backend/yuxi/modules/extensions/skills/builtin/chat-widgets/SKILL.md` 拥有模型可见说明：xAxis 与 series.dataKey 是数据列名引用；先确定数据列名，再填写引用，输出前逐条核对字段存在、类型和字段集合。现有分类模板使用 activity 数据列，消除 category 看起来像固定轴类型的歧义。采用通用字段契约，不追加领域示例或猜测映射。

## 替代方案

不断追加天气、价格等模板会扩大维护面且无法覆盖任意字段改名。解析器猜测日期列会在多列数据中改变用户意图。只改错误提示能改善定位，但无法减少生成侧的歧义。

## 后果

既有持久消息和组件协议保持兼容，错误消息具体指出需要修正的字段。模型输出仍通过解析器验证，Skill 说明不能替代运行时拒绝。

## 验证

`docker compose exec -T frontend node --test test/unit/widgetChartValidation.test.js`：Passed，24 项通过，覆盖缺字段、类型、范围、重复引用、额外字段、记录数和合法边界；不同业务列名同步改名后均可解析，遗漏同步时准确拒绝。新增提示断言在修复前因聚合文案而失败。

Skill 的四个现有 widget 围栏均经实际 parseWidget 验证通过。真实 Vite 页面上的 WidgetRenderer 显示具体横轴缺失、系列缺失和超限错误，修正 xAxis 后正常绘制 SVG 图表；浅深色截图已核对。

前端完整 unit 616 项、lint、typecheck、build 及工程契约检查 Passed；新增通用列名测试另行通过。真实模型生成效果评测 Not run：本次验证覆盖说明与可执行契约的一致性，未进行模型调用。
