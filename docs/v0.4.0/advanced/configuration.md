# 配置系统详解

## 概述

Yuxi-Know 从 v0.3.x 版本开始采用了全新的配置系统，基于 Pydantic BaseModel 和 TOML 格式，提供了类型安全、智能提示和选择性持久化等现代化特性。

## 架构设计

### 配置层次结构

```
配置系统架构
├── 默认配置 (代码定义)
│   ├── src/config/static/models.py (模型配置)
│   └── src/config/app.py (应用配置)
├── 用户配置 (TOML 文件)
│   └── saves/config/base.toml (仅保存用户修改)
└── 环境变量 (运行时覆盖)
    └── .env 文件
```

### 核心组件

#### 1. Config 类 (`src/config/app.py`)

主配置类，继承自 Pydantic BaseModel，提供：

- **类型验证**: 自动检查配置项类型
- **默认值管理**: 内置合理的默认配置
- **选择性持久化**: 仅保存用户修改的配置项
- **向后兼容**: 支持旧的字典式访问方式

```python
class Config(BaseModel):
    # 功能开关
    enable_reranker: bool = Field(default=False, description="是否开启重排序")
    enable_content_guard: bool = Field(default=False, description="是否启用内容审查")

    # 模型配置
    default_model: str = Field(default="siliconflow/deepseek-ai/DeepSeek-V3.2")
    embed_model: str = Field(default="siliconflow/BAAI/bge-m3")

    # 运行时状态 (不持久化)
    model_provider_status: dict[str, bool] = Field(exclude=True)
```

#### 2. 模型配置类 (`src/config/static/models.py`)

定义了三种类型的模型配置：

- **ChatModelProvider**: 聊天模型提供商
- **EmbedModelInfo**: 嵌入模型信息
- **RerankerInfo**: 重排序模型信息

```python
class ChatModelProvider(BaseModel):
    name: str = Field(..., description="提供商显示名称")
    url: str = Field(..., description="提供商文档或模型列表 URL")
    base_url: str = Field(..., description="API 基础 URL")
    default: str = Field(..., description="默认模型名称")
    env: str = Field(..., description="API Key 环境变量名")
    models: list[str] = Field(default_factory=list, description="支持的模型列表")
```

添加配置：


```python
# 1. 在 DEFAULT_CHAT_MODEL_PROVIDERS 中添加
"new-provider": ChatModelProvider(
    name="新提供商",
    url="https://provider.com/docs",
    base_url="https://api.provider.com/v1",
    default="default-model",
    env="NEW_PROVIDER_API_KEY",
    models=["model1", "model2"],
),

# 2. 在 .env 中配置 API Key
# NEW_PROVIDER_API_KEY=your_api_key

# 3. 重启服务或重新加载配置
```

## 配置管理特性

系统只会保存用户修改过的配置项：

```python
# 用户只修改了 enable_reranker
config.enable_reranker = True
config.save()  # 只保存 enable_reranker 到 TOML 文件

# TOML 文件内容
# enable_reranker = true
```

### 默认模型配置 (`src/config/static/models.py`)

包含所有支持的模型提供商的默认配置，开发者可以直接修改此文件添加新的模型：

```python
DEFAULT_CHAT_MODEL_PROVIDERS: dict[str, ChatModelProvider] = {
    "siliconflow": ChatModelProvider(
        name="SiliconFlow",
        url="https://cloud.siliconflow.cn/models",
        base_url="https://api.siliconflow.cn/v1",
        default="deepseek-ai/DeepSeek-V3.2",
        env="SILICONFLOW_API_KEY",
        models=[
            "deepseek-ai/DeepSeek-V3.2",
            "Qwen/Qwen3-235B-A22B-Instruct-2507",
            # ...
        ],
    ),
    # 更多提供商...
}
```

### 用户配置 (`saves/config/base.toml`)

只包含用户修改过的配置项，使用 TOML 格式：

```toml
# 用户只修改了这些配置项
enable_reranker = true
default_agent_id = "MyCustomAgent"
enable_content_guard = true

# 模型配置修改
[model_names.siliconflow]
models = [
    "deepseek-ai/DeepSeek-V3.2",
    "custom-model-name",
]
```

## 高级配置

### 动态配置更新

```python
from src.config import config

# 更新配置
config.enable_reranker = True
config.default_agent_id = "CustomAgent"

# 更新模型列表
config.model_names["siliconflow"].models.append("new-model")

# 保存配置
config.save()

# 或者只保存特定提供商的模型配置
config._save_models_to_file("siliconflow")
```

### 配置验证

```python
# 验证配置
from src.config import config

# 检查模型提供商可用性
for provider, status in config.model_provider_status.items():
    print(f"{provider}: {'✅' if status else '❌'}")

# 获取可用模型列表
available_models = config.get_model_choices()
available_embed_models = config.get_embed_model_choices()
available_rerankers = config.get_reranker_choices()
```

### 配置导出

```python
# 导出完整配置（包含运行时状态）
full_config = config.dump_config()

# 导出用户配置（仅保存到文件的部分）
user_config = {
    field: getattr(config, field)
    for field in config._user_modified_fields
}
