// Run against the real API and VITE_USE_MOCK=false. Requires playwright-core and Edge.
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require('playwright-core')

async function main() {
  const base = process.env.FRONTEND_URL || 'http://127.0.0.1:5178'
  const output = path.resolve(process.env.EVIDENCE_DIR || 'artifacts/requirement-import')
  await fs.mkdir(output, { recursive: true })
  const browser = await chromium.launch({
    executablePath: process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true,
  })
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
    const projectResponse = await page.request.post(`${base}/api/projects`, {
      data: { name: '第二阶段文件导入独立验收' },
    })
    assert.equal(projectResponse.status(), 201)
    const project = await projectResponse.json()
    const api = `${base}/api/projects/${project.id}/requirements`
    const writes = []
    const models = []
    page.on('request', request => {
      if (request.url().includes('/requirements') && request.method() !== 'GET') writes.push(request.url())
      if (request.url().includes('/agent/')) models.push(request.url())
    })
    await page.goto(`${base}/projects/${project.id}/requirements`)
    await page.getByRole('button', { name: '从文件导入', exact: true }).waitFor()
    const input = page.locator('input[type=file]')
    const editor = page.getByRole('textbox', { name: '需求原文', exact: true })
    const save = page.getByRole('button', { name: '保存需求', exact: true })
    const importFile = (name, buffer) => input.setInputFiles({ name, mimeType: 'text/plain', buffer })
    const md = '# 登录需求\n\n正确密码登录返回 200。\n错误密码返回 401。\n'
    await importFile('登录需求.md', Buffer.from('\uFEFF' + md))
    await page.waitForFunction(() => document.querySelector('textarea')?.value.includes('# 登录需求'))
    assert.equal(await editor.inputValue(), md)
    assert.equal(writes.length, 0)
    assert.equal(models.length, 0)
    assert.deepEqual(await (await page.request.get(api)).json(), [])
    await page.screenshot({ path: path.join(output, '01-markdown-preview.png'), fullPage: true })
    const edited = md + '查询本人信息返回用户编号。\n'
    await editor.fill(edited)
    await save.click()
    await page.getByText('已保存版本 v1', { exact: true }).waitFor()
    await page.reload()
    await page.getByText('已保存版本 v1', { exact: true }).waitFor()
    assert.equal(await editor.inputValue(), edited)
    const first = (await (await page.request.get(api)).json())[0]
    assert.equal(first.text, edited)
    assert.equal(first.version, 1)

    const txt = '登录需求修订\r\n\r\n正确密码返回 200。\r\n错误密码返回 401，提示凭证错误。  \r\n'
    await editor.fill('尚未保存的原稿')
    await importFile('修订需求.txt', Buffer.from(txt))
    await page.getByRole('button', { name: '保留原稿', exact: true }).click()
    assert.equal(await editor.inputValue(), '尚未保存的原稿')
    const writesBefore = writes.length
    await importFile('修订需求.txt', Buffer.from(txt))
    await page.getByRole('button', { name: '替换内容', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('textarea')?.value.startsWith('登录需求修订'))
    assert.equal(writes.length, writesBefore)
    assert.equal(models.length, 0)
    await save.click()
    await page.getByText('已保存版本 v2', { exact: true }).waitFor()
    await page.reload()
    await page.getByText('已保存版本 v2', { exact: true }).waitFor()
    const second = (await (await page.request.get(api)).json())[0]
    assert.equal(second.id, first.id)
    assert.equal(second.text, txt)
    assert.equal(second.version, 2)
    await page.screenshot({ path: path.join(output, '02-txt-saved-v2.png'), fullPage: true })

    const original = await editor.inputValue()
    for (const [name, bytes, message] of [
      ['格式.docx', Buffer.from('正文'), '.md 或 .txt'],
      ['空白.txt', Buffer.from('\uFEFF\n \t'), '不能为空或只有空白'],
      ['错误编码.txt', Buffer.from([0xff, 0xfe]), 'UTF-8 编码'],
      ['超长.md', Buffer.from('中'.repeat(16001)), '16000 字符'],
    ]) {
      await importFile(name, bytes)
      await page.getByRole('alert').filter({ hasText: message }).waitFor()
      assert.equal(await editor.inputValue(), original)
    }
    assert.equal(models.length, 0)
    assert.equal(writes.length, 2)
    await page.screenshot({ path: path.join(output, '03-invalid-preserves-source.png'), fullPage: true })
    await fs.writeFile(path.join(output, 'handoff.json'), JSON.stringify({
      mode: 'real API / SQLite, VITE_USE_MOCK=false',
      model: 'not called', date: new Date().toISOString(),
      project_id: project.id, requirement_id: first.id,
      versions: [{ version: first.version, text: first.text }, { version: second.version, text: second.text }],
      checks: ['MD BOM preview and edit', 'manual save and refresh v1', 'cancel and confirm replacement',
        'TXT CRLF manual save and refresh v2', 'invalid input preserves draft', 'no automatic save or model request'],
    }, null, 2))
    console.log('PASS: real API file import, manual save/refresh v1→v2, replacement protection and invalid files')
  } finally {
    await browser.close()
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
