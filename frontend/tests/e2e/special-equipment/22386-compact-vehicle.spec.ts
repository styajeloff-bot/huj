import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test'
import { getE2EFixtureManifest, type E2EProductKey, type JsonRecord } from './support/fixtures'
import { appUrl } from './support/runtime'
import type { SpecialEquipmentProductDetail } from '../../../features/specialEquipment/types'

interface ProductRef {
  id: string
  slug: string
  code: string
}

const fixtureProduct = (key: E2EProductKey): ProductRef => {
  const product = getE2EFixtureManifest().products[key]
  if (typeof product.slug !== 'string' || typeof product.code !== 'string') {
    throw new Error('E2E product must have a slug and code')
  }
  return { id: product.id, slug: product.slug, code: product.code }
}

interface CompactFixture {
  product: ProductRef
  warehouses: Array<{ warehouse_id: string; owner_company_name: string; address: string; count: number }>
  composite_product: { id: string; slug: string }
  price_on_request_product: ProductRef
}

const compactFixture = (): CompactFixture => {
  const fixture = getE2EFixtureManifest().compact_card as CompactFixture | undefined
  if (!fixture) throw new Error('Run scripts/e2e/22386/prepare.py after the shared E2E fixture')
  return fixture
}

const productDetail = async (request: APIRequestContext, id: string): Promise<SpecialEquipmentProductDetail> => {
  const response = await request.get(`/api/v1/special-equipment/products/${id}`)
  expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
  return response.json() as Promise<SpecialEquipmentProductDetail>
}

const hydrated = async (page: Page): Promise<void> => {
  await page.waitForFunction(() => Boolean(
    (document.querySelector('#__nuxt') as HTMLElement & { __vue_app__?: unknown } | null)?.__vue_app__,
  ))
}

const bounds = async (locator: Locator) => {
  const box = await locator.boundingBox()
  expect(box).not.toBeNull()
  return box!
}

const openCatalogCard = async (page: Page): Promise<Locator> => {
  const fixture = getE2EFixtureManifest()
  const product = compactFixture().product
  await page.goto(appUrl(`/special-equipment/categories/${fixture.categories.root.path.join('/')}`))
  await hydrated(page)
  const search = page.getByPlaceholder('Название, марка, модель или код')
  await search.fill(fixture.prefix)
  await search.press('Enter')
  const card = page.locator('[data-storefront-block="equipment.card"]').filter({
    has: page.locator(`a[href*="/products/${product.id}/"]`),
  })
  await expect(card).toHaveCount(1)
  await expect(card.getByTestId('equipment-card-attributes').locator(':scope > div')).toHaveCount(6)
  return card
}

const openDetail = async (page: Page): Promise<void> => {
  const product = compactFixture().product
  await page.goto(appUrl(`/special-equipment/products/${product.id}/${product.slug}`))
  await hydrated(page)
  await expect(page.getByTestId('detail-actions')).toBeVisible()
}

const expectNoHorizontalOverflow = async (page: Page): Promise<void> => {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    await page.evaluate(() => window.innerWidth),
  )
}

const expectCompactWarehouseStock = async (
  page: Page,
  warehouses: SpecialEquipmentProductDetail['warehouse_stock'],
): Promise<void> => {
  const quantitySection = page.getByTestId('detail-quantity')
  await expect(quantitySection.getByText('Количество техники', { exact: true })).toHaveCount(0)
  await expect(quantitySection.getByLabel('Количество', { exact: true })).toHaveCount(1)
  const rows = quantitySection.getByTestId('detail-warehouse-row')
  await expect(rows).toHaveCount(warehouses.length)
  await expect(quantitySection.getByText(/^\s*В наличии: [\d\s]+ шт\.\s*$/)).toHaveCount(warehouses.length)
  for (const warehouse of warehouses) {
    const row = rows.filter({ hasText: warehouse.address })
    await expect(row.getByText(`Дилер: ${warehouse.owner_company_name}`, { exact: true })).toHaveCount(1)
    await expect(row.getByText(`Склад: ${warehouse.address}`, { exact: true })).toHaveCount(1)
    await expect(row.getByTestId('detail-stock-count')).toHaveCount(1)
    await expect(row.getByTestId('detail-stock-count')).toHaveText(`В наличии: ${warehouse.count} шт.`)
  }
}

