# ---- Stage 1: Build ----
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (layer cache optimization)
COPY frontend/package.json ./
RUN npm install

# Copy source and build
COPY frontend/ ./

# Build args become VITE_ env vars at build time
ARG VITE_GATEWAY_WS_URL=ws://localhost:8080/ws
ARG VITE_GATEWAY_HTTP_URL=http://localhost:8080
ENV VITE_GATEWAY_WS_URL=$VITE_GATEWAY_WS_URL
ENV VITE_GATEWAY_HTTP_URL=$VITE_GATEWAY_HTTP_URL

RUN npm run build

# ---- Stage 2: Serve ----
FROM nginx:alpine AS runtime

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
COPY infrastructure/docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
