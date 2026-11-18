# Tool search_notes：搜索笔记调用实录

本篇来自对 `learning-notes` 的真实 stdio MCP 调用；本次协商协议为 `2025-11-25`。文档保存到服务端持久化的 `notes/` 目录。

## 1. 这次要完成什么

查找笔记库中与“生成器”有关的资料，获得可以继续读取的文件名。以下结果来自生成这组实录之前的搜索，当时目录中包含两份原始示例笔记。

## 2. 实际调用

客户端通过 `tools/call` 调用 `search_notes`，参数为：

```json
{
  "query": "生成器",
  "limit": 5
}
```
## 3. 实际返回

调用成功，`isError` 为 `false`，`structuredContent` 为：

```json
{
  "matches": [
    {
      "filename": "python.md",
      "line": 1,
      "excerpt": "# Python 生成器"
    }
  ],
  "truncated": false
}
```
## 4. 如何理解结果

- `filename` 是命中文件名，本次是 `python.md`，可以直接交给 `read_note`。
- `line` 是匹配行号，本次第 1 行标题包含“生成器”。
- `excerpt` 是命中行的片段，不是文件全文。
- `truncated: false` 表示此次结果没有因返回数量限制被截断。

本服务按关键词匹配正文，不做同义词或语义检索；每个文件最多返回第一处命中。生成本组文档后，再搜索“生成器”可能同时命中这些新文档，因此不能把这次的一条结果当作永远固定的结果。

## 5. 下一步

依据返回的 `filename`，实际调用 `read_note` 读取 `python.md`。完整返回见同组“读取笔记”实录。

## 同组实录

- [Tool：搜索笔记](./01-tool-search-notes.md)
- [Tool：读取笔记](./02-tool-read-note.md)
- [Tool：创建笔记](./03-tool-create-note.md)
- [Resource：笔记库说明](./04-resource-notes-guide.md)
- [Prompt：生成学习总结](./05-prompt-summarize-note.md)
