# Agent 内部 Pipeline 设计

> Agent design reviewed by Claude Opus (B0 window) on 2026-05-27.
>
> **前置阅读**: `CLAUDE.md` → `docs/architecture.md` → `docs/agent/contract.md`
>
> 谁读这份: 写 `apps/agent/src/services/*` 真实 pipeline 的人。
>
> 这份文档**只讲 Agent 服务内部怎么实现**:阶段边界、模型调用、Prompt、校验、降级、日志。对外协议看 `contract.md`,数据 schema 看 `packages/contracts/`。

---

## 0. TL;DR(决策表)

| 维度 | 决策 |
|---|---|
| Agent 业务端点数 | **2 个**:`/v1/layout`(异步,首次生成) + `/v1/chat-edit`(同步,编辑期对话改图) |
| Pipeline 阶段数(layout) | 3 个(vision / writing / composing) |
| Chat-Edit 阶段数 | 1 个(单次 DeepSeek 调用,见 §14) |
| writing + composing 调用次数 | **2 个独立的 DeepSeek 调用** |
| 火山 vision 调用 | **一次调用,多图合一批输入** |
| 模型输出强制 JSON | 必须用模型官方支持的"结构化 JSON 输出"机制(具体 API 参数 / `response_format` / function calling / JSON mode,**实施时查火山 + DeepSeek 当前官方文档确认**) |
| 单张图识别失败 | 第一版:整体失败。v1.1:跳过单张(待 PM 拍) |
| repair loop 上限 | 每阶段 1 次,失败即映射对应错误码 |
| Agent 端 schema 校验 | **必做**(Python schema 镜像 TS contracts,discriminated union + 拒未知字段) |
| zombie sweeper | **第一版必须有**:5min 内 `RUNNING` 没终态 → 标 FAILED + 释放积分。实现方式(Vercel Cron / opportunistic sweep / 长跑 server timer)由 Web 基建轨道(T6 / T-Deploy)评估后定 |
| TemplateRegistry 位置 | `packages/contracts/src/templates.ts`(21 模板,从 yvaineyu9/memoir 抽)。**21 个全部填齐是真实 composing + chat-edit 的硬前置** |
| 模型版本号 / API 参数 | 不在本文档锁死。环境变量 + 实施时查官方文档为准,见 §2.5 |
| Mock pipeline | 仅 `AGENT_PIPELINE_MODE=mock` 启用,生产环境若不是 `real` 必须启动失败 |

---

## 1. Pipeline 阶段边界

```
Web ──POST /v1/layout──► Agent (202 accepted, BackgroundTask)
                          │
                          ├─ Stage 1: vision    (火山一次多图)
                          │     in:  AgentLayoutRequest.photos[]
                          │     out: PhotoAnalysis[]
                          │     err: AGENT_VISION_FAILED
                          │
                          ├─ Stage 2: writing   (DeepSeek call #1)
                          │     in:  PhotoAnalysis[] + prompt + language
                          │     out: Magazine{title,subtitle,style}
                          │     err: AGENT_PLANNING_FAILED
                          │
                          ├─ Stage 3: composing (DeepSeek call #2)
                          │     in:  PhotoAnalysis[] + Magazine + TemplateRegistry
                          │     out: Page[] (校验通过)
                          │     err: AGENT_OUTPUT_VALIDATION
                          │
                          └─► POST callback (event=completed, layout, usage)
                                                or
                              POST callback (event=failed, stage, error, partialProgress)
```

### 1.1 错误码归属表

| 错误码 | 抛出位置 | 含义 |
|---|---|---|
| `AGENT_INVALID_INPUT` | route 接单时 | 请求体不合法(zod/pydantic 拒) |
| `AGENT_UNAUTHORIZED` | route 接单时 | Bearer 校验失败 |
| `AGENT_VISION_FAILED` | Stage 1 | 火山调用失败 / 返回非 JSON / 超时重试都失败 |
| `AGENT_PLANNING_FAILED` | Stage 2 | DeepSeek writing 调用失败 / repair 也失败 |
| `AGENT_OUTPUT_VALIDATION` | Stage 3 | DeepSeek composing 输出 schema 不合法 / repair 失败 / 业务规则违反 |
| `AGENT_CHAT_FAILED` | chat-edit(§13)| DeepSeek 调用失败 / patch 应用后校验失败 / repair 失败 / 60s 超时 |
| `AGENT_TIMEOUT` | BackgroundTask 总耗时 > 180s | 超总时长 |
| `AGENT_INTERNAL_ERROR` | 兜底 | 上面都不是的未知异常 |

