## 模型说明

### 1. 对话模型支持

模型仅支持通过API调用的模型，如果是需要运行本地模型，则建议使用 vllm 转成 API 服务之后使用。使用前请配置 APIKEY 后使用，配置项目参考：[.env.template](../.env.template)

|模型供应商(`config.model_provider`)|默认模型(`config.model_name`)|配置项目(`.env`)|
|:-|:-|:-|
|`openai` | `gpt-4o` | `OPENAI_API_KEY` |
|`qianfan`（百度）|`ernie_speed`|`QIANFAN_ACCESS_KEY`, `QIANFAN_SECRET_KEY`|
|`zhipu`(default)|`glm-4`|`ZHIPUAI_API_KEY`|
|`dashscope`（阿里） | `qwen-max-latest` | `DASHSCOPE_API_KEY`|
|`deepseek`|`deepseek-chat`|`DEEPSEEK_API_KEY`|
|`siliconflow` | `meta-llama/Meta-Llama-3.1-8B-Instruct` | `SILICONFLOW_API_KEY`|

同样支持以 OpenAI 的兼容模型运行模型，可以直接在设置里面添加。比如使用 vllm 和 Ollama 运行本地模型时。

### 2. 向量模型支持

建议直接使用智谱 AI 的 embedding-3，这样不需要做任何修改，且资费不贵。

> [!Warning]
> 需要注意，由于知识库和图数据库的构建都依赖于向量模型，如果中途更改向量模型，回导致知识库不可用。此外，知识图谱的向量索引的建立默认使用 embedding-3 构建，因此检索的时候必须使用 embedding-3（现阶段还不支持修改）


|模型名称(`config.embed_model`)|默认路径/模型|需要配置项目（`config.model_local_paths`）|
|:-|:-|:-|
|`bge-large-zh-v1.5`|`BAAI/bge-large-zh-v1.5`|`bge-large-zh-v1.5`（*可选：修改为本地路径）|
|`zhipu`|`embedding-2`, `embedding-3`|`ZHIPUAI_API_KEY` (`.env`)|


### 3. 重排序模型支持

目前仅支持 `BAAI/bge-reranker-v2-m3`。

### 4. 本地模型支持

对于**语言模型**，并不支持直接运行本地语言模型，请使用 vllm 或者 ollama 转成 API 服务之后使用。

对于**向量模型**和**重排序模型**，可以不做修改会自动下载模型，如果下载过程中出现问题，请参考 [HF-Mirror](https://hf-mirror.com/) 配置相关内容。如果想要使用本地已经下载好的模型（不建议），可以在 `saves/config/config.yaml` 配置相关内容。同时注意要在 docker 中做映射，参考 README 中的 `docker/docker-compose.yml`。

例如：

```yaml
model_local_paths:
  bge-large-zh-v1.5: /models/bge-large-zh-v1.5
```
