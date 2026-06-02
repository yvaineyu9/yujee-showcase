# Web 目录结构

> **前置阅读**: `CLAUDE.md` → `docs/architecture.md` → `docs/web/layering.md`
>
> 谁读这份: 所有 Web 工程师在创建新文件前必读。

这份文档定义 `apps/web/src/` 下**每一个目录的归属**。新增文件前先在这里找到对应目录,**找不到的先停下来问架构师**,不要随便建目录。

---

## 1. 顶层结构

```
apps/web/src/
├── app/                      # Layer 1: Routes & Pages
├── services/                 # Layer 2: 业务编排
├── db/                       # Layer 3: 数据
├── lib/                      # Layer 4: 横向能力
├── components/               # React UI 组件
├── stores/                   # Zustand 客户端状态
├── hooks/                    # React Hooks
├── config/                   # 静态产品配置
├── messages/                 # i18n 文案
└── styles/                   # 全局样式
```

---

## 2. `app/` —— Routes & Pages

```
app/
├── [locale]/                          # i18n 包裹层(所有用户页面)
│   ├── (marketing)/                   # 未登录可访问的营销页
│   │   ├── page.tsx                   # 首页
│   │   ├── pricing/page.tsx
│   │   ├── privacy/page.tsx
│   │   └── terms/page.tsx
│   ├── (auth)/                        # 登录/注册
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (tool)/                        # 核心工具页
│   │   ├── create/page.tsx            # Prompt + 照片选择
│   │   └── album/[uuid]/page.tsx      # 相册编辑器
│   ├── (dashboard)/                   # 登录后的私有页
│   │   ├── my-albums/page.tsx
│   │   ├── credits/page.tsx
│   │   └── settings/page.tsx
│   └── (admin)/                       # 内部管理
│       └── admin/...
└── api/
    ├── auth/[...all]/route.ts         # better-auth
    ├── health/route.ts
    ├── webhooks/
    │   ├── stripe/route.ts
    │   └── creem/route.ts
    └── v1/
        ├── jobs/
        │   ├── route.ts                            # POST 创建任务(fire-and-forget)
        │   └── [requestId]/
        │       └── route.ts                        # GET 轮询任务状态
        ├── albums/
        │   ├── route.ts                            # GET 列表
        │   └── [uuid]/
        │       ├── route.ts                        # GET/PATCH/DELETE
        │       ├── pages/[pageIndex]/route.ts      # PATCH 单页
        │       ├── pdf-upload-url/route.ts         # POST 签 PUT URL
        │       └── pdf/route.ts                    # PUT 标记完成 / GET 下载 URL
        ├── credit/
        │   ├── balance/route.ts
        │   └── history/route.ts
        └── internal/
            └── job-progress/route.ts               # Agent → Web 回调
```

详细 API 行为 → `docs/web/api.md`。

---

## 3. `services/` —— 业务编排

```
services/
├── generation/
│   └── generation-service.ts          # 编排: base64 → Agent → 存 album
├── album/
│   └── album-service.ts               # 相册 CRUD 业务规则
├── credit/
│   └── credit-service.ts              # 预检 / 冻结 / 结算 / 释放
├── job/
│   └── job-service.ts                 # job 状态机 + 进度更新
├── pdf/
│   └── pdf-service.ts                 # PDF 签 URL / 记录 / 分发
├── billing/
│   ├── stripe-service.ts
│   └── creem-service.ts
└── notification/
    └── email-service.ts
```

**新增 service 的判断**:
- 是不是一个**业务名词**(album / credit / pdf / billing)?如果是,可以独立成 service。
- 是不是一个**横向能力**(zod / http / log)?如果是,放 `lib/`。

---

## 4. `db/` —— 数据层

```
db/
├── client.ts                          # Drizzle 客户端单例
├── schema.ts                          # 所有表 + 枚举(权威)
├── enums.ts                           # 业务枚举
├── migrations/                        # drizzle-kit 生成
└── repos/                             # 一表一文件
    ├── user-repo.ts
    ├── album-repo.ts
    ├── album-page-repo.ts
    ├── agent-job-repo.ts
    ├── credit-hold-repo.ts
    └── credit-ledger-repo.ts
```

