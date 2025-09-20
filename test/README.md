# Yuxi-Know API 测试脚本

## 概述

本测试套件为Yuxi-Know项目提供了全面的API接口测试，涵盖认证、系统管理、对话等核心功能模块。

## 测试架构

### 测试工具栈
- **pytest**: Python测试框架
- **pytest-asyncio**: 异步测试支持
- **httpx**: 现代HTTP客户端
- **pytest-cov**: 测试覆盖率分析

### 测试模块结构

```
test/
├── api/                        # API接口测试
│   ├── test_auth_api.py       # 认证API测试
│   ├── test_system_api.py     # 系统API测试
│   └── test_chat_api.py       # 对话API测试
├── conftest.py                 # pytest配置和公共fixtures
├── run_tests.sh               # 测试运行脚本
├── .env.test.example          # 测试环境配置示例
└── README.md                  # 测试文档
```

## 快速开始

### 1. 准备环境

```bash
# 复制测试配置文件
cp test/.env.test.example test/.env.test

# 编辑配置文件，设置测试服务器地址和认证信息
vim test/.env.test
```

### 2. 运行测试

```bash
# 使用测试脚本（推荐）
./test/run_tests.sh all

# 或直接使用pytest
uv run pytest test/api/ -v
```

## 测试类型

### 认证测试 (test_auth_api.py)
- ✅ 健康检查（无需认证）
- ✅ 首次运行状态检查
- ✅ 登录凭据验证
- ✅ 用户信息获取
- ✅ 用户管理权限
- ✅ 无效令牌处理

### 系统测试 (test_system_api.py)
- ✅ 系统健康检查
- ✅ 系统信息获取
- ✅ 配置管理（获取/更新）
- ✅ 批量配置更新
- ✅ 系统日志获取
- ✅ 权限控制验证

### 对话测试 (test_chat_api.py)
- ✅ 智能体列表获取
- ✅ 简单对话调用
- ✅ 流式对话测试
- ✅ 线程管理（创建/更新/删除）
- ✅ 工具列表获取
- ✅ 智能体配置管理

## 运行命令

### 使用测试脚本

```bash
# 所有测试
./test/run_tests.sh all

# 认证测试
./test/run_tests.sh auth

# 系统测试
./test/run_tests.sh system

# 对话测试
./test/run_tests.sh chat

# 快速测试（排除慢速测试）
./test/run_tests.sh quick

# 检查服务器状态
./test/run_tests.sh check
```

### 使用pytest直接运行

```bash
# 运行所有API测试
uv run pytest test/api/ -v

# 运行特定测试文件
uv run pytest test/api/test_auth_api.py -v

# 运行特定测试方法
uv run pytest test/api/test_auth_api.py::TestAuthAPI::test_login_valid_credentials -v

# 运行带标记的测试
uv run pytest test/api/ -v -m "auth"
uv run pytest test/api/ -v -m "not slow"

# 生成覆盖率报告
uv run pytest test/api/ --cov=server --cov=src --cov-report=html
```

## 测试标记

测试使用pytest标记进行分类：

- `@pytest.mark.auth`: 需要认证的测试
- `@pytest.mark.slow`: 慢速测试（如流式对话）
- `@pytest.mark.integration`: 集成测试

## 配置说明

### 环境变量 (test/.env.test)

```bash
# 测试服务器地址
TEST_BASE_URL=http://localhost:5050

# 测试用户凭据
TEST_USERNAME=zwj
TEST_PASSWORD=zwj12138
```

### pytest配置 (pyproject.toml)

```toml
[tool.pytest.ini_options]
addopts = "-v --tb=short"
testpaths = ["test"]
markers = [
    "auth: marks tests that require authentication",
    "slow: marks tests as slow",
    "integration: marks tests as integration tests"
]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
```

## 测试特性

### 智能错误处理
- 自动检测服务器可用性
- 优雅处理认证失败
- 权限不足时跳过相关测试

### 异步支持
- 完整的异步测试支持
- 高效的并发测试执行
- 会话级别的资源管理

### 灵活配置
- 环境变量配置
- 可配置的服务器地址
- 支持不同环境切换

## 故障排除

### 常见问题

1. **连接失败**
   ```bash
   # 检查服务器是否运行
   curl http://localhost:5050/api/system/health
   
   # 检查Docker服务
   docker-compose ps
   ```

2. **认证失败**
   - 检查 `test/.env.test` 中的用户凭据
   - 确认用户存在且密码正确
   - 验证用户权限级别

3. **依赖问题**
   ```bash
   # 重新安装测试依赖
   uv add --group test pytest pytest-asyncio pytest-httpx pytest-cov
   ```

### 调试选项

```bash
# 详细输出
uv run pytest test/api/ -v -s

# 显示完整错误信息
uv run pytest test/api/ --tb=long

# 停在第一个失败
uv run pytest test/api/ -x

# 运行最后失败的测试
uv run pytest test/api/ --lf
```

## 扩展开发

### 添加新的测试

1. 在 `test/api/` 目录下创建新的测试文件
2. 继承测试基类或直接编写测试函数
3. 使用现有的fixtures (test_client, auth_headers)
4. 添加适当的pytest标记

### 自定义fixtures

在 `test/conftest.py` 中添加新的fixtures：

```python
@pytest_asyncio.fixture
async def custom_fixture():
    # 初始化资源
    yield resource
    # 清理资源
```

## 持续集成

测试脚本可以轻松集成到CI/CD流水线：

```yaml
# GitHub Actions示例
- name: Run API Tests
  run: |
    cp test/.env.test.example test/.env.test
    ./test/run_tests.sh all
```

## 性能考虑

- 会话级别的HTTP客户端复用
- 异步并发执行
- 智能跳过不可用的测试
- 最小化资源占用