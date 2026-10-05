import { expect, test, type Route } from '@playwright/test'

const COMPOSITE_PRODUCT_ID = '99999999-0000-4000-8000-000000000001'
const BASE_COMPONENT_ID = '99999999-0000-4000-8000-000000000002'
const ATTACHMENT_COMPONENT_ID = '99999999-0000-4000-8000-000000000003'

const mockProductDetail = {
  id: COMPOSITE_PRODUCT_ID,
  code: 'KMZ-1000',
  slug: 'kamaz-composite',
  title: 'Составное объявление КАМАЗ с надстройкой',
  detail_url: `/special-equipment/products/${COMPOSITE_PRODUCT_ID}/kamaz-composite`,
  condition: 'new',
  modification: {
    id: '99999999-0000-4000-8000-000000000012',
    name: 'Базовая модификация',
    model: {
      id: '99999999-0000-4000-8000-000000000011',
      name: '1000',
      mark: {
        id: '99999999-0000-4000-8000-000000000010',
        name: 'КАМАЗ',
      },
    },
  },
  trim: { id: '99999999-0000-4000-8000-000000000013', name: 'Комплектация Люкс' },
  manufacture_year: 2026,
  body_color: { id: '99999999-0000-4000-8000-000000000014', name: 'Белый' },
  interior_color: null,
  mileage_km: null,
  engine_hours: null,
  categories: [],
  terminal_category: null,
  price: '13000000',
  base_price: '13500000',
  special_price: null,
  price_on_request: false,
  price_from: null,
  currency_code: 'RUB',
  publication_status: 'published',
  sale_status: 'available',
  primary_image: null,
  images: [],
  description: 'Описание составной техники для E2E проверки отображения булевых характеристик.',
  capabilities: {
    can_favorite: true,
    can_add_to_cart: true,
    can_lease: true,
    can_buy: true,
    can_preorder: false,
  },
  available_count: 5,
  warehouse_stock: [
    {
      warehouse_id: '99999999-0000-4000-8000-000000000020',
      address: 'Центральный склад, Москва',
      brand: 'КАМАЗ',
      count: 5,
    },
  ],
  card_attributes: [
    {
      id: '99999999-0000-4000-8000-000000000031',
      code: 'abs',
      name: 'ABS',
      data_type: 'boolean',
      value: true,
      unit: null,
      group_id: null,
      group_name: '',
      option_id: null,
      option_label: null,
      display_value: 'true',
    },
    {
      id: '99999999-0000-4000-8000-000000000032',
      code: 'esp',
      name: 'ESP',
      data_type: 'boolean',
      value: false,
      unit: null,
      group_id: null,
      group_name: '',
      option_id: null,
      option_label: null,
      display_value: 'false',
    },
    {
      id: '99999999-0000-4000-8000-000000000033',
      code: 'capacity',
      name: 'Грузоподъёмность',
      data_type: 'number',
      value: '10',
      unit: 'т',
      group_id: null,
      group_name: '',
      option_id: null,
      option_label: null,
      display_value: '10',
    },
  ],
  kind: 'kit',
  superstructure: {
    name: 'Крановая установка',
    type_name: 'Кран',
    manufacturer: 'Palfinger',
  },
  attribute_groups: [
    {
      id: '99999999-0000-4000-8000-000000000041',
      name: 'Безопасность',
      section: 'chassis',
      attributes: [
        {
          id: '99999999-0000-4000-8000-000000000051',
          code: 'abs',
          name: 'ABS',
          data_type: 'boolean',
          unit: null,
          value: true,
          display_value: 'true',
          formatted_value: 'Да',
          option_id: null,
          option_label: null,
        },
        {
          id: '99999999-0000-4000-8000-000000000052',
          code: 'esp',
          name: 'ESP',
          data_type: 'boolean',
          unit: null,
          value: false,
          display_value: 'false',
          formatted_value: 'Нет',
          option_id: null,
          option_label: null,
        },
        {
          id: '99999999-0000-4000-8000-000000000053',
          code: 'capacity',
          name: 'Грузоподъёмность',
          data_type: 'number',
          unit: 'т',
          value: '10',
          display_value: '10',
          formatted_value: '10 т',
          option_id: null,
          option_label: null,
        },
      ],
    },
    {
      id: '99999999-0000-4000-8000-000000000042',
      name: 'Оборудование надстройки',
      section: 'superstructure',
      attributes: [
        {
          id: '99999999-0000-4000-8000-000000000054',
          code: 'stabilizers',
          name: 'Опоры',
          data_type: 'boolean',
          unit: null,
          value: true,
          display_value: 'true',
          formatted_value: 'Да',
          option_id: null,
          option_label: null,
        },
      ],
    },
  ],
  trim_attribute_groups: [
    {
      id: '99999999-0000-4000-8000-000000000061',
      name: 'Параметры безопасности комплектации',
      attributes: [
        {
          id: '99999999-0000-4000-8000-000000000071',
          code: 'trim_abs',
          name: 'ABS',
          data_type: 'boolean',
          unit: null,
          group_id: '99999999-0000-4000-8000-000000000061',
          group_name: 'Параметры безопасности комплектации',
          value: true,
          display_value: 'true',
          option_label: null,
          source_product: null,
        },
        {
          id: '99999999-0000-4000-8000-000000000072',
          code: 'trim_esp',
          name: 'ESP',
          data_type: 'boolean',
          unit: null,
          group_id: '99999999-0000-4000-8000-000000000061',
          group_name: 'Параметры безопасности комплектации',
          value: false,
          display_value: 'false',
          option_label: null,
          source_product: null,
        },
      ],
    },
  ],
}

