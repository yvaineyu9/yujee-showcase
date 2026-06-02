# Yujee 架构(入口文档)

> 这是项目的入口骨架。**不要在这份文档里塞细节**——所有规范、目录、协议、schema 都拆到了子文档里,按需加载。
>
> 阅读方法见根目录 `CLAUDE.md`。

---

## 0. 产品基线

| 项 | 值 |
|---|---|
| 产品名 | Yujee(遇己)|
| 域名 | yujeeai.com |
| 形态 | AI 人生纪念册 Web 应用,海外市场,英文 UI |
| 用户路径 | 输入文字 + 选照片 → AI 排版 → 用户编辑 → 浏览器导出 PDF |
| 初期容量目标 | 1000 用户(简单优先)|
| 长期容量目标 | 10 万用户(预留扩展,但**第一版不实施**)|

---

## 1. 系统切分:三个组件

```
┌─────────────────────┐        ┌──────────────────────┐         ┌──────────────────┐
│      Browser        │        │  Web (Next.js 15)    │         │ Agent (FastAPI)  │
│                     │        │                      │         │                  │
│ • 选照片            │        │ • 页面/登录/积分/支付 │         │ • 调火山识图     │
│ • 浏览器压缩 base64 │ ─────► │ • 转发图片到 Agent   │ ──────► │ • 调 DeepSeek 排版│
│ • 轮询 job 状态     │ ◄───── │ • 保存排版 JSON      │ ◄────── │ • 推 progress    │
│ • 编辑/Chat 修改    │ ─────► │ • Chat 转发 Agent    │ ──────► │ • Chat-Edit 同步 │
│ • 本地渲染 PDF      │ ◄───── │ • 写 album_messages  │ ◄────── │ • 推终态 callback│
│ • PDF 上传 R2       │ ─────► │ • PDF 上传/分发      │         │ • 不存任何数据   │
└─────────────────────┘        └──────────────────────┘         │ • 无状态         │
                                         │                       └──────────────────┘
                                         ▼
                              ┌──────────────────────┐
                              │ Postgres (Neon)      │
                              │ R2 (Cloudflare)      │
                              └──────────────────────┘
```

### 1.1 三个组件的职责边界

**Browser**
- 唯一拥有原图的地方。原图永远不出浏览器。
- Canvas 压缩到 800px、quality 0.6 → base64 data URL 作为"特征载体"。
- 拿到排版 JSON 后用 React 模板渲染预览。
- 编辑 / Chat 修改时,把当前 layout 摘要 + 用户消息发给 Web。
- 用户点导出 → 浏览器本地用 `@react-pdf/renderer` 生成 PDF → 直传 R2。

**Web (Next.js)**
- 唯一与用户、数据库、支付打交道的组件。
- 收到 base64 后**不落盘、不存 R2、不写日志**,直接转发给 Agent。
- 保存的是排版 JSON + Chat 对话历史(`album_messages`),不是图片。
- Chat 编辑请求转发给 Agent(同步),拿到 layout patch 后写回 DB。
- PDF 上传走 R2 presigned PUT,Web 不过 PDF 流量。

**Agent (FastAPI)**
- 无状态服务。无数据库连接。无文件系统持久化。
- 两个端点:
  - `POST /v1/layout` — 异步(BackgroundTask + callback),首次生成,见 §2
  - `POST /v1/chat-edit` — 同步(用户在等回复),基于当前 layout + 对话历史出 patch
- 接收 base64 数组 + 用户文本 → 火山识图 → DeepSeek 排版 → 返回 JSON。
- 不直接被浏览器调用,只被 Web 调用。

### 1.2 为什么这样切

1. **图片不落盘** —— 用户隐私是核心承诺。Web 和 Agent 都不存原图。
2. **Web 不做 AI** —— Next.js serverless 不适合长任务和大依赖。
3. **Agent 不碰用户数据** —— Agent 只看到 base64 和文本,挂掉只影响生成,不影响登录/支付/已有作品。
4. **PDF 在浏览器生成** —— 原图始终在本地。Web 只签 URL,不接 PDF 流量。

---

## 2. Web ↔ Agent 协议(骨架)

Agent 暴露**两个端点**,工作模式不同:

### 2.1 首次生成 — `POST /v1/layout`(异步)

