# syntax=docker/dockerfile:1

# Imagem de PRODUCAO do site (Next.js). Contexto de build: apps/web.
#   docker build -t apm-web --build-arg API_PROXY_URL=http://api:8000 apps/web
#
# API_PROXY_URL tem DOIS usos:
#   * em tempo de BUILD o Next grava o destino do rewrite de /api/* (next.config.ts). Em producao quem
#     roteia /api e o proxy reverso (Traefik do Dokploy); o rewrite so e usado se o dominio apontar so
#     para o site. Por isso o padrao e o nome interno do servico da API.
#   * em tempo de EXECUCAO o servidor do site chama a API por ele (sessao, /sso/*): defina a variavel no
#     servico (a mesma URL interna). Nunca use NEXT_PUBLIC_ para isso: o navegador so conhece /api/*.

FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS build
WORKDIR /app
ARG API_PROXY_URL=http://api:8000
ENV API_PROXY_URL=${API_PROXY_URL} NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
# Fica o node_modules completo: o Next le o next.config.ts em tempo de execucao.
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/package.json /app/next.config.ts /app/tsconfig.json ./
USER node
EXPOSE 3000
# `npm start` escuta so em 127.0.0.1 (-H); num contêiner o proxy precisa alcançar a porta.
CMD ["node_modules/.bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]
