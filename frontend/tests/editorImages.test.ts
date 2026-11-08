import test from 'node:test'
import assert from 'node:assert/strict'
import { computed, ref } from 'vue'
import { imageMarkdown, useEditorImages } from '../src/useEditorImages'
import type { Note } from '../src/types'

function setup() {
  const files = ref<Note[]>(
    ['first', 'second'].map((id) => ({
      id,
      notebook_id: 'folder',
      title: id,
      content: '前文后文',
      tags: [],
      is_favorite: false,
      deleted_at: null,
      created_at: '',
      updated_at: '',
    })),
  )
  const selected = ref('first')
  const current = computed(() => files.value.find((file) => file.id === selected.value))
  const messages: string[] = []
  const textarea = {
    selectionStart: 2,
    focus() {},
    setSelectionRange() {},
  } as unknown as HTMLTextAreaElement
  const state = useEditorImages(
    current,
    computed(() => files.value),
    ref(textarea),
    ref(true),
    (id, changes) =>
      Object.assign(
        files.value.find((file) => file.id === id)!,
        changes,
      ),
    {
      success: (text) => {
        messages.push(text)
      },
      error: (text) => {
        messages.push(text)
      },
    },
  )
  return { state, selected, files, messages }
}

const image = () => new File(['png-bytes'], '截图.png', { type: 'image/png' })

test('inserts at the cursor without removing text and uses multipart upload', async () => {
  const { state, files } = setup()
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/notes/first/images')
    assert.ok(options?.body instanceof FormData)
    assert.ok(options.body.get('file') instanceof File)
    assert.equal((options.headers as Record<string, string>)['Content-Type'], undefined)
    return Response.json({ path: '_assets/first/image.png', name: '截图' })
  }
  await state.uploadImages([image()])
  assert.equal(files.value[0]!.content, '前文\n![截图](_assets/first/image.png)\n\n后文')
  assert.equal(state.uploading.value, false)
})

test('switching documents during upload inserts into the original document', async () => {
  const { state, selected, files } = setup()
  let finish!: (value: Response) => void
  globalThis.fetch = () =>
    new Promise((resolve) => {
      finish = resolve
    })
  const uploading = state.uploadImages([image()])
  selected.value = 'second'
  finish(Response.json({ path: '_assets/first/image.png', name: '截图' }))
  await uploading
  assert.match(files.value[0]!.content, /!\[截图\]/)
  assert.equal(files.value[1]!.content, '前文后文')
})

test('failed upload preserves text; partial batch keeps successful images', async () => {
  const { state, files, messages } = setup()
  let calls = 0
  globalThis.fetch = async () =>
    ++calls === 1
      ? Response.json({ path: '_assets/first/one.png', name: '第一张' })
      : Response.json({ detail: '上传失败' }, { status: 500 })
  await state.uploadImages([image(), image()])
  assert.match(files.value[0]!.content, /!\[第一张\]/)
  assert.ok(messages.includes('上传失败'))
  const previous = files.value[0]!.content
  await state.uploadImages([image()])
  assert.equal(files.value[0]!.content, previous)
})

test('rejects oversized, unsupported and excessive selections before any request', async () => {
  const { state, files } = setup()
  let calls = 0
  globalThis.fetch = async () => {
    calls++
    return Response.json({})
  }
  await state.uploadImages([new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.png')])
  await state.uploadImages([new File(['<svg/>'], 'drawing.svg', { type: 'image/svg+xml' })])
  await state.uploadImages(Array.from({ length: 11 }, image))
  assert.equal(calls, 0)
  assert.equal(files.value[0]!.content, '前文后文')
})

test('pasting plain text keeps default behavior; clipboard images upload', async () => {
  const { state, files } = setup()
  let prevented = 0
  const preventDefault = () => {
    prevented++
  }
  state.onImagePaste({ clipboardData: { files: [] }, preventDefault } as unknown as ClipboardEvent)
  assert.equal(prevented, 0)
  globalThis.fetch = async () =>
    Response.json({ path: '_assets/first/paste.png', name: '粘贴截图' })
  state.onImagePaste({
    clipboardData: { files: [image()] },
    preventDefault,
  } as unknown as ClipboardEvent)
  await new Promise(setImmediate)
  assert.equal(prevented, 1)
  assert.match(files.value[0]!.content, /!\[粘贴截图\]/)
})

test('drop uploads images and escapes Markdown punctuation in alt text', async () => {
  const { state, files } = setup()
  globalThis.fetch = async () => Response.json({ path: '_assets/first/drop.png', name: '拖入图片' })
  const transfer = { files: [image()], types: ['Files'], dropEffect: 'none' }
  let prevented = 0
  const event = {
    dataTransfer: transfer,
    preventDefault: () => {
      prevented++
    },
  } as unknown as DragEvent
  state.onImageDragOver(event)
  assert.equal(state.dragging.value, true)
  state.onImageDrop(event)
  await new Promise(setImmediate)
  assert.equal(prevented, 2)
  assert.equal(state.dragging.value, false)
  assert.match(files.value[0]!.content, /!\[拖入图片\]/)
  assert.equal(
    imageMarkdown('图[一]\\截图\n', '_assets/id/a.png'),
    '![图\\[一\\]\\\\截图 ](_assets/id/a.png)',
  )
})
