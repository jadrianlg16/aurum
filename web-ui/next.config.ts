import path from 'node:path';
import type { NextConfig } from 'next';

/**
 * Static export: every page is client-rendered and talks to the Aurum API over HTTP, so
 * nothing needs a Node runtime. `next build` writes `out/`, which the nginx image in
 * ./Dockerfile serves while proxying /api to the API container.
 *
 * `trailingSlash: true` makes every route a directory with its own index.html, which is what
 * a dumb static file server needs to resolve /taxes without rewrite rules.
 */
const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  // This app is its own npm workspace inside a Python repo; pin the tracing root so Next does
  // not walk up and pick a lockfile from elsewhere on the host.
  outputFileTracingRoot: path.resolve(process.cwd()),
  images: { unoptimized: true },
  env: {
    NEXT_PUBLIC_MOCK: process.env.NEXT_PUBLIC_MOCK ?? '0',
  },
};

export default nextConfig;
