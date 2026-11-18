# RESTful 使用方法

## 1. RESTful 是什么意思？

**RESTful 是一种接口设计风格。** 在常见的 HTTP API 中，它围绕“资源”组织接口，通过 URL 标识资源，通过 HTTP 请求方法表达操作，再通过状态码和响应内容反馈结果。

REST 是 **Representational State Transfer** 的缩写，常译为“表现层状态转移”。RESTful 表示符合 REST 风格。平时说的“RESTful 方法”，通常是在说这种风格下使用的 GET、POST、PUT、PATCH、DELETE 等 **HTTP 请求方法**。

例如，针对同一个用户：

- `GET /users/123`：查看用户 123。
- `PATCH /users/123`：修改用户 123 的部分信息。
- `DELETE /users/123`：删除用户 123。

这里 `/users/123` 标识“哪个资源”，GET、PATCH、DELETE 表达“对它做什么”。

RESTful 不是一种编程语言，也不需要在 Apifox 中打开某个“RESTful 开关”。日常所说的 REST API 有时只是采用了部分 REST 原则的 HTTP API；使用 HTTP 或 JSON，并不能单独证明接口完整遵循 REST。参见 [MDN：REST](https://developer.mozilla.org/zh-CN/docs/Glossary/REST)。

> 本文所有地址、字段和响应都是教学示例，不是现有业务接口的真实定义。`https://api.example.com` 是示例域名，需要替换为实际服务地址才能调试。

## 2. 先认识三个概念

### 2.1 资源：接口要处理的对象

用户、订单、文件、会话、消息、Agent 任务，都可以建模为资源。资源不必对应某一张数据库表。

例如：

- `/users`：用户集合。
- `/users/123`：编号为 123 的用户。
- `/conversations/456/messages`：会话 456 下的消息集合。

用复数名词命名集合是一种常见约定，不是只要用了复数就满足 REST。

### 2.2 资源表示：通过网络传递的数据

服务器内部保存的用户对象，可以用 JSON 表示给客户端：

```json
{
  "id": 123,
  "name": "小林",
  "email": "lin@example.com"
}
```

JSON 是资源的一种表示格式。REST 没有规定只能使用 JSON，也可以使用 XML、图片等格式。

### 2.3 一次请求：方法、地址、请求头和请求体

可以把一次调用拆成四部分理解：

- **方法**：做什么，例如 POST。
- **URL**：访问哪里，例如 `https://api.example.com/users`。
- **Headers**：数据格式、身份凭证等附加信息。
- **Body**：提交的具体内容，例如新用户的姓名和邮箱；不是每次请求都需要 Body。

资源与接口命名的设计参考 [Microsoft：RESTful Web API 设计最佳做法](https://learn.microsoft.com/zh-cn/azure/architecture/best-practices/api-design)。

## 3. 常见请求方法怎么用？

下面用“用户管理”贯穿说明。**调用已有接口时，始终按接口文档选择方法，不能自行改成你认为更合理的方法。**

### 3.1 GET：查询资源

查询一个用户：

```http
GET /users/123
```

查询用户列表并分页：

```http
GET /users?page=1&page_size=10
```

其中 `123` 是路径中的资源编号，`page` 和 `page_size` 是查询参数。分页参数名称由接口自己约定。

GET 按语义用于读取，不应拿它完成删除用户等修改操作。GET 请求体没有通用定义，普通查询条件通常放在 Query 中。

### 3.2 POST：提交数据，由服务端处理

创建用户的示例：

```http
POST /users
Content-Type: application/json

{
  "name": "小林",
  "email": "lin@example.com"
}
```

假设创建成功，接口可以返回：

```http
HTTP/1.1 201 Created
Location: /users/123
Content-Type: application/json

{
  "id": 123,
  "name": "小林",
  "email": "lin@example.com"
}
```

`Location` 指出新资源的地址。POST 也可用于提交复杂查询、发起任务等处理，不能把它一律理解为“插入一条数据库记录”。

### 3.3 PUT：整体替换目标资源

假设示例接口规定用户的完整可写信息只有姓名和邮箱：

```http
PUT /users/123
Content-Type: application/json

{
  "name": "林同学",
  "email": "new-lin@example.com"
}
```

PUT 表达“把这个资源设成我提交的完整状态”。如果字段缺失，服务端如何处理要看接口约定，不能默认保留旧值。目标不存在时，服务端也可能允许 PUT 在该地址创建资源。

### 3.4 PATCH：局部修改目标资源

假设示例接口约定 PATCH 接受普通 JSON 对象，只修改姓名：

```http
PATCH /users/123
Content-Type: application/json

{
  "name": "林同学"
}
```

本例中的邮箱保持不变。**PATCH 不规定所有接口都采用这种 JSON 写法**，有些要求 JSON Patch 或 JSON Merge Patch 等格式，具体 Content-Type 和内容必须以接口文档为准。参见 [RFC 5789：PATCH](https://www.rfc-editor.org/rfc/rfc5789.html)。

### 3.5 DELETE：删除目标资源

```http
DELETE /users/123
```

成功时可以返回 `204 No Content`，表示成功但没有响应正文。实际业务采用物理删除还是标记删除，由后端决定。

上述 HTTP 方法语义参考 [RFC 9110：请求方法](https://www.rfc-editor.org/rfc/rfc9110.html#section-9)。HEAD、OPTIONS、TRACE 等方法也可以用于 HTTP 接口，它们的含义见 [Apifox 的使用方法](./Apifox的使用方法.md)。

## 4. 参数应该放在哪里？

以“更新用户资料”为例：

- **Path**：标识哪一个用户，如 `/users/123` 中的 `123`。
- **Query**：表达筛选、分页等条件，如 `/users?page=1`。
- **Headers / Auth**：表达格式和认证信息，如 `Authorization: Bearer {{token}}`。
- **Body**：携带提交的数据，如 `{"name":"林同学"}`。

这几个位置不能随意互换。例如，接口从 JSON Body 读取 `name`，你把它填到 Query 中，服务端可能仍然报“缺少 name”。

两个请求头尤其容易混淆：

- `Content-Type: application/json`：我发送的 Body 是 JSON。
- `Accept: application/json`：我希望收到 JSON 响应。

一个 POST 请求可以同时使用 Query、Headers 和 Body，不是只能选其中一种。

## 5. 返回结果怎么看？

先看 HTTP 状态码，再结合响应内容判断业务结果。

- **200 OK**：请求成功，常用于查询或更新。
- **201 Created**：成功创建资源。
- **202 Accepted**：已接受处理，任务可能尚未完成。
- **204 No Content**：成功，没有响应正文。
- **400 Bad Request**：请求有问题，如格式不合法。
- **401 Unauthorized**：缺少有效认证凭证，或凭证已失效。
- **403 Forbidden**：服务器拒绝访问，常见于权限不足。
- **404 Not Found**：目标资源未找到，也可能是路径写错。
- **405 Method Not Allowed**：该目标不支持所用方法，检查 GET、POST 等是否选对。
- **409 Conflict**：请求与资源当前状态冲突。
- **415 Unsupported Media Type**：请求内容格式不受支持，检查 Body 类型和 Content-Type。
- **429 Too Many Requests**：触发请求频率限制。
- **500 Internal Server Error**：服务端发生未预期的错误。

状态码含义参见 [MDN：HTTP 响应状态码](https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Reference/Status)。

有些项目还会在 JSON 中返回业务码，例如 `{"code":0,"message":"成功"}`。**业务字段 `code` 不是 HTTP 状态码**，其含义由项目约定；测试时不能只看到 HTTP 200 就认定业务一定成功。

## 6. “无状态”和“幂等”是什么意思？

### 6.1 无状态：每次请求都能被独立理解

每次请求应提供理解和处理它所需的信息，例如目标资源、操作内容和认证凭证，不依赖服务器记住上一次交互留下的隐含上下文。

**无状态不等于服务器不能保存数据。** 用户、订单、任务结果等资源状态仍可保存。需要区分“保存业务资源”与“依靠服务端会话记住客户端目前走到哪一步”。

例如，请求中明确指定用户编号，比让服务器根据“这个客户端上一条请求查了谁”来猜测目标更清晰。仅仅使用 Token 或携带会话编号，并不能证明整套 API 已满足无状态约束。

### 6.2 幂等：重复执行的预期效果与执行一次相同

例如，把姓名设置成“小林”，执行多次仍然是“小林”；新建一个用户的请求执行多次，则可能创建多个用户。

- GET、HEAD、OPTIONS、TRACE、PUT、DELETE 按 HTTP 标准语义是幂等的。
- POST、PATCH 不保证幂等；PATCH 是“设为某个值”还是“在原值上增加”，效果可能不同。
- 幂等不要求每次响应相同。例如第一次 DELETE 成功，第二次返回 404，并不必然违反幂等性。

“安全方法”则表示客户端没有请求修改资源，GET、HEAD、OPTIONS、TRACE 属于这一类。这里的“安全”不是“无需认证”或“绝对没有风险”。DELETE 可以幂等，但不是安全方法。

方法属性参考 [RFC 9110：通用方法属性](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2)。调试 POST 超时时，先确认服务端是否已经执行；只有接口提供了去重或幂等机制，才能按约定使用，不能假定再次发送一定不会重复创建。

## 7. REST 不只是“名词 URL + 增删改查”

入门时先掌握资源和 HTTP 方法即可，但严格的 REST 还包含以下约束：

1. **客户端与服务端分离**：界面与服务实现可以分别演进。
2. **无状态**：每次请求具有足够的处理上下文。
3. **可缓存性**：响应应说明是否可以缓存，不是要求所有数据都缓存。
4. **统一接口**：统一识别资源、通过表示操作资源、让消息自描述，并通过超媒体指导后续操作。
5. **分层系统**：客户端可以通过网关、代理等中间层访问服务。
6. **按需代码（可选）**：服务端可以向客户端提供可执行代码。

“超媒体”可以先理解为：响应提供相关资源链接或可用操作，引导客户端继续交互，而不只是返回几个数据字段。不是加一个任意的 `links` 字段就自动满足完整 REST 约束。

因此，评估接口时应区分“采用常见资源式 HTTP 设计”与“严格满足全部 REST 约束”。无状态及这些架构约束的原始定义见 [Fielding：REST 架构风格](https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm)。

## 8. 在 Apifox 中怎么调用？

以第 3 节的“创建用户”接口为例：

1. 新建 HTTP 请求，选择 **POST**。
2. 输入实际服务的用户集合地址，示例形式为 `https://api.example.com/users`。
3. 如果接口需要 Bearer 认证，在 **Auth → Bearer Token** 中填写有效令牌或已赋值的 `{{token}}`。
4. 打开 **Body → JSON**，只粘贴下面的 JSON，不要把 `POST /users` 和请求头一起粘进去。

   ```json
   {
     "name": "小林",
     "email": "lin@example.com"
   }
   ```

5. 检查请求 Content-Type 为 `application/json`，避免手工配置与工具生成的值冲突。
6. 发送后检查是否符合接口约定，例如返回 201、新用户编号和正确字段。
7. 用返回的编号发送 `GET /users/{id}`，确认资源可读；需要时再验证 PATCH、DELETE。

如果调用失败，按“方法和地址 → 参数位置 → 认证 → Body 格式 → 响应信息”的顺序排查。具体界面配置见 [Apifox 的使用方法](./Apifox的使用方法.md)。

## 9. Agent 接口也可以采用 RESTful 风格吗？

可以。下面是一种示意设计，把一次 Agent 执行建模为“任务资源”，而不是要求所有 Agent 服务都使用这些路径。

**第一步：提交任务。**

```http
POST /agent-tasks
Content-Type: application/json

{
  "question": "请汇总本周工单",
  "knowledge_base_ids": ["kb-demo"]
}
```

假设服务端接受任务并异步处理，可以返回 `202 Accepted`，提供任务编号 `task-001`，以及状态查询地址 `/agent-tasks/task-001`。

**第二步：查询任务状态。**

```http
GET /agent-tasks/task-001
```

示例响应：

```json
{
  "id": "task-001",
  "status": "completed",
  "result": "本周共收到 18 条工单。"
}
```

这里的 `status` 是示例业务字段，实际取值以接口约定为准。首次返回 202 只表示接受处理，不能据此认定 Agent 已完成工作。

如果现有接口使用 `POST /agent/sse` 并流式返回答案，调试时仍按它的真实约定调用。**SSE 描述事件流的传输方式，REST 描述接口架构风格，两者讨论的层面不同。** 单看路径中有 `sse`，或请求方法是 POST，无法判断它是否完整遵循 REST。

测试 Agent 时还应区分：HTTP 调用成功、任务完成、回答正确，是三个不同的判断点。接口返回 200，也不代表回答一定准确或完整。
