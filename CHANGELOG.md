# 更新日志 2025-11-14

本次更新从修改版本同步了以下新功能到原始项目：

1. **思维导图功能** - AI自动生成知识库思维导图，可视化展示知识结构，并将思维导图融入RAG问答中
2. **上传Markdown带图片文件夹功能** - 支持上传zip格式的文件夹，自动处理markdown和图片，适应某些特定场景的图文回复
3. **AI生成示例问题功能** - 自动生成知识库测试问题，提升检索体验

---

## 详细更新内容

### 1. Markmap思维导图功能

#### 后端更新

**新增文件：**

- `server/routers/mindmap_router.py` - 思维导图路由模块

**新增API接口：**

- `GET /api/mindmap/databases` - 获取所有知识库概览
- `GET /api/mindmap/databases/{db_id}/files` - 获取指定知识库的文件列表
- `POST /api/mindmap/generate` - AI生成思维导图
  - 支持选择特定文件或使用所有文件（未启用）
  - 支持自定义提示词（未启用）
  - 自动保存到知识库元数据
- `GET /api/mindmap/database/{db_id}` - 获取知识库的思维导图
- `POST /api/mindmap/database/{db_id}` - 保存思维导图到知识库

**更新文件：**

- `server/routers/__init__.py` - 添加思维导图路由注册

#### 前端更新

**新增文件：**

- `web/src/apis/mindmap_api.js` - 思维导图API调用模块

  - `getDatabases()` - 获取知识库列表
  - `getDatabaseFiles(dbId)` - 获取知识库文件列表
  - `generateMindmap(dbId, fileIds, userPrompt)` - 生成思维导图
  - `getByDatabase(dbId)` - 获取知识库思维导图
  - `saveToDatabase(dbId, mindmapData)` - 保存思维导图
- `web/src/components/MindMapSection.vue` - 思维导图可视化组件

  - 使用 Markmap 库渲染思维导图
  - 支持自动生成、重新生成、适应视图等功能
  - 自动监听容器大小变化
  - 暴露 `generateMindmap()` 和 `refreshMindmap()` 方法供父组件调用

**更新文件：**

- `web/src/views/DataBaseInfoView.vue`

  - 添加"知识导图"Tab页
  - 集成 `MindMapSection` 组件
  - 添加文件变化监听，自动生成思维导图
  - 添加思维导图组件引用管理
- `web/src/apis/index.js` - 导出思维导图API模块
- `web/package.json` - 添加依赖项：

  - `markmap-lib: ^0.18.12` - 思维导图数据处理库
  - `markmap-view: ^0.18.12` - 思维导图可视化库

#### 智能体工具更新

**更新文件：**

- `src/agents/common/tools.py` - 智能体知识库工具增强

**新增功能：**

- 知识库工具新增 `operation` 参数，支持两种操作模式：
  - `'search'` - 检索知识库内容（默认）
  - `'get_mindmap'` - 获取知识库的思维导图结构
- 智能体可以通过 `get_mindmap` 操作查询知识库的整体结构和文件分类
- 思维导图数据自动转换为层级文本格式，便于AI理解和回答用户关于知识库结构的问题

**功能特性：**

- AI自动分析知识库文件结构，生成层次分明的思维导图
- 支持2-4层层级结构
- 自动使用emoji图标增强可读性
- 确保每个文件名在思维导图中只出现一次
- 思维导图数据自动保存到知识库元数据
- 支持重新生成和适应视图
- 文件变化时自动重新生成思维导图
- **智能体可以通过知识库工具查询思维导图，回答用户关于知识库结构的问题**

---

### 2. 上传Markdown文件夹功能与RAG图文问答（为了适应某些特定场景的图文回复）

#### 后端更新

**更新文件：**

- `server/routers/knowledge_router.py`

**新增API接口：**

- `POST /api/knowledge/files/upload-folder` - 上传文件夹（zip格式）

  - 支持上传zip格式的文件夹
  - 自动计算内容hash，检查重复文件
  - 返回文件路径和hash值
- `POST /api/knowledge/files/process-folder` - 处理已上传的文件夹

  - 异步处理zip文件内容
  - 自动提取markdown文件（优先使用full.md）
  - 自动查找并上传images文件夹中的图片到MinIO
  - 自动更新markdown中的图片链接为MinIO URL
  - 保存图片元数据到文件信息中
  - 返回任务ID用于跟踪处理进度

#### 前端更新

