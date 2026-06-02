# Web 数据库 Schema

> **前置阅读**: `CLAUDE.md` → `docs/architecture.md` → `docs/web/layering.md`
>
> 谁读这份: 写 repo / migration 的人,或需要查"某个字段叫什么"的人。

---

## 1. 通用约定

- 数据库: **Postgres**(Neon serverless)
- ORM: **Drizzle** + `drizzle-kit` migrations
- 表名: `snake_case` 复数
- 字段: `snake_case`,Drizzle map 到 TS `camelCase`
- 主键: `id uuid` 默认 `gen_random_uuid()`
- 所有表都有 `created_at`、`updated_at`(`timestamptz`)
- 删除策略: **逻辑删除**(必要时加 `deleted_at`),不物理 DROP

---

## 2. 表清单

| 表名 | 作用 | 由 better-auth 管? |
|---|---|---|
| `users` | 用户主表 | ✅ 是,不动 |
| `accounts` | 第三方登录 | ✅ |
| `sessions` | 会话 | ✅ |
| `verifications` | 邮箱验证 | ✅ |
| `customers` | 用户 → Stripe / Creem 客户号映射 | |
| `albums` | 相册主表 | |
| `album_pages` | 相册单页 | |
| `album_messages` | Chat 对话历史 + AI 修改痕迹 | |
| `agent_jobs` | Agent 生成任务 | |
| `credit_holds` | 积分冻结 | |
| `credit_ledger` | 积分流水 | |

合计 **11 张**(4 张 better-auth + 7 张业务)。

---

## 3. `albums`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | uuid PK | default `gen_random_uuid()` | |
| user_id | uuid FK users(id) | NOT NULL | |
| title | text | NOT NULL | Agent 生成,可编辑 |
| status | enum | NOT NULL, default 'AGENT_RUNNING' | 见 §8 状态机 |
| prompt | text | NOT NULL | 用户输入的原始 prompt |
| layout_json | jsonb | NULL | Agent 输出的完整 layout(权威源)|
| photo_count | int | NOT NULL | |
| page_count | int | NOT NULL default 0 | |
| pdf_r2_key | text | NULL | 完成后写,如 `pdfs/{userId}/{albumId}.pdf` |
| pdf_url | text | NULL | R2 公网 URL |
| credit_hold_id | uuid FK credit_holds(id) | NULL | |
| error_message | text | NULL | FAILED 时填 |
| created_at | timestamptz | NOT NULL default now() | |
| updated_at | timestamptz | NOT NULL default now() | |

**索引**:
- `(user_id, created_at desc)` —— 列表查询
- `(status)` partial where `status in ('AGENT_RUNNING','EDITING')` —— 后台扫活跃任务

---

## 3.1 `customers`

把内部 `user_id` 映射到外部支付平台的客户号。一个用户在 Stripe / Creem 各自有一行(或 null)。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | uuid PK | default `gen_random_uuid()` | |
| user_id | uuid FK users(id) | NOT NULL | |
| provider | enum | NOT NULL | `stripe` / `creem` |
| external_customer_id | text | NOT NULL | Stripe 的 `cus_xxx` / Creem 的客户 ID |
| email | text | NULL | 冗余,方便查 |
| created_at | timestamptz | NOT NULL default now() | |
| updated_at | timestamptz | NOT NULL default now() | |

**索引**:
- `UNIQUE(user_id, provider)` —— 一个用户在一个平台只有一条
- `UNIQUE(provider, external_customer_id)` —— 反查
- `(user_id)`

---

## 4. `album_pages`

每页一行,方便编辑器局部更新。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | uuid PK | | |
| album_id | uuid FK albums(id) | NOT NULL, ON DELETE CASCADE | |
| page_index | int | NOT NULL | 0-based |
| template_id | text | NOT NULL | 来自 `config/templates.ts` |
| images_json | jsonb | NOT NULL default '{}' | `{ slotName: photoId }` |
| texts_json | jsonb | NOT NULL default '{}' | `{ slotName: string }` |
| updated_at | timestamptz | NOT NULL default now() | |

**约束**:
- `UNIQUE(album_id, page_index)`
- 索引 `(album_id)`

**注意**: `images_json` 里的 `photoId` 是**浏览器侧的本地编号**(`p1`, `p2`...),服务器只是存这个字符串。编辑器加载时,从 IndexedDB 用 photoId 查原图。

---

## 4.1 `album_messages`

Chat 编辑对话历史。一行 = 一条消息(user 或 assistant)。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | uuid PK | | |
| album_id | uuid FK albums(id) | NOT NULL, ON DELETE CASCADE | |
| user_id | uuid FK users(id) | NOT NULL | 冗余,方便按用户查;Agent 永远看不到此字段 |
| role | enum | NOT NULL | `user` / `assistant` |
| content | text | NOT NULL | 消息正文 |
| layout_patch | jsonb | NULL | assistant 消息附带的 layout 改动(`{ pageIndex, imagesJson?, textsJson? }[]`),user 消息固定 NULL |
| usage | jsonb | NULL | assistant 消息附带的模型用量,user 消息固定 NULL |
| created_at | timestamptz | NOT NULL default now() | |