### 1.2 单图失败策略

**第一版**:任何一张照片在 vision 阶段失败 → 整体 `AGENT_VISION_FAILED`。

理由:简单,容易判断成功/失败,用户能立刻知道哪里出问题。

**v1.1(未实施)**:跳过失败的图,只要剩余 ≥ 3 张能用,继续。需要在 layout 里标注哪张图被跳过。先不做。

---

## 2. Stage 1 · vision(火山 doubao-seed-1-6-vision)

### 2.1 调用方式

**一次调用,多图合一批**。火山 doubao-vision 支持 `content` 是 array,可以塞 N 个 image_url 项 + 1 个 text instruction 项。

理由:
- 省 token(系统 prompt + 解析提示只出一次)
- 模型能看到照片间上下文(同一个人在不同场景、同一次旅行的多张图等)
- 失败粒度对齐"整体失败"策略(§1.2)

### 2.2 Agent 端预校验(接单返回 202 前必须做)

`POST /v1/layout` 在 route 层校验请求体,失败 → 400 `AGENT_INVALID_INPUT`:

- 每张照片的 base64 必须是 `data:image/jpeg` 或 `data:image/png` data URL
- 单张去掉 data URL 头后,原始字节 ≤ 800KB
- `photos.length ∈ [1, 30]`(已由 Pydantic 在反序列化时强制;架构 §6.5 决策 6)
- `prompt.length ≤ 500`
- 鉴权 Bearer 失败 → 401 `AGENT_UNAUTHORIZED`

校验**必须**在 BackgroundTask 启动**之前**完成 —— 不接成功的单。

### 2.3 火山 vision Prompt 的信息架构

> 完整 prompt 文本由 T3 编写。本节定义 prompt **必须涵盖的信息**和**输出契约**,不锁字面。

System 段必须传达:
- 任务:对一批输入图片做结构化描述
- 严格 JSON 输出,数组形式,长度等于输入图片数,**顺序与输入对齐**(因为模型不知道我们的 photoId,Agent 按顺序回填)
- 每对象字段(见 §2.6 PhotoAnalysis 扩充字段)
- 业务硬规则:整组里 `quality=hero` 的最多 `ceil(N/3)` 张

User 段必须传达:
- 输入图片(按 §2.1 决策:一次多图)
- 原始用户 prompt(作为风格 / 主题上下文,但**不要求模型理解或复用**)

调用参数(timeout / retry / 是否启用 JSON 模式 / 系统消息位置等)由 T3 实施时按火山官方文档配置。

### 2.4 火山返回解析的约束

实施细节(怎么剥代码栅栏、怎么序列化)交给 T3。本节列**必须保证的属性**:

1. 模型返回必须解析成长度等于输入图片数的 JSON 数组,顺序对齐
2. 每个元素用 Python 镜像的 `PhotoAnalysis` schema 严格校验(拒未知字段)
3. Agent 按输入顺序回填 `photoId`
4. 任一约束失败 → **retry 1 次**(网络层 timeout 也走 retry)→ 仍失败 → `AGENT_VISION_FAILED`
5. **不允许**部分成功部分失败地继续(对齐 §1.2 第一版"整组失败"策略)

### 2.5 环境变量

模型名 / Base URL / 超时 / 重试次数等**全部从环境变量读**,**不硬编码**。约定名见 `agent/contract.md §10`。

具体模型版本号(如 `doubao-seed-1-6-vision-*`)以**实施时火山官方控制台可用列表**为准,不在本文档锁死 —— API 文档会更新,文档锁死会失同步。

### 2.6 PhotoAnalysis schema 扩充(契约)

vision 阶段输出契约比当前 `contract.md §4` 的版本多 5 个字段:

- `peopleCount`: `'0' | '1' | '2-3' | '4+'`
- `scene`: `'indoor' | 'outdoor' | 'nature' | 'city' | 'interior'`
- `mood`: `'warm' | 'cool' | 'sentimental' | 'energetic' | 'quiet'`
- `timeOfDay?`: `'morning' | 'day' | 'evening' | 'night'` | null
- `location?`: 自由文本 | null

理由:让 composing 阶段做"hero 用 landscape outdoor warm"这类约束匹配。

**这些字段当前是 design 阶段决策,还未在代码中落地**。对应任务见 §13。

---

## 3. Stage 2 · writing(DeepSeek call #1)

### 3.1 目标

决定整本相册的**故事调性**:标题、副标题、视觉风格 ID。**不决定页数,不决定模板,不决定每页文案**。

