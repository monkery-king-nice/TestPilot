// 极简 SPA 静态服务器：用于本地预览构建产物 frontend/dist，并支持 history 路由回退。
// 用法：node scripts/serve-dist.mjs [端口]  （默认 8090）
// 仅用于本地预览/截图，不用于生产；生产预览也可用 `npm run preview`。
import { createServer } from 'node:http'
import { readFile, stat } from 'node:fs/promises'
import { extname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const ROOT = resolve(__dirname, '..', 'dist')
const PORT = Number(process.argv[2] || 8090)

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2'
}

createServer(async (req, res) => {
  try {
    const urlPath = decodeURIComponent((req.url || '/').split('?')[0])
    let filePath = normalize(join(ROOT, urlPath))
    if (!filePath.startsWith(ROOT)) filePath = join(ROOT, 'index.html')

    let exists = false
    let isDir = false
    try {
      const s = await stat(filePath)
      exists = true
      isDir = s.isDirectory()
    } catch {
      exists = false
    }

    if (!exists || isDir) {
      // SPA 回退：未知路径一律返回 index.html
      filePath = join(ROOT, 'index.html')
    }

    const data = await readFile(filePath)
    res.writeHead(200, { 'Content-Type': MIME[extname(filePath).toLowerCase()] || 'application/octet-stream' })
    res.end(data)
  } catch (e) {
    res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' })
    res.end('server error: ' + String(e))
  }
}).listen(PORT, '127.0.0.1', () => {
  console.log(`SPA server: http://127.0.0.1:${PORT}  (root ${ROOT})`)
})
