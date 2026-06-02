# Web API 接口清单与浏览器流程

> **前置阅读**: `CLAUDE.md` → `docs/architecture.md` → `docs/web/layering.md`
>
> 谁读这份: 写 `app/api/*` 的 route.ts,或写 UI 时需要调接口的人。

---

## 1. 接口清单

| Method | Path | 鉴权 | 说明 |
|---|---|---|---|
| POST   | `/api/v1/jobs` | user | 提交 prompt + base64,触发生成,立刻返回 requestId |
| GET    | `/api/v1/jobs/[requestId]` | user | 轮询任务状态(stage / progress / status) |
| POST   | `/api/v1/albums/[uuid]/retry` | user | 失败相册复用同一 albumId 重跑(浏览器重传 base64)|
| GET    | `/api/v1/albums` | user | 我的相册列表 |
| GET    | `/api/v1/albums/[uuid]` | user | 单个相册详情(含所有页)|
| PATCH  | `/api/v1/albums/[uuid]` | user | 改标题等基础字段 |
| DELETE | `/api/v1/albums/[uuid]` | user | 删除相册 |
| PATCH  | `/api/v1/albums/[uuid]/pages/[idx]` | user | 编辑器保存单页 |
| POST   | `/api/v1/albums/[uuid]/chat` | user | Chat 编辑(同步,Web 转 Agent /v1/chat-edit) |
| GET    | `/api/v1/albums/[uuid]/messages` | user | 拉对话历史 |
| POST   | `/api/v1/albums/[uuid]/pdf-upload-url` | user | 签 R2 PUT URL |
| PUT    | `/api/v1/albums/[uuid]/pdf` | user | 上传完成后通知服务端 |
| GET    | `/api/v1/albums/[uuid]/pdf` | user | 拿当前 PDF 下载 URL |
| GET    | `/api/v1/credit/balance` | user | 当前积分 |
| GET    | `/api/v1/credit/history` | user | 积分流水 |
| POST   | `/api/v1/internal/job-progress` | agent | Agent 进度回调 |
| GET    | `/api/v1/health` | none | 健康检查 |
| POST   | `/api/webhooks/stripe` | sig | Stripe 回调 |
| POST   | `/api/webhooks/creem` | sig | Creem 回调 |

---

## 2. 统一响应

成功:
```json
{ "ok": true, "data": { ... } }
```

失败:
```json
{ "ok": false, "error": { "code": "CREDIT_INSUFFICIENT", "message": "..." } }
```

错误码完整表 → `docs/web/errors.md §2`。

---

## 3. 关键接口详细

### 3.1 `POST /api/v1/jobs`

请求:
```json
{
  "requestId": "req_xxx",
  "prompt": "我和妈妈在京都的春天",
  "language": "zh",
  "photos": [
    {
      "photoId": "p1",
      "base64": "data:image/jpeg;base64,/9j/4AAQ...",
      "width": 800,
      "height": 600
    }
  ]
}
```

约束:
- `requestId` 由**浏览器生成**(UUID v4),用于轮询 key 和全链路追踪。服务端校验格式后透传给 Agent。
- `photos.length` ∈ [1, 30](架构 §6.5 决策 6:下限 3→1)
- 每张 base64 ≤ 800KB
- `prompt` ≤ 500 字

服务端流程(**fire-and-forget**,不阻塞,详见 `docs/agent/contract.md §2.1`):

1. `requireAuth`
2. `parseBody`(zod 校验上面约束)
3. `creditService.precheck(userId, cost)`,不足 → `CREDIT_INSUFFICIENT`
4. 事务里:
   - `albumService.create({ userId, status: 'AGENT_RUNNING', prompt, photoCount })` → 拿 `albumId`
   - `jobService.create({ albumId, userId, requestId, status: 'QUEUED' })`
   - `creditService.hold(tx, userId, cost, albumId)` —— 预留积分:写 `credit_holds`(HOLDING)+ 0-delta `GENERATION_HOLD` ledger,**余额此刻不变**,生成完成时才 settle 扣费(见 §3.3)
