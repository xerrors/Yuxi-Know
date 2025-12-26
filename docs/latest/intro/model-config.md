# 模型配置

## 对话模型

系统支持多种大语言模型服务商，通过配置对应的 API 密钥即可使用：

| 服务商                                           | 环境变量                | 特点                  |
| ------------------------------------------------ | ----------------------- | --------------------- |
| [硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) | `SILICONFLOW_API_KEY` | 🆓 免费额度，默认推荐 |
| OpenAI                                           | `OPENAI_API_KEY`      | GPT 系列模型          |
| DeepSeek                                         | `DEEPSEEK_API_KEY`    | 国产大模型            |
| OpenRouter                                       | `OPENROUTER_API_KEY`  | 多模型聚合平台        |
| 智谱清言                                         | `ZHIPUAI_API_KEY`     | GLM 系列模型          |
| 阿里云百炼                                       | `DASHSCOPE_API_KEY`   | 通义千问系列          |

其余还支持火山豆包、Together、vLLM、Ollama 等。

### 配置方法

在 `.env` 文件中添加对应的环境变量：



::: tip 免费获取 API Key
[硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) 注册即送 14 元额度，支持多种开源模型。
:::

<<< @/../.env.template#model_provider{bash 5}

### 默认对话模型格式

系统的默认对话模型可以在设置页面配置，也可以通过配置项 `default_model` 指定，格式统一为 `模型提供商/模型名称`，例如：

```yaml
default_model: siliconflow/deepseek-ai/DeepSeek-V3.2
```

## 自定义模型供应商

::: tip 配置系统升级 (v0.3.x)
从 `v0.3.x` 版本开始，模型配置系统已升级为基于 Pydantic BaseModel 的类型安全配置，支持 TOML 格式的用户配置文件。

- **默认配置**: `src/config/static/models.py` (Python 代码)
- **用户配置**: `saves/config/base.toml` (TOML 格式，仅保存用户修改)
- **自定义供应商**: `saves/config/custom_providers.toml` (独立配置文件)
  :::

系统提供了完整的自定义供应商管理功能，支持通过 Web 界面直接添加、编辑、测试和删除自定义模型供应商。

### 使用方法

系统支持任何 OpenAI 兼容的云服务提供商

#### 1. Web 界面操作（推荐）

访问 **系统设置 > 模型配置**，在"自定义供应商"部分点击 **添加自定义供应商**。这里的密钥可以直接填写也可以填写对应的环境变量名称。

#### 2. 配置文件操作

如需通过配置文件管理，编辑 `saves/config/custom_providers.toml`：

```toml
[model_names.local-vllm]
name = "本地 vLLM 服务"
url = "https://docs.vllm.ai"
base_url = "http://localhost:8000/v1"
default = "Qwen/Qwen2.5-7B-Instruct"
env = "LOCAL_VLLM_API_KEY"
models = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
]
custom = true

[model_names.local-ollama]
name = "本地 Ollama"
url = "https://ollama.com"
base_url = "http://localhost:11434/v1"
default = "llama3.2"
env = "NO_API_KEY"
models = ["llama3.2", "qwen2.5"]
custom = true
```

然后在 `.env` 文件中添加对应的环境变量：

```env
LOCAL_VLLM_API_KEY=your_api_key_here
```

### API 端点

系统提供以下 API 端点管理自定义供应商：

- `GET /api/system/custom-providers` - 获取所有自定义供应商
- `POST /api/system/custom-providers` - 添加自定义供应商
- `PUT /api/system/custom-providers/{provider_id}` - 更新自定义供应商
- `DELETE /api/system/custom-providers/{provider_id}` - 删除自定义供应商
- `POST /api/system/custom-providers/{provider_id}/test` - 测试供应商连接

### 常见配置示例

#### vLLM 本地服务

```toml
[model_names.vllm-local]
name = "vLLM 本地服务"
base_url = "http://localhost:8000/v1"
default = "Qwen/Qwen2.5-7B-Instruct"
env = "NO_API_KEY"
models = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct"
]
```

#### Ollama 本地服务

```toml
[model_names.ollama-local]
name = "Ollama 本地服务"
base_url = "http://localhost:11434/v1"
default = "llama3.2"
env = "NO_API_KEY"
models = [
    "llama3.2:latest",
    "qwen2.5:latest",
    "codellama:latest"
]
```

#### 第三方 API 中转服务

```toml
[model_names.api-proxy]
name = "API 中转服务"
base_url = "https://api-proxy.example.com/v1"
default = "gpt-3.5-turbo"
env = "API_PROXY_KEY"
models = [
    "gpt-3.5-turbo",
    "gpt-4",
    "claude-3-sonnet"
]
```

### 故障排除

1. **测试连接失败**: 检查 API 地址格式和 API 密钥配置
2. **模型不可用**: 确认模型名称拼写和服务端是否支持该模型
3. **权限错误**: 确保用户具有管理员权限
4. **配置未生效**: 检查环境变量配置和服务重启状态

## 嵌入模型和重排序模型

#### 1. 配置模型信息

在 `src/config/static/models.py` 中的默认配置部分添加：

```python
# 默认嵌入模型配置
DEFAULT_EMBED_MODELS: dict[str, EmbedModelInfo] = {
    # ... 现有配置 ...

    "vllm/Qwen/Qwen3-Embedding-0.6B": EmbedModelInfo(
        name="Qwen/Qwen3-Embedding-0.6B",
        dimension=1024,
        base_url="http://localhost:8000/v1/embeddings",
        api_key="no_api_key",
    ),
}

# 默认重排序模型配置
DEFAULT_RERANKERS: dict[str, RerankerInfo] = {
    # ... 现有配置 ...

    "vllm/BAAI/bge-reranker-v2-m3": RerankerInfo(
        name="BAAI/bge-reranker-v2-m3",
        base_url="http://localhost:8000/v1/rerank",
        api_key="no_api_key",
    ),
}
```

#### 2. 动态配置（可选）

你也可以通过代码动态添加本地模型：

```python
from src.config import config
from src.config.static.models import EmbedModelInfo, RerankerInfo

# 添加本地嵌入模型
config.embed_model_names["local/embed-model"] = EmbedModelInfo(
    name="local-embed-model",
    dimension=1024,
    base_url="http://localhost:8000/v1/embeddings",
    api_key="no_api_key",
)

# 添加本地重排序模型
config.reranker_names["local/reranker-model"] = RerankerInfo(
    name="local-reranker-model",
    base_url="http://localhost:8000/v1/rerank",
    api_key="no_api_key",
)

# 保存配置
config.save()
```

#### 3. 启动模型服务

```bash
# 启动嵌入模型
vllm serve Qwen/Qwen3-Embedding-0.6B \
  --task embed \
  --dtype auto \
  --port 8000

# 启动重排序模型
vllm serve BAAI/bge-reranker-v2-m3 \
  --task score \
  --dtype fp16 \
  --port 8000
```
