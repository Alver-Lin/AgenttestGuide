<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message, Modal, theme as antTheme } from 'ant-design-vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import {
  Folder,
  FolderOpen,
  FolderPlus,
  FilePlus2,
  FileText,
  ChevronRight,
  PanelLeftClose,
  PanelLeftOpen,
  PenLine,
  Eye,
  Ellipsis,
  Trash2,
  CheckCheck,
  LoaderCircle,
  CircleAlert,
  WifiOff,
  Heading2,
  Bold,
  List,
  Quote,
  Code2,
  ImagePlus,
  X,
  MessageSquareText,
  Bookmark,
  Upload as ImportIcon,
  Moon,
  Sun,
} from 'lucide-vue-next'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useFiles } from './useFiles'
import { useComments } from './useComments'
import { useBookmarks } from './useBookmarks'
import { useEditorImages } from './useEditorImages'
import { markdownImageUrl } from './markdownImages'
import { locateAnchor, readSelectionAnchor, selectionRect } from './annotations'
import CommentsPanel from './CommentsPanel.vue'
import BookmarksPanel from './BookmarksPanel.vue'
import ImportDialog from './ImportDialog.vue'
import type { Note, TextAnchor } from './types'

const THEME_KEY = 'agenttestguide-theme'

function readStoredTheme(): boolean {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === 'dark') return true
  if (stored === 'light') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