5. `agentClient.submitLayout(...)`,Agent 5 秒内 202 接单(不等结果)。**提交失败不抛错**:`handleFailed`(退 hold + album 回 `FAILED`)后仍返回 `albumId`(§6.5.3 不孤儿化),浏览器跳 `/album/{albumId}` 即见可重试的失败卡
6. 把 `agent_jobs.status` 标 `RUNNING`,返回 `{ albumId, requestId }` 给浏览器
7. **本次 HTTP 请求到此结束**。Web 函数在 ≤ 8 秒内退出。终态由 Agent 后续 callback 写入,见 §3.3。

> **关键约定**:
> - 终态(completed / failed)由 **Agent callback** 写入 — 见 §3.3。
> - route.ts 仍 ≤ 40 行: 步骤 3-6 全部抽到 `generationService.submit(userId, input)`,route 只调一次 service。
> - **浏览器侧**:POST 拿到 `requestId` 后立刻 `router.push(/album/${albumId})`,在那个页面里开始 2 秒一次轮询 `GET /api/v1/jobs/[requestId]`。
> - **Vercel 函数超时**:不再是问题。函数执行 < 10 秒,Hobby/Pro 套餐都够。

响应(步骤 6):
```json
{ "ok": true, "data": { "albumId": "alb_xxx", "requestId": "req_xxx" } }
```

### 3.1a `POST /api/v1/albums/[uuid]/retry`

失败相册重试(§6.5.3):**复用同一 albumId 重跑**,不新建 album、不孤儿化失败卡。

请求(无 `prompt` —— 复用 album 里存的 prompt;浏览器从 IndexedDB 重传 base64,守不变式 1;`photos` ≥1 张,对齐 CT-1 §6.5.6,1–2 图走纯文字版面):
```json
{
  "requestId": "req_yyy",
  "language": "zh",
  "photos": [ { "photoId": "p1", "base64": "data:image/jpeg;base64,...", "width": 800, "height": 600 } ]
}
```

服务端流程(`generationService.retry`,与 §3.1 `submit` 共用 `dispatch` 尾段):
1. `requireAuth` + `albumService.findOwned`(归属校验 + 取 `prompt`)
2. `creditService.precheck`,不足 → `CREDIT_INSUFFICIENT`(前端跳 `/credits` 充值后回来再点重试 —— `/credits` 才是充值入口,非 `/pricing`)
3. 事务里(守不变式 8):
   - `albumService.setRetrying(tx, albumId)` —— 条件转移 `FAILED → AGENT_RUNNING` 并清空 `errorMessage`;非 FAILED(已在跑 / 输掉并发重试)→ `ALBUM_NOT_RETRIABLE`(409),回滚不占 hold
   - `jobService.create` —— **新 requestId 的新 job**(旧 FAILED job 保留;`findLatestByAlbum` 取新的)
   - `creditService.hold` —— **新 hold**(旧 hold 在失败时已 release)
4. `dispatch`:提交 Agent → job `QUEUED → RUNNING`;提交失败则 `handleFailed`(退 hold + album 回 FAILED)后**返回 `albumId` 不抛错**(§6.5.3 不孤儿化)—— album 已存在,前端拿到 id 重载即见可重试的失败卡

响应:`{ ok: true, data: { albumId, requestId } }`(同 §3.1)。即使 Agent 提交失败也返回 `albumId`(此时 album 已是 `FAILED`),浏览器据此打开失败卡。

> 浏览器侧:重试成功后 album 已回 `AGENT_RUNNING`,重新进入 §4.1 的轮询。哪些 photoId 属于这本相册由浏览器在创建时记下(`albumRecipe`),原图仍只在 IndexedDB;换设备 / 清缓存导致原图丢失时,前端提示"重新开始"而非提交残缺集(`photosFromStore` 任一原图缺失即 `PhotosUnavailableError` 中止,绝不提交残缺集)。

### 3.2 `GET /api/v1/jobs/[requestId]` (轮询)

浏览器每 2 秒拉一次,直到拿到终态。

