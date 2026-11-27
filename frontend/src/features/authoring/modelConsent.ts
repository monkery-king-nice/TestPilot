import { h } from 'vue'
import { ElMessageBox } from 'element-plus'
import { previewModelInput } from '@/api/authoring'

export async function confirmModelInput(project: string, id: string, version: number) {
  const { context, digest } = await previewModelInput(project, id, version)
  return await confirmPreview(context) ? digest : undefined
}

export async function confirmPreview(context: unknown): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      h('div', [
        h('p', '下列项目资料将发送给配置的模型服务。含私密信息时请取消，修改需求或选择精简资料。'),
        h('pre', { style: 'max-height:42vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere' },
          JSON.stringify(context, null, 2))
      ]), '核对发给模型的资料',
      { confirmButtonText: '同意发送', cancelButtonText: '取消', closeOnClickModal: false })
    return true
  } catch (error) {
    if (error === 'cancel' || error === 'close') return false
    throw error
  }
}
