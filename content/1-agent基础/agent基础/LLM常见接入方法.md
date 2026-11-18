# LLM 常见接入方法

本文面向刚开始使用 Apifox、编写接口脚本或测试 Agent 的读者，说明如何把大语言模型接入自己的程序，以及接入后需要处理哪些问题。

文档核对日期：2026-11-17。平台接口、SDK 和模型能力会变化，具体以各节链接的官方文档及账户权限为准。

> 本文提供概念和示例，没有实际调用付费模型、下载模型或部署服务。示例中的模型名、地址和凭证需要替换；Python 代码需要对应依赖及环境变量，不能在未配置时直接运行。

## 1. “接入 LLM”究竟是接入什么？

接入 LLM，就是让你的程序能够向模型提交输入，取得文本、结构化数据、工具调用请求或其他输出，并把结果用于业务。

例如，客服系统收到用户问题后，由后端调用模型，再把回答展示给用户。

需要区分三个对象：

- **模型**：真正生成内容的能力，例如某个平台提供的文本生成模型。
- **模型服务**：负责加载或托管模型，并提供可调用的接口。
- **LLM 应用 / Agent**：在模型之外，还可能组合提示词、知识检索、记忆、工具和工作流。

调用模型接口，通常需要自己组织上下文和业务流程；调用一个已经发布的 Agent 接口，则可能由该应用完成这些工作。

**接入成功、模型生成成功、业务任务完成、结果正确，是不同的判断点。**

## 2. 常见接入方式怎么分类？

这些方式并不互斥，可以叠加使用。

### 2.1 按模型由谁提供

- **模型厂商 API**：直接调用 OpenAI、Anthropic、Google、DeepSeek 等服务。
- **企业云或托管平台**：通过 Azure、Amazon Bedrock、Google Cloud、阿里云百炼等平台接入。
- **自部署模型服务**：在自己的机器或服务器上运行模型，通过 Ollama、vLLM 等提供接口。
- **进程内推理**：程序直接加载模型权重，不经过 HTTP 模型服务。

### 2.2 按程序怎么调用

- **原始 HTTP API**：自己构造 URL、请求头和请求体。
- **官方 SDK**：通过厂商提供的 Python、JavaScript 等库调用。
- **兼容接口**：通过约定的 API 格式接入其他厂商或本地服务。
- **模型网关**：通过统一入口调用多个模型或供应商。
- **应用框架**：使用 LangChain 等封装模型调用，再组合检索、工具和流程。
- **应用平台 API**：直接调用已经发布的聊天应用、工作流或 Agent。

### 2.3 按交互模式

普通请求响应、SSE 等流式输出、异步批处理、实时双向通信，都可以用于模型接入。它们解决的是“结果怎样交付”，不是“模型由谁提供”。

例如，“Python SDK + 兼容接口 + 本地 vLLM + 流式返回”是一组可以同时成立的选择。输出方式详见 [接口常见输出方式](./接口常见输出方式.md)。

## 3. 开始前需要准备什么？

先从平台控制台或接口文档确认以下信息：

1. **接口地址**：区分基础地址 `base_url` 和完整调用地址。不要重复拼出 `/v1/v1` 或 `/chat/completions/chat/completions`。
2. **认证方式**：API Key、Bearer Token、云身份凭证或平台规定的其他方式。
3. **模型标识**：请求使用的精确名称，有时是部署名称或推理配置编号，而不是界面展示名。
4. **接口类型**：Responses、Chat Completions、Messages、GenerateContent 等，请求结构不能混用。
5. **能力与限制**：是否支持流式、图片、工具调用、结构化输出，以及上下文、输出长度、配额限制。
6. **运行条件**：云接口需要网络和权限；本地模型需要权重、推理运行时和足够内存或显存。

模型名不要照抄旧教程。先选择账户实际可调用的模型，再确认它支持本节示例使用的 API。

长期 API Key 通常放在服务端环境变量或密钥管理服务中。浏览器前端如需直接连接实时接口，应使用该平台专门提供的短期凭证机制，不能把长期密钥写入网页代码。

本文示例采用如下变量命名：