响应:
```json
{
  "ok": true,
  "data": {
    "requestId": "req_xxx",
    "albumId": "alb_xxx",
    "status": "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED",
    "stage": "vision" | "writing" | "composing" | null,
    "progress": 0-100,
    "error": { "code": "...", "message": "..." } | null
  }
}
```

实现要点:
- 仅 `jobRepo.findByRequestId(requestId)` 一次,无副作用。
- `requireAuth` 后**校验归属**:`job.userId === user.id`,否则 403。
- 浏览器在 `status` ∈ `{COMPLETED, FAILED}` 时停止轮询;前者跳编辑页,后者展示错误。
- **不**做 long-poll。这是个纯 GET,完全无状态,Vercel 上必然工作。

### 3.3 `POST /api/v1/internal/job-progress`

**只能被 Agent 调用**。接收 progress / completed / failed 三类事件。

Header: `Authorization: Bearer ${AGENT_SHARED_SECRET}`

请求体(统一信封,见 `docs/agent/contract.md §2.1`):
```json
{
  "requestId": "req_xxx",
  "event": "progress" | "completed" | "failed",
  "stage": "vision" | "writing" | "composing",
  "progress": 30,
  "message": "...",
  "layout": { ... },
  "error": { "code": "...", "message": "..." },
  "usage": { "visionTokens": ..., "planningTokens": ..., "durationMs": ... }
}
```

服务端流程:
1. 校验 Bearer,失败 → 401 `AGENT_UNAUTHORIZED`
2. zod 校验 envelope
3. `jobRepo.findByRequestId(requestId)` — 找不到 → 404
4. **幂等检查**:若 `agent_jobs.status` 已是 `COMPLETED`/`FAILED`,直接返回 `{ ok: true }`(忽略重复 callback)
5. 按 `event` 分发(全部走 `jobService`):
   - `progress`:更新 `agent_jobs.stage` / `progress` / `updated_at`
   - `completed`:事务里 ——
     - zod 校验 `layout`(`AlbumLayoutPlan`)
     - `albumRepo.update(albumId, { layoutJson, title, status: 'EDITING' })`
     - `albumPageRepo.bulkInsert(albumId, layout.pages)`
     - `creditService.settle(tx, userId, album.creditHoldId)` —— 结算 §3.1 建立的 hold,**此刻才扣减积分**(写负向 `GENERATION_SETTLE` ledger;对已 SETTLED 的 hold 幂等)
     - `jobRepo.update(jobId, { status: 'COMPLETED', usage, completedAt: now })`
   - `failed`:事务里 ——
     - `albumRepo.update(albumId, { status: 'FAILED', errorMessage: error.message })`
     - `creditService.releaseByAlbum(tx, albumId)` —— 按 album 找到 hold 释放,**不扣费**(写 0-delta `GENERATION_RELEASE` ledger)
     - `jobRepo.update(jobId, { status: 'FAILED', error, completedAt: now })`
6. 返回 `{ ok: true }`

> 浏览器**不**直接收这个 callback,而是靠下次轮询拿到 `status` 变更。

完整 Agent 协议 → `docs/agent/contract.md`。

### 3.4 `GET /api/v1/albums/[uuid]`

**这是生成进度的真相源**:浏览器按 album uuid 轮询此接口(不再按 job requestId)。`album.status`(`AGENT_RUNNING` / `EDITING` / `COMPLETED` / `FAILED`)驱动整个界面。

服务端(`albumService.getDetail`):
1. `requireAuth`
2. `albumService.findOwned(user.id, uuid)` → 自动校验归属(归属不符 → 403 `ALBUM_NOT_OWNED`,不存在 → 404 `ALBUM_NOT_FOUND`)
3. 若 `status === 'AGENT_RUNNING'`:`jobService.resolveGeneration(albumId)` 取该 album **最新 job** 的 `stage`/`progress`;同时做**读时机会式收尸**——最新 job 距上次进度/启动 > 5 分钟仍无终态,当场标 album `FAILED` + 释放积分(复用 `handleFailed`),返回的 `status` 即为 `FAILED`。见 [`docs/agent/design.md §7`](../agent/design.md)。
4. 查 `album_pages`(按 `page_index asc`)
5. 返回:

```json
{
  "ok": true,
  "data": {
    "album": { "id": "...", "title": "...", "status": "EDITING", "layoutJson": {...}, "errorMessage": null },
    "pages": [ { "pageIndex": 0, "templateId": "cover-01", "imagesJson": {...}, "textsJson": {...} } ],
    "generation": { "stage": "composing", "progress": 80 }
  }
}
```

- `generation`:仅 `status === 'AGENT_RUNNING'` 且最新 job 仍在跑时为 `{ stage, progress }`;其余情况(已终态 / 被收尸 / 无 job)为 `null`。
- `generation` 是 additive 字段,join 自最新 job;**不**落 album 表(无 migration),也**不**改 web↔agent callback 契约。

### 3.5 `PATCH /api/v1/albums/[uuid]/pages/[idx]`

编辑器只 PATCH **单页**,不整体 PUT layout_json。

请求:
```json
{ "textsJson": { "title": "新标题" } }
```
或:
```json
{ "imagesJson": { "hero": "p2" } }
```

服务端:
1. 校验归属
2. `albumPageRepo.update(tx, ...)`

### 3.5a `POST /api/v1/albums/[uuid]/chat`

Chat 编辑入口。**同步**:用户在 chat 框里等 AI 回复,不轮询。

请求:
```json
{
  "message": "把第二页副标题改得更感性一些",
  "language": "zh"
}
```

约束:
- `message` ≤ 500 字
- 同一相册并发 chat → 后到的 409 `CHAT_BUSY`(防止 patch 互相覆盖)

服务端流程(`route.ts` ≤ 40 行,业务全在 `chatService`):

1. `requireAuth`
2. `albumService.findOwned(user.id, uuid)` —— 校验归属;`album.status === 'EDITING'` 才允许 chat,否则 409
3. **不**再 precheck 积分(生成时一次 hold 已包编辑期)
4. `albumMessageRepo.findRecent(albumId, limit=20)` —— 拉最近对话
5. `chatService.edit(user.id, albumId, message)`,内部:
   - 拼 Agent 入参:`{ albumId, currentLayout: albums.layout_json, history, userMessage: message, language }`
   - 调 `agentClient.chatEdit(payload)`(60s 超时,见 `docs/agent/contract.md §2.3`)
   - 事务里:
     - `albumMessageRepo.insert({ role: 'user', content: message })`
     - 把 `layoutPatch` apply 到 `album_pages`(只 PATCH 受影响的行)
     - 把 patch 写回 `albums.layout_json`
     - `albumMessageRepo.insert({ role: 'assistant', content: assistantReply, layoutPatch, usage })`
6. 返回:

```json
{
  "ok": true,
  "data": {
    "assistantReply": "已经把第二页副标题改成「春天总是来得太早」。",
    "layoutPatch": [
      { "pageIndex": 1, "textsJson": { "subtitle": "春天总是来得太早" } }
    ],
    "messageId": "msg_xxx"
  }
}
```

> `layoutPatch` 字段用**浏览器侧**命名 `imagesJson` / `textsJson`(与 §3.4 GET detail、§3.5 PATCH pages 一致)。Agent↔Web 契约内部用 `images` / `texts`;Web 在 `chatService.toBrowserPatch()` 翻译成 `imagesJson` / `textsJson` 后才返回浏览器、落 `album_messages.layoutPatch`。

> 浏览器拿到 `layoutPatch` 后**就地更新本地 store**,不需要刷整本 album。

错误码:
- `CHAT_BUSY`(409)—— 同 album 还有在跑的 chat
- `AGENT_CHAT_FAILED`(502)—— Agent 调 DeepSeek 失败 / repair 失败
- `ALBUM_NOT_EDITABLE`(409)—— album.status 不是 EDITING

### 3.5b `GET /api/v1/albums/[uuid]/messages`