### 3.2 调用方式

单次 DeepSeek 调用,必须使用 DeepSeek 当前官方文档建议的结构化 JSON 输出机制(具体 API 参数 / `response_format` / function calling 选择由 T3 实施时决定)。

### 3.3 Prompt 信息架构

> 完整 prompt 文本由 T3 编写。

System 段必须传达:
- 任务:为相册写编辑概念(title / subtitle / style)
- 输出契约:严格 JSON 对象,字段、长度、枚举值见下面 §3.4
- `style` 取值范围:`warm-film | editorial-mono | soft-pastel | bold-contrast | vintage-print`
- 选 style 的依据规则(对应 mood:warm→warm-film、quiet→editorial-mono...,留给 T3 写 explainer)

User 段必须传达:
- 用户原 prompt
- 目标语言(zh / en),title/subtitle 必须用该语言
- §2 vision 输出的 `PhotoAnalysis[]`(精简到 description / mood / tags 即可,不必塞全)

### 3.4 输出契约

```
{
  title: string         (1..60 chars,目标语言)
  subtitle?: string     (≤ 100 chars,目标语言)
  style: enum<5种,见 3.3>
}
```

### 3.5 校验 + repair

1. JSON 解析失败 → 实施层 retry 1 次(网络 timeout 也走这个 retry)
2. 解析成功但 schema 不合法 → **repair 1 次**:把上次输出 + 校验失败原因回灌
3. repair 仍失败 → `AGENT_PLANNING_FAILED`

---

## 4. Stage 3 · composing(DeepSeek call #2)

### 4.1 目标

把 photos + Magazine 排成 `Page[]`:挑模板、分配 photoId 到 slot、填 text slot。

### 4.2 输入上下文(全部塞 system prompt)

- 完整 `AlbumLayoutPlan` JSON Schema(从 `packages/contracts` 导出)
- `TemplateRegistry`(`packages/contracts/src/templates.ts`)
- `Magazine`(stage 2 输出)
- `PhotoAnalysis[]`(stage 1 输出)
- **业务规则**(下面 §4.3)

### 4.3 业务规则(硬编码进 prompt + 校验)

| 规则 | 规则文本 | 校验时机 |
|---|---|---|
| 页数 | `pages.length = max(3, ceil(photos.length / 2.5))`,最多 16 页 | Agent 端硬校验 |
| 第 1 页 | 必须是 cover 类模板(templateId 前缀 `cover-`) | Agent 端硬校验 |
| 照片利用 | 每张 photoId 至少出现一次 | Agent 端硬校验 |
| 重复使用 | 单张图可重复 ≤ 2 次,且不能在同一页 | Agent 端硬校验 |
| hero slot | 优先 `quality=hero` 的图;且 `orientation` 满足该 slot 要求 | Agent 端硬校验 |
| pageIndex | 0..N-1 严格连续 | Agent 端硬校验 |
| 模板 | `templateId` 必须在 TemplateRegistry 里 | Agent 端硬校验 |
| slot | 每页 `images` / `texts` 的 key 必须在该模板 slot 列表里 | Agent 端硬校验 |
| 文案长度 | title ≤ 60、caption ≤ 120、body ≤ 280(字符) | Agent 端硬校验 |

### 4.4 Prompt 信息架构

> 完整 prompt 文本由 T3 编写。

System 段必须传达(分块,模型才能稳定遵守):
- 任务:把 photos 排成 pages
- 完整 `AlbumLayoutPlan` JSON Schema(从 contracts 包导出,序列化喂入)
- TemplateRegistry(`templates.ts` 21 条)的 ID + slot + 约束,序列化喂入
- §4.3 全部 9 条业务规则(原文列举,不要让模型"理解"规则,要让它"逐条遵守")

User 段必须传达:
- §3 输出的 Magazine
- §2 输出的 PhotoAnalysis[]
- 目标语言

### 4.5 校验 + repair

1. JSON 解析失败 → 实施层 retry 1 次
2. schema 校验(`AlbumLayoutPlan` Python 镜像)失败 → 进 repair
3. **业务规则校验**(§4.3 全部 9 条)失败 → 进 repair
4. **repair 1 次**:把违反的规则原文 + 上次输出回灌,要求重新输出**完整** JSON(不是 patch)
5. repair 仍失败:
   - **>2 张照片**:`coerce_image_slots` 兜底(强制 slot 合规,实在塞不下的图丢弃),仍结构违规才 `AGENT_OUTPUT_VALIDATION`,**不走整套 fallback layout**。
   - **≤2 张照片**(架构 §6.5 决策 6):走 `layout_rules.build_text_first_layout` 确定性兜底——cover + 每张图按约束放一次 + 纯文字版面(mag-02/14/20)补齐页数。**这是唯一允许的 fallback layout**,因为 1-2 图的版面空间太小、模型最不可靠,且确定性兜底**不会丢用户的唯一一张图**。

