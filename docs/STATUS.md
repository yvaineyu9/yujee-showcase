# Yujee 海外版 · 项目状态

> 遇己(Yujee)AI 人生纪念册 · 海外 Web。最后更新:2026-05-29。
> 本文是项目全景快照,随大变更更新。权威细节见 `architecture.md` / `migration-plan.md` / 各 `docs/web/*` `docs/agent/*`。

## 一句话

从老 videofly fork(memoir-web)**完全重写**成 web + agent 分体架构,**已上线 https://yujeeai.com**,真用户可用。约 200 个源文件,22 个 PR,端到端跑通。

## 上线状态

| | 地址 | 状态 |
|---|---|---|
| Web | https://yujeeai.com | live,SSL 有效(307→/en→200) |
| Agent | https://yujee-agent.fly.dev | /health 200(东京双机) |
| 核心流程 | 注册→登录→选图→生成→出片 | 已验证 |

主线:`main`。

## 架构(异步 HTTP + 浏览器轮询,非 SSE)

```
浏览器 ──base64──► Web (Next.js / Vercel) ──fire&forget 202──► Agent (FastAPI / Fly 东京)
  │ 原图只在这               │ 不落盘,直接转发                  │ 火山 doubao
  │ @react-pdf 本地出 PDF    ▼                                  ▼ vision → writing → composing
  └──presigned PUT──► R2   Neon Postgres (11 表)          callback ──► Web,浏览器轮询库读状态
```

核心承诺:**原图永不落服务器**。base64 进 agent 用完即弃;PDF 浏览器生成,presigned PUT 直传 R2。

## 基础设施(均在 yvaineyu9 账号下)

| 层 | 服务 | 备注 |
|---|---|---|
| Web | Vercel,项目 `yujee-web` | git 集成**不自动部署**;改 env 后要手动 `vercel deploy --prod` |
| Agent | Fly.io,app `yujee-agent`,region `nrt`(东京) | `min_machines_running=1` 常驻;改代码 `fly deploy` |
| DB | Neon Postgres,库名 **`yujee`**(11 表) | 老 memoir-web 库(53 albums 实数据)另存,未触碰 |
| 对象存储 | Cloudflare R2 | 只存 PDF;env 变量名用 `R2_*`(老项目是 `STORAGE_*`) |
| AI | 火山方舟 doubao(单个 ARK key) | vision = `doubao-seed-1-6-vision-250815`;planning = `doubao-seed-2-0-lite-260428` |
| 支付 | Creem(海外主通道) | Stripe 代码已写,未接 live |
| 邮件 | Resend | `EMAIL_DELIVERY=resend` |
| 域名 | Cloudflare DNS,A 记录 → Vercel `76.76.21.21` | DNS-only(灰云),Vercel 自签 SSL |

## 功能清单(老 18 页 + 20 API 全迁完)

- **营销**:`/` `/pricing` `/privacy` `/terms`(en + zh)
- **认证**:better-auth 邮箱密码;新用户送 1000 积分(`FREE_PLAN_CREDITS`)
- **核心**:
  - `/create` — 浏览器 Canvas 压 800px → base64,原图存 IndexedDB,`POST /api/v1/jobs`
  - `/album/[uuid]` — 2s 轮询 → 渲染 21 模板 → 双击就地编辑 + Chat 改版 + PDF 导出
- **面板**:`/my-albums`(列表/状态/删除) `/credits`(余额/流水/充值) `/settings`
- **后台**:`/admin` 四页 + `recover-stuck` / `cleanup-photos`(Vercel cron 每日)
- **积分**:precheck → hold → settle / release,credit_ledger 双写,失败自动退

## 关键决策(非显而易见)

1. **AI 全走火山,没用 DeepSeek** —— agent 的 `DEEPSEEK_*` 槽位 base_url 指向火山 ark,一个 ARK key 同时跑 vision 和 planning。
2. **积分制**,不是早期设想的"按本收费"。
3. **composing 确定性兜底** —— doubao-lite 不可靠满足槽位 orientation/quality 约束,模型 repair 用尽后跑 `coerce_image_slots`(违规槽留空/换图),保证 layout 过校验、album 必出片。
4. **submit 超时 30s** —— web→agent `/v1/layout` 转发 ~2MB base64,跨区 + 冷启动需要 >8s;`jobs/route.ts` `maxDuration=60`。
5. **AGENT_SHARED_SECRET** —— fly 与 Vercel 必须同值,存本地 gitignored `docs/deploy/secrets.local.env`(在主仓库,勿提交)。

## 二期 backlog(open issue,已明确推迟)

- **#42 composing 版面质量** —— doubao-lite 兜底能出片但不完美(可能空槽)。要更高质量:换更强 planning 模型(火山方舟 DeepSeek-V3 接入点)或改成更结构化"工作流"。**核心二期方向。**
- **#31 PDF 中文字体** —— Noto Serif/Sans SC 全量 ~18MB,客户端导出需下载,待 subset 或只留 Sans。

## 已知风险 / 运维要点

- **Vercel cron 每日**(Hobby 套餐限制):卡死 job 最多 24h 才被 recover-stuck 回收;量大需升 Pro 才能 sub-daily。
- **改 env 必须手动重部** —— Vercel git 集成未触发自动部署,`vercel deploy --prod`。
- **Codex node 抢 PATH** —— 本机跑 `pnpm` / `vercel` / `npm i -g` 前先 `export PATH="/Users/smalldog/.nvm/versions/node/v24.15.0/bin:$PATH"`,否则 `/Applications/Codex.app` 的 node 抢占。
- **真火山规模未验** —— >10 张照片 / 16 页路径没端到端测过。
- **密钥位置** —— ARK / R2 / Creem / Resend 在老 `memoir-web/.env.local`;AGENT_SHARED_SECRET / CRON_SECRET 在 `docs/deploy/secrets.local.env`。

## 现存文档(产品/架构)

- 架构 + 十条不变式:`architecture.md`
- Agent 设计:`agent/design.md`(pipeline / prompt / 9 规则 / quality enum §5.1)、`agent/contract.md`
- Web 规范:`web/{api,database,layering,directory,conventions,errors}.md`
- 部署变量:`deploy/env.production.md`

> 迁移过程脚手架(migration-plan / migration-routes / evidence / RUN_DEMO)已于上线后清理,需要可查 git 历史。
