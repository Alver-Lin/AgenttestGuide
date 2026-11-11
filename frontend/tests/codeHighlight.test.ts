import test from 'node:test'
import assert from 'node:assert/strict'
import { highlightCode, languageClass } from '../src/codeHighlight.ts'

test('highlights python keywords strings comments and builtins', () => {
  const html = highlightCode(
    [
      '# demo',
      '@functools.wraps',
      'def score(predict: str) -> float:',
      '    print(f"ok")',
      '    return 1.0',
    ].join('\n'),
    'python',
  )
  assert.match(html, /token-comment/)
  assert.match(html, /token-decorator[^>]*>@functools\.wraps</)
  assert.match(html, /token-keyword[^>]*>def</)
  assert.match(html, /token-function[^>]*>score</)
  assert.match(html, /token-builtin[^>]*>print</)
  assert.match(html, /token-string[^>]*>f&quot;ok&quot;/)
  assert.match(html, /token-number[^>]*>1\.0/)
  assert.equal(languageClass('py'), 'language-python')
})

test('escapes html inside code and leaves plain text unhighlighted', () => {
  assert.equal(highlightCode('a < b & c', 'text'), 'a &lt; b &amp; c')
  assert.match(highlightCode('{"a": 1}', 'json'), /token-attr/)
})