**更新文件：**

- `web/src/apis/knowledge_api.js`

  - 新增 `uploadFolder(file, dbId)` - 上传zip文件夹
  - 新增 `processFolder({file_path, db_id, content_hash})` - 处理文件夹
- `web/src/components/FileUploadModal.vue`

  - 添加"上传文件夹"模式选择器
  - 添加zip文件上传区域
  - 实现文件夹上传进度显示
  - 添加文件夹结构示例说明
  - 集成文件夹处理任务到任务中心
  - 文件夹上传成功后自动刷新知识库信息

#### 技术实现

- 使用MinIO作为图片存储后端
- 图片存储在 `kb-images` bucket中
- 图片路径格式：`{db_id}/{file_id}/images/{image_name}`
- 支持多种图片格式：jpg, jpeg, png, gif, webp, bmp

#### 功能特性

- 支持上传zip格式的文件夹
- 识别markdown文件（优先full.md）
- 支持在markdown文件中嵌入图片
- 图片自动上传到MinIO存储
- 保存图片元数据到文件信息，删除文件时会自动删除关联图片
- 在知识库查询结果中可以显示图片，进行RAG图文问答

#### 文件夹结构要求

```
your-folder/
  ├── full.md (或其他 .md 文件)
  └── images/
      ├── image1.jpg
      └── image2.png
```

---

### 3. AI生成示例问题功能

#### 后端更新

**更新文件：**

- `server/routers/knowledge_router.py`

**新增API接口：**

- `POST /api/knowledge/databases/{db_id}/sample-questions` - 生成示例问题

  - 基于知识库文件列表，使用AI生成测试问题
  - 支持指定生成数量（设置10个）
  - 问题自动保存到知识库元数据
  - 返回生成的问题列表
- `GET /api/knowledge/databases/{db_id}/sample-questions` - 获取示例问题

  - 从知识库元数据中读取已生成的问题
  - 返回问题列表和数量

#### 前端更新

**更新文件：**

- `web/src/apis/knowledge_api.js`

  - 新增 `generateSampleQuestions(dbId, count)` - 生成示例问题
  - 新增 `getSampleQuestions(dbId)` - 获取示例问题
- `web/src/components/QuerySection.vue`

  - 添加示例问题显示区域
  - 实现示例问题轮播功能（每10秒切换）
  - 添加点击示例问题自动填充查询框功能
  - 添加加载和生成状态显示
  - 实现知识库切换时自动重新加载问题
  - 暴露 `generateSampleQuestions()`, `loadSampleQuestions()`, `clearQuestions()` 等方法
- `web/src/views/DataBaseInfoView.vue`

  - 添加文件变化监听，自动生成示例问题
  - 添加查询区域组件引用管理

#### 功能特性

- AI自动分析知识库文件，生成有价值的测试问题
- 问题涵盖不同方面和难度，长度控制在10-30字之间
- 支持问题轮播显示（每10秒切换）
- 点击问题自动填充到查询框并执行查询
- 问题自动保存到知识库元数据，知识库切换时自动加载对应的问题
- 当文件变化时自动重新生成问题

---

## 🔧 技术细节

### 依赖项更新

**前端新增依赖：**

```json
{
  "markmap-lib": "^0.18.12",
  "markmap-view": "^0.18.12"
}
```

**安装命令：**

```bash
cd web
pnpm install
```

### 配置要求

1. **MinIO服务** - 用于图片存储

   - 需要配置MinIO连接信息
   - 自动创建 `kb-images` bucket
2. **LLM模型** - 用于AI生成功能

   - 思维导图生成需要LLM模型
   - 示例问题生成需要LLM模型
   - 需要在配置文件中设置模型信息

### 数据存储

- **思维导图数据**：保存在知识库的全局元数据中（`global_databases_meta[db_id]["mindmap"]`）
- **示例问题数据**：保存在知识库的全局元数据中（`global_databases_meta[db_id]["sample_questions"]`）
- **图片数据**：存储在MinIO对象存储中，元数据保存在文件信息中

---

## 📚 相关文档

- Markmap思维导图：https://markmap.js.org/
- MinIO对象存储文档：https://www.minio.org.cn/docs/minio/linux/index.html
- 项目主文档：https://xerrors.github.io/Yuxi-Know/

---

**更新日期：** 2025-11-14
**更新版本：** 基于官方 v0.3.0 ，根据实际需求拓展版本——狸欢
