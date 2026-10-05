import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  formatEntityCount,
  getEntityAccusative,
  getEntityLabel,
  pluralizeRussian,
} from '../../../features/specialEquipment/management/correction/pluralization'
import type {
  CascadeBlockers,
  CascadePreviewResource,
  CascadeDeleteResult,
} from '../../../features/specialEquipment/management/correction/types'

describe('catalog cascade delete frontend unit tests', () => {
  describe('pluralization helpers', () => {
    it('pluralizes Russian numerals correctly', () => {
      assert.equal(pluralizeRussian(1, 'марка', 'марки', 'марок'), 'марка')
      assert.equal(pluralizeRussian(2, 'марка', 'марки', 'марок'), 'марки')
      assert.equal(pluralizeRussian(3, 'марка', 'марки', 'марок'), 'марки')
      assert.equal(pluralizeRussian(4, 'марка', 'марки', 'марок'), 'марки')
      assert.equal(pluralizeRussian(5, 'марка', 'марки', 'марок'), 'марок')
      assert.equal(pluralizeRussian(11, 'марка', 'марки', 'марок'), 'марок')
      assert.equal(pluralizeRussian(14, 'марка', 'марки', 'марок'), 'марок')
      assert.equal(pluralizeRussian(21, 'марка', 'марки', 'марок'), 'марка')
      assert.equal(pluralizeRussian(22, 'марка', 'марки', 'марок'), 'марки')
      assert.equal(pluralizeRussian(25, 'марка', 'марки', 'марок'), 'марок')
    })

    it('formats counts for all catalog entity types', () => {
      // marks
      assert.equal(formatEntityCount('marks', 1), '1 марка')
      assert.equal(formatEntityCount('marks', 3), '3 марки')
      assert.equal(formatEntityCount('marks', 5), '5 марок')
      assert.equal(formatEntityCount('mark', 10), '10 марок')

      // models
      assert.equal(formatEntityCount('models', 1), '1 модель')
      assert.equal(formatEntityCount('models', 2), '2 модели')
      assert.equal(formatEntityCount('models', 6), '6 моделей')

      // modifications
      assert.equal(formatEntityCount('modifications', 1), '1 модификация')
      assert.equal(formatEntityCount('modifications', 4), '4 модификации')
      assert.equal(formatEntityCount('modifications', 10), '10 модификаций')

      // trims
      assert.equal(formatEntityCount('trims', 1), '1 комплектация')
      assert.equal(formatEntityCount('trims', 2), '2 комплектации')
      assert.equal(formatEntityCount('trims', 5), '5 комплектаций')

      // categories
      assert.equal(formatEntityCount('categories', 1), '1 категория')
      assert.equal(formatEntityCount('categories', 2), '2 категории')
      assert.equal(formatEntityCount('categories', 7), '7 категорий')

      // attribute groups
      assert.equal(formatEntityCount('attribute_groups', 1), '1 группа характеристик')
      assert.equal(formatEntityCount('attribute_groups', 3), '3 группы характеристик')
      assert.equal(formatEntityCount('attribute_groups', 5), '5 групп характеристик')
      assert.equal(formatEntityCount('attribute-groups', 1), '1 группа характеристик')

      // attributes
      assert.equal(formatEntityCount('attributes', 1), '1 характеристика')
      assert.equal(formatEntityCount('attributes', 2), '2 характеристики')
      assert.equal(formatEntityCount('attributes', 5), '5 характеристик')

      // options
      assert.equal(formatEntityCount('options', 1), '1 вариант характеристики')
      assert.equal(formatEntityCount('options', 2), '2 варианта характеристики')
      assert.equal(formatEntityCount('options', 5), '5 вариантов характеристик')

      // colors
      assert.equal(formatEntityCount('colors', 1), '1 цвет')
      assert.equal(formatEntityCount('colors', 3), '3 цвета')
      assert.equal(formatEntityCount('colors', 5), '5 цветов')

      // products
      assert.equal(formatEntityCount('products', 1), '1 объявление')
      assert.equal(formatEntityCount('products', 4), '4 объявления')
      assert.equal(formatEntityCount('products', 12), '12 объявлений')
    })

    it('returns correct accusative case for modal titles', () => {
      assert.equal(getEntityAccusative('category'), 'категорию')
      assert.equal(getEntityAccusative('categories'), 'категорию')
      assert.equal(getEntityAccusative('mark'), 'марку')
      assert.equal(getEntityAccusative('marks'), 'марку')
      assert.equal(getEntityAccusative('model'), 'модель')
      assert.equal(getEntityAccusative('models'), 'модель')
      assert.equal(getEntityAccusative('modification'), 'модификацию')
      assert.equal(getEntityAccusative('modifications'), 'модификацию')
      assert.equal(getEntityAccusative('trim'), 'комплектацию')
      assert.equal(getEntityAccusative('trims'), 'комплектацию')
      assert.equal(getEntityAccusative('attribute'), 'характеристику')
      assert.equal(getEntityAccusative('attributes'), 'характеристику')
      assert.equal(getEntityAccusative('attribute_group'), 'группу характеристик')
      assert.equal(getEntityAccusative('attribute-groups'), 'группу характеристик')
      assert.equal(getEntityAccusative('option'), 'вариант характеристики')
      assert.equal(getEntityAccusative('options'), 'вариант характеристики')
      assert.equal(getEntityAccusative('color'), 'цвет')
      assert.equal(getEntityAccusative('colors'), 'цвет')
      assert.equal(getEntityAccusative('product'), 'объявление')
      assert.equal(getEntityAccusative('products'), 'объявление')
    })
  })

  describe('confirmation word validation', () => {
    const isConfirmationValid = (val: string) => val.trim() === 'УДАЛИТЬ'

    it('accepts exact uppercase Cyrillic УДАЛИТЬ', () => {
      assert.equal(isConfirmationValid('УДАЛИТЬ'), true)
    })

    it('accepts trimmed uppercase Cyrillic УДАЛИТЬ with leading/trailing spaces', () => {
      assert.equal(isConfirmationValid('  УДАЛИТЬ  '), true)
      assert.equal(isConfirmationValid('\tУДАЛИТЬ\n'), true)
    })

    it('rejects lowercase and mixed case', () => {
      assert.equal(isConfirmationValid('удалить'), false)
      assert.equal(isConfirmationValid('Удалить'), false)
      assert.equal(isConfirmationValid('УдалИТЬ'), false)
    })

    it('rejects latin letters or English words', () => {
      assert.equal(isConfirmationValid('DELETE'), false)
      assert.equal(isConfirmationValid('delete'), false)
      // Latin lookalike letters: Y (U+0059), A (U+0041), T (U+0054)
      assert.equal(isConfirmationValid('YДАЛИТЬ'), false) // Latin Y
      assert.equal(isConfirmationValid('УДALИТЬ'), false) // Latin AL
    })

    it('rejects partial or extra text', () => {
      assert.equal(isConfirmationValid('УДАЛ'), false)
      assert.equal(isConfirmationValid('УДАЛИТЬ ВСЕ'), false)
      assert.equal(isConfirmationValid(''), false)
    })
  })

  describe('blockers detection logic', () => {
    const hasBlockers = (preview: CascadePreviewResource | null) => {
      if (!preview) return false
      const b = preview.blockers
      return (
        (b?.products?.length ?? 0) > 0 ||
        (b?.distributors?.length ?? 0) > 0 ||
        (b?.support_programs?.length ?? 0) > 0
      )
    }

    it('detects no blockers when all blocker lists are empty', () => {
      const preview: CascadePreviewResource = {
        root: { type: 'categories', id: 'c1', name: 'Бульдозеры' },
        delete: [{ type: 'categories', count: 1, items: [{ type: 'categories', id: 'c1' }], truncated: false }],
        unlink: [],
        clear: [],
        user_impact: { cart_items: 0, favorites: 0 },
        blockers: { products: [], distributors: [], support_programs: [] },
        total: 1,
        preview_token: 'token123',
        catalog_revision: 5,
      }
      assert.equal(hasBlockers(preview), false)
    })

    it('detects product blockers', () => {
      const preview: CascadePreviewResource = {
        root: { type: 'modifications', id: 'm1', name: 'Модификация 1' },
        delete: [],
        unlink: [],
        clear: [],
        user_impact: { cart_items: 0, favorites: 0 },
        blockers: {
          products: [
            {
              product: { type: 'products', id: 'p1', code: 'P01', name: 'Машина 1' },
              vin: 'X123456789',
              documents: [{ type: 'application_item', id: 'doc1', number: 'APP-100', status: 'active' }],
            },
          ],
          distributors: [],
          support_programs: [],
        },
        total: 1,
        preview_token: 'token123',
        catalog_revision: 5,
      }
      assert.equal(hasBlockers(preview), true)
    })

    it('detects distributor blockers', () => {
      const preview: CascadePreviewResource = {
        root: { type: 'marks', id: 'mark1', name: 'КАМАЗ' },
        delete: [],
        unlink: [],
        clear: [],
        user_impact: { cart_items: 0, favorites: 0 },
        blockers: {
          products: [],
          distributors: [{ company: { id: 'comp1', name: 'ООО Дистрибьютор', inn: '7700000000' } }],
          support_programs: [],
        },
        total: 1,
        preview_token: 'token123',
        catalog_revision: 5,
      }
      assert.equal(hasBlockers(preview), true)
    })

    it('detects support program blockers', () => {
      const preview: CascadePreviewResource = {
        root: { type: 'models', id: 'model1', name: 'Модель А' },
        delete: [],
        unlink: [],
        clear: [],
        user_impact: { cart_items: 0, favorites: 0 },
        blockers: {
          products: [],
          distributors: [],
          support_programs: [
            {
              program: { id: 'prog1', name: 'Субсидия 2026', is_active: true },
              references: [{ type: 'models', id: 'model1', name: 'Модель А' }],
            },
          ],
        },
        total: 1,
        preview_token: 'token123',
        catalog_revision: 5,
      }
      assert.equal(hasBlockers(preview), true)
    })
  })
})
