#!/bin/bash

# Yuxi Initialization Script for Bash/Linux/macOS
# This script helps set up the environment for the Yuxi project

set -e
umask 077

# 环境输入优先于文件；无人值守必须显式选择，避免 EOF 被当成用户回答。
env_file="${YUXI_ENV_FILE:-.env}"
non_interactive="${YUXI_INIT_NON_INTERACTIVE:-0}"
skip_images="${YUXI_INIT_SKIP_IMAGES:-0}"
compose_file=docker-compose.yml

fail() {
    echo "$*" >&2
    exit 1
}

prompt_value() {
    local name="$1"
    local prompt="$2"
    [ "$non_interactive" = 0 ] && [ -t 0 ] || fail "Set ${name} through the environment or ${env_file}; interactive input is unavailable."
    read -r -s -p "$prompt: " PROMPT_VALUE || fail "Could not read ${name}."
    echo ""
}

generate_hex() {
    local length="$1"
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "$length"
    else
        tr -dc 'a-f0-9' < /dev/urandom | head -c $((length * 2))
    fi
}

set_env_value() {
    local name="$1"
    local value="$2"

    # Compose 双引号内转义反斜杠、双引号和美元符，拒绝换行以防配置注入。
    case "$value" in
        *$'\n'*|*$'\r'*) fail "${name} must be a single-line value." ;;
    esac
    case "$value" in
        *[\$\#\ \"\'\\]*)
            value="${value//\\/\\\\}"
            value="${value//\"/\\\"}"
            value="${value//\$/\$\$}"
            value="\"${value}\""
            ;;
    esac
    if grep -Eq "^${name}=" "$env_file"; then
        ENV_VALUE="$value" awk -v name="$name" '
            $0 ~ "^" name "=" {
                if (!updated) {
                    print name "=" ENVIRON["ENV_VALUE"]
                    updated = 1
                }
                next
            }
            { print }
        ' "$env_file" > "${env_file}.tmp"
        mv "${env_file}.tmp" "$env_file"
    else
        printf '\n%s=%s\n' "$name" "$value" >> "$env_file"
    fi
}

