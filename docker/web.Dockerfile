# 开发阶段
FROM node:20-alpine AS development
WORKDIR /app

ARG http_proxy
ARG https_proxy
ENV TZ=Asia/Shanghai


# 只有当代理变量不为空时才设置代理
RUN if [ -n "$http_proxy" ]; then echo "export http_proxy=$http_proxy" >> /etc/environment; fi
RUN if [ -n "$https_proxy" ]; then echo "export https_proxy=$https_proxy" >> /etc/environment; fi

# 安装 pnpm
RUN npm install -g pnpm@latest

# 复制 package.json 和 pnpm-lock.yaml
COPY ./web/package*.json ./
COPY ./web/pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install

# 复制源代码
COPY ./web .

# 暴露端口
EXPOSE 5173

# 启动开发服务器的命令在 docker-compose 文件中定义

# 生产阶段
FROM node:20-alpine AS build-stage
WORKDIR /app

# 安装 pnpm
RUN npm install -g pnpm@latest

# 复制依赖文件
COPY ./web/package*.json ./
COPY ./web/pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install --frozen-lockfile

# 复制源代码并构建
COPY ./web .
RUN pnpm run build

# 生产环境运行阶段
FROM nginx:alpine AS production
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY ./docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY ./docker/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]