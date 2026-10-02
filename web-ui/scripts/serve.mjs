#!/usr/bin/env node
/**
 * `npm run serve` - a dependency-free static file server for `out/`, used to verify a build
 * without Docker and without pulling `serve` from the network.
 *
 * The export uses `trailingSlash: true`, so every route is a directory with its own
 * index.html; this server resolves `/taxes` and `/taxes/` to `out/taxes/index.html` and
 * returns a real 404 for anything else - no SPA fallback that would turn a typo into 200.
 *
 * Config: PORT (default 3000) and DIR (default ./out). Nothing machine-specific.
 */
import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';

const PORT = Number(process.env.PORT ?? 3000);
const ROOT = path.resolve(process.env.DIR ?? 'out');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.woff2': 'font/woff2',
};

const server = createServer((req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost');
  const rel = decodeURIComponent(url.pathname).replace(/^\/+/, '');
  const target = path.resolve(ROOT, rel);
  if (!target.startsWith(ROOT)) {
    res.writeHead(403).end('forbidden');
    return;
  }

  let file = target;
  if (!existsSync(file) || statSync(file).isDirectory()) {
    const candidate = path.join(file, 'index.html');
    if (existsSync(candidate)) file = candidate;
    else if (existsSync(`${target}.html`)) file = `${target}.html`;
    else {
      res.writeHead(404, { 'Content-Type': 'text/plain' }).end('not found');
      return;
    }
  }

  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
  createReadStream(file).pipe(res);
});

server.listen(PORT, () => console.log(`serving ${ROOT} on http://localhost:${PORT}`));
