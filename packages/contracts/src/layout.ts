import { z } from 'zod';

export const PhotoOrientation = z.enum(['portrait', 'landscape', 'square']);
export type PhotoOrientation = z.infer<typeof PhotoOrientation>;

export const PhotoQuality = z.enum(['hero', 'detail', 'fill']);
export type PhotoQuality = z.infer<typeof PhotoQuality>;

export const Magazine = z.object({
  title: z.string().min(1).max(60),
  subtitle: z.string().max(100).optional(),
  style: z.string().min(1),
  language: z.enum(['zh', 'en']),
});
export type Magazine = z.infer<typeof Magazine>;

export const PhotoAnalysis = z.object({
  photoId: z.string().min(1),
  description: z.string(),
  tags: z.array(z.string()),
  quality: PhotoQuality,
  orientation: PhotoOrientation,
});
export type PhotoAnalysis = z.infer<typeof PhotoAnalysis>;

export const Page = z.object({
  pageIndex: z.number().int().nonnegative(),
  templateId: z.string().min(1),
  images: z.record(z.string(), z.string()),
  texts: z.record(z.string(), z.string()),
});
export type Page = z.infer<typeof Page>;

export const AlbumLayoutPlan = z.object({
  magazine: Magazine,
  photos: z.array(PhotoAnalysis),
  pages: z.array(Page).min(1),
});
export type AlbumLayoutPlan = z.infer<typeof AlbumLayoutPlan>;
