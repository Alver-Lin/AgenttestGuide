import test from 'node:test'
import assert from 'node:assert/strict'
import { extractKeywords } from '../src/spider/keywords.ts'

test('extractKeywords RAKE prefers repeated content phrases over stop words', () => {
  const text = `
    Model Context Protocol 连接工具。
    Model Context Protocol 很有用。
    可以 可以 可以 可以 可以 可以
    笔记服务 笔记服务
  `
  const kws = extractKeywords(text, 5)
  assert.ok(kws.length > 0)
  assert.ok(
    kws.some((k) => /model context protocol/i.test(k.phrase) || /mcp/i.test(k.key)),
    `expected protocol-like phrase, got ${kws.map((k) => k.phrase).join(', ')}`,
  )
  assert.ok(!kws.some((k) => k.phrase === '可以'))
})

test('extractKeywords ignores fenced code blocks', () => {
  const text = 'Alpha protocol Alpha protocol\n```\nzzzz zzzz zzzz zzzz\n```\n'
  const kws = extractKeywords(text, 3)
  assert.ok(kws.some((k) => /alpha/i.test(k.phrase)))
  assert.ok(!kws.some((k) => /zzzz/i.test(k.phrase)))
})