test.describe('Special Equipment — Modification Boolean Yes/No Attributes (specs/task_2026-09-28_12-42-42_MSK.md)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/auth/**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user: null }),
      })
    })

    await page.route('**/api/v1/cart', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total_count: 0 }),
      })
    })

    await page.route('**/api/v1/special-equipment/cart-items', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    })

    await page.route(`**/api/v1/special-equipment/products/${COMPOSITE_PRODUCT_ID}**`, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockProductDetail),
      })
    })

    await page.route(`**/api/v1/special-equipment/products/${COMPOSITE_PRODUCT_ID}/components**`, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    })

    await page.route(`**/api/v1/special-equipment/products/${COMPOSITE_PRODUCT_ID}/compatible-attachments**`, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    })
  })

  test('displays explicit "Да" and "Нет" in modification specs for base and attachments', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.goto(`/special-equipment/products/${COMPOSITE_PRODUCT_ID}/kamaz-composite`, { waitUntil: 'domcontentloaded' })

    // 1. Проверка подблока шасси
    const baseBlock = page.locator('[data-testid="detail-chassis-section"]')
    await expect(baseBlock).toBeVisible()

    // Логическая характеристика со значением true -> значение «Да»
    const baseAbsRow = baseBlock.locator('dl div').filter({
      has: page.locator('dt', { hasText: 'ABS' }),
    })
    await expect(baseAbsRow).toBeVisible()
    await expect(baseAbsRow.locator('dd')).toHaveText('Да')

    // Логическая характеристика со значением false -> значение «Нет»
    const baseEspRow = baseBlock.locator('dl div').filter({
      has: page.locator('dt', { hasText: 'ESP' }),
    })
    await expect(baseEspRow).toBeVisible()
    await expect(baseEspRow.locator('dd')).toHaveText('Нет')

    // Небулевая характеристика -> форматированное значение без изменений
    const baseCapacityRow = baseBlock.locator('dl div').filter({
      has: page.locator('dt', { hasText: 'Грузоподъёмность' }),
    })
    await expect(baseCapacityRow).toBeVisible()
    await expect(baseCapacityRow.locator('dd')).toHaveText('10 т')

    // 2. Проверка подблока надстройки
    const attachmentBlock = page.locator('[data-testid="detail-superstructure-section"]')
    await expect(attachmentBlock).toBeVisible()

    // Логическая характеристика надстройки (true) -> значение «Да»
    const attachmentStabilizersRow = attachmentBlock.locator('dl div').filter({
      has: page.locator('dt', { hasText: 'Опоры' }),
    })
    await expect(attachmentStabilizersRow).toBeVisible()
    await expect(attachmentStabilizersRow.locator('dd')).toHaveText('Да')
  })

  test('preserves regression: "Параметры комплектации" and "Ключевые характеристики" do not show "Да" / "Нет"', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.goto(`/special-equipment/products/${COMPOSITE_PRODUCT_ID}/kamaz-composite`, { waitUntil: 'domcontentloaded' })

    // 1. Регрессия «Параметры комплектации»:
    // true -> название со скрытым «выбрано», без «Да» / «Нет»
    // false -> строка не выводится
    const trimSection = page.getByRole('region', { name: 'Параметры комплектации' })
    await expect(trimSection).toBeVisible()

    const trimAbsRow = trimSection.locator('dl div').filter({
      has: page.locator('dt', { hasText: 'ABS' }),
    })
    await expect(trimAbsRow).toBeVisible()
    await expect(trimAbsRow).not.toContainText('Да')
    await expect(trimAbsRow).not.toContainText('Нет')
    await expect(trimAbsRow.locator('dd')).toHaveText('выбрано')

    // ESP со значением false не выводится в комплектации
    await expect(trimSection.getByText('ESP', { exact: true })).not.toBeVisible()
    await expect(trimSection.locator('dl div').filter({
      has: page.locator('dt', { hasText: 'ESP' }),
    })).toHaveCount(0)

    // 2. Регрессия «Ключевые характеристики»:
    // true -> только название со скрытым «выбрано», без «Да»
    // false -> строка не выводится
    const cardAttributesSection = page.locator('section[aria-labelledby="card-attributes-title"]')
    await expect(cardAttributesSection).toBeVisible()

    const cardAbsRow = cardAttributesSection.locator('dl div').filter({
      has: page.locator('dt', { hasText: 'ABS' }),
    })
    await expect(cardAbsRow).toBeVisible()
    await expect(cardAbsRow).not.toContainText('Да')
    await expect(cardAbsRow).not.toContainText('Нет')
    await expect(cardAbsRow.locator('dd')).toHaveText('выбрано')

    // ESP со значением false не выводится в ключевых характеристиках
    await expect(cardAttributesSection.getByText('ESP', { exact: true })).not.toBeVisible()
    await expect(cardAttributesSection.locator('dl div').filter({
      has: page.locator('dt', { hasText: 'ESP' }),
    })).toHaveCount(0)
  })
})
