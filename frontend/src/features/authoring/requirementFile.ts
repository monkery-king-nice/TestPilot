/** Read source text without normalizing whitespace or line endings. */
export async function readRequirementFile(file: File): Promise<string> {
  if (!/\.(md|txt)$/i.test(file.name)) {
    throw new Error('请选择 .md 或 .txt 文件')
  }
  // 16000 Unicode characters need at most four UTF-8 bytes each, plus a BOM.
  if (file.size > 16000 * 4 + 3) {
    throw new Error('需求原文不能超过 16000 字符')
  }
  let buffer: ArrayBuffer
  try {
    buffer = await file.arrayBuffer()
  } catch {
    throw new Error('文件读取失败，请重新选择文件')
  }
  let text: string
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(buffer)
  } catch {
    throw new Error('文件解码失败，请将文件保存为 UTF-8 编码后重试')
  }
  if (!text.trim()) throw new Error('文件内容不能为空或只有空白')
  if (Array.from(text).length > 16000) {
    throw new Error('需求原文不能超过 16000 字符')
  }
  return text
}