**索引**:
- `(album_id, created_at)` —— 按时间序拉对话流
- `(user_id, created_at desc)` —— 后台查某用户的全部 chat(用于客服 / 滥用排查)

**注意**:
- `layout_patch` 只描述"和上一版 layout 的差异",不重复保存整本相册。完整 layout 仍在 `albums.layout_json` 和 `album_pages` 两处。
- Agent 看到的对话历史**不带 `user_id` / `email`**,Web 转发时剥掉。

---

## 5. `agent_jobs`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | uuid PK | | |
| request_id | text | NOT NULL UNIQUE | 全链路追踪 + 浏览器轮询 key |
| album_id | uuid FK albums(id) | NOT NULL | |
| user_id | uuid FK users(id) | NOT NULL | |
| status | enum | NOT NULL default 'QUEUED' | QUEUED / RUNNING / COMPLETED / FAILED |
| stage | text | NULL | vision / writing / composing |
| progress | int | NOT NULL default 0 | 0-100 |
| usage | jsonb | NULL | `{ visionTokens, planningTokens, durationMs }` |
| error | jsonb | NULL | `{ code, message }` |
| created_at | timestamptz | NOT NULL default now() | |
| started_at | timestamptz | NULL | |
| completed_at | timestamptz | NULL | |

**索引**:
- `(user_id, created_at desc)`
- `(request_id)` —— UNIQUE 已隐含

---

## 6. `credit_holds`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | uuid PK | | |
| user_id | uuid FK users(id) | NOT NULL | |
| album_id | uuid FK albums(id) | NOT NULL | |
| amount | int | NOT NULL | 冻结积分数 |
| status | enum | NOT NULL default 'HOLDING' | HOLDING / SETTLED / RELEASED |
| created_at | timestamptz | NOT NULL default now() | |
| settled_at | timestamptz | NULL | |

---

## 7. `credit_ledger`

沿用 memoir-web 现有结构(暂不在本文档展开,等基建工程师同步过来)。
**修改 credit_ledger 必须先和架构师沟通**——这是支付相关表。

---

## 8. 状态机

```
album.status:
  AGENT_RUNNING ──► EDITING ──► COMPLETED
       │              │
       └─►FAILED      └─►FAILED

  • AGENT_RUNNING → EDITING 时冻结积分(创建 credit_hold,status=HOLDING)
  • EDITING → COMPLETED 时结算积分(credit_hold.status=SETTLED + ledger 扣减)
  • 任何 → FAILED 时释放积分(credit_hold.status=RELEASED,不扣)

agent_jobs.status:
  QUEUED → RUNNING → COMPLETED
                  └→ FAILED

credit_holds.status:
  HOLDING → SETTLED / RELEASED
```

---

## 9. Drizzle Schema 模板

```ts
// db/schema.ts (摘要)
import { pgTable, uuid, text, integer, jsonb, timestamp, pgEnum, uniqueIndex, index } from 'drizzle-orm/pg-core';

export const albumStatusEnum = pgEnum('album_status', [
  'AGENT_RUNNING', 'EDITING', 'COMPLETED', 'FAILED',
]);

export const albums = pgTable('albums', {
  id: uuid('id').primaryKey().defaultRandom(),
  userId: uuid('user_id').notNull().references(() => users.id),
  title: text('title').notNull(),
  status: albumStatusEnum('status').notNull().default('AGENT_RUNNING'),
  prompt: text('prompt').notNull(),
  layoutJson: jsonb('layout_json'),
  photoCount: integer('photo_count').notNull(),
  pageCount: integer('page_count').notNull().default(0),
  pdfR2Key: text('pdf_r2_key'),
  pdfUrl: text('pdf_url'),
  creditHoldId: uuid('credit_hold_id'),
  errorMessage: text('error_message'),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
}, (t) => ({
  userCreated: index('idx_albums_user_created').on(t.userId, t.createdAt),
}));

export type Album = typeof albums.$inferSelect;
export type NewAlbum = typeof albums.$inferInsert;
```

---

## 10. Migration 流程

```bash
# 1. 改 schema.ts
# 2. 生成 migration
pnpm --filter web db:generate

# 3. review 生成的 SQL
# 4. apply
pnpm --filter web db:migrate
```

**migration 硬规则**:
- 一次 migration **只做一件事**(加一列 / 加一个索引 / 一张表)
- 改字段类型 / 改 NULL 约束之类的破坏性修改,**先开 issue 由架构师 review**
- migration 文件名带日期 + 简短描述,如 `20260527_add_albums_pdf_r2_key.sql`

---

## 11. 自查

- [ ] 我加的字段命名是 snake_case 吗?
- [ ] 索引建对了吗?(列表查询需要 (user_id, created_at desc))
- [ ] 是不是只改了一件事?
- [ ] 涉及 `users` / `credit_ledger` 时,有没有先和架构师沟通?
