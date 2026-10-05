import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type Locator,
  type Page,
} from '@playwright/test'
import { getE2EFixtureManifest, resetE2EFixture, type JsonRecord } from './support/fixtures'
import { appUrl } from './support/runtime'
import { annotateTraceability } from './support/traceability'

const ADMIN_API = '/api/v1/admin/special-equipment'
const PUBLIC_API = '/api/v1/special-equipment'
const ADMIN_CATALOG_URL = '/workspace/special-equipment-catalog'

const json = async (response: Pick<APIResponse, 'ok' | 'status' | 'url' | 'json'>): Promise<JsonRecord> => {
  expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
  return response.json() as Promise<JsonRecord>
}

const record = (source: JsonRecord, key: string): JsonRecord => {
  const value = source[key]
  expect(value, `fixture record ${key}`).toBeTruthy()
  expect(typeof value).toBe('object')
  return value as JsonRecord
}

const string = (source: JsonRecord, key: string): string => {
  const value = source[key]
  expect(typeof value, `${key} must be a string`).toBe('string')
  return value as string
}

const array = (source: JsonRecord, key: string): JsonRecord[] => {
  const value = source[key]
  expect(Array.isArray(value), `${key} must be an array`).toBeTruthy()
  return value as JsonRecord[]
}

const etag = (response: { headers: () => Record<string, string>; url: () => string }): string => {
  const value = response.headers().etag
  expect(value, `${response.url()} must return ETag`).toBeTruthy()
  return String(value)
}

const unique = (): string => `${Date.now()}-${Math.random().toString(16).slice(2)}`

const problemCode = async (response: APIResponse): Promise<string> => {
  expect(response.status()).toBe(422)
  expect(response.headers()['content-type']).toContain('application/problem+json')
  return string(await response.json() as JsonRecord, 'code')
}

const contextRequest = (
  request: APIRequestContext,
  endpoint: 'facets' | 'products',
  modificationIds: string[],
  categoryPath?: string,
): Promise<APIResponse> => {
  const params = new URLSearchParams({ mileage_min: '1' })
  if (categoryPath) params.set('category_path', categoryPath)
  for (const id of modificationIds) params.append('modification_id', id)
  return request.get(`${PUBLIC_API}/${endpoint}?${params.toString()}`)
}

const openTrim = async (page: Page, trimName: string): Promise<Locator> => {
  const row = page.locator('tbody tr').filter({ hasText: trimName })
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: 'Открыть', exact: true }).click()
  const drawer = page.locator('.se-drawer[role="dialog"]')
  await expect(drawer).toBeVisible()
  return drawer
}

test.beforeEach(async ({}, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop-chromium', 'v5.16 проверяется в desktop browser')
  await resetE2EFixture()
})

