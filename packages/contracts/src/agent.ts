import { z } from 'zod';
import { JobStage } from './enums.js';
import { AlbumLayoutPlan } from './layout.js';

const AgentPhoto = z.object({
  photoId: z.string().min(1),
  base64: z.string().min(1),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
});
export type AgentPhoto = z.infer<typeof AgentPhoto>;

export const AgentLayoutRequest = z.object({
  requestId: z.string().min(1),
  prompt: z.string().min(1).max(500),
  language: z.enum(['zh', 'en']),
  callbackUrl: z.string().url(),
  photos: z.array(AgentPhoto).min(1).max(30),
});
export type AgentLayoutRequest = z.infer<typeof AgentLayoutRequest>;

export const AgentLayoutAcceptedResponse = z.object({
  ok: z.literal(true),
  data: z.object({
    requestId: z.string().min(1),
    accepted: z.literal(true),
  }),
});
export type AgentLayoutAcceptedResponse = z.infer<
  typeof AgentLayoutAcceptedResponse
>;

const CallbackError = z.object({
  code: z.string().min(1),
  message: z.string(),
});
export type CallbackError = z.infer<typeof CallbackError>;

const CallbackUsage = z.object({
  visionTokens: z.number().int().nonnegative(),
  planningTokens: z.number().int().nonnegative(),
  durationMs: z.number().int().nonnegative(),
});
export type CallbackUsage = z.infer<typeof CallbackUsage>;

const ProgressCallback = z.object({
  event: z.literal('progress'),
  requestId: z.string().min(1),
  stage: JobStage,
  progress: z.number().int().min(0).max(100),
  message: z.string().optional(),
});

const CompletedCallback = z.object({
  event: z.literal('completed'),
  requestId: z.string().min(1),
  layout: AlbumLayoutPlan,
  usage: CallbackUsage,
  message: z.string().optional(),
});

const FailedCallback = z.object({
  event: z.literal('failed'),
  requestId: z.string().min(1),
  error: CallbackError,
  message: z.string().optional(),
});

export const JobProgressCallback = z.discriminatedUnion('event', [
  ProgressCallback,
  CompletedCallback,
  FailedCallback,
]);
export type JobProgressCallback = z.infer<typeof JobProgressCallback>;
