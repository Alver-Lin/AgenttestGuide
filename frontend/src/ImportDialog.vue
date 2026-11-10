<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  Upload as UploadIcon,
  Link2,
  FileText,
  X,
  CheckCircle2,
  CircleAlert,
  LoaderCircle,
  ArrowRight,
} from 'lucide-vue-next'
import { message } from 'ant-design-vue'
import { api } from './types'
import type { Note, Notebook } from './types'

interface Config {
  mode: string
  max_bytes: number
  accepts: string[]
  supports_webpage: boolean
}
interface Job {
  id: string
  state: 'pending' | 'running' | 'done' | 'failed'
  message: string
  stage: string
  note?: Note
  warnings?: string[]
}
interface Item {
  id: string
  name: string
  file?: File
  sourceUrl?: string
  job?: Job
  error?: string
}
const props = defineProps<{ open: boolean; folders: Notebook[]; defaultFolderId: string }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  imported: [note: Note]
  'open-file': [note: Note]
}>()
const config = ref<Config>()
const configError = ref('')
const mode = ref('file')
const folderId = ref('')
const url = ref('')
const filename = ref('')
const ocr = ref(false)
const items = ref<Item[]>([])
const busy = ref(false)
let disposed = false
const accepts = computed(
  () =>
    config.value?.accepts.join(',') || '.md,.markdown,.txt,.pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg',
)
const successful = computed(() => items.value.filter((item) => item.job?.state === 'done'))
const pending = computed(() =>
  items.value.filter(
    (item) => item.file && (!item.job || item.job.state === 'failed' || item.error),
  ),
)
const ready = computed(
  () =>
    !!config.value &&
    !!folderId.value &&
    (mode.value === 'url' ? !!url.value.trim() : !!pending.value.length),
)
const folderOptions = computed(() =>
  props.folders
    .slice()
    .sort((a, b) => (a.path || a.name).localeCompare(b.path || b.name, 'zh-CN'))
    .map((folder) => ({
      label: folder.path?.includes('/')
        ? folder.path.replaceAll('/', ' / ')
        : folder.name,
      value: folder.id,
    })),
)

async function loadConfig() {
  configError.value = ''
  try {
    config.value = await api<Config>('/import/config')
  } catch (error) {
    configError.value = (error as Error).message
  }
}
watch(
  () => props.open,
  (open) => {
    if (!open) return
    folderId.value = props.folders.some((folder) => folder.id === props.defaultFolderId)
      ? props.defaultFolderId
      : props.folders[0]?.id || ''
    items.value = []
    url.value = ''
    filename.value = ''
    mode.value = 'file'
    void loadConfig()
  },
)
function addFile(file: File) {
  const extension = '.' + file.name.split('.').pop()?.toLowerCase()
  if (!config.value?.accepts.includes(extension)) {
    message.warning('当前模式暂不支持这个格式')
    return false
  }
  if (file.size > config.value.max_bytes) {
    message.warning(`单个文件最大 ${Math.round(config.value.max_bytes / 1024 / 1024)} MB`)
    return false
  }
  if (items.value.length >= 10) {
    message.warning('每次最多选择 10 个文件')
    return false
  }
  items.value.push({ id: crypto.randomUUID(), name: file.name, file })
  return false
}
async function follow(item: Item, job: Job) {
  item.job = job
  while (!disposed && job.state !== 'done' && job.state !== 'failed') {
    await new Promise((resolve) => setTimeout(resolve, 1800))
    if (disposed) return
    job = await api<Job>(`/import/jobs/${job.id}`)
    item.job = job
  }
  if (job.state === 'done' && job.note) emit('imported', job.note)
}
async function start() {
  if (busy.value || !ready.value) return
  busy.value = true
  try {
    if (mode.value === 'url') {
      const parsed = new URL(url.value.trim())
      if (!['http:', 'https:'].includes(parsed.protocol))
        throw new Error('请输入公开的 HTTP 或 HTTPS 链接')
      let item = items.value.find(
        (value) =>
          value.sourceUrl === url.value.trim() &&
          value.error &&
          value.job &&
          !['done', 'failed'].includes(value.job.state),
      )
      if (!item) {
        item = {
          id: crypto.randomUUID(),
          name: filename.value.trim() || parsed.hostname + parsed.pathname,
          sourceUrl: url.value.trim(),
        }
        items.value.push(item)
      }
      // Use the reactive item so polling is immediately reflected in the dialog.
      const current = items.value.find((value) => value.id === item.id)!
      current.error = ''
      try {
        await follow(
          current,
          current.job ||
            (await api<Job>('/import/url', {
              method: 'POST',
              body: JSON.stringify({
                notebook_id: folderId.value,
                url: url.value.trim(),
                filename: filename.value.trim(),
                is_ocr: ocr.value,
              }),
            })),
        )
        if (current.job?.state === 'done') {
          url.value = ''
          filename.value = ''
        }
      } catch (error) {
        current.error = (error as Error).message
      }
    } else {
      for (const item of [...pending.value]) {
        item.error = ''
        try {
          const form = new FormData()
          form.append('notebook_id', folderId.value)
          form.append('file', item.file!)
          form.append('is_ocr', String(ocr.value))
          if (item.job && item.job.state !== 'failed') await follow(item, item.job)
          else
            await follow(
              item,
              await api<Job>('/import/file', {
                method: 'POST',
                body: form,
                signal: AbortSignal.timeout(180000),
              }),
            )
        } catch (error) {
          item.error = (error as Error).message
        }
      }
    }
  } catch (error) {
    message.error((error as Error).message)
  } finally {
    busy.value = false
  }
}
function finish() {
  if (busy.value) return
  const note = successful.value[0]?.job?.note
  emit('update:open', false)
  if (note) emit('open-file', note)
}
function openFile(note: Note) {
  emit('update:open', false)
  emit('open-file', note)
}
onBeforeUnmount(() => {
  disposed = true
})
</script>

