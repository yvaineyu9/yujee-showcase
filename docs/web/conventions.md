# Web 代码规范

> **前置阅读**: `CLAUDE.md` → `docs/architecture.md` → `docs/web/layering.md`
>
> 谁读这份: 写 route / service / repo / 组件的所有人。

---

## 1. 命名约定

| 类型 | 规则 | 例 |
|---|---|---|
| 普通文件 | kebab-case.ts | `album-service.ts` |
| 组件文件 | PascalCase.tsx | `AlbumCard.tsx` |
| Service 对象 | `xxxService` | `albumService` |
| Repo 对象 | `xxxRepo` | `albumRepo` |
| Repo 函数 | `findX` / `createX` / `updateX` / `deleteX` | `findAlbumById` |
| API 错误码 | 大写下划线 | `CREDIT_INSUFFICIENT` |
| DB 表名 | snake_case 复数 | `agent_jobs` |
| DB 字段 | snake_case | `created_at` |
| TS 字段 | camelCase | `createdAt` |
| Drizzle 字段映射 | `createdAt: timestamp('created_at')` | |
| 环境变量 | 大写下划线 | `AGENT_SHARED_SECRET` |
| URL 路径 | kebab-case | `/api/v1/agent-layout` |
| Zustand store | `xxx-store.ts` 导出 `useXxxStore` | `usePhotosStore` |

---

## 2. Route 模板(所有 `route.ts` 按这个写)

```ts
// app/api/v1/.../route.ts
import { requireAuth } from '@/lib/auth/require-auth';
import { parseBody } from '@/lib/api/zod-parse';
import { ok } from '@/lib/api/ok';
import { fromException } from '@/lib/api/from-exception';
import { albumService } from '@/services/album/album-service';
import { z } from 'zod';

const BodySchema = z.object({
  title: z.string().min(1).max(100),
});

export async function POST(req: Request) {
  try {
    const user = await requireAuth(req);
    const body = await parseBody(BodySchema, req);
    const data = await albumService.create(user.id, body);
    return ok(data);
  } catch (e) {
    return fromException(e);
  }
}
```

**Route 的硬规则**:
- 总行数 ≤ 40
- 不 import `db` / drizzle / 外部 SDK
- 不写 if/else 业务分支
- 三件事: requireAuth → parseBody → 调 service
- 异常一律 `fromException(e)`

---

## 3. Service 模板

```ts
// services/album/album-service.ts
import { db } from '@/db/client';
import { albumRepo } from '@/db/repos/album-repo';
import { creditService } from '@/services/credit/credit-service';
import { ERRORS } from '@/lib/api/error-codes';
import { logger } from '@/lib/log/logger';

export const albumService = {
  async create(userId: string, input: { title: string }) {
    logger.info({ userId, action: 'album.create' });

    return db.transaction(async (tx) => {
      const album = await albumRepo.create(tx, { userId, ...input });
      await creditService.hold(tx, userId, album.id, 10);
      return album;
    });
  },

  async findOwned(userId: string, albumId: string) {
    const album = await albumRepo.findById(albumId);
    if (!album) throw ERRORS.ALBUM_NOT_FOUND();
    if (album.userId !== userId) throw ERRORS.ALBUM_NOT_OWNED();
    return album;
  },
};
```

**Service 的硬规则**:
- 导出**一个对象**(不是 class)
- 每个方法第一参 = `userId` 或 `actor`
- 抛 `AppError`(`ERRORS.XXX()`)
- 跨服务调用通过 import 对方 service 对象,**不直接拿 repo**
- 事务用 `db.transaction(async (tx) => ...)`,把 `tx` 传给 repo

---

## 4. Repo 模板

