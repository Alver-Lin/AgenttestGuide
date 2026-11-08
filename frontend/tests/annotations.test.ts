import test from 'node:test'
import assert from 'node:assert/strict'
import { locateAnchor, highlightSegments } from '../src/annotations.ts'

function anchor(text: string, quote: string, from = 0) {
  const start = text.indexOf(quote, from),
    end = start + quote.length
  return {
    quote,
    start,
    end,
    prefix: text.slice(Math.max(0, start - 48), start),
    suffix: text.slice(end, end + 48),
  }
}

test('locates selected text and survives insertions before the paragraph', () => {
  const text = '开始理解 Agent。任务成功率能衡量完成情况。'
  const selection = anchor(text, '任务成功率')
  assert.deepEqual(locateAnchor(text, selection), { start: selection.start, end: selection.end })
  const edited = '新增的介绍。' + text
  assert.deepEqual(locateAnchor(edited, selection), {
    start: edited.indexOf('任务成功率'),
    end: edited.indexOf('任务成功率') + 5,
  })
})

test('uses surrounding context to distinguish repeated phrases', () => {
  const text = '第一段：检查结果。第二段：检查结果。第三段：结束。'
  const selection = anchor(text, '检查结果', text.indexOf('第二段'))
  const edited = '新开头：检查结果。' + text
  const found = locateAnchor(edited, selection)!
  assert.equal(found.start, edited.indexOf('检查结果', edited.indexOf('第二段')))
})

test('does not attach comments to changed or ambiguous text', () => {
  assert.equal(
    locateAnchor('原文已经删除', { quote: '任务完成度', start: 0, end: 5, prefix: '', suffix: '' }),
    null,
  )
  assert.equal(
    locateAnchor('一样。一样。', { quote: '一样', start: 10, end: 12, prefix: '', suffix: '' }),
    null,
  )
})

test('supports emoji and multi-paragraph selections with DOM UTF-16 offsets', () => {
  const text = '🌱 学习记录\n第一段。\n第二段。'
  const selection = anchor(text, '第一段。\n第二段。')
  const found = locateAnchor('新的文字\n' + text, selection)!
  assert.equal(('新的文字\n' + text).slice(found.start, found.end), selection.quote)
})

test('overlapping comments retain both IDs without nested highlights', () => {
  const segments = highlightSegments(12, [
    { id: 'first', start: 2, end: 8 },
    { id: 'second', start: 5, end: 10 },
  ])
  assert.deepEqual(
    segments.filter((part) => part.ids.length).map((part) => [part.start, part.end, part.ids]),
    [
      [2, 5, ['first']],
      [5, 8, ['first', 'second']],
      [8, 10, ['second']],
    ],
  )
  assert.equal(
    segments.map((part) => part.end - part.start).reduce((a, b) => a + b, 0),
    12,
  )
})

test('draft ranges can be painted alongside saved comments', () => {
  const segments = highlightSegments(10, [
    { id: 'saved', start: 1, end: 4 },
    { id: '', start: 3, end: 7, draft: true },
  ])
  assert.deepEqual(
    segments.find((part) => part.start === 3),
    { start: 3, end: 4, ids: ['saved'], draft: true },
  )
})