- `LLM_CHAT_URL`：兼容 Chat Completions 的完整 URL。
- `LLM_BASE_URL`：供兼容 SDK 使用的基础地址。
- `LLM_API_KEY`、`LLM_MODEL`：该模型服务的凭证与模型标识。
- `OPENAI_API_KEY`、`OPENAI_MODEL`：OpenAI 原生接口示例使用的配置。
- `OLLAMA_MODEL`：已在本地可用的 Ollama 模型名称。

这些变量不会因为出现在文档中就自动生效，需要在运行环境中事先配置。

## 4. 方法一：直接调用 HTTP API

### 4.1 适合什么场景？

适合在 Apifox 中验证接口、编写简单脚本，或使用没有对应 SDK 的语言。它也最方便观察真实的请求和响应。

下面以 **Chat Completions 兼容接口** 为例，并非所有模型服务都采用此格式。

请求体示例：

```json
{
  "model": "替换为服务端支持的模型标识",
  "messages": [
    {"role": "system", "content": "请用简洁中文回答。"},
    {"role": "user", "content": "什么是 RESTful？"}
  ],
  "stream": false
}
```

如果服务要求 Bearer 认证，通常同时配置：

```http
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

不要把 `<API_KEY>` 当作真实密钥。其他原生 API 可能使用不同认证头。

### 4.2 Python HTTP 示例

安装依赖：`python -m pip install requests`。

以下代码适用于返回 Chat Completions 结构的普通文本请求：

```python
import os
import requests

response = requests.post(
    os.environ["LLM_CHAT_URL"],
    headers={
        "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
        "Content-Type": "application/json",
    },
    json={
        "model": os.environ["LLM_MODEL"],
        "messages": [{"role": "user", "content": "用一句话解释 LLM。"}],
        "stream": False,
    },
    timeout=(10, 60),
)
response.raise_for_status()
result = response.json()

choices = result.get("choices") or []
if not choices:
    raise RuntimeError("响应没有 choices，请核对接口类型和业务错误。")
message = choices[0].get("message", {})
if message.get("tool_calls"):
    raise RuntimeError("返回了工具调用，需要进入工具执行流程。")
if not isinstance(message.get("content"), str):
    raise RuntimeError("未取得文本回答，请检查完整响应和结束原因。")
print(message["content"])
```

这里的 10 和 60 分别是连接、读取超时配置，并非整个任务最多执行 70 秒。示例未做自动重试；接入实际业务时，应单独设计重试和业务完成检查。

兼容调用方式可参考 [DeepSeek：首次 API 调用](https://api-docs.deepseek.com/)；HTTP 客户端超时含义见 [Requests：超时说明](https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts)。

## 5. 方法二：使用厂商官方 SDK

SDK 将认证、请求序列化、响应对象和部分错误处理封装成代码接口。它通常仍在通过网络调用远端服务，并不会因为安装了 SDK 就把模型安装到本地。

### 5.1 OpenAI 原生 Responses API

安装依赖：`python -m pip install openai`。配置 `OPENAI_API_KEY` 和支持 Responses API 的 `OPENAI_MODEL`。

```python
import os
from openai import OpenAI

