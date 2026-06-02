import { z } from 'zod';
import { PhotoOrientation, PhotoQuality } from './layout';

export const TemplateSlotConstraint = z.object({
  orientation: z.array(PhotoOrientation),
  quality: z.array(PhotoQuality),
});
export type TemplateSlotConstraint = z.infer<typeof TemplateSlotConstraint>;

export const TemplateTextSlotType = z.enum([
  'array',
  'caption',
  'heading',
  'label',
  'meta',
  'paragraph',
  'quote',
]);
export type TemplateTextSlotType = z.infer<typeof TemplateTextSlotType>;

export const TemplateTextSlotConstraint = z.object({
  type: TemplateTextSlotType,
  minChars: z.number().int().nonnegative().optional(),
  maxChars: z.number().int().positive(),
});
export type TemplateTextSlotConstraint = z.infer<
  typeof TemplateTextSlotConstraint
>;

export const TemplateCategory = z.enum([
  'cover',
  'spread',
  'single',
  'grid',
  'closing',
]);
export type TemplateCategory = z.infer<typeof TemplateCategory>;

export const TemplateDef = z.object({
  id: z.string(),
  category: TemplateCategory,
  imageSlots: z.record(z.string(), TemplateSlotConstraint),
  textSlots: z.record(z.string(), TemplateTextSlotConstraint),
});
export type TemplateDef = z.infer<typeof TemplateDef>;

/**
 * 21 template registry imported from yvaineyu9/memoir:
 *   - frontend/schema.js
 *   - frontend/layouts/<template>/template.meta.json
 *
 * This registry is the only allowed templateId set for Agent composing and
 * chat-edit validation.
 */
