#docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:20-slim
#docker tag  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:20-slim  docker.io/node:20-slim

#docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slimim
#docker tag  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim  docker.io/python:3.12-slim

#docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:20-alpine
#docker tag  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:20-alpine  docker.io/node:20-alpine

#docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/ghcr.io/astral-sh/uv:0.7.2
#docker tag  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/ghcr.io/astral-sh/uv:0.7.2  ghcr.io/astral-sh/uv:0.7.2

#docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/nginx:alpine
#docker tag  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/nginx:alpine  docker.io/nginx:alpine

#docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/neo4j:5.26
#docker tag  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/neo4j:5.26  docker.io/neo4j:5.26

# docker.m.daocloud.io/vllm/vllm-openai:v0.10.1.1

# docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/minio/minio:RELEASE.2023-03-20T20-16-18Z
# swr.cn-north-4.myhuaweicloud.com/ddn-k8s/quay.io/coreos/etcd:v3.5.5
# swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/milvusdb/milvus:v2.5.6
# swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/postgres:16
# swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/redis:7.0-alpine
# paddlex:latest
#!/bin/bash

# Yuxi-Know Initialization Script for Bash/Linux/macOS
# This script helps set up the environment for the Yuxi-Know project

set -e

echo "🚀 Initializing Yuxi-Know project..."
echo "=================================="

# Check if .env file exists
if [ -f ".env" ]; then
    echo "✅ .env file already exists. Skipping environment setup."
else
    echo "📝 .env file not found. Let's set up your environment variables."
    echo ""

    # Get SILICONFLOW_API_KEY
    echo "🔑 SiliconFlow API Key required"
    echo "Get your API key from: https://cloud.siliconflow.cn/i/Eo5yTHGJ"
    while true; do
        read -s -p "Please enter your SILICONFLOW_API_KEY: " SILICONFLOW_API_KEY
        echo ""
        if [ -z "$SILICONFLOW_API_KEY" ]; then
            echo "❌ API Key cannot be empty. Please try again."
        else
            break
        fi
    done

    # Get TAVILY_API_KEY (optional)
    echo ""
    echo "🔍 Tavily API Key (optional) - for search service"
    echo "Get your API key from: https://app.tavily.com/"
    read -p "Please enter your TAVILY_API_KEY (press Enter to skip): " TAVILY_API_KEY

    # Create .env file
    cat > .env << EOF
# SiliconFlow API Key (required)
SILICONFLOW_API_KEY=${SILICONFLOW_API_KEY}

# Tavily API Key (optional - for search service)
EOF

    if [ -n "$TAVILY_API_KEY" ]; then
        echo "TAVILY_API_KEY=${TAVILY_API_KEY}" >> .env
    fi

    echo "✅ .env file created successfully!"
fi

echo ""
echo "📦 Pulling Docker images..."
echo "========================="

# List of Docker images to pull
images=(
    "python:3.12-slim"
    "node:20-slim"
    "node:20-alpine"
    "milvusdb/milvus:v2.5.6"
    "neo4j:5.26"
    "minio/minio:RELEASE.2023-03-20T20-16-18Z"
    "ghcr.io/astral-sh/uv:0.7.2"
    "nginx:alpine"
    "quay.io/coreos/etcd:v3.5.5"
    "postgres:16"
)

# Pull each image
for image in "${images[@]}"; do
    echo "🔄 Pulling ${image}..."
    if bash docker/pull_image.sh "$image"; then
        echo "✅ Successfully pulled ${image}"
    else
        echo "❌ Failed to pull ${image}"
        exit 1
    fi
done

echo ""
echo "🎉 Initialization complete!"
echo "=========================="
echo "You can now run: docker compose up -d --build"
echo "This will start all services in development mode with hot-reload enabled."