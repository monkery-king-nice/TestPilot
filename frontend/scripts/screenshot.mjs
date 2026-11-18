// 通过 Chrome DevTools Protocol 对本地 SPA 页面做全页截图（可靠等待渲染完成）。
// 用法：node scripts/screenshot.mjs <url> <输出png> [等待出现的文本]
// 依赖：Node >= 22（内置 fetch / WebSocket），系统安装 Edge。
import { spawn } from 'node:child_process'
import { writeFileSync } from 'node:fs'

const EDGE = process.env.EDGE_PATH || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const URL = process.argv[2]
const OUT = process.argv[3]
const WAIT_TEXT = process.argv[4] || 'PASS'
const PORT = 9333 + Math.floor(Math.random() * 500)

if (!URL || !OUT) {
  console.error('usage: node scripts/screenshot.mjs <url> <out.png> [waitText]')
  process.exit(2)
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function getWsUrl() {
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/list`)
      const list = await res.json()
      const page = list.find((t) => t.type === 'page')
      if (page) return page.webSocketDebuggerUrl
    } catch {
      /* not ready yet */
    }
    await sleep(200)
  }
  throw new Error('CDP endpoint not reachable')
}

async function main() {
  const proc = spawn(
    EDGE,
    [
      `--remote-debugging-port=${PORT}`,
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--hide-scrollbars',
      '--window-size=1440,1600',
      'about:blank'
    ],
    { stdio: 'ignore' }
  )

  try {
    const wsUrl = await getWsUrl()
    const ws = new WebSocket(wsUrl)
    let id = 0
    const pending = new Map()

    const send = (method, params = {}) =>
      new Promise((resolve, reject) => {
        const msgId = ++id
        pending.set(msgId, { resolve, reject })
        ws.send(JSON.stringify({ id: msgId, method, params }))
      })

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.id && pending.has(msg.id)) {
        const { resolve, reject } = pending.get(msg.id)
        pending.delete(msg.id)
        if (msg.error) reject(new Error(msg.error.message))
        else resolve(msg.result)
      }
    }

    await new Promise((r) => (ws.onopen = r))
    await send('Page.enable')
    await send('Runtime.enable')
    await send('Emulation.setDeviceMetricsOverride', {
      width: 1440,
      height: 1600,
      deviceScaleFactor: 1,
      mobile: false
    })
    await send('Page.navigate', { url: URL })

    // 等待目标文本出现（最多 20s）
    let rendered = false
    for (let i = 0; i < 40; i++) {
      await sleep(500)
      try {
        const r = await send('Runtime.evaluate', {
          expression: `!!document.body && document.body.innerText.includes(${JSON.stringify(WAIT_TEXT)})`,
          returnByValue: true
        })
        if (r.result.value === true) {
          rendered = true
          break
        }
      } catch {
        /* retry */
      }
    }
    await sleep(600)

    // 全页高度
    const metrics = await send('Runtime.evaluate', {
      expression: `({h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth})`,
      returnByValue: true
    })
    const pageH = Math.max(Number(metrics.result.value?.h) || 1600, 1600)
    const pageW = Math.max(Number(metrics.result.value?.w) || 1440, 1440)

    await send('Emulation.setDeviceMetricsOverride', {
      width: pageW,
      height: pageH,
      deviceScaleFactor: 1,
      mobile: false
    })
    await sleep(400)

    const shot = await send('Page.captureScreenshot', {
      format: 'png',
      captureBeyondViewport: true
    })
    writeFileSync(OUT, Buffer.from(shot.data, 'base64'))
    console.log(
      `rendered=${rendered} page=${pageW}x${pageH} saved=${OUT} bytes=${Buffer.byteLength(shot.data, 'base64')}`
    )
    ws.close()
  } finally {
    proc.kill()
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