详细 schema → `docs/web/database.md`。

---

## 5. `lib/` —— 横向能力

```
lib/
├── auth/
│   ├── better-auth.ts                 # better-auth 配置
│   └── require-auth.ts                # API 用,未登录抛 401
├── api/
│   ├── ok.ts                          # ok(data)
│   ├── err.ts                         # err(code, msg, status)
│   ├── zod-parse.ts                   # parseBody(schema, req)
│   ├── error-codes.ts                 # AppError + ERRORS 常量
│   └── from-exception.ts              # 把已知/未知异常转 JSON 响应
├── agent/
│   └── agent-client.ts                # HTTP 调 Agent
├── storage/
│   ├── r2-client.ts
│   └── r2-presign.ts                  # 签 PUT URL
├── photo/
│   ├── compress.ts                    # 浏览器 Canvas 压缩(client only)
│   └── to-base64.ts
├── pdf/
│   └── render.ts                      # 浏览器 @react-pdf/renderer 入口
├── i18n/
│   └── routing.ts
├── seo/
│   └── metadata.ts
├── log/
│   └── logger.ts                      # pino,自动带 requestId
└── env.ts                             # 启动时校验所有 env,缺一不启
```

**新增 lib 的判断**:
- 它知道"相册""积分"是什么吗?如果知道,放 `services/` 而不是 `lib/`。

---

## 6. `components/` —— UI 组件

```
components/
├── create/                            # PromptInput / PhotoPicker / StartButton
├── editor/                            # EditorShell / PreviewPane / ProgressPanel
├── album/                             # 21 个模板组件 + 列表卡片
│   └── templates/                     # mag-01 ~ mag-21
├── pdf/                               # 浏览器 PDF 渲染组件
├── landing/                           # 营销页组件
├── pricing/
├── billing/
├── credits/
├── admin/
├── layout/                            # AppHeader / SideNav / Footer
└── ui/                                # shadcn/ui 基础组件
```

**组件命名**: PascalCase,文件名 = 组件名(`AlbumCard.tsx`)。

---

## 7. `stores/` —— Zustand 全局状态

```
stores/
├── editor-store.ts                    # 当前编辑器状态(currentPage / dirty)
├── photos-store.ts                    # 原图引用(File / blob URL)+ 压缩 base64 缓存
└── job-store.ts                       # 当前生成任务的进度
```

**注意**: photos-store 里的原图引用绝对不能被序列化上传——这是不变式 1。

---

## 8. `hooks/` —— React Hooks

```
hooks/
├── use-job-poll.ts                    # 2 秒一次轮询 /api/v1/jobs/[id]
├── use-album.ts                       # 加载并订阅单个 album
├── use-credit.ts                      # 加载余额
└── use-photo-compress.ts              # 触发浏览器压缩
```

---

## 9. `config/` —— 静态产品配置

```
config/
├── agent.ts                           # Agent URL / 超时 / 重试
├── photo.ts                           # 压缩参数 / 张数限制
├── templates.ts                       # 21 个模板的元数据
├── pricing.ts                         # 套餐 / 积分包 / 单次生成消耗
└── brand.ts                           # 品牌名 / 文案常量
```

**与 `services/` 的区别**: config 是**纯常量**,没有任何函数逻辑。

---

## 10. `messages/` & `styles/`

```
messages/
├── en.json
└── zh.json                            # 海外版以英文为主,zh 留作运营备用

styles/
├── globals.css
└── theme.css
```

---

## 11. 顶层不允许的目录

不要在 `src/` 下创建以下目录(memoir-web 有但 Yujee 不要):

- ❌ `actions/` —— 用 Server Action 时直接放在 `app/.../actions.ts`
- ❌ `payment/` —— 已归并到 `services/billing/`
- ❌ `registry/` —— 用不上 shadcn registry
- ❌ `content/` —— 第一版不做 CMS
- ❌ `mail/` —— 邮件模板归 `lib/email/templates/`(必要时再建)

---

## 12. 新增文件 / 目录的流程

1. 在本文件搜索关键词,找到归属目录
2. 找不到 → 在 GitHub issue 里 @架构师,说明新文件用途
3. **不要先创建,再补文档**——本文件是真相源,先改本文件再写代码
