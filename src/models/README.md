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
|`vllm`|`vllm`|`VLLM_API_KEY`, `VLLM_API_BASE`|

vllm 的具体配置项可以参考[这里](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html#named-arguments), 部署参考脚本：

```bash
python -m vllm.entrypoints.openai.api_server \
	--model="/hdd/models/meta-llama/Meta-Llama-3.1-8B-Instruct" \
	--tensor-parallel-size 1 \
	--trust-remote-code \
	--device auto \
	--gpu-memory-utilization 0.98 \
	--dtype half \
	--served-model-name "vllm" \
	--host 0.0.0.0 \
	--port 8080
```

### 2. 向量模型支持

建议直接使用智谱 AI 的 embedding-3。

> [!Warning]
> 需要注意，由于知识库和图数据库的构建都依赖于向量模型，如果中途更改向量模型，回导致知识库不可用。此外，知识图谱的向量索引的建立默认使用 embedding-3 构建，因此检索的时候必须使用 embedding-3（现阶段还不支持修改）


|模型名称(`config.embed_model`)|默认路径/模型|需要配置项目（`config.model_local_paths`）|
|:-|:-|:-|
|`bge-large-zh-v1.5`|`BAAI/bge-large-zh-v1.5`|`bge-large-zh-v1.5`（*修改为本地路径）|
|`zhipu`|`embedding-2`, `embedding-3`|`ZHIPUAI_API_KEY` (`.env`)|


例如（`saves/config/config.yaml`）：

```yaml
model_provider: qianfan
model_name: null # for default

## model dir 可以写**相对路径**和**绝对路径**
### 相对路径是相对于环境变量 (.env) 中 MODEL_ROOT_DIR（若为空则是相对于 `pretrained_models`) 的路径
model_local_paths:
  bge-large-zh-v1.5: /models/bge-large-zh-v1.5
```

### 3. 重排序模型支持

目前仅支持 `BAAI/bge-reranker-v2-m3`。