> `build_text_first_layout`(`services/layout_rules.py`)对每张图按 orientation×quality 在 21 模板里找首个匹配 slot;square / fill 级图进不了任何 cover 时,cover 退化为纯文字的 mag-20,图放到后续页。产出必过 §4.3 全量校验。

---

## 5. TemplateRegistry —— 硬阻塞前置

`packages/contracts/src/templates.ts` 定义 21 个模板的 ID + slot + 约束。这是 Agent composing 阶段的**唯一可选集合**。

**当前状态**(2026-05-30 核对):21 个模板已全部填齐(`mag-01`~`mag-20` + `p01`),从 `https://github.com/yvaineyu9/memoir/blob/main/frontend/schema.js` 抽取完成,§5.1 的 quality enum 约束也已写进每个 slot。硬阻塞已解除。

> 历史:本节原文写"只有 3 个占位(cover-01 / spread-01 / spread-02)",那是 2026-05-27 骨架期的状态,上线时已补齐,2026-05-30 改正。

**硬阻塞规则**:

- **21 个模板未全部填齐前**,Agent 真实 composing(T3 验收)**不允许声明完成**;真实 pipeline 在生产模式下选择超出可用集的 templateId → 应 `AGENT_OUTPUT_VALIDATION`
- 模板数据**单向**从 `templates.ts` 流向 Agent;不允许 Agent 自由生成 templateId
- 每个模板必须给出:`imageSlots`(每个 slot 的 orientation / quality 约束)、`textSlots`(可填的 key 列表)、`category`(`cover` / `spread` / `single` / `grid` / `closing`)
- TS 类型定义和占位骨架以 `packages/contracts/src/templates.ts` 实际代码为准

### 5.1 quality enum 语义(`hero` / `detail` / `fill`)

`TemplateSlotConstraint.quality` 是 `('hero' | 'detail' | 'fill')[]`,表示**该 slot 适合放什么"画面分量"的图**。这套 enum **不在** `yvaineyu9/memoir` 老仓库的 `schema.js` / `meta.json` 里 —— 是迁移到 `packages/contracts/src/templates.ts` 时按每个模板的视觉 desc 推导的,**B-1 之后已稳定写进 21 个模板约束**,Agent composing 阶段必须严格按这套语义选图。

| 值 | 含义 | 占版面比例 | 典型 slot |
|---|---|---|---|
| `hero` | 大图主视觉、叙事担当、跨页大图 | 约满版 ~ 60% | `mag-05.image`、`mag-13.image`、`mag-08.image`、`mag-15.imagePerson` |
| `detail` | 中等细节图、辅助叙事、栏内主图 | 约 30% ~ 50% | `mag-07.imageMain`、`mag-09.imageMain`、`mag-04.image2` |
| `fill` | 小图、远景、网格填充、呼吸 / 氛围 | 约 ≤ 25% | `mag-16.imageTiny`、`mag-10.cells[*]`、`mag-12.imageTop` |

**constraint 是"可接受集合",不是"单一类型"**:`quality: ['hero', 'detail']` 意为"hero 或 detail 都接受,planning 阶段按手上的照片质量选最匹配的"。21 个模板里只有一个 slot 是单值集合(见下方边界 case)。

#### 5.1.1 planning 阶段如何用这套 enum

1. **Stage 1(vision,§2.6 扩充字段)**:火山给每张 `PhotoAnalysis` 推导 `quality`(单值 `'hero' | 'detail' | 'fill'`)。判断依据:主体是否清晰、是否有故事性、构图是否能撑大、是否只能当配菜。
2. **Stage 3(composing,§4.3)**:DeepSeek 选图填 slot 时:
   - 先取 `imageSlots[slot].quality` 这个**可接受集合**
   - 候选 = `PhotoAnalysis` 里 `quality` 落在集合内的照片
   - 在候选里,按 §4.3 第 5 条硬规则"hero slot 优先 `quality=hero` 的图"挑
   - 同时满足 `orientation` 约束
3. **composing prompt(§4.4)**:必须把每个 slot 的"可接受 quality 集合"逐字列入 system prompt,**不要假设模型能从 templateId 反推语义**。

