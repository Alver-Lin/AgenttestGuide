export interface Notebook {
  path?: string
  parent_id?: string | null
  id: string
  name: string
  color: 'green' | 'orange' | 'blue' | 'purple'
  description: string
  created_at: string
}

export interface Note {
  imported_from?: { filename: string; format: string; imported_at: string; url?: string }
  path?: string
  id: string
  notebook_id: string
  title: string
  content: string
  tags: string[]
  is_favorite: boolean
  deleted_at: string | null
  created_at: string
  updated_at: string
}

export type NoteChanges = Partial<
  Pick<Note, 'title' | 'content' | 'tags' | 'is_favorite' | 'notebook_id'>
>

export interface TextAnchor {
  quote: string
  start: number
  end: number
  prefix: string
  suffix: string
}

export interface TextComment {
  id: string
  note_id: string
  body: string
  anchor: TextAnchor
  created_at: string
  updated_at: string
}

export interface CommentDraft {
  anchor: TextAnchor
  body: string
  editingId?: string
}

export interface TextBookmark {
  id: string
  note_id: string
  title: string
  anchor: TextAnchor
  created_at: string
  updated_at: string
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...options.headers,
      },
      signal: options.signal ?? AbortSignal.timeout(15000),
    })
  } catch {
    throw new Error('无法连接服务，请检查后端是否启动。未保存的修改会保留在当前浏览器。')
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(typeof data.detail === 'string' ? data.detail : '操作未完成，请检查内容后重试')
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