client = OpenAI(timeout=60.0, max_retries=0)
response = client.responses.create(
    model=os.environ["OPENAI_MODEL"],
    input="请用三句话解释什么是大语言模型。",
)
print(response.output_text)
```

`response.output_text` 是 SDK 提供的文本汇总属性；不要假定原始 HTTP JSON 一定有同名顶层字段，也不要把它套用到 Chat Completions 响应上。

该最小示例关闭自动重试，方便首次调试观察一次调用。正式代码还应检查响应状态，以及拒绝、未完成或工具调用等情况。参见 [OpenAI 官方快速入门](https://developers.openai.com/api/docs/quickstart) 和 [Python SDK](https://developers.openai.com/api/reference/python)。

### 5.2 Anthropic 原生 Messages API

常用官方 Python 包为 `anthropic`，典型调用入口为 `client.messages.create(...)`。原生请求使用 `model`、`messages`、`max_tokens` 等字段，系统提示通常放在独立的 `system` 字段，而不是照搬其他接口的系统消息写法。

输出中的 `content` 是内容块列表，可能同时包含文本、工具使用等不同类型。不要假定第一块必然是最终文字，也不要读取不存在的 `choices[0]`。

参见 [Claude：Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python) 和 [Messages API](https://platform.claude.com/docs/en/api/messages)。

### 5.3 Google Gemini 原生 API

官方 Python 包为 `google-genai`。GenerateContent 接口的典型调用入口为 `client.models.generate_content(...)`，使用 `contents` 等输入字段；官方也提供 Interactions 等接口，具体选择应与模型和应用需要匹配。

不同 API 的输入结构、会话状态和输出对象并不相同。使用 GenerateContent 时，不要直接粘贴 Chat Completions 的 `messages` 请求体；使用 Interactions 时，也不要套用 GenerateContent 的响应解析路径。

参见 [Gemini：快速入门](https://ai.google.dev/gemini-api/docs/quickstart)、[GenerateContent API](https://ai.google.dev/api/generate-content) 和 [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/)。

### 5.4 SDK 和 HTTP API 怎么选？

初次排查先用 Apifox 或一个最小 HTTP 请求确认参数；编写正式程序时，可选官方 SDK 减少重复工作。SDK 的自动重试、超时和日志行为也需要了解，避免与外层重试叠加。

## 6. 方法三：通过 OpenAI 兼容接口接入其他模型

“兼容 OpenAI”通常表示服务实现了部分相似的路径、请求字段和响应结构，便于复用 SDK 或现有应用。

常见做法是调整三项：**基础地址、凭证、模型标识**。

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
    timeout=60.0,
    max_retries=0,
)
response = client.chat.completions.create(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "user", "content": "介绍一下你能处理哪些任务。"}],
)
print(response.choices[0].message.content)
```

示例按“成功返回纯文本”的最小路径展示。生产代码仍需处理空内容、工具调用、结束原因和业务错误。

使用 OpenAI SDK 不等于请求发给 OpenAI；真实目的地取决于配置的 `base_url`。

### 兼容范围需要逐项确认

- 支持 Chat Completions，不代表同时支持 Responses 或其他 API。
- 支持文本，不代表支持图片、工具调用、结构化输出或实时音频。
- 支持同名参数，不代表默认值、取值范围或行为完全相同。
- 请求能发通，不代表流式事件、用量字段、错误格式和模型行为一致。