test.describe('Bitrix 22098 — публичный каталог v5.16', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('AC-3 AC-4 AC-6: guest UI, public blocks, root_items и category context имеют единый контракт', async ({ page, request, playwright }, testInfo) => {
    annotateTraceability(testInfo, {
      task: '22098',
      ac: ['AC-3', 'AC-4', 'AC-6'],
      fr: ['FR-3', 'FR-4', 'FR-6'],
      kind: 'full-stack',
    })
    const fixture = getE2EFixtureManifest()
    const employeeStorageState = process.env.E2E_EMPLOYEE_STORAGE_STATE
    const apiBaseUrl = process.env.E2E_BASE_URL
    expect(employeeStorageState, 'employee storage state is required for fixture setup').toBeTruthy()
    expect(apiBaseUrl, 'E2E API base URL is required for fixture setup').toBeTruthy()
    const adminRequest = await playwright.request.newContext({
      baseURL: apiBaseUrl!,
      storageState: employeeStorageState!,
    })
    const freeAttribute = record(fixture.attributes, 'free')
    const baseWhite = record(fixture.modifications, 'baseWhite')
    const baseBlack = record(fixture.modifications, 'baseBlack')
    const noCategory = record(fixture.modifications, 'noCategory')

    try {
      const attributeResponse = await adminRequest.get(
        `${ADMIN_API}/attributes/${string(freeAttribute, 'id')}`,
      )
      const ungroupAttribute = await adminRequest.patch(
        `${ADMIN_API}/attributes/${string(freeAttribute, 'id')}`,
        {
          headers: { 'If-Match': etag(attributeResponse) },
          data: { attribute_group_id: null },
        },
      )
      expect(ungroupAttribute.ok()).toBeTruthy()

      const categoryResponse = await adminRequest.get(
        `${ADMIN_API}/categories/${fixture.categories.leaf.id}`,
      )
      const category = await json(categoryResponse)
      const attributeLinks = array(category, 'attribute_links')
        .filter(link => link.attribute_id !== string(freeAttribute, 'id'))
        .map(link => ({
          attribute_id: string(link, 'attribute_id'),
          group_id: typeof link.group_id === 'string' ? link.group_id : null,
          is_required: link.is_required === true,
          is_filterable: link.is_filterable === true,
          is_visible: link.is_visible === true,
          sort_order: Number(link.sort_order ?? 0),
        }))
      const categoryPatch = await adminRequest.patch(
        `${ADMIN_API}/categories/${fixture.categories.leaf.id}`,
        {
          headers: { 'If-Match': etag(categoryResponse) },
          data: {
            attribute_links: [...attributeLinks, {
              attribute_id: string(freeAttribute, 'id'),
              group_id: null,
              is_required: false,
              is_filterable: true,
              is_visible: false,
              sort_order: 90,
            }],
          },
        },
      )
      expect(categoryPatch.ok()).toBeTruthy()

      const modificationResponse = await adminRequest.get(
        `${ADMIN_API}/modifications/${string(baseWhite, 'id')}`,
      )
      const modification = await json(modificationResponse)
      const attributeValues = array(modification, 'attribute_values')
        .filter(item => item.attribute_id !== string(freeAttribute, 'id'))
        .map((item) => {
          const attributeId = string(item, 'attribute_id')
          return typeof item.option_id === 'string'
            ? { attribute_id: attributeId, option_id: item.option_id }
            : { attribute_id: attributeId, value: item.value }
        })
      const modificationPatch = await adminRequest.patch(
        `${ADMIN_API}/modifications/${string(baseWhite, 'id')}`,
        {
          headers: { 'If-Match': etag(modificationResponse) },
          data: {
            attribute_values: [...attributeValues, {
              attribute_id: string(freeAttribute, 'id'),
              value: `${fixture.prefix} значение без группы`,
            }],
          },
        },
      )
      expect(modificationPatch.ok()).toBeTruthy()
    } finally {
      await adminRequest.dispose()
    }

    const categories = await json(await request.get(`${PUBLIC_API}/categories`))
    expect(Array.isArray(categories.root_items)).toBeTruthy()
    expect(array(categories, 'root_items').length).toBeGreaterThan(0)

    const leafPath = fixture.categories.leaf.path.join('/')
    for (const endpoint of ['facets', 'products'] as const) {
      expect(await problemCode(await contextRequest(request, endpoint, [])))
        .toBe('CATEGORY_CONTEXT_REQUIRED')
      expect(await problemCode(await contextRequest(request, endpoint, [
        string(baseWhite, 'id'),
        string(baseBlack, 'id'),
      ]))).toBe('CATEGORY_CONTEXT_REQUIRED')
      expect(await problemCode(await contextRequest(request, endpoint, [string(noCategory, 'id')])))
        .toBe('CATEGORY_CONTEXT_REQUIRED')
      expect((await contextRequest(request, endpoint, [string(baseWhite, 'id')])).ok()).toBeTruthy()
      expect((await contextRequest(request, endpoint, [
        string(baseWhite, 'id'),
        string(baseBlack, 'id'),
      ], leafPath)).ok()).toBeTruthy()
    }

    const categoryUrl = (modificationIds: string[] = []): string => {
      const params = new URLSearchParams()
      for (const id of modificationIds) params.append('modification_id', id)
      const query = params.size > 0 ? `?${params.toString()}` : ''
      return appUrl(`/special-equipment/categories/${leafPath}${query}`)
    }
    for (const modificationIds of [
      [],
      [string(baseWhite, 'id')],
      [string(baseWhite, 'id'), string(baseBlack, 'id')],
    ]) {
      await page.goto(categoryUrl(modificationIds), { waitUntil: 'domcontentloaded' })
      await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
      await expect(page.locator('#special-equipment-results')).toHaveAttribute('aria-busy', 'false')
      await expect(page.getByRole('heading', {
        name: fixture.categories.leaf.name,
        exact: true,
        level: 1,
      })).toBeVisible()
    }

    const missingPrimary = new URLSearchParams({
      modification_id: string(noCategory, 'id'),
      usage_min: '1',
    })
    await page.goto(appUrl(`/special-equipment?${missingPrimary.toString()}`), {
      waitUntil: 'domcontentloaded',
    })
    await expect(page.getByRole('button', { name: 'Удалить фильтр Модификация' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Ничего не найдено' })).toBeVisible()
    await expect(page).not.toHaveURL(/usage_min=/)

    await page.goto(appUrl(
      `/special-equipment/products/${fixture.products.representative.id}/${fixture.products.representative.slug}`,
    ), { waitUntil: 'domcontentloaded' })
    const attachments = page.locator('section').filter({
      has: page.getByRole('heading', { name: 'Совместимые надстройки' }),
    })
    await expect(attachments.locator(
      `a[href*="/products/${fixture.products.attachmentStandalone.id}/"]`,
    ).first()).toBeVisible()

    await page.goto(appUrl(
      `/special-equipment/categories/${leafPath}?modification_id=${string(baseWhite, 'id')}&usage_min=1`,
    ), { waitUntil: 'domcontentloaded' })
    await page.getByRole('link', {
      name: 'Каталог транспортных средств и специальной техники',
      exact: true,
    }).click()
    await expect(page).toHaveURL(appUrl('/special-equipment'))
    expect(new URL(page.url()).search).toBe('')
  })

})

test.describe('Bitrix 22098 — административная форма v5.16', () => {
  test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })

  test('AC-1 AC-2 AC-5: desktop form, attachment candidates и trim POST/PUT/DELETE/412 работают вместе', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, {
      task: '22098',
      ac: ['AC-1', 'AC-2', 'AC-5'],
      fr: ['FR-1', 'FR-2', 'FR-5'],
      kind: 'full-stack',
    })
    const fixture = getE2EFixtureManifest()
    const kamaz = record(fixture.marks, 'kamaz')
    const kamazModel = record(fixture.models, 'kamaz1000')
    const baseWhite = record(fixture.modifications, 'baseWhite')
    const representative = record(fixture.products, 'representative')
    const attachmentStandalone = record(fixture.products, 'attachmentStandalone')
    const freeAttribute = record(fixture.attributes, 'free')
    const technicalGroup = record(fixture.attribute_groups, 'technical')

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать объявление', exact: true }).click()
    let drawer = page.locator('.se-drawer[role="dialog"]')
    const usedCondition = drawer.locator('.se-radio-row label').filter({ hasText: 'С пробегом' })
    await expect(usedCondition).toHaveCSS('white-space', 'nowrap')
    const attachmentCandidates = drawer.locator('.se-relation-candidates')
    await expect(attachmentCandidates).toContainText(string(attachmentStandalone, 'code'))
    await expect(attachmentCandidates).not.toContainText(string(representative, 'code'))
    await drawer.getByRole('button', { name: 'Закрыть панель' }).click()
    await expect(drawer).toBeHidden()

    const attachmentResponse = await request.get(`${ADMIN_API}/products`, {
      params: { role: 'attachment', page: 1, page_size: 200 },
    })
    const attachmentIds = array(await json(attachmentResponse), 'items').map(item => string(item, 'id'))
    expect(attachmentIds).toContain(fixture.products.attachmentStandalone.id)
    expect(attachmentIds).not.toContain(fixture.products.representative.id)

    const categoryResponse = await request.get(
      `${ADMIN_API}/categories/${fixture.categories.leaf.id}`,
    )
    const category = await json(categoryResponse)
    const attributeLinks = array(category, 'attribute_links')
      .filter(link => link.attribute_id !== string(freeAttribute, 'id'))
      .map(link => ({
        attribute_id: string(link, 'attribute_id'),
        group_id: typeof link.group_id === 'string' ? link.group_id : null,
        is_required: link.is_required === true,
        is_filterable: link.is_filterable === true,
        is_visible: link.is_visible === true,
        sort_order: Number(link.sort_order ?? 0),
      }))
    const categoryPatch = await request.patch(
      `${ADMIN_API}/categories/${fixture.categories.leaf.id}`,
      {
        headers: { 'If-Match': etag(categoryResponse) },
        data: {
          attribute_links: [...attributeLinks, {
            attribute_id: string(freeAttribute, 'id'),
            group_id: string(technicalGroup, 'id'),
            is_required: false,
            is_filterable: false,
            is_visible: false,
            sort_order: 90,
          }],
        },
      },
    )
    expect(categoryPatch.ok(), `${categoryPatch.status()} ${categoryPatch.url()}`).toBeTruthy()

    const suffix = unique()
    const trimName = `${fixture.prefix} E2E комплектация ${suffix}`
    await page.goto(appUrl(
      `${ADMIN_CATALOG_URL}?section=trims&mark_id=${string(kamaz, 'id')}&model_id=${string(kamazModel, 'id')}`,
    ), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать комплектацию', exact: true }).click()
    drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByLabel('Код', { exact: true })).toHaveCount(0)
    const modificationSelect = drawer.getByRole('combobox', { name: 'Модификация комплектации' })
    await modificationSelect.fill(string(baseWhite, 'name'))
    await drawer.getByRole('option', {
      name: `${string(baseWhite, 'name')} ${string(baseWhite, 'code')}`,
      exact: true,
    }).click()
    await drawer.getByLabel('Название', { exact: false }).fill(trimName)
    const createResponsePromise = page.waitForResponse(response =>
      response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${ADMIN_API}/trims`)
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()
    const createTrim = await createResponsePromise
    expect(createTrim.request().postDataJSON()).toEqual({
      modification_id: string(baseWhite, 'id'),
      name: trimName,
    })
    const trim = await json(createTrim)
    const trimId = string(trim, 'id')
    await expect(drawer.getByRole('heading', { name: trimName, exact: true })).toBeVisible()
    await expect(drawer.getByText('Характеристики комплектации', { exact: true })).toBeVisible()
    await expect(drawer.getByRole('button', { name: 'Сохранить', exact: true })).toBeVisible()

    const candidates = await json(await request.get(`${ADMIN_API}/trims/${trimId}/attribute-candidates`))
    const candidate = array(candidates, 'candidates').find(item =>
      item.attribute_id === string(freeAttribute, 'id') && item.is_available === true,
    )
    expect(candidate).toBeTruthy()

    await expect(drawer.getByRole('button', { name: 'Удалить', exact: true })).toHaveCount(0)

    const groupCheckbox = drawer.getByLabel(string(technicalGroup, 'name'), { exact: true })
    await groupCheckbox.check()
    await drawer.getByLabel(string(freeAttribute, 'name'), { exact: false }).check()
    await drawer.getByRole('button', { name: 'Применить', exact: true }).click()
    const binding = drawer.locator('.se-attribute-binding').filter({ hasText: string(freeAttribute, 'name') })
    await binding.locator('.se-trim-value-field input[type="text"]').fill('значение v5.16')

    let assignmentPostCount = 0
    let valuesPutCount = 0
    let valuesIfMatch = ''
    page.on('request', (request) => {
      if (request.method() === 'POST'
        && new URL(request.url()).pathname === `${ADMIN_API}/trims/${trimId}/attributes`) {
        assignmentPostCount += 1
      }
      if (request.method() === 'PUT'
        && new URL(request.url()).pathname === `${ADMIN_API}/trims/${trimId}/attribute-values`) {
        valuesPutCount += 1
      }
    })
    const valuesRoute = `**${ADMIN_API}/trims/${trimId}/attribute-values`
    await page.route(valuesRoute, async (route) => {
      if (route.request().method() === 'PUT') {
        valuesIfMatch = route.request().headers()['if-match'] ?? ''
        const committed = await route.fetch()
        expect(committed.ok()).toBeTruthy()
        await route.abort('failed')
        return
      }
      await route.continue()
    })
    const postAssignment = page.waitForResponse(response => response.request().method() === 'POST'
      && new URL(response.url()).pathname === `${ADMIN_API}/trims/${trimId}/attributes`)
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    const postResponse = await postAssignment
    expect(postResponse.status()).toBe(201)
    await expect(drawer.locator('.se-form-alert--error')).toBeVisible()
    await expect(drawer).toBeVisible()
    expect(valuesIfMatch).toBe(etag(postResponse))

    await page.unroute(valuesRoute)
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect(assignmentPostCount).toBe(1)
    expect(valuesPutCount).toBe(1)
    await expect(drawer).toBeHidden()

    drawer = await openTrim(page, trimName)
    await drawer.locator('.se-attribute-binding')
      .filter({ hasText: string(freeAttribute, 'name') })
      .getByRole('button', { name: 'Удалить связь', exact: true })
      .click()
    const deleteAssignment = page.waitForResponse(response => response.request().method() === 'DELETE'
      && new URL(response.url()).pathname
      === `${ADMIN_API}/trims/${trimId}/attributes/${string(freeAttribute, 'id')}`)
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect((await deleteAssignment).status()).toBe(204)
    await expect(drawer).toBeHidden()

    drawer = await openTrim(page, trimName)
    const currentTrim = await request.get(`${ADMIN_API}/trims/${trimId}`)
    const serverName = `${trimName} server`
    const externalPatch = await request.patch(`${ADMIN_API}/trims/${trimId}`, {
      headers: { 'If-Match': etag(currentTrim) },
      data: { name: serverName },
    })
    expect(externalPatch.ok()).toBeTruthy()

    const nameInput = drawer.locator('label.se-field').filter({ hasText: 'Название' }).locator('input')
    await nameInput.fill(`${trimName} local`)
    const conflictResponse = page.waitForResponse(response => response.request().method() === 'PATCH'
      && new URL(response.url()).pathname === `${ADMIN_API}/trims/${trimId}`
      && response.status() === 412)
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect((await conflictResponse).headers()['content-type']).toContain('application/problem+json')
    const conflictAlert = drawer.locator('.se-version-conflict')
    await expect(conflictAlert).toContainText('Запись изменилась на сервере')
    await drawer.getByRole('button', { name: 'Загрузить актуальную версию' }).click()
    await expect(nameInput).toHaveValue(serverName)
    await expect(conflictAlert).toHaveCount(0)
    await expect(drawer.locator('.se-form-alert--error')).toHaveCount(0)
  })
})
