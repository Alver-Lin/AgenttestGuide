<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  MessageSquareText,
  TextSelect,
  X,
  Quote,
  Ellipsis,
  PenLine,
  Trash2,
  LoaderCircle,
  CircleAlert,
} from 'lucide-vue-next'
import type { CommentDraft, TextComment } from './types'

const props = defineProps<{
  comments: TextComment[]
  draft: CommentDraft | null
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
  edit: [id: string]
  remove: [id: string]
  'update-body': [body: string]
  cancel: []
  submit: []
  retry: []
}>()
const list = ref<HTMLElement>()
watch(
  () => props.activeId,
  async (id) => {
    await nextTick()
    const card = [...(list.value?.querySelectorAll<HTMLElement>('[data-comment-card]') || [])].find(
      (element) => element.dataset.commentCard === id,
    )
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
</script>

<template>
  <aside class="comments-panel" aria-label="文档注释">
    <header class="comments-heading">
      <div>
        <MessageSquareText :size="18" /><strong>注释</strong
        ><span class="comments-count">{{ comments.length }}</span>
      </div>
      <button class="icon-button" aria-label="关闭注释栏" @click="emit('close')">
        <X :size="18" />
      </button>
    </header>
    <p class="comments-tip"><span class="yellow-dot"></span>选中正文中的文字，添加注释并标黄</p>
    <div v-if="error" class="comments-error">
      <CircleAlert :size="14" /><span>{{ error }}</span
      ><button @click="emit('retry')">重试</button>
    </div>
    <div ref="list" class="comments-list">
      <div v-if="loading && !comments.length" class="comments-loading">
        <LoaderCircle :size="20" class="spin" /><span>正在读取注释…</span>
      </div>
      <div v-else-if="!comments.length" class="comments-empty">
        <span class="comments-empty-icon"><TextSelect :size="28" :stroke-width="1.4" /></span
        ><strong>为你的理解留下批注</strong>
      </div>
      <article
        v-for="comment in comments"
        :key="comment.id"
        :data-comment-card="comment.id"
        :class="['comment-card', { active: activeId === comment.id }]"
      >
        <div class="comment-card-top">
          <span class="comment-avatar">我</span><strong>我的注释</strong
          ><a-dropdown :trigger="['click']"
            ><button
              class="icon-button"
              :disabled="busy"
              :aria-label="`管理注释：${comment.body.slice(0, 18)}`"
            >
              <Ellipsis :size="16" /></button
            ><template #overlay
              ><a-menu
                ><a-menu-item @click="emit('edit', comment.id)"
                  ><PenLine :size="13" /> 编辑注释</a-menu-item
                ><a-menu-item danger @click="emit('remove', comment.id)"
                  ><Trash2 :size="13" /> 删除注释</a-menu-item
                ></a-menu
              ></template
            ></a-dropdown
          >
        </div>
        <button
          class="comment-quote"
          :title="comment.anchor.quote"
          @click="emit('select', comment.id)"
        >
          <Quote :size="12" /><span>{{ comment.anchor.quote }}</span>
        </button>
        <p class="comment-body">{{ comment.body }}</p>
        <div class="comment-card-bottom">
          <time>{{ timeLabel(comment.updated_at) }}</time
          ><button @click="emit('select', comment.id)">
            {{ unlocated.includes(comment.id) ? '原文已修改' : '定位原文' }}
          </button>
        </div>
      </article>
    </div>
    <form v-if="draft" class="comment-composer" @submit.prevent="emit('submit')">
      <div class="composer-heading">
        <strong>{{ draft.editingId ? '编辑注释' : '添加注释' }}</strong
        ><button
          type="button"
          class="icon-button"
          :disabled="busy"
          aria-label="取消当前注释"
          @click="emit('cancel')"
        >
          <X :size="15" />
        </button>
      </div>
      <blockquote class="composer-quote">{{ draft.anchor.quote }}</blockquote>
      <a-textarea
        :value="draft.body"
        aria-label="注释内容"
        :placeholder="draft.editingId ? '修改你的注释…' : '写下你的注释…'"
        :maxlength="5000"
        :auto-size="{ minRows: 3, maxRows: 6 }"
        :disabled="busy"
        @update:value="(value: string) => emit('update-body', value)"
      />
      <div class="composer-actions">
        <span>注释仅关联当前文档</span
        ><a-button
          type="primary"
          html-type="submit"
          size="small"
          :loading="busy"
          :disabled="!draft.body.trim()"
          >{{ draft.editingId ? '保存修改' : '发表注释' }}</a-button
        >
      </div>
    </form>
    <div v-else class="comments-footer">
      <TextSelect :size="14" />{{
        editing ? '切换到阅读模式后可选中文字' : '选中文字即可添加新的注释'
      }}
    </div>
  </aside>
</template>