export const TEMPLATES: Record<string, TemplateDef> = {
  'mag-01': {
    id: 'mag-01',
    category: 'cover',
    imageSlots: {
      image: { orientation: ['landscape'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      heading: { type: 'heading', minChars: 4, maxChars: 12 },
      sideText: { type: 'label', minChars: 15, maxChars: 30 },
      caption1: { type: 'caption', minChars: 40, maxChars: 80 },
      caption2: { type: 'caption', minChars: 40, maxChars: 80 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-02': {
    id: 'mag-02',
    category: 'spread',
    imageSlots: {},
    textSlots: {
      // mag-02 是纯文字目录页,items 是字符串数组。
      // maxChars 在 'array' 类型下表示**单条**条目的字符上限(非合计),
      // 推断自 memoir 老仓库视觉密度:目录条目 ≤ 240 字符可容纳一段
      // 短描述。条目总数由排版引擎按版面溢出截断,不在 schema 里限。
      items: { type: 'array', maxChars: 240 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-03': {
    id: 'mag-03',
    category: 'single',
    imageSlots: {
      image: { orientation: ['portrait'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      category: { type: 'label', minChars: 5, maxChars: 15 },
      location: { type: 'label', minChars: 10, maxChars: 20 },
      caption: { type: 'caption', minChars: 0, maxChars: 60 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-04': {
    id: 'mag-04',
    category: 'spread',
    imageSlots: {
      image1: { orientation: ['landscape'], quality: ['hero', 'detail'] },
      image2: { orientation: ['portrait'], quality: ['detail', 'fill'] },
      image3: { orientation: ['square'], quality: ['detail', 'fill'] },
    },
    textSlots: {
      caption1: { type: 'caption', minChars: 40, maxChars: 80 },
      caption2: { type: 'caption', minChars: 40, maxChars: 80 },
      dateNum: { type: 'meta', minChars: 5, maxChars: 5 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-05': {
    id: 'mag-05',
    category: 'single',
    imageSlots: {
      image: { orientation: ['landscape'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      title: { type: 'heading', minChars: 10, maxChars: 25 },
      topRight: { type: 'label', minChars: 10, maxChars: 20 },
      caption: { type: 'paragraph', minChars: 60, maxChars: 120 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-06': {
    id: 'mag-06',
    category: 'single',
    imageSlots: {
      image: { orientation: ['portrait'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      category: { type: 'label', minChars: 5, maxChars: 15 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-07': {
    id: 'mag-07',
    category: 'spread',
    imageSlots: {
      imageTop: { orientation: ['landscape'], quality: ['detail', 'fill'] },
      imageMain: { orientation: ['portrait'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      caption1: { type: 'caption', minChars: 40, maxChars: 80 },
      caption2: { type: 'caption', minChars: 40, maxChars: 80 },
      caption3: { type: 'caption', minChars: 40, maxChars: 80 },
      title: { type: 'heading', minChars: 6, maxChars: 16 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-08': {
    id: 'mag-08',
    category: 'single',
    imageSlots: {
      image: { orientation: ['portrait'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      dateNum: { type: 'meta', minChars: 5, maxChars: 5 },
      caption1: { type: 'caption', minChars: 40, maxChars: 80 },
      caption2: { type: 'caption', minChars: 40, maxChars: 80 },
      title: { type: 'heading', minChars: 4, maxChars: 10 },
      subtitle: { type: 'label', minChars: 10, maxChars: 25 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-09': {
    id: 'mag-09',
    category: 'spread',
    imageSlots: {
      imageTop: { orientation: ['landscape'], quality: ['detail', 'fill'] },
      imageMain: { orientation: ['square'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      quote: { type: 'quote', minChars: 30, maxChars: 60 },
      caption1: { type: 'caption', minChars: 40, maxChars: 80 },
      title: { type: 'heading', minChars: 6, maxChars: 16 },
      caption2: { type: 'caption', minChars: 40, maxChars: 80 },
      caption3: { type: 'caption', minChars: 40, maxChars: 80 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-10': {
    id: 'mag-10',
    category: 'grid',
    imageSlots: {
      'cells[0].image': {
        orientation: ['square'],
        quality: ['detail', 'fill'],
      },
      'cells[1].image': {
        orientation: ['square'],
        quality: ['detail', 'fill'],
      },
      'cells[2].image': {
        orientation: ['square'],
        quality: ['detail', 'fill'],
      },
      'cells[3].image': {
        orientation: ['square'],
        quality: ['detail', 'fill'],
      },
    },
    textSlots: {
      // mag-10 是 2x2 grid 模板,cells 是每格的小标题/说明字符串数组,
      // 与 imageSlots cells[0..3].image 一一对应(4 格)。
      // maxChars 在 'array' 类型下表示**单格**文本上限(非合计),
      // 推断 160 字符:grid 格子小,文本量比 mag-02 目录条目低一档。
      // 数组长度逻辑上 = 4(由 cells image slot 数对齐),schema 不强制。
      cells: { type: 'array', maxChars: 160 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-11': {
    id: 'mag-11',
    category: 'single',
    imageSlots: {
      image: { orientation: ['portrait'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      title: { type: 'heading', minChars: 6, maxChars: 16 },
      plate: { type: 'label', minChars: 10, maxChars: 20 },
      caption2: { type: 'caption', minChars: 40, maxChars: 80 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-12': {
    id: 'mag-12',
    category: 'spread',
    imageSlots: {
      imageTop: { orientation: ['square'], quality: ['detail', 'fill'] },
      imageBottom: { orientation: ['portrait'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      num1: { type: 'meta', minChars: 2, maxChars: 2 },
      num2: { type: 'meta', minChars: 2, maxChars: 2 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-13': {
    id: 'mag-13',
    category: 'cover',
    imageSlots: {
      image: { orientation: ['landscape'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      title: { type: 'heading', minChars: 10, maxChars: 30 },
      intro: { type: 'paragraph', minChars: 40, maxChars: 80 },
      caption1: { type: 'caption', minChars: 40, maxChars: 80 },
      caption2: { type: 'caption', minChars: 40, maxChars: 80 },
      issue: { type: 'label', minChars: 10, maxChars: 15 },
      credit: { type: 'label', minChars: 15, maxChars: 30 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-14': {
    id: 'mag-14',
    category: 'spread',
    imageSlots: {},
    textSlots: {
      bigNum: { type: 'meta', minChars: 2, maxChars: 2 },
      bigNumTotal: { type: 'meta', minChars: 2, maxChars: 2 },
      body: { type: 'paragraph', minChars: 40, maxChars: 80 },
      subtitleQuote: { type: 'quote', minChars: 20, maxChars: 50 },
      bracketQuote: { type: 'quote', minChars: 40, maxChars: 80 },
      footnote: { type: 'caption', minChars: 30, maxChars: 60 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-15': {
    id: 'mag-15',
    category: 'spread',
    imageSlots: {
      imagePerson: { orientation: ['portrait'], quality: ['hero', 'detail'] },
      imageRoad: { orientation: ['landscape'], quality: ['detail', 'fill'] },
    },
    textSlots: {
      body: { type: 'paragraph', minChars: 30, maxChars: 60 },
      title: { type: 'heading', minChars: 6, maxChars: 16 },
      date: { type: 'label', minChars: 10, maxChars: 20 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-16': {
    id: 'mag-16',
    category: 'spread',
    imageSlots: {
      imageTiny: { orientation: ['portrait'], quality: ['fill'] },
      imagePerson: { orientation: ['landscape'], quality: ['hero', 'detail'] },
      imageHarbor: { orientation: ['landscape'], quality: ['detail', 'fill'] },
    },
    textSlots: {
      caption1: { type: 'caption', minChars: 40, maxChars: 80 },
      caption2: { type: 'caption', minChars: 40, maxChars: 80 },
      caption3: { type: 'caption', minChars: 40, maxChars: 80 },
      quote: { type: 'quote', minChars: 30, maxChars: 60 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-17': {
    id: 'mag-17',
    category: 'closing',
    imageSlots: {
      image: { orientation: ['portrait'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      name1: { type: 'label', minChars: 8, maxChars: 20 },
      name2: { type: 'label', minChars: 8, maxChars: 20 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-18': {
    id: 'mag-18',
    category: 'spread',
    imageSlots: {
      imageLeft: { orientation: ['portrait'], quality: ['detail', 'fill'] },
      imageRight: { orientation: ['portrait'], quality: ['detail', 'fill'] },
    },
    textSlots: {
      numLeft: { type: 'meta', minChars: 2, maxChars: 2 },
      numRight: { type: 'meta', minChars: 2, maxChars: 2 },
      captionLeft: { type: 'caption', minChars: 40, maxChars: 80 },
      captionRight: { type: 'caption', minChars: 40, maxChars: 80 },
      subtitle: { type: 'quote', minChars: 30, maxChars: 60 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-19': {
    id: 'mag-19',
    category: 'single',
    imageSlots: {
      image: { orientation: ['landscape'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      intro: { type: 'paragraph', minChars: 40, maxChars: 80 },
      captionLeft: { type: 'caption', minChars: 40, maxChars: 80 },
      captionRight: { type: 'caption', minChars: 40, maxChars: 80 },
      quote: { type: 'quote', minChars: 30, maxChars: 60 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  'mag-20': {
    id: 'mag-20',
    category: 'cover',
    imageSlots: {},
    textSlots: {
      boxText: { type: 'paragraph', minChars: 15, maxChars: 40 },
      title: { type: 'heading', minChars: 10, maxChars: 30 },
      plate: { type: 'label', minChars: 10, maxChars: 25 },
      folio: { type: 'meta', minChars: 2, maxChars: 2 },
    },
  },
  p01: {
    id: 'p01',
    category: 'cover',
    imageSlots: {
      image: { orientation: ['portrait'], quality: ['hero', 'detail'] },
    },
    textSlots: {
      title: { type: 'heading', minChars: 8, maxChars: 20 },
      body: { type: 'paragraph', minChars: 40, maxChars: 80 },
      category: { type: 'label', minChars: 10, maxChars: 20 },
      vol: { type: 'meta', minChars: 2, maxChars: 4 },
      date: { type: 'meta', minChars: 5, maxChars: 10 },
    },
  },
};

export const TEMPLATE_IDS = Object.keys(TEMPLATES);

export const TemplateIdEnum = z.enum(TEMPLATE_IDS as [string, ...string[]]);

export function isKnownTemplate(id: string): boolean {
  return id in TEMPLATES;
}

export function getTemplate(id: string): TemplateDef | undefined {
  return TEMPLATES[id];
}

export function validateSlotsForTemplate(
  templateId: string,
  imageSlotKeys: string[],
  textSlotKeys: string[],
): { ok: true } | { ok: false; reason: string } {
  const tpl = TEMPLATES[templateId];
  if (!tpl) return { ok: false, reason: `unknown templateId: ${templateId}` };

  for (const k of imageSlotKeys) {
    if (!(k in tpl.imageSlots)) {
      return {
        ok: false,
        reason: `image slot "${k}" not in template ${templateId}`,
      };
    }
  }

  for (const k of textSlotKeys) {
    if (!(k in tpl.textSlots)) {
      return {
        ok: false,
        reason: `text slot "${k}" not in template ${templateId}`,
      };
    }
  }

  return { ok: true };
}
