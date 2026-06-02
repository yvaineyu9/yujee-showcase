import { z } from 'zod';
import { AlbumStatus, JobStage, JobStatus } from './enums.js';
import { AlbumLayoutPlan } from './layout.js';

const BrowserPhoto = z.object({
  photoId: z.string().min(1),
  base64: z.string().min(1),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
});
export type BrowserPhoto = z.infer<typeof BrowserPhoto>;

export const CreateJobRequest = z.object({
  requestId: z.string().uuid(),
  prompt: z.string().min(1).max(500),
  language: z.enum(['zh', 'en']),
  photos: z.array(BrowserPhoto).min(1).max(30),
});
export type CreateJobRequest = z.infer<typeof CreateJobRequest>;

export const CreateJobResponse = z.object({
  albumId: z.string().min(1),
  requestId: z.string().min(1),
});
export type CreateJobResponse = z.infer<typeof CreateJobResponse>;

// Retry a FAILED album by reusing the same albumId (§6.5.3). No prompt: the
// rerun reuses the stored album.prompt. The browser resends base64 under a fresh
// requestId. Response shape matches CreateJobResponse (same albumId echoed back).
// Min 1 photo, aligned with CT-1 (§6.5.6) — the Agent renders 1–2 photos with
// text-only layouts.
export const RetryJobRequest = z.object({
  requestId: z.string().uuid(),
  language: z.enum(['zh', 'en']),
  photos: z.array(BrowserPhoto).min(1).max(30),
});
export type RetryJobRequest = z.infer<typeof RetryJobRequest>;

export const JobStatusResponse = z.object({
  requestId: z.string().min(1),
  albumId: z.string().min(1),
  status: JobStatus,
  stage: JobStage.nullable(),
  progress: z.number().int().min(0).max(100),
  error: z
    .object({
      code: z.string().min(1),
      message: z.string(),
    })
    .nullable(),
});
export type JobStatusResponse = z.infer<typeof JobStatusResponse>;

const AlbumSummary = z.object({
  id: z.string().min(1),
  title: z.string(),
  status: AlbumStatus,
  layoutJson: AlbumLayoutPlan.nullable(),
});
export type AlbumSummary = z.infer<typeof AlbumSummary>;

const AlbumPage = z.object({
  pageIndex: z.number().int().nonnegative(),
  templateId: z.string().min(1),
  imagesJson: z.record(z.string(), z.string()),
  textsJson: z.record(z.string(), z.string()),
});
export type AlbumPage = z.infer<typeof AlbumPage>;

export const AlbumDetailResponse = z.object({
  album: AlbumSummary,
  pages: z.array(AlbumPage),
});
export type AlbumDetailResponse = z.infer<typeof AlbumDetailResponse>;

export const PageUpdateRequest = z
  .object({
    imagesJson: z.record(z.string(), z.string()).optional(),
    textsJson: z.record(z.string(), z.string()).optional(),
  })
  .refine((v) => v.imagesJson !== undefined || v.textsJson !== undefined, {
    message: 'must provide imagesJson or textsJson',
  });
export type PageUpdateRequest = z.infer<typeof PageUpdateRequest>;

export const PdfUploadUrlRequest = z.object({
  contentType: z.literal('application/pdf'),
  size: z
    .number()
    .int()
    .positive()
    .max(50 * 1024 * 1024),
});
export type PdfUploadUrlRequest = z.infer<typeof PdfUploadUrlRequest>;

export const PdfUploadUrlResponse = z.object({
  putUrl: z.string().url(),
  r2Key: z.string().min(1),
  publicUrl: z.string().url(),
});
export type PdfUploadUrlResponse = z.infer<typeof PdfUploadUrlResponse>;

export const PdfCompleteRequest = z.object({
  r2Key: z.string().min(1),
});
export type PdfCompleteRequest = z.infer<typeof PdfCompleteRequest>;
