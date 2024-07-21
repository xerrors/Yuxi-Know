## 模型说明

### 1. 对话模型支持

模型仅支持通过API调用的模型，如果是需要运行本地模型，则建议使用 vllm 转成 API 服务之后使用。

|模型供应商(`config.model_provider`)|默认模型(`config.model_name`)|配置项目(`.env`)|
|:-|:-|:-|
|`qianfan`|`ernie_speed`|`QIANFAN_ACCESS_KEY`, `QIANFAN_SECRET_KEY`|
|`zhipu`|`glm-4`|`ZHIPUAPI`|
|`deepseek`|`deepseek-chat`|`DEEPSEEKAPI`|
|`vllm`|`vllm`|`VLLM_API_KEY`, `VLLM_API_BASE`|

vllm 的具体配置项可以参考[这里](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html#named-arguments), 部署参考脚本：

```bash
python -m vllm.entrypoints.openai.api_server \
	--model="/home/zwj/workspace/models/chatglm3-6b" \
	--tensor-parallel-size 1 \
	--trust-remote-code \
	--device auto \
	--gpu-memory-utilization 0.98 \
	--dtype half \
	--served-model-name "vllm" \
	--host 0.0.0.0 \
	--port 8080
```

*openai 没条件测，不知道

### 2. 向量模型支持


|模型名称(`config.embed_model`)|默认路径/模型|需要配置项目（`config.model_local_paths`）|
|:-|:-|:-|
|`bge-large-zh-v1.5`|`BAAI/bge-large-zh-v1.5`|`bge-large-zh-v1.5`（*修改为本地路径）|
|`zhipu`|`embedding-2`|`ZHIPUAPI` (`.env`)|

### 3. 重排序模型支持


例如（`config/base.yaml`）：

```yaml
model_provider: qianfan
model_name: null # for default

## model dir 可以写相对路径和绝对路径
### 相对路径是相对于环境变量 (.env) 中 MODEL_ROOT_DIR 的路径
model_local_paths:
  bge-large-zh-v1.5: /models/bge-large-zh-v1.5
```
