/** Lightweight fenced-code highlighter for reading-mode Markdown. */

type TokenKind =
  | 'comment'
  | 'string'
  | 'number'
  | 'keyword'
  | 'builtin'
  | 'class-name'
  | 'decorator'
  | 'function'
  | 'attr'
  | 'literal'

interface Token {
  kind?: TokenKind
  text: string
}

const PYTHON_KEYWORDS = new Set([
  'False',
  'None',
  'True',
  'and',
  'as',
  'assert',
  'async',
  'await',
  'break',
  'class',
  'continue',
  'def',
  'del',
  'elif',
  'else',
  'except',
  'finally',
  'for',
  'from',
  'global',
  'if',
  'import',
  'in',
  'is',
  'lambda',
  'nonlocal',
  'not',
  'or',
  'pass',
  'raise',
  'return',
  'try',
  'while',
  'with',
  'yield',
  'match',
  'case',
  'type',
])

const PYTHON_BUILTINS = new Set([
  'abs',
  'all',
  'any',
  'bool',
  'dict',
  'enumerate',
  'filter',
  'float',
  'format',
  'frozenset',
  'getattr',
  'hasattr',
  'input',
  'int',
  'isinstance',
  'len',
  'list',
  'map',
  'max',
  'min',
  'next',
  'object',
  'open',
  'print',
  'range',
  'repr',
  'reversed',
  'set',
  'setattr',
  'slice',
  'sorted',
  'str',
  'sum',
  'super',
  'tuple',
  'type',
  'zip',
  'Exception',
  'ValueError',
  'TypeError',
  'RuntimeError',
  'TimeoutError',
  'NotImplementedError',
  'KeyError',
  'IndexError',
  'AttributeError',
  'StopIteration',
  'property',
  'classmethod',
  'staticmethod',
  'dataclass',
  'field',
  'Path',
  'Counter',
  'contextmanager',
  'wraps',
])

const JS_KEYWORDS = new Set([
  'await',
  'break',
  'case',
  'catch',
  'class',
  'const',
  'continue',
  'debugger',
  'default',
  'delete',
  'do',
  'else',
  'export',
  'extends',
  'false',
  'finally',
  'for',
  'function',
  'if',
  'import',
  'in',
  'instanceof',
  'let',
  'new',
  'null',
  'of',
  'return',
  'static',
  'super',
  'switch',
  'this',
  'throw',
  'true',
  'try',
  'typeof',
  'undefined',
  'var',
  'void',
  'while',
  'with',
  'yield',
  'async',
  'from',
  'as',
  'type',
  'interface',
  'enum',
  'implements',
  'readonly',
  'public',
  'private',
  'protected',
])

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

function pushPlain(tokens: Token[], text: string) {
  if (!text) return
  const last = tokens[tokens.length - 1]
  if (last && !last.kind) last.text += text
  else tokens.push({ text })
}

function pushToken(tokens: Token[], kind: TokenKind, text: string) {
  if (!text) return
  tokens.push({ kind, text })
}