拉对话历史,供编辑器 chat 面板渲染。

Query: `?limit=50&before=msg_xxx`(分页,默认 50,按 `created_at desc`)

响应:
```json
{
  "ok": true,
  "data": {
    "messages": [
      { "id": "msg_001", "role": "user", "content": "...", "createdAt": "..." },
      { "id": "msg_002", "role": "assistant", "content": "...", "layoutPatch": [...], "createdAt": "..." }
    ]
  }
}
```

实现要点:
- 校验归属
- 仅查不写

### 3.6 `POST /api/v1/albums/[uuid]/pdf-upload-url`

签一个 R2 presigned PUT URL,浏览器拿来直传。

请求:
```json
{ "contentType": "application/pdf", "size": 4500000 }
```

约束:
- size ≤ 50MB
- 5 分钟过期

响应:
```json
{
  "ok": true,
  "data": {
    "putUrl": "https://r2.../pdfs/u123/alb_xxx.pdf?X-Amz-...",
    "r2Key": "pdfs/u123/alb_xxx.pdf",
    "publicUrl": "https://cdn.yujeeai.com/pdfs/u123/alb_xxx.pdf"
  }
}
```

### 3.7 `PUT /api/v1/albums/[uuid]/pdf`

浏览器上传完后调,通知服务端。

请求:
```json
{ "r2Key": "pdfs/u123/alb_xxx.pdf" }
```

服务端:
1. 校验归属
2. 校验 r2Key 是否真的存在(HEAD 一次 R2)
3. 事务: `albums.pdf_r2_key` 写入 + `status='COMPLETED'`(**不动积分**——积分已在生成完成时 settle,见 §3.3;PDF confirm 不再 settle)

---

## 4. 浏览器侧三个核心流程

### 4.1 生成流程

```
1. 用户在 /create 选 1-30 张照片
   → photosStore.add(File)

2. 浏览器压缩 → base64
   → lib/photo/compress.ts: Canvas 缩到 800px, quality 0.6
   → photosStore.setBase64(photoId, base64)

3. 点"开始制作":
   3a. 浏览器先生成 requestId = crypto.randomUUID()
   3b. POST /api/v1/jobs { requestId, prompt, language, photos }
       → 这个请求在 5-10 秒内返回 { albumId, requestId }
       → Agent 已经在后台开始跑了

4. POST 响应回来:
   → router.push(`/album/${albumId}`)   // 只带 uuid,不带 job id

5. 相册页 mount:
   useAlbumPoll(uuid) — 每 15 秒 GET /api/v1/albums/[uuid]
       → album.status 驱动界面(单一真相源):
         · AGENT_RUNNING → 用 data.generation.{stage,progress} 渲染"AI 在看图/写文/排版"
         · EDITING / COMPLETED → 用同一份 data.{album,pages} 直接渲染编辑器(无需二次拉取)
         · FAILED → 显示 album.errorMessage + 重试 CTA
       → 终止语义见 §5
```

> 浏览器**不**开 SSE/WebSocket。真相源是 album(按 uuid 寻址、带归属校验、自带 4 态 status、扛 job 清理),**不是** URL 里的 job requestId。一份响应同时带 `album`/`pages`/`generation`,生成完成即就地渲染,不再二次 `GET`。1000 用户阶段最坏:1000 人同时生成 → ~70 QPS 轮询(15s 间隔),Vercel + Neon 都扛得住。

### 4.2 编辑流程

编辑分两种入口:**直接 PATCH**(精确改) vs **Chat 对话**(自然语言改)。

