type Question = { quote: string; question: string; source_path?: string }

export function composeSupplement(text: string, version: number, questions: Question[], answers: string[]): string {
  const answered = questions.flatMap((question, index) => {
    const answer = answers[index]?.trim()
    if (!answer) return []
    return [
      `引用：${question.quote}`,
      ...(question.source_path ? [`来源：${question.source_path}`] : []),
      `问题：${question.question}`,
      `回答：${answer}`,
    ].join('\n')
  })
  if (!answered.length) throw new Error('请至少填写一条补充答案')
  const result = `${text}\n\n## 用户补充（基于需求 v${version}）\n\n${answered.join('\n\n')}`
  if (Array.from(result).length > 16000) throw new Error('原文与补充合计超过 16000 字符，请精简后保存')
  return result
}