#### 5.1.2 边界 case

- **`mag-16.imageTiny: { quality: ['fill'] }`** —— 21 个模板里**唯一**只接受 `fill` 的 image slot。视觉上是配菜级小图(thumbnail / 远景 / 留白填充),给 hero 级照片硬塞进去就是"放炮打蚊子",撑不开版面。Agent 选图时遇到这个 slot 必须从 `quality=fill` 的图里选,**没有 fill 级照片就让这个 slot 空**(slot key 是 optional)。
- **`mag-09.imageMain: { quality: ['hero', 'detail'] }`** —— 命名是 `imageMain`,但**接受 detail**,因为该模板另有 `imageTop`(landscape)占了上方互补位,主图不必是 hero 级。这是模板的视觉冗余设计,planning 时不要看到 `imageMain` 就强制塞 hero。
- **`mag-09.imageTop: { quality: ['detail', 'fill'] }`** —— 配图位,**不接受 hero**:同页已有 imageMain,再放 hero 会"两个主视觉撕架"。Agent 不要为了用光 hero 图把它塞进辅助位。
- **`mag-02 / mag-14 / mag-20`(`imageSlots = {}`)** —— 纯文字版面,quality enum 不参与;选模板时只看文本需求。

> issue #7 提到"mag-09 imageMain `['fill']`",对照 `templates.ts:166` 实际是 `['hero','detail']`,issue 里是笔误。真正的 fill-only slot 是 `mag-16.imageTiny`(`templates.ts:277`)。

---

## 6. 进度语义

每阶段进度数字代表"已完成的工作量百分比"。

| Stage | 0 含义 | 50 含义 | 100 含义 |
|---|---|---|---|
| vision | 火山请求已发出 | (可选,不强制) | 响应解析成功,PhotoAnalysis[] 已生成 |
| writing | DeepSeek 请求已发出 | (可选) | 响应解析+校验通过,Magazine 已生成 |
| composing | DeepSeek 请求已发出 | (可选)repair 中 | 响应解析+schema+业务规则全过 |

**每阶段至少发 2 次 progress**:开始 (progress=0)、完成 (progress=100)。中间 50 可发可不发。

**失败语义**(P0-7):
- 失败前必须先发一次 `progress` callback,字段标当前 stage 和能跑到的最大 progress(比如 vision 跑到 100、writing 失败 → 先发 `progress, stage=writing, progress=0`,再发 `failed`)
- 这样前端 progress bar 不会从 50% 直接跳"失败"

---

## 7. Zombie job 兜底(目标 + 约束)

contract.md §6 之前写"5 分钟兜底扫描,第一版不实施"。**design 阶段改决策**:第一版**必须有**。

### 目标(不可妥协)

任何 `agent_jobs.status='RUNNING'` 持续超过 **5 分钟**仍无终态(callback completed / failed),Web 侧必须:

1. 把对应 album 标 `FAILED`,`error.code = AGENT_TIMEOUT`
2. 释放对应的 `credit_hold`(status: HOLDING → RELEASED,不扣积分)
3. 让浏览器下一次轮询 `GET /api/v1/albums/[uuid]` 拿到 `status=FAILED`

### 约束

- 由 **Web 侧**承担(Agent 是无状态的,挂掉就没了)
- 必须在 **Web 部署形态**下都能工作(本地 dev / Vercel / Fly.io 都行)

### 实现方式(已落地:读时机会式 + 每日 cron 双保险)

> 历史:本节原文"实现方式不锁",并由 Web 基建轨道临时落成 **Vercel 每日 `recover-stuck` cron**(Hobby 套餐限制)。每日 cron 最坏 24h 才翻 FAILED,把"5 分钟"硬目标放水了。issue #48 把目标补回,定为双保险:

1. **读时机会式收尸(响应层,5 分钟)** —— `albumService.getDetail` / `listByUser` 在 `status=AGENT_RUNNING` 时调 `jobService.resolveGeneration(albumId)`:最新 job 距 `startedAt`(QUEUED 回退 `createdAt`)> 5 分钟无终态,**当场**复用 `handleFailed` 标 FAILED + 释放积分。利用"浏览器本就在按 uuid 轮询 album"这个动作驱动,服务**在线**用户 ≤5 分钟见结果,无需 sub-daily cron / 常驻进程。
2. **每日 `recover-stuck` cron(兜底层,10 分钟阈值)** —— `zombieSweeper.sweep`,扫 `findStaleRunning`,专收"用户一去不回"的相册,保证积分最终释放。**不可删**:读时收尸只在有人访问时触发,弃用相册的积分要靠它退。
3. 两层做**同一个 FAILED 转换**(album FAILED + hold RELEASED + job FAILED 原子事务,不变式 8),用户可见错误文案统一为 `"Generation timed out. No credit was charged."`。

