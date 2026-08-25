#!/usr/bin/env node

/**
 * Minimal HTTP server for local review of the living document.
 * Serves the public/ directory on http://localhost:8080
 */

import { createServer } from 'node:http';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { resolve, extname } from 'node:path';

const PORT = parseInt(process.env.PORT || '8080', 10);
const ROOT = new URL('./public', import.meta.url).pathname;

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.webmanifest': 'application/manifest+json',
  '.md': 'text/markdown; charset=utf-8',
};

function serveFile(res, filePath) {
  try {
    const ext = extname(filePath).toLowerCase();
    const mime = MIME_TYPES[ext] || 'application/octet-stream';
    const content = readFileSync(filePath);
    res.writeHead(200, { 'Content-Type': mime });
    res.end(content);
  } catch (err) {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not found');
  }
}

const server = createServer((req, res) => {
  let path = req.url.split('?')[0];
  if (path === '/') path = '/index.html';
  
  const filePath = resolve(ROOT, '.' + path);
  
  // Security: ensure file is within public/
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }
  
  // Serve .md files for direct access too
  serveFile(res, filePath);
});

server.listen(PORT, () => {
  console.log(`\n  📖 Echo-Node Living Document`);
  console.log(`  ───────────────────────────`);
  console.log(`  Local:  http://localhost:${PORT}\n`);
});
