import assert from 'node:assert/strict';
import test from 'node:test';

import {
  TEMPLATE_IDS,
  TEMPLATES,
  TemplateDef,
  getTemplate,
  validateSlotsForTemplate,
} from './templates';
import { TEMPLATES as INDEX_TEMPLATES } from './index';

const EXPECTED_TEMPLATE_IDS = [
  'mag-01',
  'mag-02',
  'mag-03',
  'mag-04',
  'mag-05',
  'mag-06',
  'mag-07',
  'mag-08',
  'mag-09',
  'mag-10',
  'mag-11',
  'mag-12',
  'mag-13',
  'mag-14',
  'mag-15',
  'mag-16',
  'mag-17',
  'mag-18',
  'mag-19',
  'mag-20',
  'p01',
];

test('registry contains the 21 templates imported from memoir', () => {
  assert.deepEqual(TEMPLATE_IDS, EXPECTED_TEMPLATE_IDS);
  assert.equal(INDEX_TEMPLATES, TEMPLATES);
});

test('every template parses, mirrors its id, and exposes concrete slot constraints', () => {
  for (const id of EXPECTED_TEMPLATE_IDS) {
    const template = TEMPLATES[id];

    assert.ok(template, `${id} should be registered`);
    assert.deepEqual(TemplateDef.parse(template), template);
    assert.equal(template.id, id);

    for (const [slotName, constraint] of Object.entries(template.imageSlots)) {
      assert.ok(
        constraint.orientation && constraint.orientation.length > 0,
        `${id}.${slotName} should constrain photo orientation`,
      );
      assert.ok(
        constraint.quality && constraint.quality.length > 0,
        `${id}.${slotName} should constrain photo quality`,
      );
    }

    for (const [slotName, constraint] of Object.entries(template.textSlots)) {
      assert.equal(
        typeof constraint.maxChars,
        'number',
        `${id}.${slotName} should expose maxChars`,
      );
      assert.ok(constraint.maxChars > 0, `${id}.${slotName} maxChars should be positive`);
    }
  }
});

test('selected template metadata matches the source schema semantics', () => {
  assert.deepEqual(getTemplate('mag-04')?.imageSlots, {
    image1: { orientation: ['landscape'], quality: ['hero', 'detail'] },
    image2: { orientation: ['portrait'], quality: ['detail', 'fill'] },
    image3: { orientation: ['square'], quality: ['detail', 'fill'] },
  });
  assert.deepEqual(getTemplate('mag-05')?.textSlots.caption, {
    type: 'paragraph',
    minChars: 60,
    maxChars: 120,
  });
  assert.deepEqual(getTemplate('mag-03')?.textSlots.caption, {
    type: 'caption',
    minChars: 0,
    maxChars: 60,
  });
  assert.deepEqual(getTemplate('p01')?.textSlots.vol, {
    type: 'meta',
    minChars: 2,
    maxChars: 4,
  });
});

test('slot validation accepts known memoir slots and rejects unknown slots', () => {
  assert.deepEqual(
    validateSlotsForTemplate(
      'mag-10',
      ['cells[0].image', 'cells[1].image', 'cells[2].image', 'cells[3].image'],
      ['cells', 'folio'],
    ),
    { ok: true },
  );
  assert.deepEqual(validateSlotsForTemplate('mag-02', [], ['items', 'folio']), { ok: true });

  assert.deepEqual(validateSlotsForTemplate('mag-02', ['image'], ['items']), {
    ok: false,
    reason: 'image slot "image" not in template mag-02',
  });
  assert.deepEqual(validateSlotsForTemplate('mag-01', ['image'], ['headline']), {
    ok: false,
    reason: 'text slot "headline" not in template mag-01',
  });
});
