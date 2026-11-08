import test from 'node:test'
import assert from 'node:assert/strict'
import { markdownImageUrl } from '../src/markdownImages'

test('custom relative and managed image paths resolve using the current note', () => {
  for (const path of [
    'images/图 一.jpg',
    './images/pic.png',
    '../shared/pic.png',
    '_assets/id/pic.png',
    '/images/pic.png',
    'images/a%20b%231.png?v=1#preview',
  ]) {
    const result = new URL(markdownImageUrl('note-id', path), 'http://localhost')
    assert.equal(result.pathname, '/api/notes/note-id/image')
    assert.equal(result.searchParams.get('path'), path)
  }
})

test('keeps remote, embedded and already resolved image URLs unchanged', () => {
  for (const path of [
    'https://example.org/a.png',
    'http://example.org/a.png',
    '//example.org/a.png',
    'data:image/png;base64,AA==',
    'blob:https://example.org/id',
    '/api/notes/id/assets/pic.png',
    '#image',
    '',
  ]) {
    assert.equal(markdownImageUrl('id', path), path)
  }
})
