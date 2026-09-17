# syntax=docker/dockerfile:1
#
# Frontend (Vite/React SPA) staging/production image:
#   docker build -t <registry>/knowdown-frontend:dev .
#
# Stage 1 compiles the SPA to static assets; stage 2 serves them with an
# unprivileged nginx that also reverse-proxies /api, /ws and /media to the
# backend (same-origin, so the browser never makes a cross-origin call —
# matches the dev Vite proxy in vite.config.ts).
#
# Unlike rpool's frontend image, there is no config/environments/<APP_ENV>.yml
# layer to bake in here — knowdown's frontend takes its build-time
# configuration straight from VITE_-prefixed env vars (see .env.example), none
# of which are required for a working build.

########################  build  ########################
FROM node:22-slim AS build
WORKDIR /app

# Deterministic install from the lockfile, cached until manifests change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# tsc -b && vite build -> /app/dist
RUN npm run build

########################  serve  ########################
# nginx-unprivileged already runs as non-root (uid 101) and reads templates from
# /etc/nginx/templates, running envsubst over them at container start — that's
# how ${BACKEND_URL}/${REALTIME_URL} reach the config without baking a hostname
# into the image.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# Backend/realtime Services the proxies target; overridable per environment.
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 makes the base image populate
# ${NGINX_LOCAL_RESOLVERS} from /etc/resolv.conf (the cluster DNS) for the
# per-request resolver in nginx.conf.template.
ENV BACKEND_URL=http://backend \
    REALTIME_URL=http://realtime \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
EXPOSE 3000