```ts
// db/repos/album-repo.ts
import { db } from '@/db/client';
import { albums, type NewAlbum } from '@/db/schema';
import { eq, desc } from 'drizzle-orm';
import type { PgTransaction } from 'drizzle-orm/pg-core';

type Tx = PgTransaction<any, any, any> | typeof db;

export const albumRepo = {
  findById: (id: string) =>
    db.select().from(albums).where(eq(albums.id, id)).limit(1).then(r => r[0]),

  findByUser: (userId: string) =>
    db.select().from(albums)
      .where(eq(albums.userId, userId))
      .orderBy(desc(albums.createdAt)),

  create: (tx: Tx, data: NewAlbum) =>
    tx.insert(albums).values(data).returning().then(r => r[0]),

  updateStatus: (tx: Tx, id: string, status: AlbumStatus) =>
    tx.update(albums).set({ status }).where(eq(albums.id, id)),
};
```

**Repo 的硬规则**:
- 一张表一个文件
- 只导出**纯数据访问函数**
- 写操作的第一参数是 `tx`(支持事务调用)
- 不 import service / 业务 lib
- 不写日志、不写校验

---

## 5. Lib 模板(以 agent-client 为例)

```ts
// lib/agent/agent-client.ts
import { env } from '@/lib/env';

export const agentClient = {
  async generateLayout(payload: AgentRequest): Promise<AgentResponse> {
    const res = await fetch(`${env.AGENT_BASE_URL}/v1/layout`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.AGENT_SHARED_SECRET}`,
        'Content-Type': 'application/json',
        'X-Request-Id': payload.requestId,
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(90_000),
    });
    if (!res.ok) throw new Error(`agent http ${res.status}`);
    return res.json();
  },
};
```

**Lib 的硬规则**:
- 不知道"相册""积分"是什么(无业务知识)
- 不依赖具体表
- 可被任何层调用

---

## 6. 组件规则

```tsx
// components/create/PromptInput.tsx
'use client';

import { useState } from 'react';

interface Props {
  onSubmit: (prompt: string) => void;
  disabled?: boolean;
}

export function PromptInput({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState('');
  return (
    <div>
      <textarea value={value} onChange={(e) => setValue(e.target.value)} disabled={disabled} />
      <button onClick={() => onSubmit(value)} disabled={disabled}>Start</button>
    </div>
  );
}
```

**组件硬规则**:
- 不直接调 `db` / `repo` / `service`
- 用 `fetch('/api/v1/...')` 或 Server Action
- props 用 `interface Props`,导出命名组件(不要 default export)
- 客户端组件加 `'use client'`,服务器组件不加

---

## 7. Zustand store 模板

```ts
// stores/photos-store.ts
import { create } from 'zustand';

interface LocalPhoto {
  photoId: string;
  file: File;
  base64?: string;
  width: number;
  height: number;
}

interface PhotosState {
  photos: LocalPhoto[];
  add: (photo: LocalPhoto) => void;
  remove: (photoId: string) => void;
  setBase64: (photoId: string, base64: string) => void;
  clear: () => void;
}

export const usePhotosStore = create<PhotosState>((set) => ({
  photos: [],
  add: (p) => set((s) => ({ photos: [...s.photos, p] })),
  remove: (id) => set((s) => ({ photos: s.photos.filter(p => p.photoId !== id) })),
  setBase64: (id, b64) => set((s) => ({
    photos: s.photos.map(p => p.photoId === id ? { ...p, base64: b64 } : p)
  })),
  clear: () => set({ photos: [] }),
}));
```

---

## 8. 注释规则

**默认不写注释**。代码靠命名自解释。只有以下情况写一行注释:

- 非显然的隐藏约束(如"R2 lifecycle 24h 自动过期")
- 非显然的边界条件(如"火山 API 不接受 > 800KB 的 base64")
- 业务依据(如"// 与产品约定: 失败不扣积分")

**禁止**:
- 说明代码做什么的注释(`// 创建相册`)
- TODO / FIXME(用 issue 跟踪)
- 多行 docstring

---

## 9. 提交前自查

- [ ] 文件名符合 §1?
- [ ] route.ts 是否 ≤ 40 行,符合 §2 模板?
- [ ] service 方法第一参是 userId / actor?
- [ ] service 抛 `ERRORS.XXX()`,不抛字符串?
- [ ] repo 写操作的第一参是 `tx`?
- [ ] 跨服务调用是否走对方 service?(不绕过去拿 repo)
- [ ] 组件是否直连 db / service?(应该否)
- [ ] 有多余注释吗?
