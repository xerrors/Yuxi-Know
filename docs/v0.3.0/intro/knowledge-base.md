# 知识库与知识图谱

项目中的知识库与知识图谱，即是知识管理组织的方式，同时会被封装为工具供 AgenticRAG 系统调用。

## 创建知识库

系统支持多种知识库存储形式，满足不同场景需求：

| 存储类型 | 特点 | 适用场景 |
|----------|------|----------|
| **Chroma** | 轻量级向量数据库 | 小型项目、快速原型、维护方便 |
| **Milvus** | 高性能向量数据库 | 大规模生产环境、高性能查询 |
| **LightRAG** | 图增强检索 | 复杂知识关系，构建成本较高 |

访问 Web 界面：`http://localhost:5173`，进入"知识库管理"页面，点击"新建知识库"，填写知识库信息。

这里需要**注意**的是，这里的知识库的标题和描述都会作为智能体选择工具的依据，因此尽量详尽的描述该知识库。


### LightRAG 知识库说明

在本项目中，系统支持基于 [LightRAG](https://github.com/HKUDS/LightRAG) 的知识图谱自动构建，能够从文档中自动提取实体和关系，构建结构化知识图谱。但是 LightRAG 所构建的知识图谱不作为全局的知识图谱来使用。只是将 LightRAG 作为知识的组织和检索形式。一方面是因为 LightRAG 构建的图谱的质量比较差，另一方面是不希望与全局的知识图谱弄混。

LightRAG 知识库可在知识库详情中可视化，但不支持在侧边栏图谱中直接检索，图谱检索工具不支持 LightRAG 知识库，查询需要使用对应的知识库作为工具。

在 Neo4j 的检索中可以看到，实际上 LightRAG 的节点和边依然是和知识图谱本身构建在了同一个 Neo4j 数据库中，但是使用了特殊的 tag 做区分。这点在后面介绍知识图谱的时候也会额外说明。


系统默认使用 `siliconflow` 的 `Qwen/Qwen3-30B-A3B-Instruct-2507` 模型进行图谱构建。可通过环境变量自定义图谱构建模型：

<<< @/../.env.template#lightrag{bash}


## 文档管理

本系统的“上传 → 解析入库 → 检索/可视化”流程既可通过 Web 界面完成，也可使用 API/脚本批量处理。

**支持的文件类型**

- 文本与文档：`.txt`、`.md`、`.doc`、`.docx`、`.pdf`
- 网页与数据：`.html`、`.htm`、`.json`、`.csv`、`.xls`、`.xlsx`
- 图片：`.jpg`、`.jpeg`、`.png`、`.bmp`、`.tiff`、`.tif`

接口查询：`GET /api/knowledge/files/supported-types`

**上传与入库**

1) 上传文件（返回服务端保存路径）
- `POST /api/knowledge/files/upload?db_id=<可选>`
- 成功返回：`file_path`（后续入库使用）、`content_hash`（内容去重）

2) 解析并入库（异步任务）
- `POST /api/knowledge/databases/{db_id}/documents`
- 返回：`status=queued` 与 `task_id`，可在任务中心查看进度

去重策略：系统按“内容哈希”判断是否已存在相同文件，避免重复入库。

### 批量脚本

- 上传并入库：参见 `scripts/batch_upload.py upload`

## 知识图谱

本项目存在两类“图谱相关”能力：

- 全局知识图谱（Neo4j）：用于智能体工具 `query_knowledge_graph` 的图实体查询；统一保存在 Neo4j 中，提供三元组检索和系统级可视化。
- LightRAG 知识库内图谱：针对某个知识库由 LightRAG 自动抽取实体/关系，用于该库内的图增强检索与可视化；与全局图共享同一 Neo4j 实例，但通过特殊 tag 区分，不作为全局图谱使用。

选择建议：
- 更结构化的库内检索/可视化：优先使用 LightRAG（注意构建质量与成本）。
- 统一的图查询/工具调用：依赖全局 Neo4j 图谱与工具 `query_knowledge_graph`。

因此，侧边栏知识图谱页面展示的是 Neo4j 图数据库中符合以下规则的知识图谱信息。

具体展示内容包括：

- 带有 Entity 标签的节点
- 带有 RELATION 类型的关系边

注意：

这里仅展示用户上传的实体和关系，不包含知识库中自动创建的图谱。
查询逻辑基于图谱适配器的子图查询方法实现：

```SQL
MATCH (n:Entity)-[r]->(m:Entity)
RETURN
    {id: elementId(n), name: n.name} AS h,
    {type: r.type, source_id: elementId(n), target_id: elementId(m)} AS r,
    {id: elementId(m), name: m.name} AS t
LIMIT $num
```

如需查看完整的 Neo4j 数据库内容，请使用 "Neo4j 浏览器" 按钮访问 Neo4j 原生界面。

通过网页上传的 `jsonl` 文件的图谱默认会符合上述条件。



### 1. 以三元组形式导入


系统支持通过网页导入 `jsonl` 格式的知识图谱数据：

```jsonl
{"h": "北京", "t": "中国", "r": "首都"}
{"h": "上海", "t": "中国", "r": "直辖市"}
{"h": "深圳", "t": "广东", "r": "省会"}
```

**格式说明**，每行一个三元组，系统自动验证数据格式，并自动导入到 Neo4j 数据库，添加 `Upload`、`Entity`、`Relation` 标签，会自动处理重复的三元组。

Neo4j 访问信息可以参考 `docker-compose.yml` 中配置对应的环境变量来覆盖。

- **默认账户**: `neo4j`
- **默认密码**: `0123456789`
- **管理界面**: `http://localhost:7474`
- **连接地址**: bolt://localhost:7687

::: tip 测试数据
可以使用 `test/data/A_Dream_of_Red_Mansions_tiny.jsonl` 文件进行测试导入。
:::

### 2. 接入已有 Neo4j 实例

如需接入已有的 Neo4j 实例，可修改 `.env` 中的配置：

<<< @/../.env.template#neo4j{bash}

同时记得注释掉下面的 neo4j 服务：

<<< @/../docker-compose.yml#neo4j


::: warning 注意事项
确保每个节点都有 `Entity` 标签，每个关系都有 `RELATION` 类型，否则会影响图的检索与构建功能。
:::
