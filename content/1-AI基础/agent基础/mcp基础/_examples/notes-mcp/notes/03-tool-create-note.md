# Tool create_note：创建文档调用实录

本篇来自对 `learning-notes` 的真实 stdio MCP 调用；本次协商协议为 `2025-11-25`。文档保存到服务端持久化的 `notes/` 目录。

## 1. 这次要完成什么

把搜索、读取、资源和提示模板的真实调用整理为 Markdown 文档，实际保存到笔记目录。工具返回成功后，再通过 `read_note` 回读并与待保存内容逐字核对。

## 2. 一次已经完成的创建调用

本次先创建同组的搜索实录，调用工具为 `create_note`。参数中的 `filename` 为：

```json
{
  "filename": "01-tool-search-notes.md"
}
```
另一个参数 `content` 是该搜索实录的完整 Markdown 正文，可以打开同组文件查看。这里省略长正文，避免重复嵌套整篇文档；上面的 JSON 只是参数节选，单独执行时仍需提供 `content`。

## 3. 该次实际返回

在生成本文之前，上述搜索实录已经成功创建并完成回读核对。`structuredContent` 的实际值为：

```json
{
  "filename": "01-tool-search-notes.md",
  "bytes_written": 1836
}
```
`bytes_written` 是 UTF-8 字节数，不是汉字或字符数量。调用方已经将其与完整正文编码后的长度核对，并确认读回内容一致。

## 4. 本篇自身如何保存

本文也由同一个 `create_note` 工具创建，保存后由客户端再次调用 `read_note` 核对全文。三篇 Tool 实录、一篇 Resource 实录和一篇 Prompt 实录均采用这个保存流程。

## 5. 文件行为

- 文件实际保存到示例服务的持久 `notes/` 目录，不是自动验收用的临时目录。
- 工具采用独占新建方式，同名文件不会被覆盖。
- 调用方发现整组名称已存在时，会选择新的编号后缀。
- 工具负责保存收到的 Markdown；正文组织和学习总结由助手完成。

`create_note` 的返回结果说明文件写入操作已完成；回读核对进一步验证此次保存的内容。读取 Resource 或获取 Prompt 本身都不会创建文件，需要继续调用这个工具完成保存。

## 同组实录

- [Tool：搜索笔记](./01-tool-search-notes.md)
- [Tool：读取笔记](./02-tool-read-note.md)
- [Tool：创建笔记](./03-tool-create-note.md)
- [Resource：笔记库说明](./04-resource-notes-guide.md)
- [Prompt：生成学习总结](./05-prompt-summarize-note.md)
