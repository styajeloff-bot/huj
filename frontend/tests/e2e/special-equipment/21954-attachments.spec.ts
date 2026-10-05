import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test, type APIRequestContext, type APIResponse, type Locator, type Page, type PlaywrightWorkerArgs } from '@playwright/test'
import {
  getE2EFixtureManifest,
  resetE2EFixture,
  type JsonRecord,
} from './support/fixtures'
import { annotateTraceability } from './support/traceability'
import { appUrl } from './support/runtime'

const PRODUCTS_URL = '/api/v1/special-equipment/products'
const FACETS_URL = '/api/v1/special-equipment/facets'
const ADMIN_URL = '/workspace/special-equipment-catalog'
const ADMIN_API = '/api/v1/admin/special-equipment'

const employeeRequest = (playwright: PlaywrightWorkerArgs['playwright']): Promise<APIRequestContext> =>
  playwright.request.newContext({
    baseURL: process.env.E2E_BASE_URL,
    storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE,
  })

const json = async (response: APIResponse): Promise<JsonRecord> => {
  expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
  return response.json() as Promise<JsonRecord>
}

const items = (payload: JsonRecord): JsonRecord[] => {
  expect(Array.isArray(payload.items)).toBeTruthy()
  return payload.items as JsonRecord[]
}

const productPath = (product: JsonRecord): string =>
  `/special-equipment/products/${String(product.id)}/${String(product.slug)}`

const waitForNuxtHydration = async (page: Page): Promise<void> => {
  await page.waitForFunction(() => Boolean(
    (document.querySelector('#__nuxt') as HTMLElement & { __vue_app__?: unknown } | null)?.__vue_app__,
  ), undefined, { timeout: 10_000 })
}

const productDetailsArticle = (page: Page) => page.locator('main article').first()

const recursivelyExpectPublic = (value: unknown): void => {
  if (Array.isArray(value)) {
    value.forEach(recursivelyExpectPublic)
    return
  }
  if (!value || typeof value !== 'object') return
  for (const [key, nested] of Object.entries(value as JsonRecord)) {
    expect(['vin', 'vin_or_serial', 'physical_ids', '_physical_ids', 'physical_unit_ids']).not.toContain(key)
    recursivelyExpectPublic(nested)
  }
}

const expectAscendingNullsLast = (rows: JsonRecord[], key: string): void => {
  const values = rows.map(row => row[key] as number | null | undefined)
  const firstNull = values.findIndex(value => value === null || value === undefined)
  const nonNull = (firstNull === -1 ? values : values.slice(0, firstNull)) as number[]
  expect(nonNull).toEqual([...nonNull].sort((left, right) => left - right))
  if (firstNull !== -1) expect(values.slice(firstNull).every(value => value === null || value === undefined)).toBeTruthy()
}

const expectDescendingNullsLast = (rows: JsonRecord[], key: string): void => {
  const values = rows.map(row => row[key] as number | null | undefined)
  const firstNull = values.findIndex(value => value === null || value === undefined)
  const nonNull = (firstNull === -1 ? values : values.slice(0, firstNull)) as number[]
  expect(nonNull).toEqual([...nonNull].sort((left, right) => right - left))
  if (firstNull !== -1) expect(values.slice(firstNull).every(value => value === null || value === undefined)).toBeTruthy()
}

const adminEntity = async (
  request: APIRequestContext,
  entity: 'categories' | 'products',
  query?: string,
): Promise<JsonRecord[]> => items(await json(await request.get(`${ADMIN_API}/${entity}`, {
  params: { ...(query ? { q: query } : {}), page_size: '200' },
})))

const adminProduct = async (
  request: APIRequestContext,
  productId: unknown,
): Promise<{ body: JsonRecord, etag: string }> => {
  const response = await request.get(`${ADMIN_API}/products/${String(productId)}`)
  const body = await json(response)
  const etag = response.headers().etag
  expect(etag).toBeTruthy()
  return { body, etag }
}

const patchAdminProduct = async (
  request: APIRequestContext,
  productId: unknown,
  data: JsonRecord,
): Promise<JsonRecord> => {
  const current = await adminProduct(request, productId)
  return json(await request.patch(`${ADMIN_API}/products/${String(productId)}`, {
    headers: { 'If-Match': current.etag },
    data,
  }))
}

const cartItems = async (request: APIRequestContext): Promise<JsonRecord[]> =>
  items(await json(await request.get('/api/v1/special-equipment/cart-items')))

