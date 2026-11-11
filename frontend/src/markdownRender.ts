import { marked } from 'marked'
import { highlightCode, languageClass } from './codeHighlight'

marked.setOptions({ gfm: true, breaks: false })

marked.use({
  renderer: {
    code({ text, lang }: { text: string; lang?: string }) {
      const language = (lang || '').trim()
      const highlighted = highlightCode(text, language)
      return `<pre class="code-block"><code class="hljs ${languageClass(language)}">${highlighted}</code></pre>\n`
    },
  },
})

export function renderMarkdown(content: string) {
  return marked.parse(content || '') as string
}
