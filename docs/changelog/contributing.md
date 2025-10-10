# 参与贡献

感谢所有贡献者的支持！

<a href="https://github.com/xerrors/Yuxi-Know/contributors">
    <img src="https://contributors.nn.ci/api?repo=xerrors/Yuxi-Know" alt="贡献者名单">
</a>

## 如何贡献

### 1. Fork 项目

在 GitHub 上 Fork 本项目到你的账户。

### 2. 创建分支

```bash
git checkout -b feature/amazing-feature
```

### 3. 提交更改

```bash
git commit -m 'feat: Add some amazing feature'
```

### 4. 推送分支

```bash
git push origin feature/amazing-feature
```

### 5. 创建 PR

在 GitHub 上创建 Pull Request，详细描述你的更改内容。

## 开发指南

### 代码规范

- 遵循项目代码规范
- Python 代码使用 `make format` 格式化
- 使用 `make lint` 检查代码质量
- 添加必要的测试用例
- 更新相关文档

### 提交规范

使用清晰的提交信息：

```
feat: 添加新功能
fix: 修复 bug
docs: 更新文档
style: 代码格式调整
refactor: 代码重构
test: 添加测试
chore: 构建过程或辅助工具的变动
```

### 测试要求

::: tip 测试
- `make lint` / `make format` 保持代码整洁
- `cp test/.env.test.example test/.env.test` 配置测试凭据
- `make router-tests` 运行集成路由测试，支持 `PYTEST_ARGS="-k chat_router"`
- `uv run --group test pytest test/api` 可直接运行 pytest（容器内）
:::

<details>
<summary>常用命令</summary>

```bash
# 全量路由测试
make router-tests

# 仅运行知识库相关用例
make router-tests PYTEST_ARGS="-k knowledge_router"

# 不经过 Makefile，直接调用 pytest
uv run --group test pytest test/api -vv
```

</details>

## 许可证

本项目基于 MIT License 开源，贡献的代码将遵循相同的许可证。
