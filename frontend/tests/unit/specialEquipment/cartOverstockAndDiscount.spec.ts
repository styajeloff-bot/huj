import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  commerceCartBillableQuantity,
  commerceCartLineTotal,
  commerceCartSelectedCount,
  commerceCheckoutLines,
  type CommerceCartLine,
} from '../../../features/commerce/cartProjection'
import { getCommerceLineDiscountSummary } from '../../../utils/vehicleDiscount'
import { specialEquipmentCommerceCartLine } from '../../../features/specialEquipment/adapters/specialEquipmentCommerceCartLine'
import {
  SPECIAL_EQUIPMENT_MAX_CART_QUANTITY,
  parseStoredLine,
  specialEquipmentGuestTransferBody,
  reconcileSpecialEquipmentGuestCartGroup,
  type SpecialEquipmentGuestCartSnapshot,
} from '../../../features/specialEquipment/composables/commerceStorage'
import { buildEmailData, buildText, buildHtml } from '../../../features/cart/composables/useCartEmail'
import type { SpecialEquipmentCartItem, SpecialEquipmentCommerceProduct } from '../../../features/specialEquipment/types'

const dummyPublicRoute = (path: string) => path

const createLineMock = (overrides: Partial<CommerceCartLine> = {}): CommerceCartLine => ({
  cart_id: crypto.randomUUID(),
  ref: { type: 'special_equipment', id: crypto.randomUUID() },
  mark_name: 'Zoomlion',
  model_name: 'RS1304',
  base_price: 2_700_000,
  list_price: 3_000_000,
  quantity: 1,
  allow_overstock: false,
  available_count: 5,
  is_selected: true,
  equipments: [],
  services: [],
  comment: '',
  image_url: null,
  detail_url: null,
  quantity_editable: true,
  price_editable: false,
  unavailable_status: '',
  added_at: '2026-09-24T12:00:00Z',
  capabilities: { can_lease: true, can_buy: true, can_preorder: false },
  ...overrides,
})

const createProductMock = (overrides: Partial<SpecialEquipmentCommerceProduct> = {}): SpecialEquipmentCommerceProduct => ({
  id: crypto.randomUUID(),
  slug: 'zoomlion-rs1304',
  detail_url: '/special-equipment/rs1304',
  mark: { id: crypto.randomUUID(), name: 'Zoomlion' },
  model: { id: crypto.randomUUID(), name: 'RS1304' },
  modification: { id: crypto.randomUUID(), name: 'Standard' },
  trim: null,
  body_color: { id: crypto.randomUUID(), name: 'Зеленый' },
  manufacture_year: 2024,
  price: 2_700_000,
  base_price: 3_000_000,
  special_price: 2_700_000,
  price_from: null,
  price_on_request: false,
  currency_code: 'RUB',
  sale_status: 'available',
  available_count: 3,
  primary_image: null,
  capabilities: { can_favorite: true, can_add_to_cart: true, can_lease: true, can_buy: true, can_preorder: false },
  ...overrides,
})

const createCartItemMock = (
  product: SpecialEquipmentCommerceProduct,
  overrides: Partial<SpecialEquipmentCartItem> = {},
): SpecialEquipmentCartItem => ({
  id: crypto.randomUUID(),
  product_id: product.id,
  parent_item_id: null,
  transfer_id: null,
  quantity: 1,
  allow_overstock: false,
  is_selected: true,
  custom_price: null,
  comment: '',
  equipments: [],
  services: [],
  added_at: '2026-09-24T12:00:00Z',
  updated_at: '2026-09-24T12:00:00Z',
  product,
  ...overrides,
})

