import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readRequirementFile } from './requirementFile.ts'

test('文件导入保留中文和换行，兼容 BOM，拒绝无效输入', async () => {
  const source = '# 登录需求\r\n\r\n正确密码返回 200。\n保留结尾空白  \n'
  for (const name of ['需求.md', '需求.TXT']) {
    assert.equal(await readRequirementFile(new File(['\uFEFF', source], name)), source)
  }
  assert.equal(await readRequirementFile(new File(['中'.repeat(16000)], '边界.txt')), '中'.repeat(16000))
  assert.equal(Array.from(await readRequirementFile(new File(['😀'.repeat(16000)], '边界.md'))).length, 16000)
  for (const [file, message] of [
    [new File(['正文'], '需求.docx'), /\.md/],
    [new File(['\uFEFF \r\n\t'], '空白.txt'), /空白/],
    [new File([new Uint8Array([0xff, 0xfe, 0x61])], '错误编码.txt'), /UTF-8/],
    [new File(['中'.repeat(16001)], '超长.md'), /16000/],
    [new File(['a'.repeat(64004)], '超大.txt'), /16000/],
  ]) {
    await assert.rejects(readRequirementFile(file), message)
  }
  const unreadable = new File(['正文'], '不可读.txt')
  unreadable.arrayBuffer = async () => { throw new Error('read failed') }
  await assert.rejects(readRequirementFile(unreadable), /读取失败/)
})
