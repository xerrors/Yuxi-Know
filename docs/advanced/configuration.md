# 配置系统详解

## 概述

系统采用多层配置架构，模型配置由网页界面管理，应用配置基于 Pydantic + TOML。

## 配置层级

```
代码默认值 → TOML 文件 → 环境变量
   (低)                      (高)
```

## 模型配置

由网页统一管理，详见 [模型配置](./intro/model-config.md)。

## 应用配置

配置项定义于 `backend/package/yuxi/config/app.py`，用户修改保存至 `saves/config/base.toml`。

### 修改配置

```python
from yuxi.config import config

config.enable_reranker = True
config.save()
```

## 常见问题

**配置文件损坏**：删除 `saves/config/base.toml`，系统将重新生成默认配置。
