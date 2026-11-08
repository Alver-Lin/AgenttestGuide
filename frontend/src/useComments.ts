import { computed, nextTick, reactive, ref, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { api } from './types'
import type { CommentDraft, Note, TextBookmark, TextComment } from './types'
import { locateAnchor, paintHighlights, readSelectionAnchor } from './annotations'
import type { AnchorRange, HighlightSpan } from './annotations'

export function useComments(
  file: ComputedRef<Note | undefined>,
  host: Ref<HTMLElement | undefined>,
  editing: Ref<boolean>,
  bookmarks: ComputedRef<TextBookmark[]> = computed(() => []),
  activeBookmarkId: Ref<string> = ref(''),
) {
  const open = ref(window.matchMedia('(min-width: 1200px)').matches)
  const activeId = ref('')
  const lists = reactive<Record<string, TextComment[]>>({})
  const drafts = reactive<Record<string, CommentDraft>>({})
  const errors = reactive<Record<string, string>>({})
  const fetching = reactive<Record<string, boolean>>({})
  const posting = reactive<Record<string, boolean>>({})
  const versions = new Map<string, number>()
  const positions = ref<Record<string, AnchorRange | null>>({})
  const comments = computed(() => (file.value ? lists[file.value.id] || [] : []))
  const draft = computed(() => (file.value ? drafts[file.value.id] || null : null))
  const loading = computed(() => !!file.value && !!fetching[file.value.id])
  const busy = computed(() => !!file.value && !!posting[file.value.id])
  const error = computed(() => (file.value ? errors[file.value.id] || '' : ''))
  const unlocated = computed(() =>
    comments.value
      .filter((comment) => positions.value[comment.id] === null)
      .map((comment) => comment.id),
  )
  const hasDrafts = computed(() => Object.values(drafts).some((item) => !!item.body.trim()))

  async function reload(id = file.value?.id) {
    if (!id) return
    const version = (versions.get(id) || 0) + 1
    versions.set(id, version)
    fetching[id] = true
    errors[id] = ''
    try {
      const result = await api<TextComment[]>(`/notes/${id}/comments`)
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

  async function paint() {
    await nextTick()
    if (!host.value || editing.value) return
    const text = host.value.textContent || ''
    const located: Record<string, AnchorRange | null> = {}
    const spans: HighlightSpan[] = []
    for (const comment of comments.value) {
      const range = locateAnchor(text, comment.anchor)
      located[comment.id] = range
      if (range) spans.push({ ...range, id: comment.id, kind: 'comment' })
    }
    for (const bookmark of bookmarks.value) {
      const range = locateAnchor(text, bookmark.anchor)
      if (range) spans.push({ ...range, id: bookmark.id, kind: 'bookmark' })
    }
    if (draft.value) {
      const range = locateAnchor(text, draft.value.anchor)
      if (range) spans.push({ ...range, id: '', draft: true, kind: 'comment' })
    }
    positions.value = located
    paintHighlights(host.value, spans, activeId.value, activeBookmarkId.value)
  }

  function beginDraft(anchor = readSelectionAnchor(host.value!)) {
    if (!file.value || !host.value || editing.value || busy.value || !anchor) return false
    const previous = drafts[file.value.id]
    drafts[file.value.id] = { anchor, body: previous?.editingId ? '' : previous?.body || '' }
    activeId.value = ''
    open.value = true
    return true
  }

  function captureSelection() {
    beginDraft()
  }

  function updateBody(body: string) {
    if (draft.value) draft.value.body = body
  }
  function cancelDraft() {
    if (file.value && !busy.value) delete drafts[file.value.id]
  }

  async function submit() {
    const id = file.value?.id,
      value = draft.value
    if (!id || !value || busy.value || !value.body.trim()) return
    if (!value.editingId) {
      if (editing.value) {
        editing.value = false
        await nextTick()
      }
      if (!host.value || !locateAnchor(host.value.textContent || '', value.anchor)) {
        message.warning('原文已变化，请重新选择需要评论的文字。')
        return
      }
    }
    posting[id] = true
    const snapshot = { ...value, body: value.body.trim() }
    try {
      const result = await api<TextComment>(
        `/notes/${id}/comments${snapshot.editingId ? `/${snapshot.editingId}` : ''}`,
        {
          method: snapshot.editingId ? 'PATCH' : 'POST',
          body: JSON.stringify(
            snapshot.editingId
              ? { body: snapshot.body }
              : { body: snapshot.body, anchor: snapshot.anchor },
          ),
        },
      )
      invalidate(id)
      lists[id] = snapshot.editingId
        ? (lists[id] || []).map((item) => (item.id === result.id ? result : item))
        : [...(lists[id] || []), result]
      if (drafts[id] === value) delete drafts[id]
      if (file.value?.id === id) activeId.value = result.id
      message.success(snapshot.editingId ? '评论已更新' : '评论已保存，原文已标黄')
    } catch (cause) {
      message.error((cause as Error).message)
    } finally {
      posting[id] = false
    }
  }

  function editComment(id: string) {
    const comment = comments.value.find((item) => item.id === id)
    if (!comment || !file.value || busy.value) return
    drafts[file.value.id] = { anchor: comment.anchor, body: comment.body, editingId: comment.id }
    activeId.value = id
  }

  function deleteComment(id: string) {
    const noteId = file.value?.id
    if (!noteId || busy.value) return
    Modal.confirm({
      title: '删除这条评论？',
      content: '删除后无法恢复。',
      okText: '删除评论',
      okType: 'danger',
      cancelText: '取消',
      async onOk() {
        posting[noteId] = true
        try {
          await api(`/notes/${noteId}/comments/${id}`, { method: 'DELETE' })
          invalidate(noteId)
          lists[noteId] = (lists[noteId] || []).filter((item) => item.id !== id)
          if (drafts[noteId]?.editingId === id) delete drafts[noteId]
          if (activeId.value === id) activeId.value = ''
        } catch (cause) {
          message.error((cause as Error).message)
        } finally {
          posting[noteId] = false
        }
      },
    })
  }

  async function jumpToComment(id: string) {
    open.value = true
    editing.value = false
    activeId.value = id
    await paint()
    const mark = [
      ...(host.value?.querySelectorAll<HTMLElement>('mark[data-comment-ids]') || []),
    ].find((element) => element.dataset.commentIds?.split(' ').includes(id))
    if (mark) mark.scrollIntoView({ behavior: 'smooth', block: 'center' })
    else message.info('被评论的原文已修改，暂时无法定位。')
  }

  function onHighlightClick(event: MouseEvent) {
    const target = (event.target as Element).closest<HTMLElement>('mark[data-annotation]')
    if (!target || !host.value?.contains(target) || !window.getSelection()?.isCollapsed) return null
    const commentId = target.dataset.commentIds
      ?.split(' ')
      .find((value) => comments.value.some((comment) => comment.id === value))
    const bookmarkId = target.dataset.bookmarkIds
      ?.split(' ')
      .find((value) => bookmarks.value.some((bookmark) => bookmark.id === value))
    if (!commentId && !bookmarkId) return null
    event.preventDefault()
    if (commentId) {
      activeId.value = commentId
      open.value = true
      return { type: 'comment' as const, id: commentId }
    }
    return { type: 'bookmark' as const, id: bookmarkId! }
  }

  watch(
    () => file.value?.id,
    (id) => {
      activeId.value = ''
      positions.value = {}
      if (id) void reload(id)
    },
    { immediate: true },
  )
  watch(
    [
      host,
      () => file.value?.content,
      comments,
      bookmarks,
      () => draft.value?.anchor,
      activeId,
      activeBookmarkId,
      editing,
    ],
    () => void paint(),
    { flush: 'post' },
  )

  return {
    open,
    activeId,
    comments,
    draft,
    loading,
    busy,
    error,
    unlocated,
    hasDrafts,
    reload,
    paint,
    beginDraft,
    captureSelection,
    updateBody,
    cancelDraft,
    submit,
    editComment,
    deleteComment,
    jumpToComment,
    onHighlightClick,
  }
}
