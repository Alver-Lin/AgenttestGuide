import { computed, reactive, ref, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { api } from './types'
import type { Note, TextAnchor, TextBookmark } from './types'

export function useBookmarks(file: ComputedRef<Note | undefined>, editing: Ref<boolean>) {
  const open = ref(false)
  const activeId = ref('')
  const lists = reactive<Record<string, TextBookmark[]>>({})
  const errors = reactive<Record<string, string>>({})
  const fetching = reactive<Record<string, boolean>>({})
  const posting = reactive<Record<string, boolean>>({})
  const versions = new Map<string, number>()
  const bookmarks = computed(() => (file.value ? lists[file.value.id] || [] : []))
  const loading = computed(() => !!file.value && !!fetching[file.value.id])
  const busy = computed(() => !!file.value && !!posting[file.value.id])
  const error = computed(() => (file.value ? errors[file.value.id] || '' : ''))

  async function reload(id = file.value?.id) {
    if (!id) return
    const version = (versions.get(id) || 0) + 1
    versions.set(id, version)
    fetching[id] = true
    errors[id] = ''
    try {
      const result = await api<TextBookmark[]>(`/notes/${id}/bookmarks`)
      if (versions.get(id) === version) lists[id] = result
    } catch (cause) {
      if (versions.get(id) === version) errors[id] = (cause as Error).message
    } finally {
      if (versions.get(id) === version) fetching[id] = false
    }
  }

  function invalidate(id: string) {
    versions.set(id, (versions.get(id) || 0) + 1)
    fetching[id] = false
    errors[id] = ''
  }

  async function add(anchor: TextAnchor) {
    const id = file.value?.id
    if (!id || busy.value) return false
    if (editing.value) editing.value = false
    posting[id] = true
    try {
      const result = await api<TextBookmark>(`/notes/${id}/bookmarks`, {
        method: 'POST',
        body: JSON.stringify({ anchor }),
      })
      invalidate(id)
      lists[id] = [...(lists[id] || []), result]
      activeId.value = result.id
      open.value = true
      message.success('书签已添加')
      return true
    } catch (cause) {
      message.error((cause as Error).message)
      return false
    } finally {
      posting[id] = false
    }
  }

  async function rename(id: string, title: string) {
    const noteId = file.value?.id
    const next = title.trim()
    if (!noteId || !next || busy.value) return false
    posting[noteId] = true
    try {
      const result = await api<TextBookmark>(`/notes/${noteId}/bookmarks/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ title: next }),
      })
      invalidate(noteId)
      lists[noteId] = (lists[noteId] || []).map((item) => (item.id === result.id ? result : item))
      activeId.value = result.id
      message.success('书签已更新')
      return true
    } catch (cause) {
      message.error((cause as Error).message)
      return false
    } finally {
      posting[noteId] = false
    }
  }

  function remove(id: string) {
    const noteId = file.value?.id
    if (!noteId || busy.value) return
    Modal.confirm({
      title: '删除这个书签？',
      content: '删除后无法恢复。',
      okText: '删除书签',
      okType: 'danger',
      cancelText: '取消',
      async onOk() {
        posting[noteId] = true
        try {
          await api(`/notes/${noteId}/bookmarks/${id}`, { method: 'DELETE' })
          invalidate(noteId)
          lists[noteId] = (lists[noteId] || []).filter((item) => item.id !== id)
          if (activeId.value === id) activeId.value = ''
        } catch (cause) {
          message.error((cause as Error).message)
        } finally {
          posting[noteId] = false
        }
      },
    })
  }

  watch(
    () => file.value?.id,
    (id) => {
      activeId.value = ''
      if (id) void reload(id)
    },
    { immediate: true },
  )

  return {
    open,
    activeId,
    bookmarks,
    loading,
    busy,
    error,
    reload,
    add,
    rename,
    remove,
  }
}
