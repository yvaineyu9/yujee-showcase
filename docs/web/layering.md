# Web 分层架构

> **前置阅读**: `CLAUDE.md` → `docs/architecture.md`
>
> 谁读这份: Web 基建、DB/Repo、API、Service、UI 工程师都要读。

---

## 1. 四层模型

Web 内部严格分四层,**数据从上往下流,绝对不允许跨层、不允许反向依赖**。

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Route (app/.../route.ts, app/.../page.tsx)    │
│     职责: 接请求 / 返响应 / 参数解析                       │
│     ↓                                                    │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Service (services/*/...-service.ts)           │
│     职责: 业务编排 / 事务 / 调外部 / 调多个 repo            │
│     ↓                                                    │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Repository (db/repos/*.ts)                    │
│     职责: 纯数据库读写,一张表一个 repo                     │
│     ↓                                                    │
├─────────────────────────────────────────────────────────┤
│  Layer 4: Lib (lib/*)                                   │
│     职责: 横向能力(auth/r2/agent-client/zod/log)         │
│     特点: 无业务知识,可被任何层调用                        │
└─────────────────────────────────────────────────────────┘
```

依赖方向: **Route → Service → Repo → Lib**。

---

## 2. 禁止事项

| ❌ 禁止 | ✅ 应该 |
|---|---|
| Route 直接 import `db` 或 drizzle | Route 调 Service,Service 调 Repo |
| Route 直接调外部 HTTP / OpenAI / R2 | 走 `lib/*` 封装,再由 Service 调用 |
| Service A import Service B 的 repo | Service A 调 Service B 的对象 |
| Repo 调 Service | Repo 只写 SQL,逻辑挪到 Service |
| Repo 写日志 / 写 zod 校验 | 日志在 Service,校验在 Route(parseBody)|
| 组件直接 fetch repo / lib | 组件只调 Server Action 或 `/api/*` |
| Service 之间循环依赖 | 拆共享逻辑到 `lib/*` 或事件 |

---

## 3. 每层的边界规则

### 3.1 Route(`app/.../route.ts`)

- 总行数 **≤ 40 行**
- 不 import `db`、drizzle、Agent SDK、外部 HTTP
- 不写 if/else 业务分支
- 三件事: ① requireAuth ② parseBody(zod) ③ 调一个 service 方法
- 错误处理统一走 `err.fromException(e)`

代码模板见 `docs/web/conventions.md §3`。

### 3.2 Service(`services/*/*-service.ts`)

- 导出**一个对象**,不是 class
- 每个方法第一参是 `userId` 或 `actor`
- 所有业务规则、事务、外部调用都在这里
- 抛 `AppError`(见 `docs/web/errors.md`),不抛字符串
- 跨服务调用通过 import 另一个 service 对象,**不直接拿对方 repo**

### 3.3 Repo(`db/repos/*.ts`)

- 一张表一个文件
- 只导出**纯数据访问函数**
- 不 import service / 业务 lib
- 不写日志、不写 zod 校验、不做权限判断
- 可以 import: `db/client`、`db/schema`、`drizzle-orm` 操作符

### 3.4 Lib(`lib/*`)

- 无业务知识(不知道"相册""积分"是什么)
- 不依赖具体表
- 可被任何层调用
- 典型成员: `auth`、`agent`、`storage`、`api`、`log`、`env`

---

## 4. 跨服务通信

**Service 之间禁止 import repo**,只能 import 对方的 service 对象:

```ts
// ✅ 正确
import { creditService } from '@/services/credit/credit-service';
await creditService.hold(userId, amount);

// ❌ 错误
import { creditHoldRepo } from '@/db/repos/credit-hold-repo';
await creditHoldRepo.create({ ... });
```

如果 A、B 两个 service 互相 import 形成循环,**说明它们共用一段逻辑,把那段抽到 `lib/`**——不要用 events、不要 setTimeout、不要 dynamic import 绕。

---

## 5. 组件 / Server Action

- **组件不调 repo,不调 lib(除 UI lib),不调 service**
- 组件用 `fetch('/api/v1/...')` 或 Next.js Server Action 调到 Route 层
- Server Action 本身相当于一个 Route,遵循 Route 的硬规则

---

## 6. 自查清单

提交前回答:

- [ ] route.ts 是否 ≤ 40 行?
- [ ] route.ts 是否 import 了 `db` / drizzle / 外部 SDK?(应该是否)
- [ ] service 方法第一参是不是 userId / actor?
- [ ] service 是否 import 了别人的 repo?(应该是否,只 import 别人的 service)
- [ ] repo 是否只做数据访问?(没有日志、没有校验、没有业务判断)
- [ ] 有没有循环依赖?(import 链画出来,看有没有环)
