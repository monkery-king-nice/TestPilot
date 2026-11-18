// 通过 CDP 转储渲染后的页面文本，用于验证 SPA 渲染结果。
// 用法：node scripts/dump-text.mjs <url> <等待文本>
import { spawn } from 'node:child_process'

const EDGE = process.env.EDGE_PATH || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const URL = process.argv[2]
const WAIT = process.argv[3] || 'PASS'
const PORT = 10400 + Math.floor(Math.random() * 500)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function getWsUrl() {
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/list`)
      const list = await res.json()
      const page = list.find((t) => t.type === 'page')
      if (page) return page.webSocketDebuggerUrl
    } catch {}
    await sleep(200)
  }
  throw new Error('CDP not reachable')
}

async function main() {
  const proc = spawn(EDGE, [`--remote-debugging-port=${PORT}`, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--window-size=1440,2000', 'about:blank'], { stdio: 'ignore' })
  try {
    const ws = new WebSocket(await getWsUrl())
    let id = 0
    const pending = new Map()
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const i = ++id
      pending.set(i, { resolve, reject })
      ws.send(JSON.stringify({ id: i, method, params }))
    })
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data)
      if (m.id && pending.has(m.id)) {
        const { resolve, reject } = pending.get(m.id)
        pending.delete(m.id)
        m.error ? reject(new Error(m.error.message)) : resolve(m.result)
      }
    }
    await new Promise((r) => (ws.onopen = r))
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Page.navigate', { url: URL })
    for (let i = 0; i < 40; i++) {
      await sleep(500)
      const r = await send('Runtime.evaluate', { expression: `!!document.body && document.body.innerText.includes(${JSON.stringify(WAIT)})`, returnByValue: true })
      if (r.result.value === true) break
    }
    await sleep(500)
    const r = await send('Runtime.evaluate', { expression: 'document.body.innerText', returnByValue: true })
    console.log(r.result.value)
    ws.close()
  } finally {
    proc.kill()
  }
}

main().catch((e) => { console.error(e); process.exit(1) })
