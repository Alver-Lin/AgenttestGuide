import { nextTick, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { api } from './types'
import type { Note, NoteChanges } from './types'

const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const imageName = /\.(png|jpe?g|gif|webp)$/i

export function imageMarkdown(name: string, path: string) {
  const alt = name.replace(/[\r\n]/g, ' ').replace(/[\\\[\]]/g, '\\$&')
  return `![${alt}](${path})`
}

export function useEditorImages(
  current: ComputedRef<Note | undefined>,
  files: ComputedRef<Note[]>,
  editor: Ref<HTMLTextAreaElement | undefined>,
  editing: Ref<boolean>,
  updateFile: (id: string, changes: NoteChanges) => void,
  notify: { success: (text: string) => void; error: (text: string) => void },
) {
  const imageInput = ref<HTMLInputElement>()
  const uploading = ref(false)
  const uploadStatus = ref('')
  const dragging = ref(false)
  let pickerTarget: { id: string; position: number } | undefined

  function target() {
    return current.value && editor.value
      ? { id: current.value.id, position: editor.value.selectionStart }
      : undefined
  }

  function openImagePicker() {
    if (uploading.value) return
    pickerTarget = target()
    imageInput.value?.click()
  }

  async function uploadImages(images: File[], destination = target()) {
    if (!destination || !images.length || uploading.value) return
    if (images.length > 10) {
      notify.error('一次最多插入 10 张图片，请分批添加')
      return
    }
    // Validate the whole selection first, so an oversized file does not cause a partial batch.
    for (const image of images) {
      if (!/^image\/(png|jpeg|gif|webp)$/i.test(image.type) && !imageName.test(image.name)) {
        notify.error('请选择 PNG、JPEG、GIF 或 WebP 图片')
        return
      }
      if (!image.size || image.size > MAX_IMAGE_BYTES) {
        notify.error(image.size ? '单张图片不能超过 10 MB' : '图片内容为空，请重新选择')
        return
      }
    }
    uploading.value = true
    const markdown: string[] = []
    try {
      for (const [index, image] of images.entries()) {
        uploadStatus.value = `正在上传图片 ${index + 1}/${images.length}…`
        const body = new FormData()
        body.append('file', image)
        const result = await api<{ path: string; name: string }>(
          `/notes/${encodeURIComponent(destination.id)}/images`,
          { method: 'POST', body, signal: AbortSignal.timeout(60000) },
        )
        markdown.push(imageMarkdown(result.name, result.path))
      }
    } catch (error) {
      notify.error((error as Error).message)
    } finally {
      // Insert successful uploads even if a later image failed; never write into a newly selected file.
      const file = files.value.find((item) => item.id === destination.id)
      if (markdown.length && file && !file.deleted_at) {
        const position = Math.min(destination.position, file.content.length)
        const before = file.content.slice(0, position)
        const after = file.content.slice(position)
        const insertion = `${before && !before.endsWith('\n') ? '\n' : ''}${markdown.join('\n\n')}\n${after && !after.startsWith('\n') ? '\n' : ''}`
        updateFile(file.id, { content: before + insertion + after })
        await nextTick()
        if (current.value?.id === destination.id && editing.value && editor.value) {
          editor.value.focus()
          editor.value.setSelectionRange(position + insertion.length, position + insertion.length)
        }
        notify.success(`已插入 ${markdown.length} 张图片，切换到阅读模式即可查看`)
      } else if (markdown.length) notify.error('原文件已删除，未插入图片')
      uploading.value = false
      uploadStatus.value = ''
    }
  }

  async function onImageInput(event: Event) {
    const input = event.target as HTMLInputElement
    const images = Array.from(input.files || [])
    input.value = ''
    const destination = pickerTarget
    pickerTarget = undefined
    await uploadImages(images, destination)
  }

  function onImagePaste(event: ClipboardEvent) {
    const images = Array.from(event.clipboardData?.files || [])
    if (!images.length) return
    event.preventDefault()
    void uploadImages(images)
  }

  function onImageDragOver(event: DragEvent) {
    if (!event.dataTransfer?.types.includes('Files')) return
    event.preventDefault()
    event.dataTransfer.dropEffect = uploading.value ? 'none' : 'copy'
    dragging.value = !uploading.value
  }

  function onImageDrop(event: DragEvent) {
    dragging.value = false
    const images = Array.from(event.dataTransfer?.files || [])
    if (!images.length) return
    event.preventDefault()
    void uploadImages(images)
  }

  return {
    imageInput,
    uploading,
    uploadStatus,
    dragging,
    openImagePicker,
    uploadImages,
    onImageInput,
    onImagePaste,
    onImageDragOver,
    onImageDrop,
  }
}
