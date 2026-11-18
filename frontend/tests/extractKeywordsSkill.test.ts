import test from 'node:test'
import assert from 'node:assert/strict'
import { parseKeywordSkillResponse } from '../src/spider/skills/extractKeywordsSkill.ts'

test('parseKeywordSkillResponse reads JSON object', () => {
  const kws = parseKeywordSkillResponse(
    JSON.stringify({
      keywords: [
        { phrase: 'MCP', count: 5 },
        { phrase: 'Model Context Protocol', count: 3 },
      ],
    }),
    10,
  )
  assert.equal(kws.length, 2)
  assert.equal(kws[0]?.phrase, 'MCP')
  assert.equal(kws[0]?.key, 'mcp')
  assert.equal(kws[1]?.count, 3)
})

test('parseKeywordSkillResponse tolerates markdown fence', () => {
  const kws = parseKeywordSkillResponse('```json\n{"keywords":["FastAPI","依赖注入"]}\n```', 5)
  assert.deepEqual(
    kws.map((k) => k.phrase),
    ['FastAPI', '依赖注入'],
  )
})

test('parseKeywordSkillResponse returns empty on garbage', () => {
  assert.deepEqual(parseKeywordSkillResponse('not json at all'), [])
})

test('parseKeywordSkillResponse dedupes and respects max', () => {
  const kws = parseKeywordSkillResponse(
    JSON.stringify({
      keywords: ['A', 'a', 'B', 'C'],
    }),
    2,
  )
  assert.equal(kws.length, 2)
  assert.equal(kws[0]?.phrase, 'A')
  assert.equal(kws[1]?.phrase, 'B')
})