test.describe('Bitrix 22386 — компактная карточка и страница ТС', () => {
  test.beforeEach(async ({}, testInfo) => {
    testInfo.annotations.push({ type: 'task', description: '22386' })
  })

  test('API возвращает владельца и количество каждого склада, включая склад базового компонента', async ({ request }) => {
    const fixture = compactFixture()
    const detail = await productDetail(request, fixture.product.id)
    expect(detail.warehouse_stock).toHaveLength(2)
    expect(detail.available_count).toBe(2)
    expect(detail.warehouse_stock.map(stock => ({
      warehouse_id: stock.warehouse_id,
      owner_company_name: stock.owner_company_name,
      address: stock.address,
      count: stock.count,
    })).sort((left, right) => left.warehouse_id.localeCompare(right.warehouse_id))).toEqual(
      [...fixture.warehouses].sort((left, right) => left.warehouse_id.localeCompare(right.warehouse_id)),
    )
    const listResponse = await request.get('/api/v1/special-equipment/products', {
      params: { search: getE2EFixtureManifest().prefix, page_size: 100 },
    })
    expect(listResponse.ok()).toBeTruthy()
    const list = await listResponse.json() as { items: SpecialEquipmentProductDetail[] }
    const card = list.items.find(item => item.id === fixture.product.id)
    expect(card?.warehouse_stock).toEqual(detail.warehouse_stock)
    expect(card?.card_attributes).toHaveLength(6)
    expect(card?.card_attributes.some(attribute => attribute.value === '0')).toBe(true)
    expect(card?.card_attributes.some(attribute => attribute.value === false)).toBe(true)
    const composite = await productDetail(request, fixture.composite_product.id)
    expect(composite.warehouse_stock).toHaveLength(1)
    expect(fixture.warehouses.some(stock => (
      stock.warehouse_id === composite.warehouse_stock[0]?.warehouse_id
      && stock.owner_company_name === composite.warehouse_stock[0]?.owner_company_name
    ))).toBe(true)
    expect((await request.get('/api/v1/admin/warehouses')).status()).toBe(401)
    const hidden = getE2EFixtureManifest().products.unpublishedAvailable
    expect((await request.get(`/api/v1/special-equipment/products/${hidden.id}`)).status()).toBe(404)
  })

  for (const width of [768, 1024, 1440]) {
    test(`Компоновка карточки и страницы при ${width}px`, async ({ page, request }, testInfo) => {
      await page.setViewportSize({ width, height: 1000 })
      const product = await productDetail(request, compactFixture().product.id)
      const card = await openCatalogCard(page)
      await expect(card.getByTestId('equipment-card-title')).toHaveText(
        `${product.modification?.model.mark.name} ${product.modification?.model.name}`,
      )
      await expect(card.getByTestId('equipment-card-status')).toHaveText('В наличии')
      await expect(card.getByText('Цвет салона', { exact: true })).toHaveCount(0)
      await expect(card.getByText('Доступное количество', { exact: true })).toHaveCount(0)
      const cardBox = await bounds(card)
      const status = await bounds(card.getByTestId('equipment-card-status'))
      const favorite = await bounds(card.getByRole('button', { name: 'Добавить в избранное' }))
      expect(status.y - cardBox.y).toBeLessThan(20)
      expect(favorite.y - cardBox.y).toBeLessThan(20)
      expect(cardBox.x + cardBox.width - favorite.x - favorite.width).toBeLessThan(20)
      const positions = await card.getByTestId('equipment-card-attributes').locator(':scope > div').evaluateAll(
        elements => elements.map(element => {
          const rect = element.getBoundingClientRect()
          return { x: rect.x, y: rect.y }
        }),
      )
      expect(new Set(positions.map(position => Math.round(position.y))).size).toBe(2)
      expect(new Set(positions.slice(0, 3).map(position => Math.round(position.y))).size).toBe(1)
      expect(positions[0]!.x).toBeLessThan(positions[1]!.x)
      expect(positions[1]!.x).toBeLessThan(positions[2]!.x)
      const stock = await bounds(card.getByTestId('equipment-card-stock'))
      const price = await bounds(card.getByTestId('equipment-card-price'))
      const cart = await bounds(card.getByRole('button', { name: 'Добавить в корзину' }))
      expect(stock.x).toBeLessThan(price.x)
      expect(price.y + price.height).toBeLessThanOrEqual(cart.y)
      expect(Math.abs(price.x + price.width - cart.x - cart.width)).toBeLessThan(3)
      const emptyCells = await card.locator('dd').evaluateAll(elements => elements.filter(element => !element.textContent?.trim()).length)
      expect(emptyCells).toBe(0)
      await expectNoHorizontalOverflow(page)
      await card.screenshot({ path: testInfo.outputPath(`card-${width}.png`) })
      await testInfo.attach(`card-height-${width}`, { body: JSON.stringify({ width, height: cardBox.height }), contentType: 'application/json' })
      await card.getByRole('link', { name: 'Подробнее' }).click()
      await hydrated(page)
      await expect(page.getByTestId('detail-basic-parameters').locator('dt').nth(3)).toBeVisible()
      const parameterLabels = await page.getByTestId('detail-basic-parameters').locator('dt').allTextContents()
      expect(parameterLabels.slice(0, 4)).toEqual(['Категория', 'Состояние', 'Год выпуска', 'Цвет кузова'])
      expect(parameterLabels).not.toContain('Комплектация')
      const actions = page.getByTestId('detail-actions')
      await expect(actions.getByRole('button')).toHaveCount(2)
      await expect(page.getByRole('button', { name: /Оформить в лизинг|Купить онлайн|Онлайн оплата/ })).toHaveCount(0)
      await expect(page.getByText('Остатки по складам', { exact: true })).toHaveCount(0)
      const detailFavorite = await bounds(actions.getByRole('button', { name: 'Добавить в избранное' }))
      const detailCart = await bounds(actions.getByRole('button', { name: 'Добавить в корзину' }))
      expect(detailFavorite.width).toBeLessThanOrEqual(48)
      expect(detailFavorite.width).toBe(detailFavorite.height)
      expect(detailFavorite.x + detailFavorite.width).toBeLessThan(detailCart.x)
      expect((await bounds(actions)).y).toBeLessThan((await bounds(page.getByTestId('detail-quantity'))).y)
      await expectCompactWarehouseStock(page, product.warehouse_stock)
      await expect(page.getByTestId('detail-quantity').getByText('В наличии: 2 шт.', { exact: true })).toHaveCount(0)
      await expect(page.getByTestId('detail-quantity').getByLabel('Количество', { exact: true })).toHaveAttribute('max', '2')
      await expectNoHorizontalOverflow(page)
      await page.screenshot({ path: testInfo.outputPath(`detail-${width}.png`), fullPage: true })
    })
  }

  test('Один склад показывает наличие один раз, комплектация остаётся только в названии и подробностях', async ({ page, request }, testInfo) => {
    const productRef = fixtureProduct('trimAbsEsp')
    const product = await productDetail(request, productRef.id)
    expect(product.trim?.name).toBeTruthy()
    expect(product.trim_attribute_groups?.length).toBeGreaterThan(0)
    expect(product.warehouse_stock).toHaveLength(1)
    expect(product.available_count).toBe(1)
    await page.goto(appUrl(`/special-equipment/products/${productRef.id}/${productRef.slug}`))
    await hydrated(page)
    const info = page.locator('[data-storefront-block="equipment.detail.info"]')
    await expect(info.locator(':scope > p').first()).toContainText(product.trim!.name)
    await expect(page.getByTestId('detail-basic-parameters').getByText('Комплектация', { exact: true })).toHaveCount(0)
    await expect(page.locator('[data-storefront-block="equipment.detail.trim"]').getByRole('heading', { name: 'Параметры комплектации' })).toBeVisible()
    await expectCompactWarehouseStock(page, product.warehouse_stock)
    const quantitySection = page.getByTestId('detail-quantity')
    await expect(quantitySection.getByLabel('Количество', { exact: true })).toHaveAttribute('max', '1')
    await expect(quantitySection.getByLabel('Количество', { exact: true })).toHaveValue('1')
    await expect(quantitySection.getByRole('button', { name: 'Увеличить количество' })).toBeDisabled()
    await expectNoHorizontalOverflow(page)
    await quantitySection.screenshot({ path: testInfo.outputPath('single-warehouse.png') })
  })

  test('Гость сохраняет избранное и корзину после перехода на страницу и перезагрузки', async ({ page }) => {
    const card = await openCatalogCard(page)
    await card.getByRole('button', { name: 'Добавить в избранное' }).click()
    await expect(card.getByRole('button', { name: 'Удалить из избранного' })).toHaveAttribute('aria-pressed', 'true')
    await card.getByRole('button', { name: 'Добавить в корзину' }).click()
    await expect(card.getByRole('button', { name: 'Убрать из корзины' })).toBeEnabled()
    await card.getByRole('link', { name: 'Подробнее' }).click()
    await hydrated(page)
    await page.reload()
    await hydrated(page)
    const actions = page.getByTestId('detail-actions')
    await expect(actions.getByRole('button', { name: 'Убрать из избранного' })).toHaveAttribute('aria-pressed', 'true')
    await expect(actions.getByRole('button', { name: 'Убрать из корзины' })).toBeEnabled()
    await actions.getByRole('button', { name: 'Убрать из избранного' }).click()
    await actions.getByRole('button', { name: 'Убрать из корзины' }).click()
    await expect(actions.getByRole('button', { name: 'Добавить в избранное' })).toHaveAttribute('aria-pressed', 'false')
    await expect(actions.getByRole('button', { name: 'Добавить в корзину' })).toBeEnabled()
  })

  test('Обычная, специальная и запросная цена сохраняются после перекомпоновки', async ({ page, playwright }) => {
    const product = fixtureProduct('nonEquivalent')
    const requestProduct = compactFixture().price_on_request_product
    const admin = await playwright.request.newContext({
      baseURL: process.env.E2E_BASE_URL,
      storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE,
    })
    const adminPath = (id: string) => `/api/v1/admin/special-equipment/products/${id}`
    const originalResponse = await admin.get(adminPath(product.id))
    expect(originalResponse.ok()).toBeTruthy()
    const original = await originalResponse.json() as JsonRecord
    const requestOriginalResponse = await admin.get(adminPath(requestProduct.id))
    expect(requestOriginalResponse.ok()).toBeTruthy()
    const requestOriginal = await requestOriginalResponse.json() as JsonRecord
    const patch = async (id: string, data: JsonRecord) => {
      const current = await admin.get(adminPath(id))
      const etag = current.headers().etag
      expect(etag).toBeTruthy()
      const response = await admin.patch(adminPath(id), { headers: { 'If-Match': etag! }, data })
      expect(response.ok(), await response.text()).toBeTruthy()
    }
    const open = async (item: { id: string; slug: string }) => {
      await page.goto(appUrl(`/special-equipment/products/${item.id}/${item.slug}`))
      await hydrated(page)
    }
    const expectCatalogPrice = async (item: { id: string; code: string }, price: string | RegExp) => {
      await page.goto(appUrl(`/special-equipment?search=${encodeURIComponent(item.code)}`))
      await hydrated(page)
      const card = page.locator('[data-storefront-block="equipment.card"]').filter({
        has: page.locator(`a[href*="/products/${item.id}/"]`),
      })
      await expect(card.getByTestId('equipment-card-price').locator('.text-storefront-price')).toHaveText(price)
    }
    try {
      await patch(product.id, { price: '3000000.00', special_price: null })
      await open(product)
      const info = page.locator('[data-storefront-block="equipment.detail.info"]')
      await expect(info.locator('.text-storefront-price').first()).toHaveText(/3\s000\s000\s₽/)
      await expect(info.locator('.line-through')).toHaveCount(0)
      await expectCatalogPrice(product, /3\s000\s000\s₽/)
      await patch(product.id, { special_price: '2500000.00' })
      await open(product)
      await expect(info.locator('.text-storefront-price').first()).toHaveText(/2\s500\s000\s₽/)
      await expect(info.locator('.line-through')).toHaveText(/3\s000\s000\s₽/)
      await expectCatalogPrice(product, /2\s500\s000\s₽/)
      await open(requestProduct)
      await expect(info.locator('.text-storefront-price').first()).toHaveText(/от 2\s700\s000\s₽/)
      await expect(info.locator('.line-through')).toHaveCount(0)
      await expect(page.getByTestId('detail-actions').getByRole('button', { name: 'Добавить в корзину' })).toBeEnabled()
      await expect(page.getByTestId('detail-quantity')).toContainText('Доступно оформление под заказ')
      await expect(page.getByText('Остатки по складам', { exact: true })).toHaveCount(0)
      await expectCatalogPrice(requestProduct, /от 2\s700\s000\s₽/)
      await patch(requestProduct.id, { price_from: null })
      await open(requestProduct)
      await expect(info.locator('.text-storefront-price').first()).toHaveText('Цена по запросу')
      await expectCatalogPrice(requestProduct, 'Цена по запросу')
    } finally {
      await patch(product.id, { price: original.price, special_price: original.special_price })
      await patch(requestProduct.id, { price_from: requestOriginal.price_from })
      await admin.dispose()
    }
  })

  test('Неполные характеристики не оставляют пустых ячеек, недоступные предложения скрыты', async ({ page, request }) => {
    const product = fixtureProduct('nonEquivalent')
    const detail = await productDetail(request, product.id)
    expect(detail.card_attributes.length).toBeLessThan(6)
    expect(detail.card_attributes.length).toBeGreaterThan(0)
    await page.goto(appUrl(`/special-equipment?search=${encodeURIComponent(product.code)}`))
    const card = page.locator('[data-storefront-block="equipment.card"]').filter({
      has: page.locator(`a[href*="/products/${product.id}/"]`),
    })
    const attributes = card.getByTestId('equipment-card-attributes').locator(':scope > div')
    await expect(attributes).toHaveCount(detail.card_attributes.length)
    expect(await attributes.locator('dd').allTextContents()).not.toContain('')
    await expect(card.getByText('Изображение отсутствует')).toHaveCount(1)
    const unavailable = fixtureProduct('publishedUnavailable')
    const unavailableResponse = await request.get(`/api/v1/special-equipment/products/${unavailable.id}`)
    expect(unavailableResponse.status()).toBe(404)
    await page.goto(appUrl(`/special-equipment?search=${encodeURIComponent(unavailable.code)}`))
    await expect(page.locator(`[data-storefront-block="equipment.card"] a[href*="/products/${unavailable.id}/"]`)).toHaveCount(0)
  })

  test('Для отсутствующего предложения показана существующая страница 404', async ({ page }) => {
    const response = await page.goto(appUrl('/special-equipment/products/00000000-0000-4000-8000-000000000001/missing'))
    expect(response?.status()).toBe(404)
    await expect(page.getByRole('heading', { name: '404' })).toBeVisible()
    await expect(page.getByText('Техника не найдена', { exact: true })).toBeVisible()
    await expect(page.getByTestId('detail-actions')).toHaveCount(0)
  })
})