- **传输模式**:异步 HTTP(Web 立刻返回,Agent 后台跑,浏览器轮询拿状态)
- **入口**:`POST https://agent.yujeeai.com/v1/layout` — Agent 接单后立刻 `202 Accepted` 返回,在后台 task 里跑
- **进度 / 终态回推**:Agent → Web `POST /api/v1/internal/job-progress`,事件类型 `progress` / `completed` / `failed`
- **浏览器侧**:不开长连接、不开 SSE。每 2 秒轮询 `GET /api/v1/jobs/[requestId]` 拿 `stage` / `progress` / `status`,看到 `COMPLETED` / `FAILED` 停轮询

### 2.2 Chat 编辑 — `POST /v1/chat-edit`(同步)

- **传输模式**:同步 HTTP(用户在 chat 里等回复,无需轮询)
- **入口**:`POST https://agent.yujeeai.com/v1/chat-edit`
- **入参**:当前 `layoutJson` + 对话历史(最近 N 条)+ 用户新消息 + language
- **出参**:`{ newLayout 或 layoutPatch, assistantReply, usage }`
- **浏览器侧**:用户发消息 → 转 Web → Web 转 Agent → 拿到 patch 后 Web 写 `album_messages` + 更新 `album_pages`,返回给浏览器渲染
- **超时**:60 秒(同步要等)

### 2.3 共通

- **鉴权**:Bearer Token,共享密钥 `AGENT_SHARED_SECRET`,两个端点都用
- **超时**:Web → Agent `/v1/layout` 接单 5 秒;`/v1/chat-edit` 60 秒;Agent → 外部模型 30 秒,重试 1 次;Agent → Web callback 10 秒,重试 2 次

**为什么不用 SSE**:Vercel serverless 多 lambda 实例,进程内 EventEmitter 无法跨实例,SSE 接收端和回调接收端不在同一进程,**1 个用户就不通**。轮询零依赖、零运维、Vercel 上必然工作,1000 用户阶段足够。

**详细 req/res、错误码、状态机** → 见 [`docs/agent/contract.md`](./agent/contract.md)。

---

## 3. 十条不变式(违反 = bug)

1. 浏览器原图**永远不写入数据库,不存 R2**(只 base64 临时穿过 Web)。
2. Web 收到 base64 后**只转发给 Agent**,不写日志、不落盘。
3. Agent 处理完请求**不留任何数据**,无状态。
4. PDF 由浏览器生成,通过 presigned PUT 上传 R2,Web 不接 PDF 流量。
5. 所有 API route.ts ≤ 40 行,业务逻辑全在 service。
6. Route 不 import drizzle,Service 不 import 其他 service 的 repo。
7. 所有 service 方法第一参数是 `userId` 或 `actor`,数据归属明确。
8. 所有积分变更必须在 DB 事务里,和 album 状态变更原子。
9. Agent 输出的 layout 写库前必须 zod 校验。
10. `AGENT_SHARED_SECRET` 不允许出现在任何 client bundle 里。

---

## 4. 项目目录(顶层)

```
memoir-agent-rebuild/
├── apps/
│   ├── web/
│   │   ├── src/              # Next.js 源码       → docs/web/*
│   │   ├── fonts/            # 全量 Noto SC TTF(server-only,非公开)— PDF subset 源,见 #31
│   │   └── design-v1/        # V1 UI 实现稿(HTML),React 化前的视觉权威源
│   └── agent/                # FastAPI 服务       → docs/agent/*
├── packages/
│   └── contracts/            # 跨服务 zod schema + TS 类型
├── docs/                     # 所有架构文档
└── CLAUDE.md                 # 工程入口,所有 agent 必读
```

> `apps/web/design-v1/` 不参与构建,只是 React 化时的视觉/token/i18n key 真相源。详见 [`apps/web/design-v1/README.md`](../apps/web/design-v1/README.md)。

**目录扩张规则**:新增顶层目录(`infra/` / `scripts/` / 新 `packages/*`)、或在 `apps/web/src` / `apps/agent/src` 下加顶层目录,**必须先由架构师在本文件登记**,再让工程师建。AI 工程师不能自己设计目录结构,只能往已登记的目录里填代码。

详细目录到文件级 → 见 [`docs/web/directory.md`](./web/directory.md)、[`docs/agent/contract.md`](./agent/contract.md)。

---

## 5. 部署

| 服务 | 平台 | 域名 |
|---|---|---|
| Web | Vercel | yujeeai.com |
| Agent | Fly.io | agent.yujeeai.com |
| Postgres | Neon | (内部连接)|
| R2 / CDN | Cloudflare | cdn.yujeeai.com |