const uploadImport = async (
  page: Page,
  filePath: string,
  mode: 'PATCH' | 'FULL_SNAPSHOT' = 'PATCH',
): Promise<string> => {
  await page.goto(appUrl('/workspace/special-equipment-import'), { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('load')
  await waitForNuxtHydration(page)
  if (mode === 'FULL_SNAPSHOT') await page.getByLabel('Полная замена').check()
  await page.getByLabel('Выбрать файл').setInputFiles(filePath)
  const creationResponse = page.waitForResponse(response => (
    response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/special-equipment/imports'
  ))
  await page.getByRole('button', { name: 'Создать и загрузить' }).click()
  const creation = await creationResponse
  expect(creation.ok(), `${creation.status()} ${creation.url()}`).toBeTruthy()
  const created = await creation.json() as JsonRecord
  const importId = String(created.id)
  expect(importId).toMatch(/^[0-9a-f-]{36}$/i)
  await expect(page.getByRole('heading', { name: '3. Предварительная проверка' })).toBeVisible({ timeout: 30_000 })
  return importId
}

const expectImportOutcome = async (
  request: APIRequestContext,
  importId: string,
  expectedStatus: 'completed' | 'completed_with_warnings' | 'validation_failed',
  expectedIssueCodes: string[],
): Promise<void> => {
  await expect.poll(async () => {
    const response = await request.get(`/api/v1/special-equipment/imports/${importId}`)
    if (!response.ok()) return `http:${response.status()}`
    return String(((await response.json()) as JsonRecord).status)
  }, { timeout: 15_000 }).toBe(expectedStatus)

  const issueResponse = await request.get(`/api/v1/special-equipment/imports/${importId}/issues`, {
    params: { limit: '500' },
  })
  const issueCodes = items(await json(issueResponse))
    .map(issue => String(issue.code))
    .sort()
  expect(issueCodes).toEqual([...expectedIssueCodes].sort())
}

test.describe('Bitrix 21954 — публичные надстройки и агрегация', () => {
  test.beforeEach(async () => { await resetE2EFixture() })

  test('AC-1 AC-2 AC-3: attachment-классификация следует DAG и mixed assignment отклоняется атомарно', async ({ page, request, playwright }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: ['AC-1', 'AC-2', 'AC-3'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const categories = items(await json(await request.get('/api/v1/special-equipment/categories')))
    const byId = new Map(categories.map(category => [category.id, category]))

    expect(byId.get(fixture.categories.attachmentRoot.id)?.is_attachment_category).toBe(true)
    expect(byId.get(fixture.categories.attachmentChild.id)?.is_attachment_category).toBe(true)
    expect(byId.get(fixture.categories.attachmentDescendant.id)?.is_attachment_category).toBe(true)
    expect(fixture.categories.attachmentDescendant.parent_ids).toEqual([
      fixture.categories.attachmentChild.id,
    ])
    expect(byId.get(fixture.categories.root.id)?.is_attachment_category).toBe(false)

    const employee = await employeeRequest(playwright)
    try {
      const rawCategories = await adminEntity(employee, 'categories')
      const rawById = new Map(rawCategories.map(category => [category.id, category]))
      expect(rawById.get(fixture.categories.attachmentRoot.id)?.is_attachment_category).toBe(true)
      expect(rawById.get(fixture.categories.attachmentChild.id)?.is_attachment_category).toBe(false)
      expect(rawById.get(fixture.categories.attachmentDescendant.id)?.is_attachment_category).toBe(false)

      const before = await adminProduct(employee, fixture.products.equivalent.id)
      const mixed = await employee.patch(`${ADMIN_API}/products/${fixture.products.equivalent.id}`, {
        headers: { 'If-Match': before.etag },
        data: { category_ids: [fixture.categories.root.id, fixture.categories.attachmentDescendant.id] },
      })
      expect(mixed.status()).toBe(422)
      const problem = await mixed.json() as JsonRecord
      expect(JSON.stringify(problem)).toContain('MIXED_ATTACHMENT_CATEGORIES')
      const after = await adminProduct(employee, fixture.products.equivalent.id)
      expect(after.body.category_ids).toEqual(before.body.category_ids)
    }
    finally {
      await employee.dispose()
    }

    await page.goto(appUrl(`/special-equipment/categories/${fixture.categories.attachmentRoot.path.join('/')}`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('link', { name: fixture.categories.attachmentChild.name }).click()
    await expect(page.getByRole('link', { name: fixture.categories.attachmentDescendant.name })).toBeVisible()
    await page.goto(appUrl(`/special-equipment/categories/${fixture.categories.root.path.join('/')}`), { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: /Варианты надстроек/ })).toBeVisible()
    await expect(page.getByRole('link', { name: fixture.categories.attachmentChild.name })).toBeVisible()
  })

  test('AC-4 AC-6: самостоятельная и совместимая надстройки доступны только при публикации и продаже', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: ['AC-4', 'AC-6'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()

    await page.goto(appUrl(`/special-equipment/categories/${fixture.categories.attachmentDescendant.path.join('/')}`), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const search = page.getByPlaceholder('Название, марка, модель или код')
    await search.fill(String(fixture.products.attachmentCompatible.code))
    await search.press('Enter')
    const standaloneDetails = page.getByRole('link', { name: 'Подробнее' }).first()
    await expect(standaloneDetails).toHaveAttribute('href', new RegExp(`/products/${fixture.products.attachmentCompatible.id}/`))
    await standaloneDetails.click()
    await expect(page).toHaveURL(new RegExp(`/products/${fixture.products.attachmentCompatible.id}/`))
    await waitForNuxtHydration(page)
    const standaloneArticle = productDetailsArticle(page)
    await expect(standaloneArticle.getByRole('button', { name: 'Добавить в корзину' })).toBeEnabled()
    await expect(standaloneArticle.getByRole('button', { name: 'Купить онлайн', exact: true })).toHaveCount(0)
    await expect(standaloneArticle.getByRole('button', { name: 'Оформить в лизинг', exact: true })).toHaveCount(0)

    const compatibility = items(await json(await request.get(
      `/api/v1/special-equipment/products/${fixture.products.representative.id}/compatible-attachments`,
    )))
    const compatibleIds = compatibility.map(item => (item.product as JsonRecord)?.id)
    expect(compatibleIds).toContain(fixture.products.attachmentCompatible.id)
    expect(compatibleIds).toContain(fixture.products.attachmentStandalone.id)
    expect(compatibleIds).not.toContain(fixture.products.unpublishedAvailable.id)
    expect(compatibleIds).not.toContain(fixture.products.publishedUnavailable.id)

    await page.goto(appUrl(productPath(fixture.products.representative)), { waitUntil: 'domcontentloaded' })
    const attachments = page.locator('section').filter({
      has: page.getByRole('heading', { name: 'Совместимые надстройки' }),
    })
    const onOrderCard = attachments.locator('article').filter({
      has: page.locator(`a[href*="/products/${fixture.products.attachmentStandalone.id}/"]`),
    })
    await expect(onOrderCard.getByText('Под заказ', { exact: true })).toBeVisible()
  })

  test('AC-7 AC-8 AC-20 AC-23: aggregation, полный fingerprint-контракт, все sort и privacy', async ({ request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: ['AC-7', 'AC-8', 'AC-20', 'AC-23'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const baseQuery = { sort: 'published_desc', page: '1', page_size: '100' }
    const publicRows = items(await json(await request.get(PRODUCTS_URL, { params: baseQuery })))
    const representative = publicRows.find(row => row.id === fixture.products.representative.id)
    expect(representative?.available_count).toBe(2)
    expect(publicRows.some(row => row.id === fixture.products.equivalent.id)).toBe(false)
    expect(publicRows.some(row => row.id === fixture.products.nonEquivalent.id)).toBe(true)
    recursivelyExpectPublic(publicRows)

    const expectedProbeKeys = [
      'fingerprintModification', 'fingerprintCategory', 'fingerprintSeller',
      'fingerprintCondition', 'fingerprintYear', 'fingerprintPrice',
      'fingerprintMileage', 'fingerprintHours', 'fingerprintOwners',
      'fingerprintSaleStatus', 'fingerprintDescription', 'fingerprintAttributes',
      'fingerprintCompatibility',
    ]
    expect(Object.keys(fixture.fingerprint_probes).sort()).toEqual(expectedProbeKeys.sort())
    const publicById = new Map(publicRows.map(row => [row.id, row]))
    for (const [field, probe] of Object.entries(fixture.fingerprint_probes)) {
      const row = publicById.get(probe.id)
      expect(row, `${field} must remain a separate public card`).toBeTruthy()
      expect(row?.available_count, `${field} must not aggregate`).toBe(1)
      expect(row?.currency_code).toBe('RUB')
    }
    expect(new Set(Object.values(fixture.fingerprint_probes).map(probe => probe.id)).size)
      .toBe(expectedProbeKeys.length)

    const compatibilityProbe = items(await json(await request.get(
      `${PRODUCTS_URL}/${fixture.fingerprint_probes.fingerprintCompatibility.id}/compatible-attachments`,
    )))
    expect(compatibilityProbe).toHaveLength(0)

    const datedCards = [...Object.values(fixture.products), ...Object.values(fixture.fingerprint_probes)]
    const publishedAtById = new Map(datedCards.map(card => [card.id, card.published_at]))
    const leafQuery = { ...baseQuery, category_path: fixture.categories.leaf.path.join('/') }
    const publishedDesc = items(await json(await request.get(PRODUCTS_URL, {
      params: { ...leafQuery, sort: 'published_desc' },
    })))
    const publishedAsc = items(await json(await request.get(PRODUCTS_URL, {
      params: { ...leafQuery, sort: 'published_asc' },
    })))
    const timestamps = (rows: JsonRecord[]) => rows.map(row => {
      const publishedAt = publishedAtById.get(String(row.id))
      expect(publishedAt, `missing published_at oracle for ${String(row.id)}`).toBeTruthy()
      return Date.parse(String(publishedAt))
    })
    expect(timestamps(publishedDesc)).toEqual([...timestamps(publishedDesc)].sort((left, right) => right - left))
    expect(timestamps(publishedAsc)).toEqual([...timestamps(publishedAsc)].sort((left, right) => left - right))
    const tieOrder = (rows: JsonRecord[]): Map<string | null | undefined, JsonRecord[]> => {
      const grouped = new Map<string | null | undefined, JsonRecord[]>()
      for (const row of rows) {
        const date = publishedAtById.get(String(row.id))
        grouped.set(date, [...(grouped.get(date) ?? []), row])
      }
      return grouped
    }
    const ascTies = tieOrder(publishedAsc)
    const descTies = tieOrder(publishedDesc)
    for (const [date, rows] of ascTies) {
      if (rows.length > 1) expect(rows.map(row => row.id)).toEqual(descTies.get(date)?.map(row => row.id))
    }
    const repeatedDesc = items(await json(await request.get(PRODUCTS_URL, {
      params: { ...leafQuery, sort: 'published_desc' },
    })))
    expect(repeatedDesc.map(row => row.id)).toEqual(publishedDesc.map(row => row.id))

    for (const [sort, key, direction] of [
      ['price_asc', 'price', 'asc'],
      ['price_desc', 'price', 'desc'],
    ] as const) {
      const rows = items(await json(await request.get(PRODUCTS_URL, { params: { ...baseQuery, sort } })))
        .map(row => ({ ...row, price: row.price === null ? null : Number(row.price) }))
      if (direction === 'asc') expectAscendingNullsLast(rows, key)
      else expectDescendingNullsLast(rows, key)
    }

    const named = items(await json(await request.get(PRODUCTS_URL, { params: { ...baseQuery, sort: 'name_asc' } })))
    const names = named.map(row => {
      const modification = row.modification as JsonRecord
      const model = modification.model as JsonRecord
      const mark = model.mark as JsonRecord
      return `${String(mark.name)}\u0000${String(model.name)}\u0000${String(modification.name)}`.toLocaleLowerCase('ru')
    })
    expect(names).toEqual([...names].sort((left, right) => left.localeCompare(right, 'ru')))

    const mileageRows = items(await json(await request.get(PRODUCTS_URL, {
      params: { ...baseQuery, sort: 'mileage_asc', condition: 'used' },
    })))
    expectAscendingNullsLast(mileageRows, 'mileage_km')
    const mileageDescRows = items(await json(await request.get(PRODUCTS_URL, {
      params: { ...baseQuery, sort: 'mileage_desc', condition: 'used' },
    })))
    expectDescendingNullsLast(mileageDescRows, 'mileage_km')
    const hourRows = items(await json(await request.get(PRODUCTS_URL, {
      params: { ...baseQuery, sort: 'engine_hours_asc', condition: 'used' },
    })))
    expectAscendingNullsLast(hourRows, 'engine_hours')
    const hourDescRows = items(await json(await request.get(PRODUCTS_URL, {
      params: { ...baseQuery, sort: 'engine_hours_desc', condition: 'used' },
    })))
    expectDescendingNullsLast(hourDescRows, 'engine_hours')

    const facets = await json(await request.get(FACETS_URL, { params: { condition: 'used' } }))
    recursivelyExpectPublic(facets)
  })

  test('AC-11 AC-12: guest собирает группу локально, затем OTP переносит её идемпотентно', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: ['AC-11', 'AC-12'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const mutatingBeforeOtp: string[] = []
    let otpConfirmed = false
    let transfers = 0
    let transferPath = ''
    let transferBody: JsonRecord | undefined
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && url.pathname.startsWith('/api/v1/special-equipment/')) {
        if (!otpConfirmed) mutatingBeforeOtp.push(`${request.method()} ${url.pathname}`)
        if (url.pathname.includes('/special-equipment/cart-transfers/')) {
          transfers += 1
          transferPath = url.pathname
          transferBody = request.postDataJSON() as JsonRecord
        }
      }
    })

    await page.goto(appUrl(productPath(fixture.products.representative)), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const representativeArticle = productDetailsArticle(page)
    const productQuantity = representativeArticle.getByLabel('Количество', { exact: true })
    await expect(productQuantity).toHaveAttribute('max', '2')
    await productQuantity.fill('2')
    await productQuantity.press('Tab')
    await expect(productQuantity).toHaveValue('2')
    const attachments = page.locator('section').filter({
      has: page.getByRole('heading', { name: 'Совместимые надстройки' }),
    })
    const attachmentCard = attachments.locator('article').filter({
      has: page.locator(`a[href*="/products/${fixture.products.attachmentCompatible.id}/"]`),
    })
    await attachmentCard.getByRole('checkbox').check()
    await expect(attachmentCard.getByRole('spinbutton', { name: 'Количество надстроек' })).toHaveValue('1')
    await representativeArticle.getByRole('button', { name: 'Добавить в корзину' }).click()
    await expect(representativeArticle.getByRole('button', { name: 'Убрать из корзины' })).toBeVisible()
    expect(mutatingBeforeOtp).toEqual([])

    const guestGroup = await page.evaluate((storageKey) => {
      const raw = localStorage.getItem(storageKey)
      if (!raw) return []
      const parsed = JSON.parse(raw) as { items?: JsonRecord[] }
      return parsed.items ?? []
    }, String(fixture.cart.guest_storage_key))
    const guestRoot = guestGroup.find(row => row.product_id === fixture.products.representative.id && row.parent_local_id === null)
    expect(guestRoot?.quantity).toBe(2)
    const guestChild = guestGroup.find(row => row.product_id === fixture.products.attachmentCompatible.id && row.parent_local_id === guestRoot?.local_id)
    expect(guestChild?.quantity).toBe(1)

    await page.goto(appUrl('/cart'), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const leasingButton = page.getByRole('button', { name: 'Получить специальное предложение', exact: true })
    await expect(leasingButton).toBeEnabled()
    await leasingButton.click()
    const registration = page.getByRole('dialog').filter({
      has: page.getByRole('heading', { name: 'Регистрация', exact: true }),
    })
    await expect(registration).toBeVisible()
    await registration.getByRole('button', { name: 'Уже есть аккаунт? Войти', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Вход в личный кабинет' })).toBeVisible()
    expect(mutatingBeforeOtp).toEqual([])
    const client = fixture.auth.client as JsonRecord
    await page.getByLabel(/Номер телефона/).fill(String(client.phone))
    await page.getByRole('button', { name: 'Получить код' }).click()
    await page.getByLabel('Код подтверждения').fill('0000')
    otpConfirmed = true
    await page.getByRole('button', { name: 'Подтвердить' }).click()
    await expect.poll(() => transfers, { timeout: 10_000 }).toBe(1)
    await expect(page).toHaveURL(/\/application\/new(?:\?|$)/, { timeout: 10_000 })
    await expect(page.getByRole('heading', { name: 'Оформление заявки на лизинг' })).toBeVisible()
    await expect.poll(async () => {
      const rows = await cartItems(page.context().request)
      const root = rows.find(row => row.product_id === fixture.products.representative.id && row.parent_item_id === null)
      const child = rows.find(row => row.product_id === fixture.products.attachmentCompatible.id && row.parent_item_id === root?.id)
      return { rootQuantity: root?.quantity, childQuantity: child?.quantity }
    }).toEqual({ rootQuantity: 2, childQuantity: 1 })
    const beforeReplay = (await cartItems(page.context().request))
      .map(row => [row.id, row.product_id, row.parent_item_id, row.quantity])
      .sort((left, right) => String(left[0]).localeCompare(String(right[0])))
    const replay = await json(await page.context().request.put(transferPath, { data: transferBody }))
    expect(replay.replayed).toBe(true)
    expect((await cartItems(page.context().request))
      .map(row => [row.id, row.product_id, row.parent_item_id, row.quantity])
      .sort((left, right) => String(left[0]).localeCompare(String(right[0])))).toEqual(beforeReplay)
  })
})

test.describe('Bitrix 21954 — самостоятельное оформление надстройки', () => {
  test.use({ storageState: process.env.E2E_CLIENT_STORAGE_STATE })

  test('AC-4: надстройка находится в публичном каталоге и оформляется без базовой техники', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: 'AC-4', kind: 'full-stack' })
    await resetE2EFixture()
    const fixture = getE2EFixtureManifest()
    expect((await request.delete('/api/v1/special-equipment/cart-items?confirm=true')).status()).toBe(204)

    await page.goto(appUrl(`/special-equipment/categories/${fixture.categories.attachmentDescendant.path.join('/')}`), { waitUntil: 'domcontentloaded' })
    const search = page.getByPlaceholder('Название, марка, модель или код')
    await search.fill(String(fixture.products.attachmentCompatible.code))
    await search.press('Enter')
    const details = page.getByRole('link', { name: 'Подробнее' }).first()
    await expect(details).toHaveAttribute('href', new RegExp(`/products/${fixture.products.attachmentCompatible.id}/`))
    await Promise.all([
      page.waitForURL(new RegExp(`/products/${fixture.products.attachmentCompatible.id}/`)),
      details.click(),
    ])
    await waitForNuxtHydration(page)
    const standaloneArticle = productDetailsArticle(page)

    const addResponse = page.waitForResponse(response => (
      new URL(response.url()).pathname === '/api/v1/special-equipment/cart-items'
      && response.request().method() === 'POST'
    ))
    await standaloneArticle.getByRole('button', { name: 'Добавить в корзину' }).click()
    expect((await addResponse).status()).toBe(201)
    await expect(standaloneArticle.getByRole('button', { name: 'Убрать из корзины' })).toBeVisible()
    const standaloneCart = await cartItems(request)
    expect(standaloneCart).toHaveLength(1)
    expect(standaloneCart[0]).toMatchObject({
      product_id: fixture.products.attachmentCompatible.id,
      parent_item_id: null,
      quantity: 1,
    })

    const activateCheckoutButton = async (button: Locator): Promise<void> => {
      await expect(button).toBeVisible()
      await button.click()
    }

    await page.goto(appUrl('/cart'), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    await activateCheckoutButton(page.getByRole('button', { name: 'Купить', exact: true }))
    const purchaseDialog = page.getByRole('dialog')
    await expect(purchaseDialog).toHaveCount(1)
    await expect(purchaseDialog).toBeVisible()
    await expect(purchaseDialog.getByRole('heading', { name: 'Покупка техники', exact: true })).toBeVisible()
    await activateCheckoutButton(purchaseDialog.getByRole('button', {
      name: /^Полная покупка\s+Оплатить полную стоимость выбранной техники\.$/,
    }))
    await activateCheckoutButton(purchaseDialog.getByRole('button', { name: 'Продолжить', exact: true }))
    const bankTransfer = purchaseDialog.getByRole('radio', {
      name: /^По реквизитам\s+Безналичный перевод по счёту$/,
    })
    await expect(bankTransfer).toBeVisible()
    await bankTransfer.check()
    await activateCheckoutButton(purchaseDialog.getByRole('button', { name: 'Продолжить', exact: true }))
    await expect(purchaseDialog.getByRole('heading', { name: 'Проверьте заказ' })).toBeVisible()
    const orderResponse = page.waitForResponse(response => (
      new URL(response.url()).pathname === '/api/v1/special-equipment/purchase-orders'
      && response.request().method() === 'POST'
    ))
    await activateCheckoutButton(purchaseDialog.getByRole('button', { name: 'Подтвердить и оплатить', exact: true }))
    const createdResponse = await orderResponse
    expect(createdResponse.status()).toBe(201)
    const created = await createdResponse.json() as JsonRecord
    await expect(purchaseDialog.locator('#commerce-order-success-title')).toHaveText('Заказ создан')

    const orders = items(await json(await request.get('/api/v1/special-equipment/purchase-orders')))
    expect(orders).toHaveLength(1)
    const orderItems = (created.order as JsonRecord).items as JsonRecord[]
    expect(orderItems).toHaveLength(1)
    expect(orderItems[0]?.product_id).toBe(fixture.products.attachmentCompatible.id)

    await resetE2EFixture()
    expect((await request.delete('/api/v1/special-equipment/cart-items?confirm=true')).status()).toBe(204)
    await page.goto(appUrl(productPath(fixture.products.attachmentCompatible)), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const leasingAddButton = productDetailsArticle(page).getByRole('button', { name: 'Добавить в корзину' })
    await expect(leasingAddButton).toBeEnabled()
    const leasingAddResponse = page.waitForResponse(response => (
      new URL(response.url()).pathname === '/api/v1/special-equipment/cart-items'
      && response.request().method() === 'POST'
    ))
    await leasingAddButton.click()
    expect((await leasingAddResponse).status()).toBe(201)
    await page.goto(appUrl('/cart'), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Получить специальное предложение', exact: true }).click()
    await expect(page).toHaveURL(/\/application\/new(?:\?|$)/, { timeout: 10_000 })
    const leasingCart = await cartItems(request)
    expect(leasingCart).toHaveLength(1)
    expect(leasingCart[0]).toMatchObject({
      product_id: fixture.products.attachmentCompatible.id,
      parent_item_id: null,
      quantity: 1,
    })
    const company = Object.values(fixture.companies)[0] as JsonRecord
    const leasing = await request.post('/api/v1/special-equipment/leasing-applications', {
      headers: { 'Idempotency-Key': randomUUID() },
      data: {
        source_type: 'platform',
        company_id: company.id,
        cart_item_ids: [leasingCart[0]!.id],
        comment: 'E2E 21954 standalone attachment leasing',
      },
    })
    const leasingBody = await leasing.json() as JsonRecord
    expect(leasing.status(), JSON.stringify(leasingBody)).toBe(201)
    expect(leasingBody.product_ids).toEqual([fixture.products.attachmentCompatible.id])
  })
})

test.describe('Bitrix 21954 — административные связи и импорт', () => {
  test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })

  test('AC-5: сотрудник добавляет и переставляет несколько совместимых надстроек', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: 'AC-5', kind: 'full-stack' })
    await resetE2EFixture()
    const fixture = getE2EFixtureManifest()
    await page.goto(appUrl(`${ADMIN_URL}?section=products&q=${encodeURIComponent(String(fixture.products.representative.code))}`), { waitUntil: 'domcontentloaded' })
    await page.locator('.se-entity-name:visible').first().click()
    const dialog = page.getByRole('dialog')
    const editor = dialog.locator('.se-relation-editor').filter({ hasText: 'Совместимые надстройки' }).first()
    await expect(editor.getByRole('heading', { name: 'Совместимые надстройки', exact: true })).toBeVisible()

    const selectedRelations = editor.getByRole('list', { name: 'Выбранные надстройки' })
    await selectedRelations.getByRole('listitem')
      .filter({ hasText: String(fixture.products.attachmentStandalone.code) })
      .getByRole('button', { name: /^Удалить/ }).click()
    await selectedRelations.getByRole('listitem')
      .filter({ hasText: String(fixture.products.attachmentCompatible.code) })
      .getByRole('button', { name: /^Удалить/ }).click()
    await editor.locator('.se-relation-candidates li')
      .filter({ hasText: String(fixture.products.attachmentStandalone.code) })
      .getByRole('checkbox').check()
    await editor.locator('.se-relation-candidates li')
      .filter({ hasText: String(fixture.products.attachmentCompatible.code) })
      .getByRole('checkbox').check()
    await editor.getByRole('button', { name: 'Добавить выбранные (2)', exact: true }).click()
    await selectedRelations.getByRole('listitem')
      .filter({ hasText: String(fixture.products.attachmentStandalone.code) })
      .getByRole('button', { name: /^Опустить/ }).click()

    const endpoint = `${ADMIN_API}/products/${fixture.products.representative.id}/compatible-attachments`
    const saveResponse = page.waitForResponse(response => (
      new URL(response.url()).pathname === endpoint
      && response.request().method() === 'PUT'
    ))
    await dialog.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect((await saveResponse).ok()).toBeTruthy()
    const finalRows = items(await json(await request.get(endpoint)))
    expect(finalRows.map(row => row.attachment_product_id)).toEqual([
      fixture.products.unpublishedAvailable.id,
      fixture.products.publishedUnavailable.id,
      fixture.products.attachmentCompatible.id,
      fixture.products.attachmentStandalone.id,
    ])
    expect(finalRows.map(row => row.position)).toEqual([0, 1, 2, 3])
  })

  test('AC-21: XLSX v2 импортирует категории, совместимость и состав по кодам', async ({ page, playwright, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: 'AC-21', kind: 'full-stack' })
    test.setTimeout(60_000)
    await resetE2EFixture()
    const clientRequest = await playwright.request.newContext({
      baseURL: process.env.E2E_BASE_URL,
      storageState: process.env.E2E_CLIENT_STORAGE_STATE,
    })
    let cartBeforeSnapshot: unknown[][] = []
    try {
      cartBeforeSnapshot = (await cartItems(clientRequest))
        .map(row => [row.id, row.product_id, row.parent_item_id, row.quantity])
        .sort((left, right) => String(left[0]).localeCompare(String(right[0])))
      expect(cartBeforeSnapshot).toHaveLength(3)
    } finally {
      await clientRequest.dispose()
    }
    const imports = getE2EFixtureManifest().imports
    const importId = await uploadImport(page, String(imports.v2Full), 'FULL_SNAPSHOT')
    await page.getByLabel('Введите «ПОЛНАЯ ЗАМЕНА»').fill('ПОЛНАЯ ЗАМЕНА')
    const applyButton = page.getByRole('button', { name: 'Применить изменения' })
    await expect(applyButton).toBeEnabled({ timeout: 15_000 })
    await applyButton.click()
    await expect(page.getByRole('heading', { name: 'Каталог обновлён' })).toBeVisible({ timeout: 30_000 })
    await expectImportOutcome(request, importId, 'completed', [])

    const preservedCartRequest = await playwright.request.newContext({
      baseURL: process.env.E2E_BASE_URL,
      storageState: process.env.E2E_CLIENT_STORAGE_STATE,
    })
    try {
      expect((await cartItems(preservedCartRequest))
        .map(row => [row.id, row.product_id, row.parent_item_id, row.quantity])
        .sort((left, right) => String(left[0]).localeCompare(String(right[0]))))
        .toEqual(cartBeforeSnapshot)
    } finally {
      await preservedCartRequest.dispose()
    }

    const fixture = getE2EFixtureManifest()
    const importPrefix = `${fixture.prefix}_IMPORT`
    const importedCategory = await adminEntity(request, 'categories')
    expect(importedCategory.some(row => row.code === `${importPrefix}_ATTACHMENT_CATEGORY` && row.is_attachment_category === true)).toBeTruthy()
    const products = await adminEntity(request, 'products', importPrefix)
    const byCode = new Map(products.map(row => [row.code, row]))
    const importedProduct = byCode.get(`${importPrefix}_PRODUCT`)
    const importedAttachment = byCode.get(`${importPrefix}_ATTACHMENT`)
    expect(importedProduct && importedAttachment).toBeTruthy()
    const compatibility = items(await json(await request.get(
      `${ADMIN_API}/products/${String(importedProduct!.id)}/compatible-attachments`,
    )))
    expect(compatibility.map(row => row.attachment_product_id)).toEqual([importedAttachment!.id])
  })

  test('AC-22: старый контракт v2 отклоняется, PATCH add/set/delete и пустой FULL_SNAPSHOT фиксируют post-state', async ({ page, playwright, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: 'AC-22', kind: 'full-stack' })
    test.setTimeout(120_000)
    await resetE2EFixture()
    const fixture = getE2EFixtureManifest()
    const imports = fixture.imports
    const clientRequest = await playwright.request.newContext({
      baseURL: process.env.E2E_BASE_URL,
      storageState: process.env.E2E_CLIENT_STORAGE_STATE,
    })
    let cartBeforeSnapshot: unknown[][] = []
    try {
      cartBeforeSnapshot = (await cartItems(clientRequest))
        .map(row => [row.id, row.product_id, row.parent_item_id, row.quantity])
        .sort((left, right) => String(left[0]).localeCompare(String(right[0])))
      expect(cartBeforeSnapshot).toHaveLength(3)
    }
    finally {
      await clientRequest.dispose()
    }

    await uploadImport(page, String(imports.v2OldContract), 'PATCH')
    await expect(page.getByRole('button', { name: 'Применить изменения' })).toHaveCount(0)
    await expect(page.getByText(/верси|schema|формат/i).first()).toBeVisible()

    await uploadImport(page, String(imports.v2Patch), 'PATCH')
    await page.getByLabel('Введите «ПОДТВЕРЖДАЮ ИЗМЕНЕНИЯ»').fill('ПОДТВЕРЖДАЮ ИЗМЕНЕНИЯ')
    await page.getByRole('button', { name: 'Применить изменения' }).click()
    await expect(page.getByRole('heading', { name: 'Каталог обновлён' })).toBeVisible({ timeout: 30_000 })
    const patched = await adminProduct(request, fixture.products.representative.id)
    expect(patched.body.description).toBe('E2E описание обновлено импортом')

    const representativeCompatibility = items(await json(await request.get(
      `${ADMIN_API}/products/${fixture.products.representative.id}/compatible-attachments`,
    )))
    expect(representativeCompatibility.map(row => [
      row.attachment_product_id,
      row.position,
    ])).toEqual([
      [fixture.products.unpublishedAvailable.id, 2],
      [fixture.products.publishedUnavailable.id, 3],
      [fixture.products.attachmentCompatible.id, 7],
    ])

    await page.getByRole('button', { name: 'Загрузить ещё файл' }).click()
    const bestEffortImportId = await uploadImport(page, String(imports.v2MixedBestEffort), 'PATCH')
    await expect(page.getByText(/Корректные записи можно применить/)).toBeVisible()
    await page.getByRole('button', { name: 'Применить изменения' }).click()
    await expect(page.getByRole('heading', { name: 'Каталог обновлён' })).toBeVisible({ timeout: 30_000 })
    await expectImportOutcome(request, bestEffortImportId, 'completed', ['CODE_INVALID'])
    const bestEffortCode = `${fixture.prefix}_IMPORT_BEST_EFFORT_OK`
    const categories = await adminEntity(request, 'categories')
    expect(categories.filter(row => row.code === bestEffortCode)).toHaveLength(1)
    expect(categories.filter(row => row.code === 'INVALID CODE WITH SPACES')).toHaveLength(0)

    const atomicImportId = await uploadImport(page, String(imports.v2MixedAtomic), 'FULL_SNAPSHOT')
    await expect(page.getByRole('button', { name: 'Применить изменения' })).toHaveCount(0)
    await expectImportOutcome(request, atomicImportId, 'validation_failed', ['CODE_INVALID'])
    expect(await adminEntity(request, 'categories', `${fixture.prefix}_IMPORT_CATEGORY`)).toHaveLength(0)

    await uploadImport(page, String(imports.v2Full), 'FULL_SNAPSHOT')
    await page.getByLabel('Введите «ПОЛНАЯ ЗАМЕНА»').fill('ПОЛНАЯ ЗАМЕНА')
    const applyPopulatedSnapshot = page.getByRole('button', { name: 'Применить изменения' })
    await expect(applyPopulatedSnapshot).toBeEnabled({ timeout: 15_000 })
    await applyPopulatedSnapshot.click()
    await expect(page.getByRole('heading', { name: 'Каталог обновлён' })).toBeVisible({ timeout: 30_000 })
    const importPrefix = `${fixture.prefix}_IMPORT`
    const populatedProducts = await adminEntity(request, 'products', importPrefix)
    const populatedByCode = new Map(populatedProducts.map(row => [row.code, row]))
    const importedProduct = populatedByCode.get(`${importPrefix}_PRODUCT`)
    const importedAttachment = populatedByCode.get(`${importPrefix}_ATTACHMENT`)
    const importedComposite = populatedByCode.get(`${importPrefix}_COMPOSITE`)
    const importedBase = populatedByCode.get(`${importPrefix}_BASE_COMPONENT`)
    expect(importedProduct && importedAttachment && importedComposite && importedBase).toBeTruthy()
    expect((await adminProduct(request, fixture.products.representative.id)).body.publication_status).toBe('archived')
    const originalCategory = (await adminEntity(request, 'categories'))
      .find(row => row.id === fixture.categories.root.id)
    expect(originalCategory?.is_active).toBe(false)
    const preservedCartRequest = await playwright.request.newContext({
      baseURL: process.env.E2E_BASE_URL,
      storageState: process.env.E2E_CLIENT_STORAGE_STATE,
    })
    try {
      expect((await cartItems(preservedCartRequest))
        .map(row => [row.id, row.product_id, row.parent_item_id, row.quantity])
        .sort((left, right) => String(left[0]).localeCompare(String(right[0]))))
        .toEqual(cartBeforeSnapshot)
    } finally {
      await preservedCartRequest.dispose()
    }
    expect(items(await json(await request.get(
      `${ADMIN_API}/products/${String(importedProduct!.id)}/compatible-attachments`,
    ))).map(row => [row.attachment_product_id, row.position])).toEqual([
      [importedAttachment!.id, 0],
    ])
    expect(items(await json(await request.get(
      `${ADMIN_API}/products/${String(importedComposite!.id)}/components`,
    ))).map(row => [row.component_product_id, row.position, row.is_base])).toEqual([
      [importedBase!.id, 0, true],
      [importedAttachment!.id, 1, false],
    ])

    await uploadImport(page, String(imports.v2EmptyRelations), 'FULL_SNAPSHOT')
    await page.getByLabel('Введите «ПОЛНАЯ ЗАМЕНА»').fill('ПОЛНАЯ ЗАМЕНА')
    const applyFullSnapshot = page.getByRole('button', { name: 'Применить изменения' })
    await expect(applyFullSnapshot).toBeEnabled({ timeout: 15_000 })
    await applyFullSnapshot.click()
    await expect(page.getByRole('heading', { name: 'Каталог обновлён' })).toBeVisible({ timeout: 30_000 })
    const clearedProducts = await adminEntity(request, 'products', importPrefix)
    const clearedByCode = new Map(clearedProducts.map(row => [row.code, row]))
    expect(clearedByCode.get(`${importPrefix}_PRODUCT`)?.id).toBe(importedProduct!.id)
    expect(clearedByCode.get(`${importPrefix}_COMPOSITE`)?.id).toBe(importedComposite!.id)
    expect(items(await json(await request.get(
      `${ADMIN_API}/products/${String(importedProduct!.id)}/compatible-attachments`,
    )))).toEqual([])
    expect(items(await json(await request.get(
      `${ADMIN_API}/products/${String(importedComposite!.id)}/components`,
    )))).toEqual([])
  })
})

test.describe('Bitrix 21954 — серверная корзина и оформление', () => {
  test.use({ storageState: process.env.E2E_CLIENT_STORAGE_STATE })

  test.beforeEach(async () => { await resetE2EFixture() })

  test('AC-9: quantity разворачивается в конкретные различные UUID физической техники', async ({ request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: 'AC-9', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const rows = await cartItems(request)
    const root = rows.find(row => row.parent_item_id === null && row.product_id === fixture.products.representative.id)
    expect(root).toBeTruthy()
    for (const row of rows) {
      const response = await request.patch(`/api/v1/special-equipment/cart-items/${String(row.id)}`, {
        data: row.id === root!.id ? { quantity: 2, is_selected: true } : { is_selected: false },
      })
      expect(response.ok()).toBeTruthy()
    }
    const response = await request.post('/api/v1/special-equipment/purchase-orders', {
      headers: { 'Idempotency-Key': `e2e-${fixture.namespace}-quantity-physical-ids` },
      data: {
        cart_item_ids: [root!.id],
        purchase_type: 'full_purchase',
        payment_method: 'bank_transfer',
      },
    })
    expect(response.status()).toBe(201)
    const order = (await response.json() as JsonRecord).order as JsonRecord
    const orderItems = order.items as JsonRecord[]
    const allocated = orderItems.filter(row => row.item_role === 'offer' && row.source_cart_item_id === root!.id)
    expect(allocated).toHaveLength(2)
    expect(new Set(allocated.map(row => row.product_id)).size).toBe(2)
    expect(Number(order.total_price)).toBe(2 * Number((root!.product as JsonRecord).price))
  })

  test('AC-10: превышение и конкурентное списание дают один атомарный результат', async ({ request, playwright }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: ['AC-9', 'AC-10'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const rows = await cartItems(request)
    const root = rows.find(row => row.parent_item_id === null && row.product_id === fixture.products.representative.id)
    expect(root).toBeTruthy()
    const tooMany = await request.patch(`/api/v1/special-equipment/cart-items/${String(root!.id)}`, {
      data: { quantity: 999_999 },
    })
    expect(tooMany.status()).toBe(409)
    const after = await cartItems(request)
    expect(after.find(row => row.id === root!.id)?.quantity).toBe(root!.quantity)

    for (const row of after) {
      const response = await request.patch(`/api/v1/special-equipment/cart-items/${String(row.id)}`, {
        data: { is_selected: row.id === root!.id },
      })
      expect(response.ok()).toBeTruthy()
    }
    const secondClient = await playwright.request.newContext({
      baseURL: process.env.E2E_BASE_URL,
      storageState: process.env.E2E_CLIENT_STORAGE_STATE,
    })
    try {
      const create = (client: APIRequestContext, suffix: string) => client.post('/api/v1/special-equipment/purchase-orders', {
        headers: { 'Idempotency-Key': `e2e-${fixture.namespace}-concurrent-${suffix}` },
        data: {
          cart_item_ids: [root!.id],
          purchase_type: 'full_purchase',
          payment_method: 'bank_transfer',
        },
      })
      const attempts = await Promise.all([create(request, 'a'), create(secondClient, 'b')])
      expect(attempts.filter(response => response.status() === 201)).toHaveLength(1)
      expect(attempts.filter(response => response.status() === 409)).toHaveLength(1)
      const publicRows = items(await json(await request.get(PRODUCTS_URL, { params: { page_size: '100' } })))
      const remaining = publicRows.find(row => row.id === fixture.products.equivalent.id)
      expect(remaining?.available_count).toBe(1)
      expect(publicRows.some(row => row.id === fixture.products.representative.id)).toBe(false)
      const orders = items(await json(await request.get('/api/v1/special-equipment/purchase-orders')))
      expect(orders).toHaveLength(1)
    }
    finally {
      await secondClient.dispose()
    }
  })

  test('AC-13 AC-14: удаление parent отделяет child, standalone и child не сливаются', async ({ request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: ['AC-13', 'AC-14'], kind: 'full-stack' })
    const before = await cartItems(request)
    const root = before.find(row => row.parent_item_id === null && before.some(child => child.parent_item_id === row.id))
    expect(root).toBeTruthy()
    const child = before.find(row => row.parent_item_id === root!.id)
    expect(child).toBeTruthy()
    const matchingBefore = before.filter(row => row.product_id === child!.product_id)
    expect(matchingBefore.length).toBeGreaterThanOrEqual(2)
    const expectedQuantity = matchingBefore.reduce((sum, row) => sum + Number(row.quantity), 0)

    expect((await request.delete(`/api/v1/special-equipment/cart-items/${String(root!.id)}`)).status()).toBe(204)
    const after = await cartItems(request)
    const matchingAfter = after.filter(row => row.product_id === child!.product_id)
    expect(matchingAfter).toHaveLength(1)
    expect(matchingAfter[0]?.parent_item_id).toBeNull()
    expect(matchingAfter[0]?.quantity).toBe(expectedQuantity)
  })

  test('AC-15: purchase/reservation/preorder/leasing сохраняют группу, состав и точную сумму', async ({ request, playwright }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: 'AC-15', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    for (const purchaseType of ['full_purchase', 'reservation', 'preorder'] as const) {
      await resetE2EFixture()
      if (purchaseType === 'preorder') {
        const employee = await employeeRequest(playwright)
        try {
          await patchAdminProduct(employee, fixture.products.representative.id, { sale_status: 'on_order' })
        }
        finally {
          await employee.dispose()
        }
      }
      const cart = await cartItems(request)
      const groupRoot = cart.find(row => (
        row.parent_item_id === null
        && row.product_id === fixture.products.representative.id
        && cart.some(child => child.parent_item_id === row.id)
      ))
      expect(groupRoot).toBeTruthy()
      const selected = cart.filter(row => (
        row.id === groupRoot!.id || row.parent_item_id === groupRoot!.id
      ))
      const cartItemIds = selected.map(row => String(row.id))
      const expectedTotal = selected.reduce((sum, row) => {
        const product = row.product as JsonRecord
        return sum + Number(row.quantity) * Number(row.custom_price ?? product.price)
      }, 0)
      const response = await request.post('/api/v1/special-equipment/purchase-orders', {
        headers: { 'Idempotency-Key': `e2e-${fixture.namespace}-${purchaseType}` },
        data: { cart_item_ids: cartItemIds, purchase_type: purchaseType, payment_method: 'bank_transfer' },
      })
      const responseBody = await response.json() as JsonRecord
      expect(response.status(), JSON.stringify(responseBody)).toBe(201)
      const order = responseBody.order as JsonRecord
      const orderItems = order.items as JsonRecord[]
      expect(order.purchase_type).toBe(purchaseType)
      expect(Number(order.total_price)).toBe(expectedTotal)
      expect(new Set(orderItems.map(item => item.source_cart_item_id))).toEqual(new Set(cartItemIds))
      expect(orderItems.some(item => item.item_role === 'attachment' && item.parent_group_id !== null)).toBeTruthy()
    }

    await resetE2EFixture()
    const leasingCart = await cartItems(request)
    const leasingRoot = leasingCart.find(row => (
      row.parent_item_id === null
      && row.product_id === fixture.products.representative.id
      && leasingCart.some(child => child.parent_item_id === row.id)
    ))
    expect(leasingRoot).toBeTruthy()
    const leasingRootUpdate = await request.patch(`/api/v1/special-equipment/cart-items/${String(leasingRoot!.id)}`, {
      data: { quantity: 2, is_selected: true },
    })
    expect(leasingRootUpdate.ok()).toBeTruthy()
    const resizedLeasingCart = await cartItems(request)
    const leasingGroup = resizedLeasingCart.filter(row => (
      row.id === leasingRoot!.id || row.parent_item_id === leasingRoot!.id
    ))
    expect(leasingGroup).toHaveLength(2)
    const leasingIds = leasingGroup.map(row => String(row.id))
    const leasingAttachment = leasingGroup.find(row => row.parent_item_id === leasingRoot!.id)
    expect(leasingAttachment?.product_id).toBe(fixture.products.attachmentCompatible.id)
    const expectedLeasingTotal = 2 * Number((leasingRoot!.product as JsonRecord).price)
      + Number((leasingAttachment!.product as JsonRecord).price)
    const company = Object.values(fixture.companies)[0] as JsonRecord
    const leasing = await request.post('/api/v1/special-equipment/leasing-applications', {
      headers: { 'Idempotency-Key': randomUUID() },
      data: { source_type: 'platform', company_id: company.id, cart_item_ids: leasingIds, comment: 'E2E 21954 group leasing' },
    })
    const leasingBody = await leasing.json() as JsonRecord
    expect(leasing.status(), JSON.stringify(leasingBody)).toBe(201)
    expect(leasingBody.item_ids).toHaveLength(3)
    expect((leasingBody.product_ids as string[]).sort()).toEqual([
      fixture.products.representative.id,
      fixture.products.equivalent.id,
      fixture.products.attachmentCompatible.id,
    ].sort())
    expect(new Set(leasingBody.product_ids as string[]).size).toBe(3)
    const leasingDetail = await json(await request.get(
      `/api/v1/applications/${String(leasingBody.application_id)}`,
    ))
    expect(leasingDetail.items_count).toBe(3)
    expect(Number(leasingDetail.total_items_price)).toBe(expectedLeasingTotal)
    expect(Number(leasingDetail.total_amount)).toBe(expectedLeasingTotal)
    expect(leasingDetail.items).toHaveLength(2)
    const rootItem = (leasingDetail.items as JsonRecord[]).find(item => item.item_role === 'offer')
    expect(rootItem?.quantity).toBe(2)
    expect(rootItem?.product_ids).toHaveLength(2)
    const attachmentItem = (leasingDetail.items as JsonRecord[]).find(item => item.item_role === 'attachment')
    expect(attachmentItem?.quantity).toBe(1)
    expect(attachmentItem?.product_ids).toHaveLength(1)
    const allProductIds = (leasingDetail.items as JsonRecord[]).flatMap(item => (item.product_ids as string[]) || [])
    expect(allProductIds.sort()).toEqual((leasingBody.product_ids as string[]).sort())
    const remainingCart = await cartItems(request)
    expect(remainingCart).toHaveLength(1)
    expect(remainingCart[0]).toMatchObject({
      product_id: fixture.products.attachmentCompatible.id,
      parent_item_id: null,
      quantity: 1,
    })
  })

  test('AC-24 AC-25: backfill artifact и pipeline жёстко ставят полный №21940 перед №21954', async ({ request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21954', ac: ['AC-24', 'AC-25'], kind: 'contract-guard' })
    expect((await request.get('/api/v1/health')).ok()).toBeTruthy()
    const artifactPath = resolve(String(process.env.E2E_ARTIFACT_DIR), 'backfill-21954.json')
    expect(existsSync(artifactPath)).toBeTruthy()
    const artifact = JSON.parse(readFileSync(artifactPath, 'utf8')) as JsonRecord
    expect(artifact).toMatchObject({
      is_attachment_category: false,
      quantity: 1,
      catalog_product_id: '21954000-0000-5000-8000-000000000005',
      catalog_product_code: 'E2E_21954_PRODUCT',
      legacy_rows_retained: true,
    })
    expect(typeof artifact.revision).toBe('string')
    const backfill = readFileSync(resolve(__dirname, '../../../../scripts/e2e/backfill_21954.py'), 'utf8')
    expect(backfill).toContain('def _expected_head_revision()')
    expect(backfill).toContain('"revision": revision')
    const runner = readFileSync(resolve(__dirname, '../../../../scripts/e2e/run.sh'), 'utf8')
    expect(runner.indexOf('for suite in 21940 21954 21984')).toBeGreaterThan(-1)
    expect(runner.indexOf('21940)')).toBeLessThan(runner.indexOf('21954)'))
    expect(runner.indexOf('21954-backfill.smoke.spec.ts')).toBeLessThan(runner.indexOf('backfill_21954.py" cleanup'))
    const pipeline = readFileSync(resolve(__dirname, '../../../../.gitlab-ci.yml'), 'utf8')
    expect(pipeline).toContain('E2E_BACKFILL_COMMAND: "bash scripts/e2e/verify-backfill.sh"')
    expect(pipeline).toContain('bash scripts/e2e/run.sh --ci')
  })
})