```
1. 编辑页加载
   → GET /api/v1/albums/[uuid]
   → GET /api/v1/albums/[uuid]/messages (拉对话历史,渲染 chat 面板)
   → 拿到 layoutJson + pages + messages[]

2. 从 IndexedDB 按 photoId 加载原图 blob URL
   → photosStore 提供 blob URL 缓存

3a. 用户直接改文案(双击就地编辑)
    → PATCH /api/v1/albums/[uuid]/pages/0 { textsJson: { title: "新" } }
    → 乐观更新本地 store,失败回滚

3b. 用户拖图换位置
    → PATCH /api/v1/albums/[uuid]/pages/0 { imagesJson: { hero: "p3" } }

4. 用户在 Chat 面板里说"把第二页副标题改感性点"
   → POST /api/v1/albums/[uuid]/chat { message }
   → 等(loading)~5-20s
   → 拿到 { assistantReply, layoutPatch }
   → 本地按 patch 就地更新 album_pages store(不需要刷全 album)
   → chat 面板追加 user + assistant 两条
```

> 编辑期间(`album.status === 'EDITING'`)**不再扣积分**,生成时那一笔 hold 包了。

### 4.3 PDF 导出

```
1. 用户点"导出 PDF"

2. 浏览器组合 layoutJson + 原图,用 @react-pdf/renderer 生成 Blob
   → lib/pdf/render.ts

3. POST /api/v1/albums/[uuid]/pdf-upload-url { contentType, size }
   → 拿到 { putUrl, r2Key, publicUrl }

4. PUT putUrl  (浏览器直接 PUT Blob 到 R2)
   Content-Type: application/pdf
   Body: Blob

5. PUT /api/v1/albums/[uuid]/pdf { r2Key }
   → 服务器结算积分,album.status='COMPLETED'

6. 显示下载链接 = publicUrl
```

---

## 5. 轮询实现注意点

轮询对象是 `GET /api/v1/albums/[uuid]`(`useAlbumPoll`),**不是** `/api/v1/jobs/[requestId]`。

- 间隔:固定 15 秒。不做指数退避——简单优先。生成期间用户在等,15s 足够跟手;终态立即停。
- **终止语义**(确定性错误必须暴露,不再静默无限重试):
  - 200 + `AGENT_RUNNING` → 继续轮询
  - 200 + `EDITING` / `COMPLETED` → 停,渲染编辑器
  - 200 + `FAILED` → 停,显示 `album.errorMessage`
  - **401** → 致命:停,跳 `/login?from=/album/[uuid]`
  - **403 / 404** → 致命:停,报错(别人的 / 已删)
  - **5xx / fetch 异常** → 临时:有限重试(连续 4 次封顶)→ 仍失败才报错
- 软上限:仍 `AGENT_RUNNING` 超过 6 分钟(已过服务端 5 分钟收尸窗口)→ 停轮询 + "还在生成,刷新查看",**绝不写失败**。
- **服务端收尸双保险**(完整设计见 [`docs/agent/design.md §7`](../agent/design.md)):
  - 读时机会式:`GET /api/v1/albums/[uuid]` 与 `listByUser` 发现 `AGENT_RUNNING` 且最新 job > 5 分钟无终态 → 当场标 FAILED + 退积分。服务在线用户。
  - 每日 `recover-stuck` cron(`zombieSweeper`,10 分钟阈值):兜底"用户一去不回"的相册,保证积分最终释放。
- **不**用 Node runtime 的任何流式特性;都是普通 Route Handler。
- `GET /api/v1/jobs/[requestId]` 仍保留(后台 / 调试可用),但**不再是浏览器轮询路径**。

---

## 6. 限流(第一版只做最简单的)

放在 Vercel Edge Middleware 里:
- 单用户 60 秒内最多 5 次 `POST /api/v1/jobs`
- 单 IP 1 分钟内最多 60 次任意 `/api/v1/*`

实现可以用 Upstash Ratelimit(免费额度够 1000 用户)。

---

## 7. 自查

- [ ] 我的 route.ts 行数 ≤ 40?
- [ ] 我的请求/响应字段是 camelCase(TS 层)?
- [ ] 我把业务逻辑全放进 service 了吗?
- [ ] 错误是用 `ERRORS.XXX()` 抛的吗?
- [ ] `POST /jobs` 是 fire-and-forget,函数执行 < 10 秒?
- [ ] `job-progress` callback 做了幂等检查?
- [ ] 修改了接口,有没有同步 `packages/contracts`?