test.describe('Bitrix 22386 — действия авторизованного клиента', () => {
  test.use({ storageState: process.env.E2E_CLIENT_STORAGE_STATE })

  test('Количество, избранное и удаление из корзины сохраняются через реальный API', async ({ page, request }) => {
    const id = compactFixture().product.id
    expect((await request.delete('/api/v1/special-equipment/cart-items?confirm=true')).status()).toBe(204)
    await request.delete(`/api/v1/special-equipment/favorites/${id}`)
    await openDetail(page)
    const actions = page.getByTestId('detail-actions')
    await actions.getByRole('button', { name: 'Добавить в избранное' }).click()
    await expect(actions.getByRole('button', { name: 'Убрать из избранного' })).toBeEnabled()
    const quantity = page.getByTestId('detail-quantity').getByLabel('Количество', { exact: true })
    await quantity.fill('2')
    await quantity.press('Tab')
    await actions.getByRole('button', { name: 'Добавить в корзину' }).click()
    await expect(actions.getByRole('button', { name: 'Убрать из корзины' })).toBeEnabled()
    const cart = await request.get('/api/v1/special-equipment/cart-items')
    expect(cart.ok()).toBeTruthy()
    expect((await cart.json() as { items: JsonRecord[] }).items).toEqual(expect.arrayContaining([
      expect.objectContaining({ product_id: id, quantity: 2 }),
    ]))
    await page.reload()
    await hydrated(page)
    await expect(actions.getByRole('button', { name: 'Убрать из избранного' })).toHaveAttribute('aria-pressed', 'true')
    await actions.getByRole('button', { name: 'Убрать из корзины' }).click()
    await actions.getByRole('button', { name: 'Убрать из избранного' }).click()
    await expect(actions.getByRole('button', { name: 'Добавить в корзину' })).toBeEnabled()
    expect((await (await request.get('/api/v1/special-equipment/cart-items')).json() as { items: JsonRecord[] }).items).toHaveLength(0)
  })

  test('Ошибка добавления не оставляет кнопку в ложном состоянии корзины', async ({ page, request }) => {
    expect((await request.delete('/api/v1/special-equipment/cart-items?confirm=true')).status()).toBe(204)
    await openDetail(page)
    await page.route('**/api/v1/special-equipment/cart-items', async route => {
      if (route.request().method() === 'POST') await route.fulfill({ status: 503, contentType: 'application/problem+json', body: JSON.stringify({ detail: 'Сервис временно недоступен' }) })
      else await route.continue()
    })
    const actions = page.getByTestId('detail-actions')
    await actions.getByRole('button', { name: 'Добавить в корзину' }).click()
    await expect(page.locator('[data-storefront-block="shared.toast"]')).toContainText('Сервис временно недоступен')
    await expect(actions.getByRole('button', { name: 'Добавить в корзину' })).toBeEnabled()
    await expect(actions.getByRole('button', { name: 'Убрать из корзины' })).toHaveCount(0)
    expect((await (await request.get('/api/v1/special-equipment/cart-items')).json() as { items: JsonRecord[] }).items).toHaveLength(0)
  })
})
