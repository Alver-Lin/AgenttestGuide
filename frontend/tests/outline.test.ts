import test from 'node:test'
import assert from 'node:assert/strict'
import {
  extractOutline,
  outlineHasChildren,
  outlineItemVisible,
  collapsibleOutlineIds,
} from '../src/outline.ts'

test('extracts headings and ignores markdown inside fenced code', () => {
  const items = extractOutline(
    [
      '# Title',
      '',
      '```python',
      '# 井号后面是注释，解释器会忽略',
      'print(1)',
      '```',
      '',
      '## Section',
      '### Detail',
    ].join('\n'),
  )
  assert.deepEqual(
    items.map((item) => [item.level, item.text]),
    [
      [1, 'Title'],
      [2, 'Section'],
      [3, 'Detail'],
    ],
  )
})

test('collapse hides nested headings until parent expands', () => {
  const items = extractOutline(['## A', '### A1', '### A2', '## B', '### B1'].join('\n'))
  assert.equal(outlineHasChildren(items, 0), true)
  assert.equal(outlineHasChildren(items, 1), false)
  assert.deepEqual(collapsibleOutlineIds(items), [items[0].id, items[3].id])

  const collapsed = new Set([items[0].id])
  assert.equal(outlineItemVisible(items, 0, collapsed), true)
  assert.equal(outlineItemVisible(items, 1, collapsed), false)
  assert.equal(outlineItemVisible(items, 3, collapsed), true)
  assert.equal(outlineItemVisible(items, 4, collapsed), true)
})