get_env_value() {
    local name="$1"
    local value
    value=$(awk -v name="$name" '
        index($0, name "=") == 1 && !found {
            print substr($0, length(name) + 2)
            found = 1
        }
    ' "$env_file")
    if [[ "$value" == \'* || "$value" == \"* ]]; then
        local quote="${value:0:1}" decoded="" char next closed=0
        value="${value:1}"
        while [ -n "$value" ]; do
            char="${value:0:1}"
            value="${value:1}"
            if [ "$char" = "$quote" ]; then
                closed=1
                break
            fi
            next="${value:0:1}"
            if [ "$char" = '\' ] && { [ "$next" = "$quote" ] || { [ "$quote" = '"' ] && [ "$next" = '\' ]; }; }; then
                char="$next"
                value="${value:1}"
            fi
            decoded+="$char"
        done
        [ "$closed" = 1 ] || fail "${name} has an unterminated quote in ${env_file}."
        value=$(trim_whitespace "$value")
        [[ -z "$value" || "$value" == \#* ]] || fail "${name} has unexpected text after its quote in ${env_file}."
        if [ "$quote" = '"' ]; then
            decoded="${decoded//\$\$/\$}"
        fi
        value="$decoded"
    elif [[ "$value" == *' #'* ]]; then
        value="${value%% #*}"
        value=$(trim_whitespace "$value")
    fi
    printf '%s' "$value"
}

trim_whitespace() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

security_secret_is_valid() {
    local value="$1"
    shift
    local trimmed
    trimmed=$(trim_whitespace "$value")
    if [ "$value" != "$trimmed" ] || [ "${#value}" -lt 32 ]; then
        return 1
    fi
    case "$value" in
        \"*|*\"|\'*|*\') return 1 ;;
    esac
    local other
    for other in "$@"; do
        if [ -n "$other" ] && [ "$value" = "$other" ]; then
            return 1
        fi
    done
}

read_security_secret() {
    local name="$1"
    shift
    local value
    while true; do
        prompt_value "$name" "Please enter your ${name} (press Enter to auto-generate)"
        value="$PROMPT_VALUE"
        if [ -z "$value" ]; then
            value=$(generate_hex 32)
            echo "Generated ${name} for ${env_file}."
        fi
        if security_secret_is_valid "$value" "$@"; then
            SECURITY_SECRET_VALUE="$value"
            return
        fi
        echo "❌ ${name} must contain at least 32 non-whitespace characters and must not reuse another security secret."
    done
}

ensure_security_secret() {
    local name="$1"
    shift
    local current
    current=$(get_env_value "$name")
    local other_values=()
    local other_name
    for other_name in "$@"; do
        other_values+=("$(get_env_value "$other_name")")
    done
    if security_secret_is_valid "$current" "${other_values[@]}"; then
        return
    fi

    if [ "$non_interactive" = 1 ]; then
        [ -z "$current" ] || fail "${name} is invalid in ${env_file}; refusing to rotate an existing secret."
        set_env_value "$name" "$(generate_hex 32)"
        return
    fi
    echo "${name} is missing, too short, or reuses another security secret in ${env_file}."
    read_security_secret "$name" "${other_values[@]}"
    set_env_value "$name" "$SECURITY_SECRET_VALUE"
}

validate_security_env() {
    local jwt_secret api_key_secret
    jwt_secret=$(get_env_value "JWT_SECRET_KEY")
    api_key_secret=$(get_env_value "API_KEY_DERIVATION_SECRET")

    security_secret_is_valid "$jwt_secret" || {
        echo "JWT_SECRET_KEY must contain at least 32 non-whitespace characters." >&2
        return 1
    }
    security_secret_is_valid "$api_key_secret" "$jwt_secret" || {
        echo "API_KEY_DERIVATION_SECRET must be at least 32 characters and independent from JWT_SECRET_KEY." >&2
        return 1
    }
}

ensure_required_value() {
    local name="$1"
    local value
    value=$(get_env_value "$name")
    while [ -z "$value" ]; do
        prompt_value "$name" "Please enter your ${name}"
        value="$PROMPT_VALUE"
        set_env_value "$name" "$value"
    done
}

if [ "${1:-}" = "--validate-security-env" ]; then
    [ -f "$env_file" ] || fail "${env_file} does not exist"
    validate_security_env
    exit 0
fi
[ $# -eq 0 ] || fail "Unknown argument: $1"
case "$non_interactive:$skip_images" in
    0:0|0:1|1:0|1:1) ;;
    *) fail "YUXI_INIT_NON_INTERACTIVE and YUXI_INIT_SKIP_IMAGES must be 0 or 1." ;;
esac

skip_existing_image() {
    local image="$1"

    if ! docker image inspect "$image" >/dev/null 2>&1; then
        return 1
    fi

    echo "⏭️  ${image} already exists. Skipping pull."
    return 0
}

echo "🚀 Initializing Yuxi project..."
echo "=================================="

if [ ! -f "$env_file" ]; then
    touch "$env_file"
fi
chmod 600 "$env_file"

# 只接收初始化拥有的输入，不把宿主全部环境或开发配置复制进新部署。
for name in SILICONFLOW_API_KEY WEB_SEARCH_PROVIDER DOUBAO_SEARCH_API_KEY TAVILY_API_KEY DEEPSEEK_API_KEY \
    JWT_SECRET_KEY API_KEY_DERIVATION_SECRET YUXI_INSTANCE_ID YUXI_ENV \
    POSTGRES_PASSWORD NEO4J_PASSWORD MINIO_ACCESS_KEY MINIO_SECRET_KEY \
    CUBE_API_URL CUBE_API_KEY CUBE_PROXY_NODE_IP CUBE_PROXY_PORT_HTTP CUBE_TEMPLATE_ID \
    CUBE_NODE_USER_DATA_DIR CUBE_NODE_SKILL_PROJECTION_DIR COMPOSE_PROJECT_NAME YUXI_STATE_DIR YUXI_FRONTEND_PORT; do
    if [ "${!name+x}" = x ]; then
        case "$name" in
            JWT_SECRET_KEY|API_KEY_DERIVATION_SECRET)
                security_secret_is_valid "${!name}" || fail "${name} must be at least 32 characters without surrounding whitespace or quotes."
                ;;
        esac
        set_env_value "$name" "${!name}"
    fi
done

ensure_required_value SILICONFLOW_API_KEY
provider=$(get_env_value WEB_SEARCH_PROVIDER)
provider="${provider#"${provider%%[![:space:]]*}"}"
provider="${provider%"${provider##*[![:space:]]}"}"
provider=$(printf '%s' "$provider" | tr '[:upper:]' '[:lower:]')
case "$provider" in
    ""|tavily|deepseek|doubao) ;;
    *) fail "WEB_SEARCH_PROVIDER must be tavily, deepseek, or doubao." ;;
esac
echo "🔍 Configure Search and Fetch after login in Settings → 网络搜索 (environment keys are also supported)."

# 先检查已有的非空值，避免无人值守时轮换持久密钥。
ensure_security_secret JWT_SECRET_KEY
ensure_security_secret API_KEY_DERIVATION_SECRET JWT_SECRET_KEY
validate_security_env
if [ -z "$(get_env_value YUXI_INSTANCE_ID)" ]; then
    if [ "$non_interactive" = 1 ]; then
        instance="instance-$(generate_hex 8)"
    else
        prompt_value YUXI_INSTANCE_ID "YUXI_INSTANCE_ID (Enter to auto-generate)"
        instance="${PROMPT_VALUE:-instance-$(generate_hex 8)}"
    fi
    set_env_value YUXI_INSTANCE_ID "$instance"
fi

if [ "$(get_env_value YUXI_ENV)" = production ]; then
    compose_file=docker-compose.prod.yml
    for name in POSTGRES_PASSWORD NEO4J_PASSWORD MINIO_ACCESS_KEY MINIO_SECRET_KEY; do
        if [ -z "$(get_env_value "$name")" ]; then
            set_env_value "$name" "$(generate_hex 32)"
        fi
    done
    for name in CUBE_API_URL CUBE_PROXY_NODE_IP CUBE_NODE_USER_DATA_DIR CUBE_NODE_SKILL_PROJECTION_DIR; do
        ensure_required_value "$name"
    done
fi

echo "✅ Configuration saved to ${env_file}."
if [ "$skip_images" = 1 ]; then
    echo "Image preparation skipped (YUXI_INIT_SKIP_IMAGES=1)."
    exit 0
fi

echo ""
echo "📦 Pulling Docker images..."
echo "========================="

# List of Docker images to pull
images=(
    "alpine:3.20"
    "python:3.13-slim"
    "node:24-slim"
    "node:24-alpine"
    "milvusdb/milvus:v3.0.2"
    "neo4j:5.26.29"
    "ghcr.io/astral-sh/uv:0.12.6"
    "nginx:alpine"
    "quay.io/coreos/etcd:v3.5.25"
    "postgres:16"
    "redis:7.4.10-alpine"
)

# Pull each image
for image in "${images[@]}"; do
    if skip_existing_image "$image"; then
        continue
    fi

    echo "🔄 Pulling ${image}..."
    if bash scripts/pull_image.sh "$image"; then
        echo "✅ Successfully pulled ${image}"
    else
        echo "❌ Failed to pull ${image}"
        exit 1
    fi
done

# MinIO 官方镜像已全面下架，改为从仓库内 Dockerfile 构建
echo "🔄 Building minio and storage-init images..."
if YUXI_ENV_FILE="$env_file" docker compose --env-file "$env_file" -f "$compose_file" build minio storage-init; then
    echo "✅ Successfully built minio and storage-init images"
else
    echo "❌ Failed to build minio or storage-init image"
    exit 1
fi


echo ""
echo "🎉 Initialization complete!"
echo "=========================="
echo "Use ${env_file} with ${compose_file}; see docs/advanced/deployment.md for production startup."
if [ "$compose_file" = docker-compose.yml ]; then
    echo "Backend code changes require an explicit service restart; frontend hot-reload remains enabled."
fi
