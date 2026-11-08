import { computed, ref } from 'vue'
import { api } from './types'
import type { Note, NoteChanges, Notebook } from './types'

/** Persist to real Markdown files while retaining compatible browser drafts. */
export function useFiles() {
  const folders = ref<Notebook[]>([])
  const files = ref<Note[]>([])
  const loading = ref(true)
  const loadError = ref('')
  const saveError = ref('')
  const saving = ref(false)
  const pendingCount = ref(0)
  const activeFiles = computed(() => files.value.filter((file) => !file.deleted_at))
  const dirty: Record<string, NoteChanges> = {}
  const jobs = new Map<string, Promise<boolean>>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  const storageKey = 'evalnote.unsaved.v1'

  function cacheDrafts() {
    pendingCount.value = Object.keys(dirty).length
    try {
      if (pendingCount.value) localStorage.setItem(storageKey, JSON.stringify(dirty))
      else localStorage.removeItem(storageKey)
    } catch {
      saveError.value = '浏览器草稿缓存不可用，请保持页面打开并尽快保存'
    }
  }

  function updateFile(id: string, changes: NoteChanges) {
    const file = files.value.find((item) => item.id === id)
    if (!file || file.deleted_at) return
    Object.assign(file, changes)
    dirty[id] = { ...dirty[id], ...changes }
    cacheDrafts()
    clearTimeout(timers.get(id))
    timers.set(
      id,
      setTimeout(() => void saveFile(id), 700),
    )
  }

  function saveFile(id: string): Promise<boolean> {
    if (jobs.has(id)) return jobs.get(id)!
    if (!dirty[id] || !Object.keys(dirty[id]!).length) return Promise.resolve(true)
    clearTimeout(timers.get(id))
    const job = (async () => {
      saving.value = true
      try {
        while (dirty[id] && Object.keys(dirty[id]!).length) {
          const snapshot = { ...dirty[id] }
          const result = await api<Note>(`/notes/${id}`, {
            method: 'PATCH',
            body: JSON.stringify(snapshot),
          })
          const file = files.value.find((item) => item.id === id)
          for (const key of Object.keys(snapshot) as (keyof NoteChanges)[]) {
            if (JSON.stringify(dirty[id]?.[key]) === JSON.stringify(snapshot[key])) {
              delete dirty[id]![key]
              if (file) Object.assign(file, { [key]: result[key] })
            }
          }
          if (file) file.updated_at = result.updated_at
          if (!Object.keys(dirty[id] || {}).length) delete dirty[id]
          cacheDrafts()
        }
        saveError.value = ''
        return true
      } catch (error) {
        saveError.value = (error as Error).message
        return false
      } finally {
        jobs.delete(id)
        saving.value = jobs.size > 0
      }
    })()
    jobs.set(id, job)
    return job
  }

  async function saveAll() {
    return (await Promise.all(Object.keys(dirty).map(saveFile))).every(Boolean)
  }

  async function load() {
    loading.value = true
    loadError.value = ''
    try {
      const data = await api<{ notebooks: Notebook[]; notes: Note[] }>('/bootstrap')
      folders.value = data.notebooks
      files.value = data.notes
      try {
        const drafts = JSON.parse(localStorage.getItem(storageKey) || '{}') as Record<
          string,
          NoteChanges
        >
        for (const [id, changes] of Object.entries(drafts)) {
          if (files.value.some((file) => file.id === id && !file.deleted_at))
            updateFile(id, changes)
        }
      } catch {
        /* A malformed cache must not prevent opening server data. */
      }
    } catch (error) {
      loadError.value = (error as Error).message
    } finally {
      loading.value = false
    }
  }

  async function createFolder(name: string) {
    const folder = await api<Notebook>('/notebooks', {
      method: 'POST',
      body: JSON.stringify({ name }),
    })
    folders.value.push(folder)
    return folder
  }

  async function renameFolder(id: string, name: string) {
    const original = folders.value.find((folder) => folder.id === id)!
    const folder = await api<Notebook>(`/notebooks/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ name, color: original.color, description: original.description }),
    })
    folders.value[folders.value.findIndex((item) => item.id === id)] = folder
  }

  async function createFile(folderId: string, title: string) {
    const file = await api<Note>('/notes', {
      method: 'POST',
      body: JSON.stringify({ notebook_id: folderId, title }),
    })
    files.value.push(file)
    return file
  }

  async function deleteEntry(kind: 'folder' | 'file', id: string) {
    const affected = activeFiles.value.filter((file) =>
      kind === 'folder' ? file.notebook_id === id : file.id === id,
    )
    // Finish pending writes before moving files so a late autosave cannot race deletion.
    if (!(await Promise.all(affected.map((file) => saveFile(file.id)))).every(Boolean))
      throw new Error('修改尚未保存，暂未删除。请保存成功后重试。')
    await api(kind === 'folder' ? `/notebooks/${id}?recursive=true` : `/notes/${id}`, {
      method: 'DELETE',
    })
    for (const file of affected) {
      clearTimeout(timers.get(file.id))
      timers.delete(file.id)
      file.deleted_at = new Date().toISOString()
      delete dirty[file.id]
    }
    if (kind === 'folder') folders.value = folders.value.filter((folder) => folder.id !== id)
    cacheDrafts()
  }

  async function restoreEntry(kind: 'folder' | 'file', id: string) {
    let restored: Note[]
    if (kind === 'folder') {
      const result = await api<{ notebook: Notebook; notes: Note[] }>(`/notebooks/${id}/restore`, {
        method: 'POST',
      })
      if (!folders.value.some((folder) => folder.id === id)) folders.value.push(result.notebook)
      restored = result.notes
    } else restored = [await api<Note>(`/notes/${id}/restore`, { method: 'POST' })]
    for (const file of restored) {
      const index = files.value.findIndex((item) => item.id === file.id)
      if (index < 0) files.value.push(file)
      else files.value[index] = file
    }
  }

  function dispose() {
    timers.forEach(clearTimeout)
  }

  function addImportedFile(file: Note) {
    if (!files.value.some((item) => item.id === file.id)) files.value.push(file)
  }

  return {
    folders,
    activeFiles,
    loading,
    loadError,
    saving,
    saveError,
    pendingCount,
    load,
    updateFile,
    saveAll,
    createFolder,
    renameFolder,
    createFile,
    deleteEntry,
    restoreEntry,
    addImportedFile,
    dispose,
  }
}