DeepSeek、阿里云百炼和部分自部署服务提供兼容接口，但地址可能与区域、工作空间或产品入口相关，应从当前官方文档复制。参考 [DeepSeek 接入说明](https://api-docs.deepseek.com/)、[百炼 OpenAI Chat 接口兼容](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)。

## 7. 方法四：通过企业云平台接入

适合已经使用云账号、区域部署、统一权限或企业网络的团队。除了模型名和 Key，还要处理云平台的资源配置。

### 7.1 Azure / Microsoft Foundry

通常先创建资源并部署模型，再使用对应端点和部署标识调用。认证可涉及 API Key 或 Microsoft Entra ID。

Azure 的不同 API 代际存在差异；当前 v1 接口不再要求按旧方式填写带日期的 `api-version` 参数。不要把旧教程中的路径、版本参数和新 SDK 配置混用。参见 [Azure OpenAI v1 API](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle)。

### 7.2 Amazon Bedrock

通过 AWS 的区域、模型访问权限和身份凭证接入。Converse 和 ConverseStream 提供消息式调用入口，后者用于流式交互；某些能力也有模型专用参数。

AWS SDK 可以处理请求签名和凭证链，不能默认把普通 Bearer Key 示例原样用于 Bedrock。参见 [Bedrock：Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)。

### 7.3 Google Cloud 与其他企业平台

Google Cloud 的托管模型入口需要关注项目、位置、启用的服务、身份权限和模型标识。它与仅使用 Gemini 开发者 API Key 的调用方式不能混为一谈。参见 [Google Cloud：模型接入入门](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start)。

国内企业平台同样要确认区域、工作空间、模型权限和实际端点。不要假定一个区域的 Key 能访问所有其他区域。

## 8. 方法五：通过模型网关或聚合服务接入

网关为应用提供统一入口，后面连接多个模型服务。它可以负责模型别名、鉴权、限流、日志、用量统计、路由和故障切换。

例如，应用请求逻辑模型名 `customer-support`，网关再把它映射到实际供应商和模型部署。

LiteLLM 提供统一调用库和可自部署网关，是此类方案的一个例子。参见 [LiteLLM 官方文档](https://docs.litellm.ai/docs/)。

接入时重点确认：

- `base_url` 和 Key 属于网关还是上游厂商？
- 逻辑模型名最终映射到哪个模型和版本？
- 网关是否完整转发流式消息、工具字段和用量信息？
- 自动切换模型后，回答、延迟和支持能力是否发生变化？
- 重试由网关、SDK 还是业务层负责，是否会叠加？

统一入口可以降低改代码的成本，但不能自动保证不同模型的效果一致。请求和响应也会经过网关，应将其纳入数据访问和日志管理范围。

## 9. 方法六：本地或私有服务器部署模型服务

### 9.1 Ollama：通过本地 HTTP 接口调用

适合个人实验、桌面开发或较简单的内部部署。先安装并启动 Ollama，准备一个适合设备、已下载到本地的模型，再调用服务。

本地原生聊天地址通常为 `http://localhost:11434/api/chat`。下面使用 `requests`，并通过 `stream: false` 获取完整响应：

```python
import os
import requests

response = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": os.environ["OLLAMA_MODEL"],
        "messages": [{"role": "user", "content": "用一句话解释 RAG。"}],
        "stream": False,
    },
    timeout=(10, 120),
)
response.raise_for_status()
print(response.json()["message"]["content"])
```

原生接口支持流式返回，相关接口默认流式时采用逐行 JSON；这里显式关闭流式，避免把多行数据当成一个 JSON 解析。参见 [Ollama：Chat API](https://docs.ollama.com/api/chat) 和 [流式说明](https://docs.ollama.com/api/streaming)。

Ollama 也提供兼容入口，例如本地 `http://localhost:11434/v1/`。其支持范围是 OpenAI API 的子集；原生接口与兼容接口的响应格式、流式格式不能混用。参见 [Ollama：兼容接口](https://docs.ollama.com/api/openai-compatibility)。

**“访问 localhost”不必然代表模型在本地推理。** 如果选择了云模型或转发配置，仍可能调用远端。需要离线运行时，应确认权重和计算都在本地，且没有额外联网依赖。

### 9.2 vLLM：部署面向服务调用的推理接口

适合在匹配的硬件和运行环境上部署模型，供多个应用调用。部署方需要管理模型权重、设备支持、内存或显存、并发和服务访问控制。

基础服务启动命令形式如下，需先配置模型标识或路径：

```bash
vllm serve "$VLLM_MODEL" --host 127.0.0.1 --port 8000
```

该示例只绑定本机。其他应用可以按实际部署配置访问兼容接口；聊天模型还需要正确的 chat template（对话模板），不是所有权重都可直接作为聊天接口使用。

这里不提供通用的安装或 GPU 参数，因为它们取决于硬件、模型和 vLLM 版本。参见 [vLLM：在线服务](https://docs.vllm.ai/en/stable/serving/online_serving/)。

### 9.3 本地部署不等于没有成本

除了设备，还要承担启动加载、推理延迟、并发排队、监控和更新维护。模型量化能改变内存占用，也可能改变质量；应在真实任务和目标设备上验证。

## 10. 方法七：程序内直接加载模型

程序通过 Transformers 等库加载 tokenizer（分词器）和模型权重，在同一进程内生成结果，不先部署 HTTP 服务。

常见流程是：加载模型与分词器 → 按模型模板组织消息 → 转成输入 token → 调用生成方法 → 解码新生成的 token。

适合离线实验、研究和需要控制推理细节的任务。相比 API 调用，需要自己处理：

- 模型授权、下载、依赖和硬件适配。
- 聊天模板、停止条件及输入输出长度。
- 并发、内存和错误恢复。
- 区分输入提示词和新增输出，避免把输入重复当作回答。

不要用一个随意拼接的字符串替代模型要求的聊天模板。官方实现参考 [Transformers：文本生成](https://huggingface.co/docs/transformers/en/llm_tutorial)。

## 11. 方法八：通过 LangChain 等框架接入

框架在模型调用上方增加抽象，帮助组织消息、检索、工具和运行流程。它仍然需要底层模型服务及对应权限。

以 LangChain 的模型接口为例，常见操作包括 `invoke()` 获取结果、`stream()` 获取流式输出；模型由相应供应商集成提供。参见 [LangChain：Models](https://docs.langchain.com/oss/python/langchain/models)。

适合需要组合多步逻辑、统一模型调用或构建 Agent 的项目。使用框架之前，建议先独立调用模型成功，再加入框架，便于判断问题来自模型服务还是封装层。

框架统一了部分代码接口，但不保证所有模型都支持相同能力。更换模型后仍需重测工具调用、上下文、输出解析和流式行为。

## 12. 方法九：直接调用现成应用、工作流或 Agent API

例如，在 Dify 或企业自建平台中发布一个应用后，由业务系统调用其 API。

此时调用方通常提供问题、用户标识、会话标识和业务输入，而平台内部可能执行知识检索、模型调用及工具操作。

应先确认：

- 当前 Key 对应哪个应用，而不是默认认为它是模型厂商 Key。
- 输入参数叫 `query`、`inputs` 还是其他名称。
- 会话由谁创建和维护，用户标识如何隔离。
- 返回的是最终答案、工作流事件还是任务编号。
- 工具、知识库和模型版本由谁配置。

参见 [Dify：API 接入入门](https://docs.dify.ai/en/api-reference/guides/get-started)。

前面截图中的 `/agent/sse` 路径更像一个应用接口的命名，但仅凭路径不能确认内部架构。应根据接口文档判断它接收的是模型原生参数，还是业务层封装后的参数。

## 13. 多轮对话、流式、批处理和实时接入

### 13.1 多轮对话：决定上下文由谁维护

常见方式有两类：

- **客户端传历史**：每次带上需要保留的用户消息、助手回复和工具结果。
- **服务端维护状态**：通过平台规定的响应编号、会话编号或其他状态引用继续对话。

对于无状态的聊天调用，只发“继续”，服务端通常无法凭空知道上一轮讨论什么。也不能随意添加 `conversation_id` 就假定模型服务支持会话。

管理历史时要考虑上下文长度、摘要、费用和用户隔离；摘要可能丢失信息，不能只检查接口是否调用成功。

### 13.2 流式输出：按事件逐步接收

流式返回适合逐字展示和较长生成。以下是 OpenAI Responses API 的文本流示例，其他 API 不能直接套用事件名。

```python
import os
from openai import OpenAI

client = OpenAI(timeout=60.0, max_retries=0)
completed = False
with client.responses.create(
    model=os.environ["OPENAI_MODEL"],
    input="请简要解释 HTTP 与 REST 的关系。",
    stream=True,
) as stream:
    for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)
        elif event.type == "response.completed":
            completed = True
        elif event.type in {"response.failed", "response.incomplete", "error"}:
            raise RuntimeError(f"生成未正常完成：{event.type}")
if not completed:
    raise RuntimeError("未收到完成事件，需要检查连接或服务状态。")
print()
```

该示例关注文本增量和生命周期；需要工具调用、拒绝或其他模态时，还应处理对应事件。参见 [OpenAI：流式响应](https://developers.openai.com/api/docs/guides/streaming-responses)。

不同接口可能返回 SSE、NDJSON 或其他格式；`stream: true` 本身不能确定协议。流在中途断开时，已经显示的内容应视为可能不完整。

如果使用 Python Requests，还要区分两个开关：JSON 请求体里的 `"stream": true` 是向模型服务请求流式生成；`requests.post(..., stream=True)` 则控制客户端如何读取响应。只设置其中一个，不等于完成了端到端流式处理。接收端还需要按 SSE 或 NDJSON 等格式解析完整消息，而不是把每个网络字节块当成一条 JSON。

### 13.3 异步批处理

适合离线评测、批量标注和大规模摘要，不要求每条结果立即返回。

典型流程是准备输入记录、提交批任务、查询状态、下载结果，再按自定义请求编号关联原始数据。不能假定结果顺序与提交顺序相同，也要逐条检查失败情况。示例机制见 [OpenAI：Batch API](https://developers.openai.com/api/docs/guides/batch)。

“同时发出多个普通请求”和“使用厂商 Batch API”是两种不同做法；前者仍要自己管理并发、限流和重试。

SDK 的 `async/await` 也主要是程序的非阻塞调用方式，不代表厂商一定创建了一个可稍后查询的后台任务。

### 13.4 实时语音和双向交互

持续语音、打断和低延迟交流可使用厂商专门的 Realtime / Live 接口。传输可能采用 WebRTC、WebSocket 等，不能只给普通聊天接口加 `stream: true` 就认为实现了实时语音。

需要额外处理音频编码、采样率、输入结束、说话轮次、取消和连接生命周期。能力示例见 [OpenAI：Realtime API](https://developers.openai.com/api/docs/guides/realtime)。

## 14. 结构化输出、工具调用、RAG 和 MCP

它们会影响接入设计，但不是彼此替代的网络协议。

### 14.1 结构化输出：让程序可以稳定读取字段

“接口外层是 JSON”与“模型回答符合指定 JSON Schema”是两回事。例如 `{"output":"这里是一段随意文本"}` 的外层合法，不代表模型内容可按业务字段解析。

需要结构化结果时，使用服务明确支持的 Schema 或结构化输出能力，仍要处理拒绝、截断和校验失败。格式符合 Schema，也不保证字段里的事实正确。参见 [OpenAI：结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs)。

### 14.2 Tool Calling：模型提出调用请求，程序负责执行

自定义工具的常见流程：

1. 应用向模型说明工具名称、用途和参数结构。
2. 模型返回工具调用请求及参数。
3. 应用验证参数和权限，再执行实际函数或业务接口。
4. 应用将结果与对应调用编号一起回传。
5. 模型继续生成答案，必要时再次调用工具。

模型输出“调用查询函数”并不代表数据库已经被查询；执行者通常是应用或工具平台。内置托管工具的执行方则由厂商机制决定。要设置超时、循环上限并处理失败。参见 [OpenAI：工具调用](https://developers.openai.com/api/docs/guides/function-calling)。

### 14.3 RAG：先检索资料，再让模型回答

RAG 通常包含文档处理、检索，以及把相关片段提供给生成模型的过程。向量检索可能需要独立的 Embedding 模型，重排序也可能使用另一种模型；它们的输入输出与聊天生成不同。

调用 Embedding API 得到的是向量，不是自然语言答案。接通聊天模型，也不等于模型已经能查询企业知识库。测试时应分别检查检索命中、上下文内容和最终回答。

### 14.4 MCP：连接工具和上下文能力

MCP 用于规范应用与工具、资源等能力之间的交互。常见架构中，应用一边调用模型，一边通过 MCP 使用外部能力；接通 MCP 服务不等于已经配置好文本生成模型。

MCP 有自己的协议能力和生命周期，不是 Chat Completions 的替代字段格式。参见 [MCP：架构说明](https://modelcontextprotocol.io/docs/learn/architecture)。

### 14.5 多模态：图片、音频和文件的输入输出

先确认模型和 API 支持所需模态，再按该接口约定传递内容块、文件编号、可访问 URL 或编码后的数据。把本地路径直接写进提示词，不会自动让远端模型读到文件。

多模态接入还需确认文件类型、大小、音频编码或采样率、上传后的使用方式，以及输出究竟是文字、文件字节还是下载地址。上传成功不代表模型已经分析了文件；接入视觉模型也不代表它支持所有音频或视频任务。能力和输入形式示例见 [Gemini：模型输入与能力入门](https://ai.google.dev/gemini-api/docs/quickstart)。

## 15. 常见参数与响应字段怎样理解？

### 输入参数

- **model**：模型标识，某些平台使用部署名或其他字段。
- **messages / input / contents**：不同 API 表达输入的方式，不能互换。
- **system / instructions / developer**：不同接口放置行为指令的方式，支持范围和优先级按接口定义。
- **temperature / top_p**：影响采样行为；不保证所有模型支持，降低温度也不保证结果完全确定。
- **max_tokens / max_completion_tokens / max_output_tokens**：不同接口的生成预算参数，含义和是否计入推理 token 要单独确认；token 数不是汉字数。
- **stream**：请求流式行为，具体输出格式按接口约定。
- **tools / tool_choice**：描述可用工具或控制调用选择，需要模型与服务共同支持。

### 响应信息

- **正文**：可能是字符串、内容块列表，也可能没有正文而返回工具调用。
- **完成原因 / 状态**：区分正常结束、长度截断、工具调用、拒绝和失败。
- **usage**：Token 用量等计量信息，各平台字段和统计方式可能不同。
- **请求编号**：用于排查问题和关联日志，不等于会话编号。

应为每种接口建立明确的解析规则，不要写一个“所有平台都取 `output`”的通用假设。跨平台公共概念可参考 [LangChain：模型能力与接口](https://docs.langchain.com/oss/python/langchain/models)，实际字段仍以厂商原生 API 为准。

## 16. 用 Apifox 验证最小接入

以支持 Chat Completions 格式的接口为例：

1. 在环境中配置基础地址、模型标识和密钥。
2. 新建 HTTP 请求，选择 POST，按服务文档填写完整地址。
3. 在 Auth 中配置服务要求的认证方式。
4. 在 Body → JSON 中填写 `model`、一条用户 `messages`，先设置 `stream: false`。
5. 发送后确认状态码、正文、完成原因和用量，不只检查“有没有字”。
6. 成功后再验证 `stream: true`，根据实际 Content-Type 选择解析方式。
7. 最后加入多轮、图片、Schema 或工具等能力，每次只增加一个变量，便于定位问题。

如果测的是 Agent 应用，应使用它的业务请求体，不能直接把模型 API 的 `messages` 粘进去。界面说明见 [Apifox 的使用方法](./Apifox的使用方法.md)。

## 17. 常见错误与排查顺序

- **401 / 403**：核对认证方式、凭证有效性、模型权限和资源权限，不是简单地一直重发。
- **404**：检查域名、接口路径、部署名称，以及是否重复拼接 `/v1`。
- **400 / 422**：检查请求结构、参数支持情况、角色、工具格式和长度限制。
- **429**：区分请求频率、Token 速率、并发或配额等限制，按服务规则退避；不能一律理解为“余额不足”。
- **5xx / 超时**：检查服务状态、网络、代理和模型加载情况，结合请求编号排查。
- **JSON 解析失败**：先确认返回的是普通 JSON，还是 SSE、NDJSON 或代理错误页面。
- **响应有内容但程序读不到**：检查是否用了另一个 API 的解析路径，或实际返回工具调用、拒绝信息。
- **流式直到最后才显示**：检查服务端、网关、代理和客户端是否在缓冲。
- **本地调用慢或内存不足**：检查模型规模、量化、设备、上下文长度、并发及首次加载。

错误码的具体业务含义可能不同，以上是排查方向。重试应有次数上限和退避，避免多层自动重试造成重复计费或重复业务操作。

## 18. 接入验收与选择建议

### 验收重点

- **基础可用性**：认证成功，模型标识正确，输入和输出解析符合协议。
- **功能覆盖**：普通文本、多轮、流式、结构化和工具等实际需要的能力均验证通过。
- **异常处理**：失效凭证、超时、限流、断流、截断、拒绝和工具失败都能正确报告。
- **业务质量**：使用固定测试集检查正确性、格式、引用和任务完成情况。
- **性能与成本**：记录首个有效输出时延、总耗时、并发表现和平台用量；不把心跳算作首段答案。
- **可追溯性**：记录供应商、实际模型或部署版本、SDK 版本、关键配置和请求编号；对凭证及敏感正文做适当处理。

### 从需求出发选择

- 第一次学习或排查：先用 Apifox / HTTP 验证最小请求。
- 常规后端功能：使用对应厂商 SDK，或经过验证的兼容 SDK。
- 已有企业云体系：优先评估现有托管模型入口与权限体系。
- 需要多供应商统一管理：评估网关，并验证切换后的质量差异。
- 需要离线或自主管理部署：评估 Ollama、vLLM 或进程内推理，并核算硬件和运维条件。
- 需要检索、工具和工作流：在模型接通后引入框架，或调用已经发布的应用 API。
- 离线大批量任务：评估 Batch API；实时语音则评估专用实时接口。

进一步阅读：[RESTful 使用方法](./RESTful使用方法.md)、[接口常见输出方式](./接口常见输出方式.md)。