### 同步改文档

- ✅ `docs/agent/contract.md §6` 已改
- ✅ `docs/web/api.md §5` 已改

---

## 8. callback envelope 强约束(discriminated union)

`packages/contracts/src/agent.ts` 里 TS 端已经按 discriminated union 定义。**Python 侧必须镜像**,且满足以下约束:

- 按 `event` 字段做 discriminator,区分 progress / completed / failed 三种 variant
- 每种 variant **拒未知字段**(Pydantic `extra='forbid'`)
- 字段集严格按 contract.md §2.1 callback 请求体定义,Agent 发出 callback 前必须用这个 schema 校验一次,不通过就**不发**

**当前 mock 实现**(`apps/agent/src/services/pipeline.py`)用的是宽松 dict 拼装。**对应任务见 §13** —— 不是已完成。

---

## 9. 隐私 / 日志红线

### 允许打的字段

- `requestId`
- `photoCount`
- `promptLength`(数字)
- `language`
- `stage`、`progress`
- `durationMs` per stage
- `error.code` + `error.message`(短文本,模型不返回原文)
- `usage`(数字)
- `modelName`(`doubao-seed-1-6-vision-250815` 之类)

### 禁止打的字段

- `base64`(原图)的任何片段
- `prompt`(用户原文)
- 模型 raw response(只允许打**长度** + **是否解析成功**)
- 用户邮箱 / userId(只打 requestId,Web 侧需要时自己 join)

### 实施约束

- Agent 日志库(当前是 structlog)在 processor 链最后加一道 redact,把上面列出的"禁止打的字段"统一改成 `<redacted>`,不依赖每个 caller 自觉
- redact 列表至少包含 `base64`、`prompt`、`raw_response`、`email`,可继续加
- redact 不通过的字段 → 测试里**断言**不出现在日志输出

---

## 10. usage 字段重定义

> ⚠️ **未落地(2026-05-30 核对)**:本节是当初的设计提案,代码从未采用。layout 完成 callback 至今仍发旧 3 字段 `{ visionTokens, planningTokens, durationMs }`(`schemas.py:JobUsage`、`agent.ts:CallbackUsage` 一致),Web 也按旧形状消费。下面这套 `Usage` 富 schema 若二期要(做成本归集),需当作新任务开,且两端同步。chat-edit 用的是另一套 `ChatEditUsage`(`schemas.py:160`),已含 `planningInputTokens`,但无 Web 消费方。

contract.md §4 的 usage 当前只有 `{ visionTokens, planningTokens, durationMs }`,不够。

**新 schema**(同步改 contracts/agent.ts + Python 镜像):

```ts
export const Usage = z.object({
  durationMs: z.number().int().nonnegative(),
  visionCallCount: z.number().int().nonnegative(),
  visionCostCents: z.number().nonnegative().optional(),   // 火山按次计费,如果能拿到单价
  planningInputTokens: z.number().int().nonnegative(),
  planningOutputTokens: z.number().int().nonnegative(),
  planningCostCents: z.number().nonnegative().optional(),
  repairAttempts: z.number().int().nonnegative(),
  models: z.object({
    vision: z.string(),
    planning: z.string(),
  }),
});
```

`visionCostCents` / `planningCostCents` 可选 — Agent 端如果不知道单价就留空,Web 侧定时跑成本归集。

---

## 11. 测试验收 fixtures

> ⚠️ **已 stale(2026-05-30 核对)**:下面这批独立 fixtures JSON 没有按原样建。实际测试覆盖改用 `apps/agent/tests/conftest.py` + `test_pipeline_mock.py` / `test_chat_edit_patch.py` / `test_layout_rules.py` / `test_schemas.py` / `test_logging_redact.py` / `test_upstream_error_mapping.py` + `test_e2e.sh`。本节当设计意图读,不当现状读。

`apps/agent/tests/fixtures/`(原计划,未按此落地):

```
photos_3_minimal.json        # 3 张,en prompt
photos_30_max.json           # 30 张,zh prompt
malformed_vision_response.json  # 火山返回非 JSON
malformed_planning_response.json # DeepSeek 返回非 JSON,触发 repair
missing_template_id.json     # composing 选了不存在的 templateId
duplicate_photo_on_page.json # 业务规则违反:同一图重复在同一页
sparse_photo_coverage.json   # 某张图没出现在任何 page
```

