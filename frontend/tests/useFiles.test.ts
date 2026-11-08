import test from 'node:test'
import assert from 'node:assert/strict'
import { useFiles } from '../src/useFiles'
import type { Note, Notebook } from '../src/types'

const folder: Notebook = {
  id: 'folder',
  name: '测试',
  color: 'blue',
  description: '',
  created_at: '2026-11-06',
}
const file: Note = {
  id: 'file',
  notebook_id: folder.id,
  title: '文档',
  content: '原正文',
  tags: [],
  is_favorite: false,
  deleted_at: null,
  created_at: '2026-11-06',
  updated_at: '2026-11-06',
}

function setup(handler: (url: string, options: RequestInit) => Response | Promise<Response>) {
  const cache = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => cache.get(key) ?? null,
      setItem: (key: string, value: string) => cache.set(key, value),
      removeItem: (key: string) => cache.delete(key),
    },
  })
  globalThis.fetch = async (url, options = {}) => {
    if (url === '/api/bootstrap') return Response.json({ notebooks: [folder], notes: [file] })
    return handler(String(url), options)
  }
  return useFiles()
}

test('deletion waits for in-flight autosave and undo restores saved content', async () => {
  const calls: string[] = []
  let finishSave!: (value: Response) => void
  const saved = { ...file, content: '最新正文' }
  const state = setup((url, options) => {
    calls.push(`${options.method} ${url}`)
    if (options.method === 'PATCH')
      return new Promise((resolve) => {
        finishSave = resolve
      })
    if (options.method === 'DELETE') return new Response(null, { status: 204 })
    return Response.json(saved)
  })
  try {
    await state.load()
    state.updateFile(file.id, { content: saved.content })
    const saving = state.saveAll()
    const deleting = state.deleteEntry('file', file.id)
    assert.deepEqual(calls, ['PATCH /api/notes/file'])
    finishSave(Response.json(saved))
    await saving
    await deleting
    assert.deepEqual(calls, ['PATCH /api/notes/file', 'DELETE /api/notes/file'])
    assert.equal(state.activeFiles.value.length, 0)
    assert.equal(state.pendingCount.value, 0)
    await state.restoreEntry('file', file.id)
    assert.equal(state.activeFiles.value[0]?.content, '最新正文')
  } finally {
    state.dispose()
  }
})

test('a failed save blocks deletion and retains the browser draft', async () => {
  const calls: string[] = []
  const state = setup((url, options) => {
    calls.push(`${options.method} ${url}`)
    return Response.json({ detail: '磁盘已满' }, { status: 500 })
  })
  try {
    await state.load()
    state.updateFile(file.id, { content: '未保存正文' })
    await assert.rejects(state.deleteEntry('folder', folder.id), /修改尚未保存/)
    assert.deepEqual(calls, ['PATCH /api/notes/file'])
    assert.equal(state.activeFiles.value[0]?.content, '未保存正文')
    assert.equal(state.folders.value.length, 1)
    assert.equal(state.pendingCount.value, 1)
    assert.match(localStorage.getItem('evalnote.unsaved.v1')!, /未保存正文/)
  } finally {
    state.dispose()
  }
})

test('folder deletion failure retains the tree; success and undo update it together', async () => {
  let fail = true
  const state = setup((_url, options) => {
    if (options.method === 'DELETE')
      return fail
        ? Response.json({ detail: '删除失败' }, { status: 409 })
        : new Response(null, { status: 204 })
    return Response.json({ notebook: folder, notes: [file] })
  })
  try {
    await state.load()
    await assert.rejects(state.deleteEntry('folder', folder.id), /删除失败/)
    assert.equal(state.folders.value.length, 1)
    assert.equal(state.activeFiles.value.length, 1)
    fail = false
    await state.deleteEntry('folder', folder.id)
    assert.equal(state.folders.value.length, 0)
    assert.equal(state.activeFiles.value.length, 0)
    await state.restoreEntry('folder', folder.id)
    assert.equal(state.folders.value.length, 1)
    assert.equal(state.activeFiles.value[0]?.id, file.id)
  } finally {
    state.dispose()
  }
})