const isDark = ref(readStoredTheme())
const theme = computed(() => ({
  algorithm: isDark.value ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
  token: {
    colorPrimary: isDark.value ? '#3c8cff' : '#1677ff',
    colorInfo: isDark.value ? '#3c8cff' : '#1677ff',
    borderRadius: 6,
    colorText: isDark.value ? '#e8e8e8' : '#262626',
    colorBorder: isDark.value ? '#424242' : '#d9d9d9',
    colorBgContainer: isDark.value ? '#141414' : '#ffffff',
    colorBgElevated: isDark.value ? '#1f1f1f' : '#ffffff',
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
}))

function applyTheme(dark: boolean) {
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light')
}

function toggleTheme() {
  isDark.value = !isDark.value
}

watch(isDark, applyTheme, { immediate: true })
const {
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
} = useFiles()
const selectedFileId = ref('welcome')
const selectedFolderId = ref('')
const selectedKeys = ref<string[]>([])
const expandedKeys = ref<(string | number)[]>([])
const sidebarHidden = ref(false)
const mobileSidebar = ref(false)
const editing = ref(false)
const editor = ref<HTMLTextAreaElement>()
const markdownBody = ref<HTMLElement>()
const scroller = ref<HTMLElement>()
const current = computed(() => activeFiles.value.find((file) => file.id === selectedFileId.value))
const {
  imageInput,
  uploading: imageUploading,
  uploadStatus: imageUploadStatus,
  dragging: imageDragging,
  openImagePicker,
  onImageInput,
  onImagePaste,
  onImageDragOver,
  onImageDrop,
} = useEditorImages(current, activeFiles, editor, editing, updateFile, {
  success: (text) => {
    void message.success(text)
  },
  error: (text) => {
    void message.error(text)
  },
})
const currentFolder = computed(() =>
  folders.value.find((folder) => folder.id === current.value?.notebook_id),
)
const targetFolder = computed(() =>
  folders.value.find((folder) => folder.id === selectedFolderId.value),
)
const treeData = computed(() =>
  folders.value.map((folder) => ({
    key: `folder:${folder.id}`,
    title: folder.name,
    kind: 'folder',
    id: folder.id,
    children: activeFiles.value
      .filter((file) => file.notebook_id === folder.id)
      .sort((a, b) => a.title.localeCompare(b.title, 'zh-CN'))
      .map((file) => ({
        key: `file:${file.id}`,
        title: file.title,
        kind: 'file',
        id: file.id,
        isLeaf: true,
      })),
  })),
)
const outlineOpen = ref(false)
const outline = computed(() => {
  const items: { id: string; level: number; text: string }[] = []
  const content = current.value?.content || ''
  let index = 0
  for (const match of content.matchAll(/^(#{1,3})\s+(.+)$/gm)) {
    const text = match[2]
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[*_`~]+/g, '')
      .trim()
    if (!text) continue
    items.push({ id: `heading-${index++}`, level: match[1].length, text })
  }
  return items
})
const rendered = computed(() => {
  const html = DOMPurify.sanitize(
    marked.parse(current.value?.content || '', { gfm: true }) as string,
  )
  const id = current.value?.id
  if (!id) return html
  const document = new DOMParser().parseFromString(html, 'text/html')
  for (const image of document.querySelectorAll('img[src]')) {
    const source = image.getAttribute('src') || ''
    image.setAttribute('src', markdownImageUrl(id, source))
    image.setAttribute('data-image-source', source)
  }
  let index = 0
  for (const heading of document.querySelectorAll('h1, h2, h3')) {
    heading.id = `heading-${index++}`
  }
  return document.body.innerHTML
})
const {
  open: bookmarksOpen,
  activeId: activeBookmarkId,
  bookmarks,
  loading: bookmarksLoading,
  busy: bookmarksBusy,
  error: bookmarksError,
  reload: reloadBookmarks,
  add: addBookmark,
  rename: renameBookmark,
  remove: removeBookmark,
} = useBookmarks(current, editing)
const {
  open: commentsOpen,
  activeId: activeCommentId,
  comments,
  draft: commentDraft,
  loading: commentsLoading,
  busy: commentsBusy,
  error: commentsError,
  unlocated: unlocatedComments,
  hasDrafts: hasCommentDrafts,
  reload: reloadComments,
  paint: paintAnnotations,
  beginDraft,
  updateBody: updateCommentBody,
  cancelDraft: cancelComment,
  submit: submitComment,
  editComment,
  deleteComment,
  jumpToComment,
  onHighlightClick,
} = useComments(current, markdownBody, editing, bookmarks, activeBookmarkId)
const selectionMenu = ref<{ anchor: TextAnchor; left: number; top: number } | null>(null)
watch(editing, (value) => {
  if (value) selectionMenu.value = null
})
const unlocatedBookmarks = computed(() => {
  if (!markdownBody.value || editing.value) return [] as string[]
  const text = markdownBody.value.textContent || ''
  return bookmarks.value
    .filter((bookmark) => !locateAnchor(text, bookmark.anchor))
    .map((bookmark) => bookmark.id)
})
const characterCount = computed(
  () => current.value?.content.replace(/[#*`>\[\]()\-\s]/g, '').length || 0,
)
const dialogOpen = ref(false)
const importOpen = ref(false)
const dialogKind = ref<'folder' | 'file'>('folder')
const renameId = ref('')
const dialogName = ref('')
const dialogBusy = ref(false)
const dialogFolderId = ref('')
const nameInput = ref<{ focus: () => void }>()
const dialogTitle = computed(
  () => `${renameId.value ? '重命名' : '新建'}${dialogKind.value === 'folder' ? '文件夹' : '文件'}`,
)

async function initialize() {
  await load()
  if (loadError.value) return
  expandedKeys.value = folders.value.map((folder) => `folder:${folder.id}`)
  const first = activeFiles.value.find((file) => file.id === 'welcome') || activeFiles.value[0]
  if (first) selectNode([`file:${first.id}`], false)
  else if (folders.value[0]) selectNode([`folder:${folders.value[0].id}`], false)
}

function selectNode(keys: (string | number)[], closeSidebar = true) {
  const key = String(keys[0] || '')
  if (!key) return
  selectedKeys.value = [key]
  if (key.startsWith('file:')) {
    const id = key.slice(5)
    const file = activeFiles.value.find((item) => item.id === id)
    if (!file) return
    selectedFileId.value = id
    selectedFolderId.value = file.notebook_id
    if (closeSidebar) mobileSidebar.value = false
  } else {
    selectedFolderId.value = key.slice(7)
    selectedFileId.value = ''
    if (!expandedKeys.value.includes(key)) expandedKeys.value.push(key)
  }
  editing.value = false
  outlineOpen.value = false
  selectionMenu.value = null
  nextTick(() => scroller.value?.scrollTo({ top: 0 }))
}

function toggleOutline() {
  outlineOpen.value = !outlineOpen.value
}

function jumpToHeading(id: string) {
  if (editing.value) editing.value = false
  nextTick(() => {
    const target = scroller.value?.querySelector(`#${CSS.escape(id)}`)
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function onTreeSelect(keys: (string | number)[]) {
  selectNode(keys)
}

function expandNodes(keys: (string | number)[]) {
  expandedKeys.value = keys
}

function openImportedFile(file: Note) {
  addImportedFile(file)
  const key = `folder:${file.notebook_id}`
  if (!expandedKeys.value.includes(key)) expandedKeys.value.push(key)
  selectNode([`file:${file.id}`])
}

function openCreate(kind: 'folder' | 'file') {
  const folderId = selectedFolderId.value || currentFolder.value?.id || folders.value[0]?.id || ''
  if (kind === 'file' && !folderId) {
    message.info('请先创建一个文件夹')
    return
  }
  dialogKind.value = kind
  dialogFolderId.value = folderId
  renameId.value = ''
  dialogName.value = ''
  dialogOpen.value = true
  nextTick(() => nameInput.value?.focus())
}

function openRename(kind: 'folder' | 'file', id: string) {
  dialogKind.value = kind
  renameId.value = id
  dialogName.value =
    kind === 'folder'
      ? folders.value.find((item) => item.id === id)!.name
      : activeFiles.value.find((item) => item.id === id)!.title
  dialogOpen.value = true
  nextTick(() => nameInput.value?.focus())
}

function confirmDelete(kind: 'folder' | 'file', id: string) {
  const folder = kind === 'folder' ? folders.value.find((item) => item.id === id) : undefined
  const file = kind === 'file' ? activeFiles.value.find((item) => item.id === id) : undefined
  const name = folder?.name || file?.title
  if (!name) return
  const count = activeFiles.value.filter((item) => item.notebook_id === id).length
  Modal.confirm({
    title: `删除${kind === 'folder' ? '文件夹' : '文件'}“${name}”？`,
    content:
      kind === 'folder'
        ? `文件夹${count ? `及其中的 ${count} 个文件` : ''}将移入回收目录，删除后可点击“撤销”恢复。`
        : '文件和已保存的注释、书签将保留在回收目录，删除后可点击“撤销”恢复。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    autoFocusButton: 'cancel',
    async onOk() {
      try {
        const previousFolderId = file?.notebook_id
        await deleteEntry(kind, id)
        if (kind === 'folder') {
          expandedKeys.value = expandedKeys.value.filter((key) => key !== `folder:${id}`)
          if (selectedFolderId.value === id) {
            const first = folders.value[0]
            if (first) selectNode([`folder:${first.id}`], false)
            else {
              selectedFileId.value = ''
              selectedFolderId.value = ''
              selectedKeys.value = []
              editing.value = false
            }
          }
        } else if (selectedFileId.value === id) {
          const next = activeFiles.value.find((item) => item.notebook_id === previousFolderId)
          selectNode([next ? `file:${next.id}` : `folder:${previousFolderId}`], false)
        }
        const key = `deleted:${kind}:${id}`
        let restoring = false
        message.success({
          key,
          duration: 12,
          content: h('span', [
            `已删除“${name}”`,
            h(
              'button',
              {
                class: 'undo-delete',
                onClick: async () => {
                  if (restoring) return
                  restoring = true
                  try {
                    await restoreEntry(kind, id)
                    selectNode([`${kind}:${id}`], false)
                    message.success({ key, content: '已恢复', duration: 3 })
                  } catch (error) {
                    restoring = false
                    message.error((error as Error).message)
                  }
                },
              },
              '撤销',
            ),
          ]),
        })
      } catch (error) {
        message.error((error as Error).message)
        // Keep the confirmation open so a failed delete can be retried or cancelled.
        throw error
      }
    },
  })
}

async function submitName() {
  if (dialogBusy.value) return
  const name = dialogName.value.trim()
  if (!name) {
    message.warning('请输入名称')
    return
  }
  dialogBusy.value = true
  try {
    if (renameId.value) {
      if (dialogKind.value === 'folder') await renameFolder(renameId.value, name)
      else updateFile(renameId.value, { title: name })
    } else if (dialogKind.value === 'folder') {
      const folder = await createFolder(name)
      selectNode([`folder:${folder.id}`], false)
      mobileSidebar.value = true
    } else {
      const file = await createFile(dialogFolderId.value, name)
      const parentKey = `folder:${file.notebook_id}`
      if (!expandedKeys.value.includes(parentKey)) expandedKeys.value.push(parentKey)
      selectNode([`file:${file.id}`])
      editing.value = true
      nextTick(() => editor.value?.focus())
    }
    dialogOpen.value = false
  } catch (error) {
    message.error((error as Error).message)
  } finally {
    dialogBusy.value = false
  }
}

function updateTitle(event: Event) {
  if (current.value)
    updateFile(current.value.id, { title: (event.target as HTMLInputElement).value })
}
function updateContent(event: Event) {
  if (current.value)
    updateFile(current.value.id, { content: (event.target as HTMLTextAreaElement).value })
}
function insertMarkdown(before: string, after = '') {
  const element = editor.value,
    file = current.value
  if (!element || !file || imageUploading.value) return
  const start = element.selectionStart,
    end = element.selectionEnd
  updateFile(file.id, {
    content:
      file.content.slice(0, start) +
      before +
      file.content.slice(start, end) +
      after +
      file.content.slice(end),
  })
  nextTick(() => {
    element.focus()
    element.setSelectionRange(start + before.length, end + before.length)
  })
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'Asia/Shanghai',
  }).format(new Date(value))
}
function toggleSidebar() {
  if (window.matchMedia('(max-width: 760px)').matches) mobileSidebar.value = !mobileSidebar.value
  else sidebarHidden.value = !sidebarHidden.value
}
function onKey(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    void saveAll()
  }
  if (event.key === 'Escape') {
    mobileSidebar.value = false
    outlineOpen.value = false
    clearSelectionMenu()
  }
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (pendingCount.value || hasCommentDrafts.value || imageUploading.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
function onOnline() {
  void saveAll()
}
function onLink(event: MouseEvent) {
  const link = (event.target as Element).closest('a')
  if (link && /^https?:/.test(link.href)) {
    link.target = '_blank'
    link.rel = 'noopener noreferrer'
  }
}
function clearSelectionMenu() {
  selectionMenu.value = null
}

function updateSelectionMenu() {
  if (!markdownBody.value || editing.value || commentsBusy.value || bookmarksBusy.value) {
    clearSelectionMenu()
    return
  }
  const anchor = readSelectionAnchor(markdownBody.value)
  const rect = selectionRect(markdownBody.value)
  const reader = markdownBody.value.closest('.document-reader') as HTMLElement | null
  if (!anchor || !rect || !reader) {
    clearSelectionMenu()
    return
  }
  const bounds = reader.getBoundingClientRect()
  selectionMenu.value = {
    anchor,
    left: Math.min(Math.max(rect.left - bounds.left + rect.width / 2, 72), bounds.width - 72),
    top: Math.min(rect.bottom - bounds.top + 10, bounds.height - 48),
  }
}

function openCommentsPanel() {
  bookmarksOpen.value = false
  clearSelectionMenu()
  commentsOpen.value = !commentsOpen.value
}

function openBookmarksPanel() {
  commentsOpen.value = false
  clearSelectionMenu()
  bookmarksOpen.value = !bookmarksOpen.value
}

async function addBookmarkFromSelection() {
  if (!selectionMenu.value) return
  const anchor = selectionMenu.value.anchor
  clearSelectionMenu()
  window.getSelection()?.removeAllRanges()
  commentsOpen.value = false
  await addBookmark(anchor)
}

function addCommentFromSelection() {
  if (!selectionMenu.value) return
  const anchor = selectionMenu.value.anchor
  clearSelectionMenu()
  bookmarksOpen.value = false
  beginDraft(anchor)
}

async function jumpToBookmark(id: string) {
  commentsOpen.value = false
  bookmarksOpen.value = true
  editing.value = false
  activeBookmarkId.value = id
  await paintAnnotations()
  const mark = [
    ...(markdownBody.value?.querySelectorAll<HTMLElement>('mark[data-bookmark-ids]') || []),
  ].find((element) => element.dataset.bookmarkIds?.split(' ').includes(id))
  if (mark) mark.scrollIntoView({ behavior: 'smooth', block: 'center' })
  else message.info('被标记的原文已修改，暂时无法定位。')
}

async function openComment(id: string) {
  bookmarksOpen.value = false
  await jumpToComment(id)
}

function onMarkdownClick(event: MouseEvent) {
  const hit = onHighlightClick(event)
  if (!hit) {
    onLink(event)
    return
  }
  clearSelectionMenu()
  if (hit.type === 'bookmark') {
    commentsOpen.value = false
    bookmarksOpen.value = true
    activeBookmarkId.value = hit.id
  } else {
    bookmarksOpen.value = false
  }
}
function onMarkdownImageError(event: Event) {
  const image = event.target
  if (!(image instanceof HTMLImageElement)) return
  const source = image.dataset.imageSource || image.getAttribute('src') || ''
  image.classList.add('image-load-error')
  image.alt = `图片无法加载：${source}`
  image.title =
    '请检查图片是否存在。相对路径以当前 Markdown 文件所在目录为基准；编辑模式显示 Markdown 源码，阅读模式显示图片。'
}
onMounted(() => {
  void initialize()
  window.addEventListener('keydown', onKey)
  window.addEventListener('beforeunload', beforeUnload)
  window.addEventListener('online', onOnline)
})
onBeforeUnmount(() => {
  dispose()
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('beforeunload', beforeUnload)
  window.removeEventListener('online', onOnline)
})
</script>

<template>
  <a-config-provider :theme="theme" :locale="zhCN">
    <div class="app-shell" :class="{ 'sidebar-hidden': sidebarHidden }">
      <div v-if="mobileSidebar" class="sidebar-overlay" @click="mobileSidebar = false"></div>
      <aside class="file-sidebar" :class="{ 'is-open': mobileSidebar }">
        <div class="brand">
          <span class="brand-icon"
            ><img src="/icon.png?v=shark-2" width="32" height="32" alt="" /></span
          ><strong>AgenttestGuide</strong
          ><button
            class="icon-button mobile-close"
            aria-label="关闭文件栏"
            @click="mobileSidebar = false"
          >
            <X :size="17" />
          </button>
        </div>
        <div class="explorer-heading">
          <span>文件</span>
          <div class="explorer-actions">
            <a-tooltip title="导入文档"
              ><button
                class="icon-button"
                aria-label="导入文档"
                :disabled="loading || !!loadError || !folders.length"
                @click="importOpen = true"
              >
                <ImportIcon :size="18" /></button
            ></a-tooltip>
            <a-tooltip title="新建文件夹"
              ><button
                class="icon-button"
                aria-label="新建文件夹"
                :disabled="loading || !!loadError"
                @click="openCreate('folder')"
              >
                <FolderPlus :size="18" /></button></a-tooltip
            ><a-tooltip title="新建文件"
              ><button
                class="icon-button"
                aria-label="新建文件"
                :disabled="loading || !!loadError"
                @click="openCreate('file')"
              >
                <FilePlus2 :size="18" /></button
            ></a-tooltip>
          </div>
        </div>
        <div class="file-tree" aria-label="文件夹和文件">
          <a-tree
            v-if="!loading && !loadError"
            :tree-data="treeData"
            :selected-keys="selectedKeys"
            :expanded-keys="expandedKeys"
            block-node
            @select="onTreeSelect"
            @expand="expandNodes"
          >
            <template #title="{ title, kind, id, key }"
              ><span :class="['tree-node', kind]"
                ><FolderOpen
                  v-if="kind === 'folder' && expandedKeys.includes(key)"
                  :size="16"
                /><Folder v-else-if="kind === 'folder'" :size="16" /><FileText
                  v-else
                  :size="15"
                /><span class="tree-name" :title="title">{{ title }}</span
                ><a-dropdown :trigger="['click']"
                  ><button class="node-menu icon-button" :aria-label="`管理${title}`" @click.stop>
                    <Ellipsis :size="15" /></button
                  ><template #overlay
                    ><a-menu
                      ><a-menu-item @click="openRename(kind, id)"
                        ><PenLine :size="13" /> 重命名</a-menu-item
                      ><a-menu-divider />
                      <a-menu-item danger @click="confirmDelete(kind, id)"
                        ><Trash2 :size="13" /> 删除{{
                          kind === 'folder' ? '文件夹' : '文件'
                        }}</a-menu-item
                      ></a-menu
                    ></template
                  ></a-dropdown
                ></span
              ></template
            >
          </a-tree>
          <div v-if="!loading && !loadError && !folders.length" class="tree-empty">
            还没有文件夹<button @click="openCreate('folder')">创建文件夹</button>
          </div>
        </div>
        <footer class="sidebar-footer">
          <a-tooltip title="收起文件栏"
            ><button
              class="icon-button sidebar-collapse"
              aria-label="收起文件栏"
              @click="toggleSidebar"
            >
              <PanelLeftClose :size="18" /></button
          ></a-tooltip>
        </footer>
      </aside>
      <main class="document-pane">
        <header class="document-header">
          <div class="document-path">
            <button
              class="icon-button sidebar-toggle sidebar-reopen"
              aria-label="显示文件栏"
              @click="toggleSidebar"
            >
              <PanelLeftOpen :size="18" />
            </button>
            <a-tooltip v-if="current" title="目录"
              ><button
                class="icon-button outline-toggle"
                :class="{ active: outlineOpen }"
                aria-label="目录"
                :aria-expanded="outlineOpen"
                @click="toggleOutline"
              >
                <List :size="17" /></button
            ></a-tooltip>
            <template v-if="current"
              ><span class="path-folder">{{ currentFolder?.name }}</span
              ><ChevronRight :size="15" /><span class="path-file">{{
                current.title
              }}</span></template
            ><span v-else class="path-file">{{ targetFolder?.name || '文件' }}</span>
          </div>
          <div class="document-header-actions">
            <a-tooltip :title="isDark ? '浅色模式' : '深色模式'"
              ><button
                class="icon-button theme-toggle"
                :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
                @click="toggleTheme"
              >
                <Sun v-if="isDark" :size="17" /><Moon v-else :size="17" /></button
            ></a-tooltip>
            <template v-if="current">
              <a-tooltip title="阅读"
                ><button
                  class="icon-button"
                  :class="{ active: !editing }"
                  aria-label="阅读"
                  @click="editing = false"
                >
                  <Eye :size="17" /></button></a-tooltip
              ><a-tooltip title="编辑"
                ><button
                  class="icon-button"
                  :class="{ active: editing }"
                  aria-label="编辑"
                  @click="editing = true"
                >
                  <PenLine :size="17" /></button
              ></a-tooltip>
              <a-tooltip title="书签"
                ><button
                  class="icon-button comments-toggle"
                  :class="{ active: bookmarksOpen }"
                  aria-label="书签"
                  :aria-expanded="bookmarksOpen"
                  @click="openBookmarksPanel"
                >
                  <Bookmark :size="17" /><span
                    v-if="bookmarks.length"
                    class="comments-badge"
                    >{{ bookmarks.length }}</span
                  >
                </button></a-tooltip
              >
              <a-tooltip title="注释"
                ><button
                  class="icon-button comments-toggle"
                  :class="{ active: commentsOpen }"
                  aria-label="注释"
                  :aria-expanded="commentsOpen"
                  @click="openCommentsPanel"
                >
                  <MessageSquareText :size="17" /><span
                    v-if="comments.length"
                    class="comments-badge"
                    >{{ comments.length }}</span
                  >
                </button></a-tooltip
              >
            </template>
          </div>
        </header>
        <div v-if="loading" class="center-state">
          <LoaderCircle class="spin" :size="26" />
          <p>正在打开文件…</p>
        </div>
        <div v-else-if="loadError" class="center-state error-state">
          <WifiOff :size="30" />
          <h2>暂时无法打开文件</h2>
          <p>{{ loadError }}</p>
          <a-button type="primary" @click="initialize">重新连接</a-button
          ><small>请确认后端已在 8317 端口启动。</small>
        </div>
        <template v-else>
          <div v-if="saveError" class="save-error">
            <CircleAlert :size="15" /><span>{{ saveError }}</span
            ><a-button size="small" @click="saveAll">重试保存</a-button>
          </div>
          <template v-if="current">
            <div class="document-workspace">
              <aside v-if="outlineOpen" class="outline-panel" aria-label="目录">
                <header class="outline-heading">
                  <div>
                    <List :size="16" /><strong>目录</strong>
                  </div>
                </header>
                <nav class="outline-list">
                  <button class="outline-item level-0" @click="jumpToHeading('document-title')">
                    {{ current.title }}
                  </button>
                  <button
                    v-for="item in outline"
                    :key="item.id"
                    :class="['outline-item', `level-${item.level}`]"
                    :title="item.text"
                    @click="jumpToHeading(item.id)"
                  >
                    {{ item.text }}
                  </button>
                  <p v-if="!outline.length" class="outline-empty">正文中还没有标题</p>
                </nav>
              </aside>
              <div class="document-reader">
                <div
                  v-if="selectionMenu && !editing"
                  class="selection-toolbar"
                  :style="{ left: `${selectionMenu.left}px`, top: `${selectionMenu.top}px` }"
                  role="toolbar"
                  aria-label="选区操作"
                  @mousedown.prevent
                >
                  <button type="button" @click="addBookmarkFromSelection">
                    <Bookmark :size="14" />书签
                  </button>
                  <button type="button" @click="addCommentFromSelection">
                    <MessageSquareText :size="14" />注释
                  </button>
                </div>
                <div ref="scroller" class="document-scroll">
                  <article class="document-content" :class="{ 'is-editing': editing }">
                    <input
                      v-if="editing"
                      class="title-input"
                      aria-label="文件名称"
                      :value="current.title"
                      maxlength="200"
                      @input="updateTitle"
                    />
                    <h1 v-else id="document-title" class="document-title">{{ current.title }}</h1>
                    <p class="document-date">{{ formatDate(current.updated_at) }} 更新</p>
                    <div
                      v-if="editing"
                      class="editor"
                      :class="{ 'is-dragging-image': imageDragging }"
                    >
                      <div class="editor-toolbar">
                        <a-tooltip title="标题"
                          ><button aria-label="插入标题" @click="insertMarkdown('\n## ')">
                            <Heading2 :size="17" /></button></a-tooltip
                        ><a-tooltip title="加粗"
                          ><button aria-label="插入加粗" @click="insertMarkdown('**', '**')">
                            <Bold :size="16" /></button></a-tooltip
                        ><a-tooltip title="列表"
                          ><button aria-label="插入列表" @click="insertMarkdown('\n- ')">
                            <List :size="17" /></button></a-tooltip
                        ><a-tooltip title="引用"
                          ><button aria-label="插入引用" @click="insertMarkdown('\n> ')">
                            <Quote :size="16" /></button></a-tooltip
                        ><a-tooltip title="代码块"
                          ><button
                            aria-label="插入代码块"
                            @click="insertMarkdown('\n```text\n', '\n```\n')"
                          >
                            <Code2 :size="17" /></button></a-tooltip
                        ><a-tooltip title="插入图片（也可粘贴或拖入图片）"
                          ><button
                            class="image-insert-button"
                            aria-label="插入图片"
                            :disabled="imageUploading"
                            @click="openImagePicker"
                          >
                            <LoaderCircle v-if="imageUploading" class="spin" :size="16" />
                            <ImagePlus v-else :size="17" />图片
                          </button></a-tooltip
                        ><span>Markdown</span>
                      </div>
                      <input
                        ref="imageInput"
                        type="file"
                        accept="image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"
                        multiple
                        hidden
                        aria-label="选择要插入的图片"
                        @change="onImageInput"
                      />
                      <textarea
                        :key="current.id"
                        ref="editor"
                        :value="current.content"
                        aria-label="文件正文"
                        spellcheck="false"
                        :readonly="imageUploading"
                        :aria-busy="imageUploading"
                        placeholder="从这里开始写…支持粘贴或拖入图片"
                        @input="updateContent"
                        @paste="onImagePaste"
                        @dragover="onImageDragOver"
                        @dragleave="imageDragging = false"
                        @drop="onImageDrop"
                      ></textarea>
                      <div class="editor-image-hint" role="status" aria-live="polite">
                        {{
                          imageUploadStatus ||
                          (imageDragging
                            ? '松开即可在光标处插入图片'
                            : '支持粘贴截图或拖入图片 · 单张不超过 10 MB')
                        }}
                      </div>
                    </div>
                    <div
                      v-else-if="current.content"
                      ref="markdownBody"
                      class="markdown-body"
                      v-html="rendered"
                      @mouseup="updateSelectionMenu"
                      @keyup="updateSelectionMenu"
                      @click="onMarkdownClick"
                      @error.capture="onMarkdownImageError"
                    ></div>
                    <div v-else class="empty-content">
                      <p>这个文件还是空白的。</p>
                      <a-button @click="editing = true">开始编写</a-button>
                    </div>
                  </article>
                </div>
                <footer class="document-footer">
                  <span class="save-status"
                    ><LoaderCircle v-if="saving" class="spin" :size="13" /><CircleAlert
                      v-else-if="saveError"
                      :size="13"
                    /><CheckCheck v-else :size="13" /><span>{{
                      saving
                        ? '正在保存…'
                        : saveError
                          ? '尚未保存'
                          : pendingCount
                            ? '等待保存…'
                            : '已保存'
                    }}</span></span
                  ><span class="footer-meta"
                    ><span>{{ characterCount.toLocaleString() }} 字符</span
                    ><span class="footer-divider" aria-hidden="true"></span
                    ><span :title="current.path ? `content/${current.path}` : 'Markdown 文件'"
                      >Markdown 文件</span
                    ></span
                  >
                </footer>
              </div>
              <BookmarksPanel
                v-if="bookmarksOpen"
                :bookmarks="bookmarks"
                :active-id="activeBookmarkId"
                :loading="bookmarksLoading"
                :busy="bookmarksBusy"
                :error="bookmarksError"
                :unlocated="unlocatedBookmarks"
                :editing="editing"
                @close="bookmarksOpen = false"
                @select="jumpToBookmark"
                @rename="renameBookmark"
                @remove="removeBookmark"
                @retry="reloadBookmarks()"
              />
              <CommentsPanel
                v-else-if="commentsOpen"
                :comments="comments"
                :draft="commentDraft"
                :active-id="activeCommentId"
                :loading="commentsLoading"
                :busy="commentsBusy"
                :error="commentsError"
                :unlocated="unlocatedComments"
                :editing="editing"
                @close="commentsOpen = false"
                @select="openComment"
                @edit="editComment"
                @remove="deleteComment"
                @update-body="updateCommentBody"
                @cancel="cancelComment"
                @submit="submitComment"
                @retry="reloadComments()"
              />
            </div>
          </template>
          <div v-else class="center-state">
            <FolderOpen v-if="targetFolder" :size="42" :stroke-width="1.2" /><FileText
              v-else
              :size="42"
              :stroke-width="1.2"
            />
            <h2>{{ targetFolder?.name || '选择一个文件' }}</h2>
            <p>
              {{
                targetFolder
                  ? '在左侧打开文件，或者创建一个新文件。'
                  : '用文件夹整理内容，用文件记录知识。'
              }}
            </p>
            <div class="empty-actions">
              <a-button v-if="!folders.length" @click="openCreate('folder')"
                ><FolderPlus :size="15" />新建文件夹</a-button
              ><a-button v-else @click="openCreate('file')"
                ><FilePlus2 :size="15" />新建文件</a-button
              >
            </div>
          </div>
        </template>
      </main>
      <ImportDialog
        v-model:open="importOpen"
        :folders="folders"
        :default-folder-id="selectedFolderId || currentFolder?.id || ''"
        @imported="addImportedFile"
        @open-file="openImportedFile"
      />
      <a-modal
        v-model:open="dialogOpen"
        :title="dialogTitle"
        :confirm-loading="dialogBusy"
        :ok-text="renameId ? '保存' : '创建'"
        cancel-text="取消"
        width="400px"
        @ok="submitName"
        ><label class="name-label" for="item-name">{{
          dialogKind === 'folder' ? '文件夹名称' : '文件名称'
        }}</label
        ><a-input
          id="item-name"
          ref="nameInput"
          v-model:value="dialogName"
          :maxlength="dialogKind === 'folder' ? 40 : 200"
          :placeholder="
            dialogKind === 'folder' ? '例如：Agent 评测基础' : '例如：我的第一份评测笔记'
          "
          @press-enter="submitName"
      /></a-modal>
    </div>
  </a-config-provider>
</template>