`tests/test_pipeline_real.py`(可选,需要真 API key):
- 3 张 / 30 张 / en / zh 各跑一遍
- 火山 mock 返回 429 → 应该 retry 1 次
- DeepSeek 返回 invalid JSON 第一次 → 应该 repair 后成功
- DeepSeek 返回 invalid JSON 两次 → AGENT_PLANNING_FAILED 或 AGENT_OUTPUT_VALIDATION

`tests/test_e2e.sh`(已存在,新增 case):
- prompt="FAIL_TEST" → failed callback(已有)
- prompt="REPAIR_PLANNING" → 第一次假返回 invalid,repair 后通过(需要测试 hook)

---

## 12. Mock / dev / prod 边界(约束)

引入 `AGENT_PIPELINE_MODE` 环境变量,取值 `mock` | `real`。

启动时必须满足:
- `AGENT_PIPELINE_MODE` 必填,值不在白名单 → 启动失败
- `AGENT_ENV=production` 且 `AGENT_PIPELINE_MODE != real` → 启动失败

环境约定:
- 生产 / 预发:`real`,配真 API key
- CI 跑 e2e:`mock`,不烧 API token
- 本地 dev:默认 `mock`,联调真 AI 时手动开 `real`

---

## 13. Chat-Edit Pipeline(同步)

### 13.1 触发与边界

入口:`POST /v1/chat-edit`(对外协议见 `contract.md §2.2`)。

**不**是 layout 三阶段的子集,是一个**独立的轻量 pipeline**:
- 单次 DeepSeek 调用,**不**调火山 vision(已有的 PhotoAnalysis 从 currentLayout.photos 直接读)
- **不**进 BackgroundTask,**不**发 callback —— 用户在 HTTP 连接上等
- repair 上限 1 次,跟 composing 一致

### 13.2 输入裁剪

Web 传过来的 `currentLayout` 是完整 `AlbumLayoutPlan`。Agent 端:
- 直接转发给 DeepSeek 当上下文(不需要再 vision)
- 历史对话 `history` Web 已裁到最近 ≤20 条
- **拒未知字段**:`history[].role` 只允许 `user` / `assistant`

### 13.3 Prompt 信息架构

> 完整 prompt 文本由 T3 编写。

System 段必须传达:
- 任务:基于当前 layout + 对话历史,出**最小修改**的 layoutPatch
- 完整 `AlbumLayoutPlan` schema(从 contracts 序列化)
- TemplateRegistry 全 21 条(同 composing)
- §4.3 的 9 条业务规则全部仍然适用(patch 应用后必须仍满足)
- 输出契约见 §13.4
- **不允许**:新增/删除页;新增 photoId(只能在 currentLayout.photos 内的 photoId 间换);出现 currentLayout.photos 以外的 photoId

User 段:
- `currentLayout`(完整 JSON)
- `history`(裁剪后)
- `userMessage`(用户这次的话)
- `language`

### 13.4 输出契约

```ts
export const LayoutPatchEntry = z.object({
  pageIndex: z.number().int().nonnegative(),
  templateId: z.string().optional(),                 // 换模板时给
  images: z.record(z.string(), z.string()).optional(),
  texts: z.record(z.string(), z.string()).optional(),
});

export const ChatEditResponse = z.object({
  layoutPatch: z.array(LayoutPatchEntry).min(1).max(16),
  assistantReply: z.string().min(1).max(500),        // 给用户看的自然语言回复
  usage: Usage,
});
```

### 13.5 校验 + repair

1. DeepSeek 返回 JSON 解析失败 → retry 1 次
2. patch schema(§13.4)失败 → repair 1 次
3. **patch 应用到 currentLayout 后,完整 layout 还要再过一遍 `AlbumLayoutPlan` schema + §4.3 业务规则** → 失败 → repair 1 次
4. repair 失败 → 返回 502 `AGENT_CHAT_FAILED`,**不**走 fallback,**不**写库(Web 侧也不写 album_messages)

### 13.6 隐私

跟 §9 一致:`history[].content` 视为用户原文,**禁止打日志**(走 redact)。

---

## 14. 落地任务清单(状态 2026-05-30 核对)

本文档**只定决策**。下表是当初拆出的落地任务,状态以**当前代码**为准(一期已上线,大部分已落)。