function highlightPython(source: string): Token[] {
  const tokens: Token[] = []
  let index = 0
  while (index < source.length) {
    const rest = source.slice(index)
    const comment = rest.match(/^#.*?(?=\n|$)/)
    if (comment) {
      pushToken(tokens, 'comment', comment[0])
      index += comment[0].length
      continue
    }
    const triple = rest.match(/^[fFrRbBuU]{0,2}("""[\s\S]*?"""|'''[\s\S]*?''')/)
    if (triple) {
      pushToken(tokens, 'string', triple[0])
      index += triple[0].length
      continue
    }
    const string = rest.match(/^[fFrRbBuU]{0,2}("""|'''|"|')/)
    if (string) {
      const quote = string[1]!
      if (quote.length === 1) {
        let end = index + string[0].length
        while (end < source.length) {
          const char = source[end]
          if (char === '\\') {
            end += 2
            continue
          }
          if (char === quote) {
            end += 1
            break
          }
          if (char === '\n') break
          end += 1
        }
        pushToken(tokens, 'string', source.slice(index, end))
        index = end
        continue
      }
    }
    const decorator = rest.match(/^@[A-Za-z_][\w.]*/)
    if (decorator) {
      pushToken(tokens, 'decorator', decorator[0])
      index += decorator[0].length
      continue
    }
    const number = rest.match(/^(0[xX][\da-fA-F_]+|\d[\d_]*(\.\d[\d_]*)?([eE][+-]?\d+)?)/)
    if (number) {
      pushToken(tokens, 'number', number[0])
      index += number[0].length
      continue
    }
    const ident = rest.match(/^[A-Za-z_]\w*/)
    if (ident) {
      const word = ident[0]
      const next = source.slice(index + word.length).match(/^\s*(\(|:)/)
      if (PYTHON_KEYWORDS.has(word)) pushToken(tokens, 'keyword', word)
      else if (word === 'self' || word === 'cls') pushToken(tokens, 'literal', word)
      else if (PYTHON_BUILTINS.has(word)) pushToken(tokens, 'builtin', word)
      else if (/^[A-Z]/.test(word)) pushToken(tokens, 'class-name', word)
      else if (next?.[1] === '(') pushToken(tokens, 'function', word)
      else pushPlain(tokens, word)
      index += word.length
      continue
    }
    pushPlain(tokens, source[index]!)
    index += 1
  }
  return tokens
}

function highlightJavascript(source: string): Token[] {
  const tokens: Token[] = []
  let index = 0
  while (index < source.length) {
    const rest = source.slice(index)
    const lineComment = rest.match(/^\/\/.*?(?=\n|$)/)
    if (lineComment) {
      pushToken(tokens, 'comment', lineComment[0])
      index += lineComment[0].length
      continue
    }
    const blockComment = rest.match(/^\/\*[\s\S]*?\*\//)
    if (blockComment) {
      pushToken(tokens, 'comment', blockComment[0])
      index += blockComment[0].length
      continue
    }
    const string = rest.match(/^(`(?:\\.|[^`\\])*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/)
    if (string) {
      pushToken(tokens, 'string', string[0])
      index += string[0].length
      continue
    }
    const number = rest.match(/^(0[xX][\da-fA-F]+|\d+(\.\d+)?([eE][+-]?\d+)?)/)
    if (number) {
      pushToken(tokens, 'number', number[0])
      index += number[0].length
      continue
    }
    const ident = rest.match(/^[A-Za-z_$]\w*/)
    if (ident) {
      const word = ident[0]
      if (JS_KEYWORDS.has(word)) pushToken(tokens, 'keyword', word)
      else if (/^[A-Z]/.test(word)) pushToken(tokens, 'class-name', word)
      else if (/^\s*\(/.test(source.slice(index + word.length))) pushToken(tokens, 'function', word)
      else pushPlain(tokens, word)
      index += word.length
      continue
    }
    pushPlain(tokens, source[index]!)
    index += 1
  }
  return tokens
}

function highlightJson(source: string): Token[] {
  const tokens: Token[] = []
  let index = 0
  while (index < source.length) {
    const rest = source.slice(index)
    const string = rest.match(/^"(?:\\.|[^"\\])*"/)
    if (string) {
      const after = source.slice(index + string[0].length).match(/^\s*:/)
      pushToken(tokens, after ? 'attr' : 'string', string[0])
      index += string[0].length
      continue
    }
    const number = rest.match(/^-?\d+(\.\d+)?([eE][+-]?\d+)?/)
    if (number) {
      pushToken(tokens, 'number', number[0])
      index += number[0].length
      continue
    }
    const literal = rest.match(/^(true|false|null)\b/)
    if (literal) {
      pushToken(tokens, 'keyword', literal[0])
      index += literal[0].length
      continue
    }
    pushPlain(tokens, source[index]!)
    index += 1
  }
  return tokens
}

function highlightBash(source: string): Token[] {
  const tokens: Token[] = []
  let index = 0
  while (index < source.length) {
    const rest = source.slice(index)
    const comment = rest.match(/^#.*?(?=\n|$)/)
    if (comment) {
      pushToken(tokens, 'comment', comment[0])
      index += comment[0].length
      continue
    }
    const string = rest.match(/^("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/)
    if (string) {
      pushToken(tokens, 'string', string[0])
      index += string[0].length
      continue
    }
    const flag = rest.match(/^--?[A-Za-z][\w-]*/)
    if (flag) {
      pushToken(tokens, 'attr', flag[0])
      index += flag[0].length
      continue
    }
    pushPlain(tokens, source[index]!)
    index += 1
  }
  return tokens
}

function renderTokens(tokens: Token[]) {
  return tokens
    .map((token) => {
      const text = escapeHtml(token.text)
      return token.kind ? `<span class="token token-${token.kind}">${text}</span>` : text
    })
    .join('')
}

function normalizeLanguage(lang?: string) {
  const value = (lang || '').trim().toLowerCase()
  if (!value) return 'text'
  if (['py', 'python', 'python3'].includes(value)) return 'python'
  if (['js', 'javascript', 'jsx'].includes(value)) return 'javascript'
  if (['ts', 'typescript', 'tsx'].includes(value)) return 'typescript'
  if (['sh', 'bash', 'shell', 'zsh'].includes(value)) return 'bash'
  if (['json', 'jsonc'].includes(value)) return 'json'
  if (['txt', 'text', 'plain'].includes(value)) return 'text'
  return value
}

export function highlightCode(code: string, lang?: string) {
  const language = normalizeLanguage(lang)
  let tokens: Token[]
  switch (language) {
    case 'python':
      tokens = highlightPython(code)
      break
    case 'javascript':
    case 'typescript':
      tokens = highlightJavascript(code)
      break
    case 'json':
      tokens = highlightJson(code)
      break
    case 'bash':
      tokens = highlightBash(code)
      break
    default:
      return escapeHtml(code)
  }
  return renderTokens(tokens)
}

export function languageClass(lang?: string) {
  return `language-${normalizeLanguage(lang)}`
}
