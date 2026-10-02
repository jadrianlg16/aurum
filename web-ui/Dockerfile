# web-ui - Next.js 15 App Router, built as a **static export** and served by nginx.
#
# Static, not `output: 'standalone'`: nothing in this UI needs a Node runtime. Every page is
# client-rendered and talks to the Aurum API over HTTP, so `next build` writes `out/`, which any
# file server can host. This image is the compose option; the `export` stage is what to copy out
# if something else should serve the files.
#
# Build args / env: see docs/modules/web-ui.md.

# --------------------------------------------------------------------- build
FROM node:20-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Baked into the bundle at build time because the browser is what calls it. `/api` (same origin)
# is right for the compose deployment: nginx below proxies /api to ${API_URL}.
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Documented on the Tools screen; the browser never calls the MCP server itself.
ARG NEXT_PUBLIC_MCP_PORT=5042
ENV NEXT_PUBLIC_MCP_PORT=$NEXT_PUBLIC_MCP_PORT

# Never 1 in an image you deploy - it swaps the real API for the in-browser fake.
ARG NEXT_PUBLIC_MOCK=0
ENV NEXT_PUBLIC_MOCK=$NEXT_PUBLIC_MOCK

COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts || npm install --ignore-scripts
COPY . .
RUN npm run build

# -------------------------------------------------------------------- export
# Nothing but the static site:
#   docker build --target export -o type=local,dest=./web-out ./web-ui
FROM scratch AS export
COPY --from=build /app/out /

# ----------------------------------------------------------------------- run
FROM nginx:alpine AS run

# Consumed by the official image's envsubst-on-templates entrypoint.
ENV WEB_PORT=8080
ENV API_URL=http://api:5041
# Upload cap in MB; nginx and the API enforce the same value (compose passes it to both).
ENV AURUM_MAX_UPLOAD_MB=25

# DNS server for the lazy upstream lookup in the /api/ proxy. Left unset on purpose: the
# entrypoint snippet below defaults it to the resolver the container was actually given.
# ENV DNS_RESOLVER=

COPY docker-resolver.envsh /docker-entrypoint.d/18-aurum-resolver.envsh
RUN chmod +x /docker-entrypoint.d/18-aurum-resolver.envsh
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/out /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null "http://127.0.0.1:${WEB_PORT}/" || exit 1