| 任务 ID | 内容 | 归属轨道(`execution-plan.md`) | 当前状态(2026-05-30) |
|---|---|---|---|
| D-1 | `docs/agent/contract.md` PhotoAnalysis schema 加 5 字段 + Usage 重定义 + callback envelope discriminated 表达 | **T0**(Contracts) | ✅ 文档已改(代码侧见 D-3/D-4) |
| D-2 | `docs/web/api.md §5` zombie sweeper 改"目标导向" | T0(同步)| ✅ |
| D-3 | `packages/contracts/src/layout.ts` PhotoAnalysis 加 5 字段 | T0 | ⛔ **未做** —— TS 仍只有 5 个基础字段;Python `schemas.py:71-75` 已加 5 字段。**契约漂移**,见表下注。 |
| D-4 | `packages/contracts/src/agent.ts` Usage 字段扩充 | T0 | ⛔ **未做** —— §10 的新 Usage schema 两端都没落;layout callback 仍用旧 3 字段(`visionTokens/planningTokens/durationMs`),有意为之(避免破坏 Web)。 |
| D-5 | `packages/contracts/src/templates.ts` 占位骨架 | T0 | ✅ |
| D-6 | 把 21 个模板从 `yvaineyu9/memoir` 抽到 `templates.ts` | **T4 / B-1**(硬阻塞,见 §5)| ✅ 21 个全填齐(mag-01~20 + p01) |
| D-7 | `apps/agent/src/schemas.py` 镜像 TS contracts(discriminated union + extra='forbid') | T3 | ✅ `_Strict(extra='forbid')` + progress/completed/failed 三 variant |
| D-8 | `apps/agent/src/services/pipeline.py` 把 mock 换成真实 vision + writing + composing | T3 | ✅ real 分支已落(`_run_real`),mock 保留给 CI |
| D-9 | `apps/agent/src/logging_config.py` 加 redact processor | T3 | ✅ `_REDACT_KEY_*` + `test_logging_redact.py` |
| D-10 | Web 侧 zombie sweeper(目标见 §7,实现方式由轨道评估)| T6 / T-Deploy | ✅ 双保险(issue #48):**读时机会式收尸**(`getDetail`/`listByUser` → `jobService.resolveGeneration`,5 分钟,响应层)+ **每日 `recover-stuck` cron**(`zombieSweeper`,10 分钟,兜底层)。§7/api.md §5 已同步。 |
| D-11 | `AGENT_PIPELINE_MODE` 启动检查 | T3 | ✅ `main.py:21-34`(production 必须 real,real 必须配齐 key) |
| D-12 | Agent fixtures(§11) | T3 | ⚠️ 换形态:没建 §11 那批独立 fixtures JSON,改用 `conftest.py` + `test_pipeline_mock.py` / `test_chat_edit_patch.py` 等。§11 列表已 stale。 |
| D-13 | `packages/contracts/src/chat.ts`:`ChatEditRequest` / `ChatEditResponse` / `LayoutPatchEntry` zod | T0 | ⛔ **未做** —— TS 无 `chat.ts`,chat 契约只活在 Python `schemas.py:140-176`。**契约漂移**,见表下注。 |
| D-14 | `apps/agent/src/routes/chat_edit.py` + `services/chat_edit.py`:实现 §13 同步 pipeline + repair | T3 | ✅ |
| D-15 | Web `services/chat/chat-service.ts` + `app/api/v1/albums/[uuid]/chat/route.ts` + `messages/route.ts` + repos | Web Editor 轨道 | ✅(PR #24)|
| D-16 | DB:新增 `customers` + `album_messages` 表 + migration | T2 | ✅(11 表已含)|

> **遗留项 · TS↔Python 契约漂移(二期可清)**:`packages/contracts`(TS,本应是单一真相源、Web 直接 import)落后于 Agent 的 Python `schemas.py`。具体:D-3(PhotoAnalysis 5 字段)、D-13(chat 三个 schema)只在 Python 端存在,TS 端缺失。当前**端到端能跑**——因为 Web 实际只消费 callback 里的 layout(走 `AlbumLayoutPlan`,两端一致)和 chat 的 browser-patch(Web 自己翻译),漂移字段未被 Web 直接依赖,所以没炸。但"TS 是真相源、Python 镜像"这个不变式名存实亡了。二期若要复用这些字段(如 #42 让 composing 用 scene/mood 做约束、或给前端展示 usage 成本),应先把 D-3/D-13 补回 TS 并让 Python 重新对齐。**优先级低,不阻塞,但要记账。**
