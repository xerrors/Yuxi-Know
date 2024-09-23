# 使用 Node.js 作为基础镜像，用于构建前端
FROM node:latest AS build-stage
WORKDIR /app

# 将 package.json 和 package-lock.json 复制到工作目录
COPY ./package*.json ./

# 安装依赖
RUN npm install

# 复制前端源代码并运行构建
COPY . .
RUN npm run build

# 使用 Nginx 作为生产镜像
FROM nginx:alpine AS production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html

# 复制 Nginx 配置文件
COPY ../nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
