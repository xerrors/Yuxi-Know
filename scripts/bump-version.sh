#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Yuxi 版本号升级脚本
# =============================================================================
# 用法: ./scripts/bump-version.sh <新版本号>
# 示例: ./scripts/bump-version.sh 0.6.2
#
# 该脚本从 backend/package/pyproject.toml 读取当前版本，
# 自动同步所有需要硬编码版本号的位置。
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 检查参数
if [ $# -ne 1 ]; then
    echo "用法: $0 <新版本号>"
    echo "示例: $0 0.6.2"
    exit 1
fi

NEW_VERSION="$1"

# 验证版本号格式（支持 x.y.z 或 x.y.z.devN）
if [[ ! "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.[a-zA-Z0-9]+)?$ ]]; then
    echo "错误: 版本号格式无效，期望格式如 0.6.2 或 0.6.2.dev1"
    exit 1
fi

# 读取当前版本号（以 backend/package/pyproject.toml 为 SSOT）
PYPROJECT_FILE="${PROJECT_ROOT}/backend/package/pyproject.toml"
if [ ! -f "$PYPROJECT_FILE" ]; then
    echo "错误: 找不到 ${PYPROJECT_FILE}"
    exit 1
fi

CURRENT_VERSION=$(grep -E '^version\s*=\s*"' "$PYPROJECT_FILE" | head -1 | sed -E 's/^version\s*=\s*"([^"]+)".*/\1/')

if [ -z "$CURRENT_VERSION" ]; then
    echo "错误: 无法从 ${PYPROJECT_FILE} 读取当前版本号"
    exit 1
fi

if [ "$CURRENT_VERSION" = "$NEW_VERSION" ]; then
    echo "当前版本已经是 ${NEW_VERSION}，无需更新"
    exit 0
fi

echo "准备将版本号从 ${CURRENT_VERSION} 升级到 ${NEW_VERSION}"
echo "受影响的文件:"
echo "  - backend/package/pyproject.toml"
echo "  - backend/pyproject.toml"
echo "  - web/package.json"
echo "  - docker-compose.yml"
echo "  - docker-compose.prod.yml"
echo "  - backend/uv.lock"
echo "  - README.md"
echo "  - docs/intro/quick-start.md"
echo ""
read -rp "确认继续? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# -----------------------------------------------------------------------------
# 1. 更新 Python 包版本 (backend/package/pyproject.toml)
# -----------------------------------------------------------------------------
echo "→ 更新 backend/package/pyproject.toml"
sed -i -E "s/^version = \"[^\"]+\"/version = \"${NEW_VERSION}\"/" \
    "${PROJECT_ROOT}/backend/package/pyproject.toml"

# -----------------------------------------------------------------------------
# 2. 更新后端工作区版本 (backend/pyproject.toml)
# -----------------------------------------------------------------------------
echo "→ 更新 backend/pyproject.toml"
sed -i -E "s/^version = \"[^\"]+\"/version = \"${NEW_VERSION}\"/" \
    "${PROJECT_ROOT}/backend/pyproject.toml"

# -----------------------------------------------------------------------------
# 3. 更新前端版本 (web/package.json)
# -----------------------------------------------------------------------------
echo "→ 更新 web/package.json"
sed -i -E "s/\"version\": \"[^\"]+\"/\"version\": \"${NEW_VERSION}\"/" \
    "${PROJECT_ROOT}/web/package.json"

# -----------------------------------------------------------------------------
# 4. 更新 Docker Compose 镜像标签默认值
# -----------------------------------------------------------------------------
echo "→ 更新 docker-compose.yml"
sed -i -E "s/\\\$\{YUXI_VERSION:-[^}]+\}/\${YUXI_VERSION:-${NEW_VERSION}}/g" \
    "${PROJECT_ROOT}/docker-compose.yml"

echo "→ 更新 docker-compose.prod.yml"
sed -i -E "s/\\\$\{YUXI_VERSION:-[^}]+\}/\${YUXI_VERSION:-${NEW_VERSION}}/g" \
    "${PROJECT_ROOT}/docker-compose.prod.yml"

# -----------------------------------------------------------------------------
# 5. 更新 uv.lock 中的项目版本号
# -----------------------------------------------------------------------------
echo "→ 更新 backend/uv.lock"
# yuxi 包版本
sed -i -E "/^name = \"yuxi\"$/{n;s/^version = \"[^\"]+\"/version = \"${NEW_VERSION}\"/;}" \
    "${PROJECT_ROOT}/backend/uv.lock"
# yuxi-workspace 版本
sed -i -E "/^name = \"yuxi-workspace\"$/{n;s/^version = \"[^\"]+\"/version = \"${NEW_VERSION}\"/;}" \
    "${PROJECT_ROOT}/backend/uv.lock"

# -----------------------------------------------------------------------------
# 6. 更新文档中的版本引用
# -----------------------------------------------------------------------------
# 只替换 git clone 命令中的版本标签（确保总是指向最新版本）
# 发布历史记录（如 [2026/04/01] v0.6.1 版本发布）不修改，保持为历史版本记录
echo "→ 更新 README.md"
sed -i -E "s/(git clone --branch v)[0-9]+\.[0-9]+\.[0-9]+/\1${NEW_VERSION}/g" \
    "${PROJECT_ROOT}/README.md"

echo "→ 更新 docs/intro/quick-start.md"
sed -i -E "s/(git clone --branch v)[0-9]+\.[0-9]+\.[0-9]+/\1${NEW_VERSION}/g" \
    "${PROJECT_ROOT}/docs/intro/quick-start.md"

# -----------------------------------------------------------------------------
# 7. 验证
# -----------------------------------------------------------------------------
echo ""
echo "版本号升级完成，验证结果:"
echo ""

echo "  backend/package/pyproject.toml:"
grep -E "^version = \"" "${PROJECT_ROOT}/backend/package/pyproject.toml" | head -1 | sed 's/^/    /'

echo "  backend/pyproject.toml:"
grep -E "^version = \"" "${PROJECT_ROOT}/backend/pyproject.toml" | head -1 | sed 's/^/    /'

echo "  web/package.json:"
grep -E '"version"' "${PROJECT_ROOT}/web/package.json" | head -1 | sed 's/^/    /'

echo "  docker-compose.yml (api):"
grep -E "image: yuxi-api:" "${PROJECT_ROOT}/docker-compose.yml" | head -1 | sed 's/^/    /'

echo "  docker-compose.prod.yml (web):"
grep -E "image: yuxi-web:" "${PROJECT_ROOT}/docker-compose.prod.yml" | head -1 | sed 's/^/    /'

echo ""
echo "后续步骤:"
echo "  1. 检查 git diff 确认修改无误"
echo "  2. 基于 [Roadmap](docs/develop-guides/roadmap.md) 整理后，更新到 docs/develop-guides/changelog.md"
echo "  3. git add . && git commit -m 'chore(release): bump version to ${NEW_VERSION}'"
echo "  4. git tag v${NEW_VERSION}"
echo "  5. git push origin main --tags"
