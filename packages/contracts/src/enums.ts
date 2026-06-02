import { z } from 'zod';

export const AlbumStatus = z.enum([
  'AGENT_RUNNING',
  'EDITING',
  'COMPLETED',
  'FAILED',
]);
export type AlbumStatus = z.infer<typeof AlbumStatus>;

export const JobStatus = z.enum([
  'QUEUED',
  'RUNNING',
  'COMPLETED',
  'FAILED',
]);
export type JobStatus = z.infer<typeof JobStatus>;

export const JobStage = z.enum(['vision', 'writing', 'composing']);
export type JobStage = z.infer<typeof JobStage>;

export const CallbackEvent = z.enum(['progress', 'completed', 'failed']);
export type CallbackEvent = z.infer<typeof CallbackEvent>;
