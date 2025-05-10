# 开发阶段
FROM node:latest AS development
WORKDIR /app

# 复制 package.json 和 package-lock.json（如果存在）
COPY ./web/package*.json ./

# 安装依赖
RUN npm install -g pnpm@latest-10
RUN pnpm install
# RUN npm install --registry http://mirrors.cloud.tencent.com/npm/ --verbose --force

# 复制源代码
COPY ./web .

# 暴露端口
EXPOSE 5173

# 启动开发服务器的命令在 docker-compose 文件中定义

# 生产阶段
FROM node:latest AS build-stage
WORKDIR /app

COPY ./web/package*.json ./
RUN npm install --force
# RUN npm install --registry https://registry.npmmirror.com --force

COPY ./web .
RUN npm run build

# 生产环境运行阶段
FROM nginx:alpine AS production
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY ./docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY ./docker/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]