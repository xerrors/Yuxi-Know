## 模型说明

### 1. 对话模型支持

模型仅支持通过API调用的模型，如果是需要运行本地模型，则建议使用 vllm 转成 API 之后使用。

|模型供应商(`config.model_provider`)|默认模型(`model.model_name`)|配置项目(`.env`)|
|:-|:-|:-|
|`qianfan`|`ernie_speed`|`QIANFAN_ACCESS_KEY`, `QIANFAN_SECRET_KEY`|
|`zhipu`|`glm-4`|`ZHIPUAPI`|
|`deepseek`|`deepseek-chat`|`DEEPSEEKAPI`|
|`vllm`|`vllm`|`VLLM_API_KEY`, `VLLM_API_BASE`|

vllm 部署参考脚本：

```bash
python -m vllm.entrypoints.openai.api_server --model ~/models/Meta-Llama-3-8B-Instruct --served-model-name vllm --trust-remote-code
```

*openai 没条件测，不知道

### 2. 向量模型支持


|模型名称(`config.embed_model`)|默认路径|可配置项目（`config.model_local_paths`）|
|:-|:-|:-|
|`bge-large-zh-v1.5`|`BAAI/bge-large-zh-v1.5`|`bge-large-zh-v1.5`|

### 3. 重排序模型支持


例如：

```yaml
model_provider: qianfan
model_name: null # for default

## model dir 可以写相对路径和绝对路径
### 相对路径是相对于环境变量 (.env) 中 MODEL_ROOT_DIR 的路径
model_local_paths:
  bge-large-zh-v1.5: bge-large-zh-v1.5
```