环境变量完整清单 → 见各子文档结尾。

---

## 6. 扩展到 10 万用户的路径(未来,**第一版不实施**)

| 阈值 | 行动 |
|---|---|
| Agent QPS > 5 | 加 Redis 队列 + Python worker |
| 浏览器轮询 QPS > 200 | 上 SSE/WebSocket(配 Upstash Redis pubsub 跨实例广播)|
| Postgres 写 > 100 QPS | 给 `albums` / `agent_jobs` 加分表或归档 |
| 单次生成成本 > $0.20 | 加结果缓存(按 prompt + photo hashes 命中)|

第一版**不留任何抽象**给这些扩展。YAGNI。

---

## 6.5 二期决策记录(2026-06-01 · 架构拍板)

> 二期两块需求(UI 还原 `docs/product/ui-restore-gap.md` + 生成积分 `docs/product/credit-hold-on-generation.md`)的架构定调。**执行窗口动手前必读本节** —— 它覆盖/修正产品文档里的部分前提。

1. **计费现状澄清**:`generation-service.ts:20/35` + `job-service.ts:112/193/218` 已接 precheck/hold/settle/release/zombie。`credit-hold-on-generation.md` 的「现状」节(称"完全没接")**已过时**,以本节为准。`settle` 只在成功发生 → "失败不扣、成功扣一次、重试不重复计费"**现已满足**。

2. **余额不足接回 = 前端保留 + 购后重提(否决服务端占位任务)**。理由:不变式 1 下原图只在浏览器,付款接回时 base64 必须浏览器从 IndexedDB 重传,服务端占位任务的"持久性"是假的(换设备/清缓存即僵尸),不值得新增 `PENDING_PAYMENT` 状态 + schema 迁移。流程:precheck 不足 → 抛 `CREDIT_INSUFFICIENT` → 前端跳 `/pricing`(prompt+照片留 IndexedDB)→ 充值 → 前端重提交 `POST /api/v1/jobs`。**不加 album 状态,不改 generation-service 主流程。**

3. **失败重试 = 复用同一 album 重跑**(`FAILED→AGENT_RUNNING`),浏览器重传 base64,新 precheck+hold(D1 已退旧 hold),**不孤儿化失败卡**。需要一个 retry 路径复用 albumId。

4. **失败结算 = 失败即退 hold(不改现状)**;settle 只在成功;zombie sweeper 兜底不变。

5. **编辑器拆分**:**UI-1a 功能版**(准确平铺预览 + 编辑 + Chat + 导出 + 顶栏 chrome)= **P0 先上**;**UI-1b 3D 翻书 + 缩略图条**= **P1 polish 跟进**。理由:翻书是表现层,且与导出的 `@react-pdf` 平铺页不一致,不该拖住核心编辑功能上线。

6. **照片下限 ≥3 → ≥1(CT-1,跨 Web↔Agent,架构协调)**:web 路由 schema + `create/page.tsx` + agent `schemas.py:45`(`min_length` 3→1)+ composing 对 1-2 图用纯文字版面(mag-02/14/20)兜底。**验收必须含 1 图 fixture 跑通**,不许只改下限就宣布完成,不许某窗口单边改一半。

7. **路由结构统一**:`/create`、`/album/[uuid]` 现在 `[locale]` 段**外**(故无 i18n、文案硬编码英文)。目标收进 `[locale]` 做 2 语(中/英)。各屏 owner(UI-2 / UI-1a)在**自己 PR 里**迁移本屏路由,不单开任务。

8. **依赖**:① 统一 chrome(UI-0)是 UI-1a/UI-2/UI-4/UI-6/UI-9 的地基,**先定组件 props 接口再并行**。② BILL 语义(本节 2/3)先于 UI-2(/create)、UI-4(/my-albums)实现,因为这两屏要渲染"不足跳转/失败重试"态。

---

## 7. 怎么读这份文档系列

不要从头到尾读 `docs/`。按角色加载:

1. **任何任务开始前** → 读 `CLAUDE.md`(根目录,~150 行)
2. 在 `CLAUDE.md` 找你的**角色行**,看起手必读清单
3. 按清单**一份一份读**,读完一份再读下一份
4. 任务过程中遇到清单外的细节(如表字段、错误码、协议字段),按需查对应子文档

完整角色→文档映射表在 `CLAUDE.md` §3。
