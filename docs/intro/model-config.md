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

在 `src/.env` 文件中添加对应的环境变量：

<<< @/../src/.env.template#model_provider{bash 2}


::: tip 免费获取 API Key
[硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) 注册即送 14 元额度，支持多种开源模型。
:::

## 自定义模型供应商

::: warning
原本网页中的自定义模型已在 `0.3.x` 版本移除，请在 `src/config/static/models.yaml` 中按如下方式配置，并重启服务后选择并使用。此外，这里也推荐一下团队的另外一个小工具 [mvllm (Manage and Route vLLM Servers)](https://github.com/xerrors/mvllm)。
:::

系统理论上兼容任何 OpenAI 兼容的模型服务，包括：

- **vLLM**: 高性能推理服务
- **Ollama**: 本地模型管理
- **API 中转服务**: 各种代理和聚合服务

如需添加新的模型供应商，请按以下步骤操作：

### 1. 编辑模型配置文件

**方式一：修改默认配置**
编辑 `src/config/static/models.yaml` 文件

**方式二：使用覆盖配置**
创建自定义配置文件并通过环境变量指定：
```bash
# 创建自定义配置文件
cp src/config/static/models.yaml /path/to/your/custom-models.yaml

# 设置环境变量
export OVERRIDE_DEFAULT_MODELS_CONFIG_WITH=/path/to/your/custom-models.yaml
```

### 2. 添加模型配置

在配置文件中添加新的模型供应商：

```yaml
custom-provider-name:
  name: custom-provider-name
  default: custom-model-name
  base_url: "https://api.your-provider.com/v1"
  env: CUSTOM_API_KEY_ENV_NAME  # 注意：现在是单个环境变量
  models:
    - supported-model-name
    - another-model-name

# 本地 Ollama 服务
local-ollama:
  name: Local Ollama
  base_url: "http://localhost:11434/v1"
  default: llama3.2
  env: NO_API_KEY  # 对于不需要API Key的服务，使用NO_API_KEY
  models:
    - llama3.2
    - qwen2.5

# 本地 vLLM 服务
local-vllm:
  name: Local vLLM
  base_url: "http://localhost:8000/v1"
  default: Qwen/Qwen2.5-7B-Instruct
  env: NO_API_KEY
  models:
    - Qwen/Qwen2.5-7B-Instruct
    - Qwen/Qwen2.5-14B-Instruct
```

### 3. 配置环境变量

在 `src/.env` 文件中添加对应的环境变量：
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

在 `src/config/static/models.yaml` 中或通过覆盖配置文件添加配置：

```yaml
EMBED_MODEL_INFO:
  vllm/Qwen/Qwen3-Embedding-0.6B:
    name: Qwen/Qwen3-Embedding-0.6B
    dimension: 1024
    base_url: http://localhost:8000/v1/embeddings
    api_key: no_api_key

RERANKER_LIST:
  vllm/BAAI/bge-reranker-v2-m3:
    name: BAAI/bge-reranker-v2-m3
    base_url: http://localhost:8000/v1/rerank
    api_key: no_api_key
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

## 常见问题

**Q: 如何查看当前可用的模型？**

在 Web 界面的"设置"页面可以查看所有已配置的模型。

**Q: 模型配置不生效？**

1. 检查环境变量是否正确设置
2. 确认 API 密钥有效
3. 重启服务：`docker compose restart api-dev`

**Q: 如何测试模型连接？**

在 Web 界面的对话页面选择对应模型进行测试。
