<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { Eye, EyeOff } from 'lucide-vue-next'
import { appSettings, resetAiSettings } from './useSettings'

const open = defineModel<boolean>('open', { default: false })
const props = defineProps<{
  dark: boolean
  spiderEnabled: boolean
}>()
const emit = defineEmits<{
  'update:dark': [value: boolean]
  'update:spiderEnabled': [value: boolean]
}>()

const showKey = ref(false)
const draftDark = ref(props.dark)
const draftSpider = ref(props.spiderEnabled)
const draft = ref({
  enabled: appSettings.ai.enabled,
  baseUrl: appSettings.ai.baseUrl,
  apiKey: appSettings.ai.apiKey,
  model: appSettings.ai.model,
})

watch(
  () => open.value,
  (visible) => {
    if (!visible) return
    draftDark.value = props.dark
    draftSpider.value = props.spiderEnabled
    draft.value = {
      enabled: appSettings.ai.enabled,
      baseUrl: appSettings.ai.baseUrl,
      apiKey: appSettings.ai.apiKey,
      model: appSettings.ai.model,
    }
    showKey.value = false
  },
)

const themeLabel = computed(() => (draftDark.value ? '深色' : '浅色'))

function save() {
  emit('update:dark', draftDark.value)
  emit('update:spiderEnabled', draftSpider.value)
  appSettings.ai.enabled = draft.value.enabled
  appSettings.ai.baseUrl = draft.value.baseUrl.trim()
  appSettings.ai.apiKey = draft.value.apiKey.trim()
  appSettings.ai.model = draft.value.model.trim() || 'gpt-4o-mini'
  message.success('设置已保存')
  open.value = false
}

function clearAi() {
  resetAiSettings()
  draft.value = {
    enabled: appSettings.ai.enabled,
    baseUrl: appSettings.ai.baseUrl,
    apiKey: '',
    model: appSettings.ai.model,
  }
  message.success('已清空 AI 配置')
}
</script>

<template>
  <a-modal
    v-model:open="open"
    title="设置"
    ok-text="保存"
    cancel-text="取消"
    width="480px"
    destroy-on-close
    class="settings-modal"
    @ok="save"
  >
    <div class="settings">
      <section class="settings-section">
        <header class="settings-section-head">
          <h3>外观</h3>
        </header>
        <div class="settings-card">
          <div class="settings-row">
            <div class="settings-copy">
              <div class="settings-label">主题</div>
              <p class="settings-hint">当前：{{ themeLabel }}模式</p>
            </div>
            <a-switch
              class="settings-switch"
              :checked="draftDark"
              @update:checked="(v: boolean) => (draftDark = v)"
            />
          </div>
          <div class="settings-divider" />
          <div class="settings-row">
            <div class="settings-copy">
              <div class="settings-label">小蜘蛛</div>
            </div>
            <a-switch class="settings-switch" v-model:checked="draftSpider" />
          </div>
        </div>
      </section>

      <section class="settings-section">
        <header class="settings-section-head">
          <h3>AI 接入</h3>
          <p class="settings-hint">
            兼容 OpenAI 接口（OpenAI / OpenRouter / 本地 Ollama）。密钥仅保存在本机。
          </p>
        </header>
        <div class="settings-card">
          <div class="settings-row">
            <div class="settings-copy">
              <div class="settings-label">启用 AI</div>
              <p class="settings-hint">关闭后：通读全文再用本地 RAKE；开启后用 AI skill</p>
            </div>
            <a-switch class="settings-switch" v-model:checked="draft.enabled" />
          </div>
          <div class="settings-divider" />
          <div class="settings-fields" :class="{ muted: !draft.enabled }">
            <label class="field">
              <span class="field-label">Base URL</span>
              <a-input
                v-model:value="draft.baseUrl"
                placeholder="https://api.openai.com/v1"
                allow-clear
                :disabled="!draft.enabled"
              />
            </label>
            <label class="field">
              <span class="field-label">API Key</span>
              <a-input
                v-model:value="draft.apiKey"
                :type="showKey ? 'text' : 'password'"
                placeholder="sk-…（本地服务可留空）"
                allow-clear
                :disabled="!draft.enabled"
              >
                <template #suffix>
                  <button
                    type="button"
                    class="key-toggle"
                    :aria-label="showKey ? '隐藏密钥' : '显示密钥'"
                    :disabled="!draft.enabled"
                    @click="showKey = !showKey"
                  >
                    <EyeOff v-if="showKey" :size="15" />
                    <Eye v-else :size="15" />
                  </button>
                </template>
              </a-input>
            </label>
            <label class="field">
              <span class="field-label">模型</span>
              <a-input
                v-model:value="draft.model"
                placeholder="gpt-4o-mini"
                allow-clear
                :disabled="!draft.enabled"
              />
            </label>
          </div>
          <div class="settings-footer-row">
            <button type="button" class="clear-ai" @click="clearAi">清空 AI 配置</button>
          </div>
        </div>
      </section>
    </div>
  </a-modal>
</template>

<style scoped>
.settings {
  display: grid;
  gap: 20px;
  padding: 2px 0 4px;
}

.settings-section {
  margin: 0;
  display: grid;
  gap: 10px;
}

.settings-section-head {
  display: grid;
  gap: 4px;
  padding: 0 2px;
}

.settings-section-head h3 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ant-color-text-secondary, rgba(255, 255, 255, 0.55));
}

.settings-card {
  display: grid;
  gap: 0;
  padding: 4px 14px 12px;
  border-radius: 10px;
  border: 1px solid var(--ant-color-border-secondary, rgba(255, 255, 255, 0.08));
  background: color-mix(in srgb, var(--ant-color-fill-tertiary, #ffffff) 6%, transparent);
}

.settings-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 16px;
  padding: 12px 0;
}

.settings-copy {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.settings-label {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
  color: var(--ant-color-text, inherit);
}

.settings-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ant-color-text-secondary, rgba(255, 255, 255, 0.55));
}

.settings-switch {
  flex-shrink: 0;
}

.settings-divider {
  height: 1px;
  background: var(--ant-color-border-secondary, rgba(255, 255, 255, 0.08));
}

.settings-fields {
  display: grid;
  gap: 12px;
  padding: 12px 0 4px;
  transition: opacity 0.15s ease;
}

.settings-fields.muted {
  opacity: 0.48;
}

.field {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  margin: 0;
  font-size: 13px;
}

.field-label {
  color: var(--ant-color-text-secondary, rgba(255, 255, 255, 0.55));
  font-size: 13px;
  line-height: 1.3;
  white-space: nowrap;
}

.settings-footer-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
}

.key-toggle {
  display: inline-flex;
  align-items: center;
  border: 0;
  background: transparent;
  color: inherit;
  opacity: 0.65;
  cursor: pointer;
  padding: 0;
}

.key-toggle:hover:not(:disabled) {
  opacity: 1;
}

.key-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.clear-ai {
  border: 0;
  background: transparent;
  color: #ff7875;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
  padding: 4px 0;
}

.clear-ai:hover {
  color: #ff4d4f;
  text-decoration: underline;
}

@media (max-width: 520px) {
  .field {
    grid-template-columns: 1fr;
    gap: 6px;
  }
}
</style>
