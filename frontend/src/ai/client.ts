import { appSettings, type AiSettings } from '../useSettings'

export function isAiReady(ai: AiSettings = appSettings.ai): boolean {
  return Boolean(ai.enabled && ai.baseUrl.trim() && ai.model.trim())
}

export type ChatMessage = {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export type ChatCompletionOptions = {
  messages: ChatMessage[]
  temperature?: number
  maxTokens?: number
  signal?: AbortSignal
  /**
   * DeepSeek (and some peers) default to thinking mode; reasoning can exhaust
   * max_tokens and leave message.content empty. Keyword JSON does not need CoT.
   * Default: disabled.
   */
  thinking?: 'enabled' | 'disabled'
  /** Override settings (tests / one-off). */
  ai?: AiSettings
}

export class AiClientError extends Error {
  constructor(
    message: string,
    readonly causeName?: string,
  ) {
    super(message)
    this.name = 'AiClientError'
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, '')
}

type ChatChoiceMessage = {
  content?: string | null
  reasoning_content?: string | null
}

type ChatCompletionResponse = {
  error?: { message?: string }
  choices?: Array<{
    finish_reason?: string | null
    message?: ChatChoiceMessage
  }>
}

function pickAssistantText(message: ChatChoiceMessage | undefined): string {
  const content = message?.content?.trim() || ''
  if (content) return content
  // Last resort: some thinking runs park the whole answer in reasoning_content.
  const reasoning = message?.reasoning_content?.trim() || ''
  return reasoning
}

/** OpenAI-compatible chat completion; returns assistant text. */
export async function chatCompletion(opts: ChatCompletionOptions): Promise<string> {
  const ai = opts.ai ?? appSettings.ai
  if (!isAiReady(ai)) {
    throw new AiClientError('AI 未启用或配置不完整')
  }

  const url = `${normalizeBaseUrl(ai.baseUrl)}/chat/completions`
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (ai.apiKey.trim()) headers.Authorization = `Bearer ${ai.apiKey.trim()}`

  const thinking = opts.thinking ?? 'disabled'
  const body: Record<string, unknown> = {
    model: ai.model.trim(),
    temperature: opts.temperature ?? 0.2,
    max_tokens: opts.maxTokens ?? 1200,
    messages: opts.messages,
    // DeepSeek OpenAI-compatible extension (ignored by providers that don't know it).
    thinking: { type: thinking },
  }
  // Also set reasoning_effort none when disabling — helps some gateways.
  if (thinking === 'disabled') body.reasoning_effort = 'none'

  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers,
      signal: opts.signal,
      body: JSON.stringify(body),
    })
  } catch (err) {
    const name = err instanceof Error ? err.name : 'NetworkError'
    if (name === 'AbortError') throw err
    throw new AiClientError('无法连接 AI 服务', name)
  }

  const raw = await response.text()
  let data: ChatCompletionResponse = {}
  try {
    data = raw ? (JSON.parse(raw) as ChatCompletionResponse) : {}
  } catch {
    throw new AiClientError(`AI 返回非 JSON（HTTP ${response.status}）`)
  }

  if (!response.ok) {
    throw new AiClientError(data.error?.message || `AI 请求失败（HTTP ${response.status}）`)
  }

  const choice = data.choices?.[0]
  const text = pickAssistantText(choice?.message)
  if (!text) {
    const reason = choice?.finish_reason || 'unknown'
    if (reason === 'length') {
      throw new AiClientError(
        'AI 输出被截断（thinking 占满 token）。已建议关闭 thinking；请重试或增大 max_tokens',
      )
    }
    throw new AiClientError('AI 返回空内容')
  }
  return text
}
