import { reactive, watch } from 'vue'

const SETTINGS_KEY = 'agenttestguide-settings'

export type AiSettings = {
  enabled: boolean
  baseUrl: string
  apiKey: string
  model: string
}

export type AppSettings = {
  ai: AiSettings
}

const defaults: AppSettings = {
  ai: {
    enabled: false,
    baseUrl: 'https://api.openai.com/v1',
    apiKey: '',
    model: 'gpt-4o-mini',
  },
}

function readSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (!raw) return structuredClone(defaults)
    const parsed = JSON.parse(raw) as Partial<AppSettings>
    return {
      ai: {
        ...defaults.ai,
        ...(parsed.ai || {}),
      },
    }
  } catch {
    return structuredClone(defaults)
  }
}

export const appSettings = reactive<AppSettings>(readSettings())

watch(
  appSettings,
  (value) => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(value))
  },
  { deep: true },
)

export function resetAiSettings() {
  appSettings.ai.enabled = defaults.ai.enabled
  appSettings.ai.baseUrl = defaults.ai.baseUrl
  appSettings.ai.apiKey = ''
  appSettings.ai.model = defaults.ai.model
}
