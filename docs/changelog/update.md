目前已有的开发计划包括：


### v2.0 Prerelease

💭 **Features Todo**
- [x] 知识库使用 LightRAG（GraphRAG 轻量版）重构（🌟🌟🌟🌟🌟）
- [x] 集成 MinerU 处理 PDF 文件。（🌟🌟🌟）
- [x] 优化现有向量模型的逻辑，全局配置的向量模型作为新建知识库的默认模型，但是查询的时候，使用对应数据库的向量模型查询（单例模式）（🌟🌟🌟）
- [x] 多类型知识库支持（🌟🌟🌟🌟🌟）
- [x] 设计问答知识库，支持针对问答对的调优
- [x] 添加了批量上传文件的脚本，并优化文件信息

🐛**BUGs**
- [x] 智能体的工具切换有问题
- [ ] 知识图谱可视化页面的效果有点问题
- [x] 处理失败的文件，在特定情况下会一直处于 processing 状态，且无法删除
- [ ] 与最新的 LightRAG 版本兼容性存在问题 #233

# 💯 More:

下面的功能会放在后续版本实现，暂时未定

- [ ] 封装现有工具为 mcp（stdio）调用
- [ ] 支持额外 mcp 配置（代码端）
- [ ] 添加用户日志与用户反馈模块，可以在 AgentView 中查看信息（🌟🌟）
- [ ] 对话页面支持文档/图片临时上传（🌟🌟🌟🌟）
- [ ] 在 @web/src/components/ToolCallingResult/KnowledgeBaseResult.vue 文件中，添加点击某个片段的时候可以弹出信息预览框（最好可以提供源文件下载的功能），这里需要将DatabaseInfoView 里面的那个文件详情的弹窗给组件化。
    - 先实现 result 中可以按照 file_id 聚合信息；信息的展示以结果卡片的形式展示
    但是同时也要能够配置，选择显示源文件还是chunk的结果，如果可以的话，最好是在一个文件里面显示所有的chunk，而不是每个chunk都单独显示。不过似乎有点难度，毕竟是有 overlap 的存在，还是分开吧。对于URL链接的这种，可以选择直接跳转就可以。(sub1: sub2：根据 file_id 可以从后端获取文件的基本信息，比如可下载的路径，chunks 等信息；sub3：在前端获取到所有的 chunks 信息之后，能够根据传入的 chunks_idx 高亮被选中的 chunks 区域；sub4：如果可能的话，使用 markdown 展示（但是存在 overlap 拼接的问题。不知道现在知识库里面是否存储的有 fulltext，这时候 start_idx 和 end_idx 就有用了。）
- [ ] 先实现在 DatabaseInfo.vue 中，点击文件详情按钮，能够弹出文件详情的弹窗，显示的方法有两种，一种是以现在的 chunk 的形式展示，一种是以 markdown渲染全文的形式，但是存在 overlap 拼接的问题。不知道现在知识库里面是否存储的有 fulltext，这时候 start_idx 和 end_idx 就有用了。
- [ ] 各种结果的可视化：知识库检索页面，工具调用检索页面，知识图谱检索页面


根据这个模糊的分析，判断一下这个需求应该如何实现，务必阅读所有相关的文献，包括但不限于当前代码中，保存文本片段的时候所保存的信息是否支撑功能的实现，当某些需求无法实现的时候，能否采用退而求其次的方法实现略差一些的功能（不要过度增加代码的复杂度）。

模糊的需求如下：先实现在 DatabaseInfo.vue 中，点击文件详情按钮，能够弹出文件详情的弹窗，显示的方法有两种，一种是以现在的 chunk 的形式展示，一种是以 markdown渲染全文的形式，但是存在 overlap 拼接的问题。不知道现在知识库里面是否存储的有 fulltext，这时候 start_idx 和 end_idx 就有用了。并不对，直接读取源文件的方法是错的，因为源文件并不全是 markdown 格式，可能是 html、pdf 等结构文件，因此，只能想办法拼接，而不是尝试读取文件。项目中已经安装了 md-editor-v3 ，可以参考 AgentMessageComponent.vue 中对于 markdown 的渲染。

先告诉我你要如何实现这些功能，重点实现的是 milvus db 和 chroma db ，lightrag db 尽量实现，实现不了也没事。相关的上下文如下 knowledge_router.py knowledge_base.py DataBaseInfoView.vue。