<template>
  <a-modal
    :open="open"
    title="导入文档"
    width="620px"
    :closable="!busy"
    :mask-closable="!busy"
    :keyboard="!busy"
    @cancel="emit('update:open', false)"
  >
    <div class="import-engine">
      <span class="import-engine-dot"></span><strong>MinerU</strong
      ><span>{{ config?.mode === 'precision' ? '精准解析' : '轻量解析' }}</span
      ><span v-if="config" class="import-limits"
        >{{ Math.round(config.max_bytes / 1024 / 1024) }} MB / 文件{{
          config.mode === 'agent' ? ' · 20 页' : ''
        }}</span
      >
    </div>
    <div v-if="configError" class="import-error">
      {{ configError }}<button @click="loadConfig">重试</button>
    </div>
    <label class="import-label">导入到</label
    ><a-select
      v-model:value="folderId"
      :options="folderOptions"
      :disabled="busy"
      style="width: 100%"
      aria-label="导入目标文件夹"
    />
    <div class="import-tabs">
      <button :class="{ active: mode === 'file' }" :disabled="busy" @click="mode = 'file'">
        <UploadIcon :size="15" />上传文件</button
      ><button :class="{ active: mode === 'url' }" :disabled="busy" @click="mode = 'url'">
        <Link2 :size="15" />输入 URL
      </button>
    </div>
    <div v-if="mode === 'file'" class="import-upload">
      <a-upload-dragger
        :accept="accepts"
        multiple
        :before-upload="addFile"
        :show-upload-list="false"
        :disabled="busy || !config"
        ><span class="import-upload-icon"><UploadIcon :size="29" :stroke-width="1.5" /></span
        ><strong>点击选择文件，或拖动文件到这里</strong>
        <p>支持 Markdown、PDF、Word、PPT、Excel 和图片</p>
        <small>Markdown 直接导入，其它文档通过 MinerU 转为 Markdown</small></a-upload-dragger
      >
    </div>
    <div v-else class="import-url">
      <label class="import-label">文档或网页链接</label
      ><a-input
        v-model:value="url"
        :disabled="busy"
        placeholder="https://example.com/document.pdf"
        aria-label="导入文档URL"
        ><template #prefix><Link2 :size="15" /></template></a-input
      ><label class="import-label">文件名称 <small>可选，无扩展名的文档链接建议填写</small></label
      ><a-input
        v-model:value="filename"
        :disabled="busy"
        placeholder="例如：Agent 评测入门.pdf"
        aria-label="链接文件名称"
      />
      <p v-if="config && !config.supports_webpage" class="import-url-hint">
        当前支持公开文档链接；网页链接需要配置 MinerU Token 启用精准解析。
      </p>
    </div>
    <a-checkbox v-model:checked="ocr" :disabled="busy" class="import-ocr"
      >扫描件 OCR 增强识别</a-checkbox
    >
    <div v-if="items.length" class="import-items">
      <article v-for="item in items" :key="item.id" class="import-item">
        <div class="import-item-line">
          <FileText :size="17" /><strong :title="item.name">{{ item.name }}</strong
          ><LoaderCircle
            v-if="!item.error && item.job && !['done', 'failed'].includes(item.job.state)"
            :size="15"
            class="spin"
          /><CheckCircle2
            v-else-if="item.job?.state === 'done'"
            :size="16"
            class="import-success"
          /><CircleAlert
            v-else-if="item.error || item.job?.state === 'failed'"
            :size="16"
            class="import-failed"
          /><button
            v-else
            class="icon-button"
            aria-label="移除待导入文件"
            :disabled="busy"
            @click="items = items.filter((value) => value.id !== item.id)"
          >
            <X :size="14" />
          </button>
        </div>
        <p v-if="item.error || item.job?.state === 'failed'" class="import-result-error">
          {{ item.error || item.job?.message }}
        </p>
        <p v-else-if="item.job" class="import-status">{{ item.job.message }}</p>
        <template v-if="item.job?.note"
          ><div class="import-result-path">
            <ArrowRight :size="12" /><span>{{ item.job.note.path }}</span
            ><button :disabled="busy" @click="openFile(item.job!.note!)">打开</button>
          </div>
          <p v-for="warning in item.job.warnings || []" :key="warning" class="import-warning">
            {{ warning }}
          </p></template
        >
      </article>
    </div>
    <p class="import-footnote">
      PDF 等文档或链接将交由 MinerU 解析，Markdown 文件直接保存。结果为独立 .md
      文件，同名文件自动编号。
    </p>
    <template #footer
      ><a-button :disabled="busy" @click="finish">{{
        successful.length ? '完成' : '取消'
      }}</a-button
      ><a-button
        v-if="!successful.length || pending.length || mode === 'url'"
        type="primary"
        :loading="busy"
        :disabled="!ready"
        @click="start"
        >{{ busy ? '正在解析导入' : '开始导入' }}</a-button
      ></template
    >
  </a-modal>
</template>
