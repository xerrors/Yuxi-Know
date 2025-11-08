# 模型配置

## 对话模型

系统支持多种大语言模型服务商，通过配置对应的 API 密钥即可使用：

| 服务商 | 环境变量 | 特点 |
|--------|----------|------|
| [硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) | `SILICONFLOW_API_KEY` | 🆓 免费额度，默认推荐 |
| OpenAI | `OPENAI_API_KEY` | GPT 系列模型 |
| DeepSeek | `DEEPSEEK_API_KEY` | 国产大模型 |
| OpenRouter | `OPENROUTER_API_KEY` | 多模型聚合平台 |
| 智谱清言 | `ZHIPUAI_API_KEY` | GLM 系列模型 |
| 阿里云百炼 | `DASHSCOPE_API_KEY` | 通义千问系列 |

其余还支持火山、Together、vLLM、Ollama 等。

### 配置方法

在 `.env` 文件中添加对应的环境变量：

<<< @/../.env.template#model_provider{bash 2}

### 默认对话模型格式

系统的默认对话模型通过配置项 `default_model` 指定，格式统一为 `模型提供商/模型名称`，例如：

```yaml
default_model: siliconflow/deepseek-ai/DeepSeek-V3.2-Exp
```

在 Web 界面中选择模型时也会自动按照这一格式保存，无需手动拆分提供商和模型名称。


::: tip 免费获取 API Key
[硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) 注册即送 14 元额度，支持多种开源模型。
:::

## 自定义模型供应商

::: warning
原本网页中的自定义模型已在 `0.3.x` 版本移除，请在 `src/config/static/models.py` 中按如下方式配置，并重启服务后选择并使用。此外，这里也推荐一下团队的另外一个小工具 [mvllm (Manage and Route vLLM Servers)](https://github.com/xerrors/mvllm)。
:::

::: tip 配置系统升级 (v0.3.x)
从 `v0.3.x` 版本开始，模型配置系统已升级为基于 Pydantic BaseModel 的类型安全配置，支持 TOML 格式的用户配置文件。
- **默认配置**: `src/config/static/models.py` (Python 代码)
- **用户配置**: `saves/config/base.toml` (TOML 格式，仅保存用户修改)
:::

系统理论上兼容任何 OpenAI 兼容的模型服务，包括：

- **vLLM**: 高性能推理服务
- **Ollama**: 本地模型管理
- **API 中转服务**: 各种代理和聚合服务

如需添加新的模型供应商，请按以下步骤操作：

### 1. 编辑模型配置文件

**方式一：修改默认配置（推荐）**
编辑 `src/config/static/models.py` 文件中的 `DEFAULT_CHAT_MODEL_PROVIDERS` 字典

在 `src/config/static/models.py` 中添加新的模型供应商：

```python
DEFAULT_CHAT_MODEL_PROVIDERS: dict[str, ChatModelProvider] = {
    # ... 现有配置 ...

    "custom-provider": ChatModelProvider(
        name="自定义提供商",
        url="https://your-provider.com/docs",
        base_url="https://api.your-provider.com/v1",
        default="custom-model-name",
        env="CUSTOM_API_KEY_ENV_NAME",
        models=[
            "supported-model-name",
            "another-model-name",
        ],
    ),

    # 本地 Ollama 服务
    "local-ollama": ChatModelProvider(
        name="Local Ollama",
        url="https://ollama.com",
        base_url="http://localhost:11434/v1",
        default="llama3.2",
        env="NO_API_KEY",  # 对于不需要API Key的服务，使用NO_API_KEY
        models=["llama3.2", "qwen2.5"],
    ),

    # 本地 vLLM 服务
    "local-vllm": ChatModelProvider(
        name="Local vLLM",
        url="https://docs.vllm.ai",
        base_url="http://localhost:8000/v1",
        default="Qwen/Qwen2.5-7B-Instruct",
        env="NO_API_KEY",
        models=[
            "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen2.5-14B-Instruct",
        ],
    ),
}
```

### 3. 配置环境变量

在 `.env` 文件中添加对应的环境变量：
```env
CUSTOM_API_KEY_ENV_NAME=your_api_key_here
```

### 4. 重新部署

```bash
docker compose restart api-dev
```

## 嵌入模型和重排序模型

::: warning 重要说明
从 v0.2 版本开始，项目采用微服务架构，模型部署与项目本身完全解耦。如需使用本地模型，需要先通过 vLLM 或 Ollama 部署为 API 服务。
:::

### 本地模型部署

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

#### 2. 启动模型服务

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