# Agent 输入支持多张内联图片

状态：implemented
类型：feature
Owner：backend/yuxi/modules/agents/input_messages.py

## 问题

Agent 可以从一条用户消息读取多张图片，但单值图片字段、历史投影和网关请求体上限会使图片丢失或在到达 API 前被拒绝。图片的实际顺序和总量必须在输入边界固定，并在刷新历史后仍可回读。

## 决策

### 实现方案

Public Thread/Session 的一条输入消息包含有序的文本与 `input_image` 内容块，HTTP Schema 只接受内联 `data:image/...;base64,...` 图片。[输入归一](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/input_messages.py)校验每条消息最多 10 张、base64 总量最多 80 MiB；首图保留在 Message 的 `image_content` 投影，完整内容块保存在原始消息中。[历史读取](https://github.com/xerrors/Yuxi/blob/main/backend/yuxi/modules/agents/services/checkpoint_messages.py)按原始顺序生成 `image_contents`。Web 的粘贴、选择和拖拽入口汇入同一图片预算与发送路径。

[内置 nginx](https://github.com/xerrors/Yuxi/blob/main/docker/nginx/default.conf)只对 Public Thread/Session 创建及消息事件请求体放宽到 100 MiB，其余 `/api/` 仍为 20 MiB。外层代理需要允许相同大小；后端归一仍以 422 拒绝超出图片限制的请求。

## 替代方案

| 方案 | 取舍 |
|---|---|
| 每张图片增加独立数据库列 | 原始消息已经保留有序内容块，会复制大块 base64 并扩大 Schema。 |
| 前端直接解析 LangChain 原始消息 | 把内部格式变成浏览器协议，历史投影将随 LangChain 形状变化。 |
| 只限制张数 | 少量大图仍可超过网关限制，客户端无法得到明确的图片预算错误。 |
| 图片统一先上传为附件 | 引入新的引用与清理生命周期，超出当前内联输入契约。 |

## 后果

Message 首图、完整原始消息、历史响应和 checkpoint 都会携带图片内容，响应与存储体积随图片数量增长。支持大请求体的入口严格限于当前 Public 输入路径；网关或宿主代理未同步上限时，大图请求会在 API 之前收到 413。图片附件引用与清理需另行设计。

## 验证

输入服务单元测试校验单图、多图顺序、10 张上限、总量和非法元素；历史读取单元测试校验刷新后的完整图片列表。真实 HTTP 与浏览器检查多图发送与回显。独立 nginx 容器加载实际配置：21 MiB 请求体到四个 Public 创建/事件路径均到达 API 并返回 422，旧运行路径及其他 `/api/` 路径由网关返回 413；配置通过 `nginx -t`。