describe('special equipment cart discount and overstock unit tests', () => {
  describe('getCommerceLineDiscountSummary', () => {
    it('calculates discount amount and percent for special equipment with list_price and base_price', () => {
      const line = createLineMock({
        list_price: 3_000_000,
        base_price: 2_700_000,
        quantity: 2,
      })

      const summary = getCommerceLineDiscountSummary(line)
      assert.ok(summary)
      assert.equal(summary.amount, 300_000)
      assert.equal(summary.percent, 10)
      assert.equal(summary.basePrice, 3_000_000)
      assert.equal(summary.discountedPrice, 2_700_000)
    })

    it('custom_price takes precedence over base_price as effective price', () => {
      const line = createLineMock({
        list_price: 3_000_000,
        base_price: 2_700_000,
        custom_price: 2_500_000,
      })

      const summary = getCommerceLineDiscountSummary(line)
      assert.ok(summary)
      assert.equal(summary.amount, 500_000)
      assert.equal(summary.percent, 17) // 500k / 3000k = 16.66% -> 17%
      assert.equal(summary.discountedPrice, 2_500_000)
    })

    it('returns null if price_on_request is true', () => {
      const line = createLineMock({
        list_price: 3_000_000,
        base_price: 2_700_000,
        price_on_request: true,
      })

      assert.equal(getCommerceLineDiscountSummary(line), null)
    })

    it('returns null if discounted price is greater than or equal to list_price', () => {
      const lineEqual = createLineMock({
        list_price: 3_000_000,
        base_price: 3_000_000,
      })

      assert.equal(getCommerceLineDiscountSummary(lineEqual), null)

      const lineExpensive = createLineMock({
        list_price: 3_000_000,
        base_price: 3_500_000,
      })

      assert.equal(getCommerceLineDiscountSummary(lineExpensive), null)
    })

    it('returns null if list_price is missing, zero, or negative', () => {
      const lineNull = createLineMock({
        list_price: null,
        base_price: 2_700_000,
      })

      assert.equal(getCommerceLineDiscountSummary(lineNull), null)

      const lineZero = createLineMock({
        list_price: 0,
        base_price: 2_700_000,
      })

      assert.equal(getCommerceLineDiscountSummary(lineZero), null)
    })
  })

  describe('commerceCartBillableQuantity and projections', () => {
    it('clamps billable quantity to available_count when allow_overstock is true for special equipment', () => {
      const overstockLine = createLineMock({
        base_price: 1_000_000,
        quantity: 15,
        available_count: 5,
        allow_overstock: true,
      })

      assert.equal(commerceCartBillableQuantity(overstockLine), 5)
      assert.equal(commerceCartLineTotal(overstockLine), 5_000_000)
    })

    it('does not clamp billable quantity when allow_overstock is false', () => {
      const regularLine = createLineMock({
        base_price: 1_000_000,
        quantity: 15,
        available_count: 5,
        allow_overstock: false,
      })

      assert.equal(commerceCartBillableQuantity(regularLine), 15)
      assert.equal(commerceCartLineTotal(regularLine), 15_000_000)
    })

    it('does not clamp billable quantity for vehicles even if allow_overstock is set', () => {
      const vehicleLine = createLineMock({
        ref: { type: 'vehicle', id: crypto.randomUUID() },
        base_price: 2_000_000,
        quantity: 3,
        available_count: 1,
        allow_overstock: true,
      })

      assert.equal(commerceCartBillableQuantity(vehicleLine), 3)
      assert.equal(commerceCartLineTotal(vehicleLine), 6_000_000)
    })

    it('calculates selected count and checkout lines using billable quantity', () => {
      const lines: CommerceCartLine[] = [
        createLineMock({
          base_price: 1_000_000,
          quantity: 20,
          available_count: 5,
          allow_overstock: true,
          is_selected: true,
        }),
        createLineMock({
          base_price: 500_000,
          quantity: 2,
          available_count: 10,
          allow_overstock: false,
          is_selected: true,
        }),
      ]

      assert.equal(commerceCartSelectedCount(lines), 7) // 5 + 2

      const checkout = commerceCheckoutLines(lines)
      assert.equal(checkout.length, 2)
      assert.equal(checkout[0].quantity, 20)
      assert.equal(checkout[0].allow_overstock, true)
      assert.equal(checkout[1].quantity, 2)
      assert.equal(checkout[1].allow_overstock, undefined)
    })
  })

  describe('specialEquipmentCommerceCartLine adapter', () => {
    it('maps body_color to color and base_price to list_price', () => {
      const product = createProductMock()
      const item = createCartItemMock(product, {
        quantity: 2,
        allow_overstock: false,
      })

      const line = specialEquipmentCommerceCartLine(item, dummyPublicRoute)
      assert.equal(line.color, 'Зеленый')
      assert.equal(line.list_price, 3_000_000)
      assert.equal(line.base_price, 2_700_000)
      assert.equal(line.year, 2024)
      assert.equal(line.allow_overstock, false)
      assert.equal(line.unavailable_status, '')
    })

    it('suppresses out_of_stock when allow_overstock is true and available_count >= 1 even if quantity exceeds stock', () => {
      const product = createProductMock({ available_count: 3 })
      const item = createCartItemMock(product, {
        quantity: 10,
        allow_overstock: true,
      })

      const line = specialEquipmentCommerceCartLine(item, dummyPublicRoute)
      assert.equal(line.allow_overstock, true)
      assert.equal(line.unavailable_status, '')
    })

    it('keeps out_of_stock when allow_overstock is false and quantity exceeds stock', () => {
      const product = createProductMock({ available_count: 3 })
      const item = createCartItemMock(product, {
        quantity: 10,
        allow_overstock: false,
      })

      const line = specialEquipmentCommerceCartLine(item, dummyPublicRoute)
      assert.equal(line.unavailable_status, 'out_of_stock')
    })

    it('keeps out_of_stock when available_count is 0 even if allow_overstock is true', () => {
      const product = createProductMock({ available_count: 0, sale_status: 'unavailable' })
      const item = createCartItemMock(product, {
        quantity: 5,
        allow_overstock: true,
      })

      const line = specialEquipmentCommerceCartLine(item, dummyPublicRoute)
      assert.equal(line.unavailable_status, 'unavailable')
    })
  })

  describe('commerceStorage guest cart persistence and reconciliation', () => {
    it('clamps quantity to SPECIAL_EQUIPMENT_MAX_CART_QUANTITY = 1000', () => {
      assert.equal(SPECIAL_EQUIPMENT_MAX_CART_QUANTITY, 1000)

      const line = parseStoredLine({
        local_id: crypto.randomUUID(),
        parent_local_id: null,
        product_id: crypto.randomUUID(),
        quantity: 5000,
        allow_overstock: true,
      })

      assert.ok(line)
      assert.equal(line.quantity, 1000)
      assert.equal(line.allow_overstock, true)
    })

    it('rejects allow_overstock for attachment lines with non-null parent_local_id', () => {
      const parentId = crypto.randomUUID()
      const rootLine = parseStoredLine({
        local_id: parentId,
        parent_local_id: null,
        product_id: crypto.randomUUID(),
        quantity: 2,
        allow_overstock: true,
      })

      const attLine = parseStoredLine({
        local_id: crypto.randomUUID(),
        parent_local_id: parentId,
        product_id: crypto.randomUUID(),
        quantity: 2,
        allow_overstock: true,
      })

      assert.ok(rootLine)
      assert.ok(attLine)
      assert.equal(rootLine.allow_overstock, true)
      assert.equal(attLine.allow_overstock, false)
    })

    it('generates guest transfer body with allow_overstock preserved', () => {
      const parentId = crypto.randomUUID()
      const snapshot: SpecialEquipmentGuestCartSnapshot = {
        version: 2,
        transfer_id: crypto.randomUUID(),
        items: [
          {
            local_id: parentId,
            parent_local_id: null,
            product_id: crypto.randomUUID(),
            quantity: 10,
            allow_overstock: true,
            is_selected: true,
            comment: null,
            equipments: [],
            services: [],
          },
          {
            local_id: crypto.randomUUID(),
            parent_local_id: parentId,
            product_id: crypto.randomUUID(),
            quantity: 1,
            allow_overstock: false,
            is_selected: true,
            comment: null,
            equipments: [],
            services: [],
          },
        ],
      }

      const body = specialEquipmentGuestTransferBody(snapshot)
      assert.equal(body.items.length, 2)
      assert.equal(body.items[0].allow_overstock, true)
      assert.equal(body.items[1].allow_overstock, false)
    })

    it('reconciles guest cart group and preserves allow_overstock flag', () => {
      const parentProductId = crypto.randomUUID()
      const childProductId = crypto.randomUUID()
      const existingParentId = crypto.randomUUID()

      const snapshot: SpecialEquipmentGuestCartSnapshot = {
        version: 2,
        transfer_id: crypto.randomUUID(),
        items: [
          {
            local_id: existingParentId,
            parent_local_id: null,
            product_id: parentProductId,
            quantity: 5,
            allow_overstock: true,
            is_selected: true,
            comment: null,
            equipments: [],
            services: [],
          },
        ],
      }

      const result = reconcileSpecialEquipmentGuestCartGroup(
        snapshot,
        parentProductId,
        20,
        [{ product_id: childProductId, quantity: 2 }],
        () => crypto.randomUUID(),
      )

      assert.equal(result.parent.quantity, 20)
      assert.equal(result.parent.allow_overstock, true)
      assert.equal(result.children.length, 1)
      assert.equal(result.children[0].allow_overstock, false)
    })
  })

  describe('useCartEmail formatting and discounts', () => {
    it('formats year before color and adds overstock details', () => {
      const line = createLineMock({
        mark_name: 'Zoomlion',
        model_name: 'RS1304',
        list_price: 3_000_000,
        base_price: 2_700_000,
        quantity: 10,
        available_count: 4,
        allow_overstock: true,
        year: 2024,
        color: 'Красный',
      })

      const emailData = buildEmailData([line], null, {}, 27_000_000)

      assert.equal(emailData.items.length, 1)
      const it = emailData.items[0]

      // Check quantity line has overstock annotation
      assert.ok(it.quantityLine.includes('сверх наличия 6'))
      assert.ok(it.quantityLine.includes('не входят в расчёт'))

      // Check discount lines
      assert.equal(it.discountLines.length, 2)
      assert.ok(it.discountLines[0].includes('Скидка: −300'))
      assert.ok(it.discountLines[1].includes('Цена со скидкой: 2'))

      // Check details order: Year before Color
      const yearIdx = it.details.findIndex((d) => d.label === 'Год')
      const colorIdx = it.details.findIndex((d) => d.label === 'Цвет')
      assert.ok(yearIdx !== -1)
      assert.ok(colorIdx !== -1)
      assert.ok(yearIdx < colorIdx, 'Год should precede Цвет')

      // Check applied discounts total = 300,000 * 4 billable = 1,200,000
      assert.equal(emailData.appliedDiscountsTotal, 1_200_000)

      // Test buildText
      const text = buildText(emailData).replace(/\s+/g, ' ')
      assert.ok(text.includes('Применённые скидки: −1 200 000'))
      assert.ok(text.includes('сверх наличия 6'))

      // Test buildHtml
      const html = buildHtml(emailData).replace(/\s+/g, ' ')
      assert.ok(html.includes('Применённые скидки: −1 200 000') || html.includes('Применённые скидки: −1&nbsp;200&nbsp;000'))
      assert.ok(html.includes('сверх наличия 6'))
    })
  })
})
