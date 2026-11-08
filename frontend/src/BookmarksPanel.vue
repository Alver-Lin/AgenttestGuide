<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  Bookmark,
  BookmarkPlus,
  X,
  Quote,
  Ellipsis,
  PenLine,
  Trash2,
  LoaderCircle,
  CircleAlert,
} from 'lucide-vue-next'
import type { TextBookmark } from './types'

const props = defineProps<{
  bookmarks: TextBookmark[]
  activeId: string
  loading: boolean
  busy: boolean
  error: string
  unlocated: string[]
  editing: boolean
}>()
const emit = defineEmits<{
  close: []
  select: [id: string]
  rename: [id: string, title: string]
  remove: [id: string]
  retry: []
}>()
const list = ref<HTMLElement>()
const renamingId = ref('')
const renameTitle = ref('')
const renameInput = ref<HTMLInputElement>()

watch(
  () => props.activeId,
  async (id) => {
    await nextTick()
    const card = [
      ...(list.value?.querySelectorAll<HTMLElement>('[data-bookmark-card]') || []),
    ].find((element) => element.dataset.bookmarkCard === id)
    if (card && list.value) {
      const bounds = card.getBoundingClientRect(),
        container = list.value.getBoundingClientRect()
      if (bounds.top < container.top || bounds.bottom > container.bottom)
        card.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  },
)

function timeLabel(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Shanghai',
  }).format(new Date(value))
}

function startRename(bookmark: TextBookmark) {
  renamingId.value = bookmark.id
  renameTitle.value = bookmark.title
  nextTick(() => {
    renameInput.value?.focus()
    renameInput.value?.select()
  })
}

function cancelRename() {
  renamingId.value = ''
  renameTitle.value = ''
}

function submitRename(id: string) {
  const title = renameTitle.value.trim()
  if (!title || props.busy) return
  emit('rename', id, title)
  cancelRename()
}
</script>

<template>
  <aside class="comments-panel bookmarks-panel" aria-label="文档书签">
    <header class="comments-heading">
      <div>
        <Bookmark :size="18" /><strong>书签</strong>
      </div>
      <button class="icon-button" aria-label="关闭书签栏" @click="emit('close')">
        <X :size="18" />
      </button>
    </header>
    <div v-if="error" class="comments-error">
      <CircleAlert :size="14" /><span>{{ error }}</span
      ><button @click="emit('retry')">重试</button>
    </div>
    <div ref="list" class="comments-list">
      <div v-if="loading && !bookmarks.length" class="comments-loading">
        <LoaderCircle :size="20" class="spin" /><span>正在读取书签…</span>
      </div>
      <div v-else-if="!bookmarks.length" class="comments-empty">
        <span class="comments-empty-icon bookmark-empty-icon"
          ><BookmarkPlus :size="28" :stroke-width="1.4" /></span
        ><strong>标记重要段落，方便回来继续看</strong>
      </div>
      <article
        v-for="bookmark in bookmarks"
        :key="bookmark.id"
        :data-bookmark-card="bookmark.id"
        :class="['comment-card', 'bookmark-card', { active: activeId === bookmark.id }]"
      >
        <div class="comment-card-top">
          <span class="comment-avatar bookmark-avatar"><Bookmark :size="11" /></span
          ><strong>书签</strong
          ><a-dropdown :trigger="['click']"
            ><button
              class="icon-button"
              :disabled="busy"
              :aria-label="`管理书签：${bookmark.title.slice(0, 18)}`"
            >
              <Ellipsis :size="16" /></button
            ><template #overlay
              ><a-menu
                ><a-menu-item @click="startRename(bookmark)"
                  ><PenLine :size="13" /> 重命名</a-menu-item
                ><a-menu-item danger @click="emit('remove', bookmark.id)"
                  ><Trash2 :size="13" /> 删除书签</a-menu-item
                ></a-menu
              ></template
            ></a-dropdown
          >
        </div>
        <form
          v-if="renamingId === bookmark.id"
          class="bookmark-rename"
          @submit.prevent="submitRename(bookmark.id)"
        >
          <input
            ref="renameInput"
            v-model="renameTitle"
            maxlength="80"
            aria-label="书签名称"
            :disabled="busy"
          />
          <button type="submit" :disabled="busy || !renameTitle.trim()">保存</button>
          <button type="button" :disabled="busy" @click="cancelRename">取消</button>
        </form>
        <button
          v-else
          class="comment-quote bookmark-quote"
          :title="bookmark.anchor.quote"
          @click="emit('select', bookmark.id)"
        >
          <Quote :size="12" /><span>{{ bookmark.title }}</span>
        </button>
        <p v-if="renamingId !== bookmark.id" class="bookmark-snippet">
          {{ bookmark.anchor.quote }}
        </p>
        <div class="comment-card-bottom">
          <time>{{ timeLabel(bookmark.updated_at) }}</time>
          <span v-if="unlocated.includes(bookmark.id)" class="comment-unlocated">原文已修改</span>
        </div>
      </article>
    </div>
    <div class="comments-footer">
      <BookmarkPlus :size="13" /><span>{{
        editing ? '切换到阅读模式后可选中文字添加书签' : '选中文字后点击「书签」即可添加'
      }}</span>
    </div>
  </aside>
</template>
