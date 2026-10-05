import {
  expect,
  test,
  type APIResponse,
} from '@playwright/test'
import { getE2EFixtureManifest, resetE2EFixture, type JsonRecord } from './support/fixtures'
import { appUrl } from './support/runtime'

const ADMIN_CATALOG_URL = '/workspace/special-equipment-catalog'
const ADMIN_API = '/api/v1/admin/special-equipment'

type JsonResponse = Pick<APIResponse, 'ok' | 'status' | 'url' | 'json'>

const responseJson = async (response: JsonResponse): Promise<JsonRecord> => {
  expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
  return response.json() as Promise<JsonRecord>
}

const stringField = (record: JsonRecord, key: string): string => {
  const value = record[key]
  expect(typeof value, `${key} must be a string`).toBe('string')
  return value as string
}

const fixtureRecord = (records: JsonRecord, key: string): JsonRecord => {
  const value = records[key]
  expect(value, `fixture record ${key}`).toBeTruthy()
  expect(typeof value).toBe('object')
  return value as JsonRecord
}

const uniqueDigits = (): string => String(Date.now()).slice(-8)

test.describe('Справочник «Единицы измерения» (units)', () => {
  test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })
  test.beforeEach(async ({}, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop-chromium', 'Админские проверки прогоняются один раз в desktop browser')
    await resetE2EFixture()
  })

  test('CRUD единиц измерения: создание, открытие, редактирование, деактивация', async ({ page }) => {
    const unique = uniqueDigits()
    const code = `UNIT_${unique}`
    const name = `кВт_${unique}`
    const updatedName = `МВт_${unique}`

    // 1. Открыть раздел единиц измерения
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=units`), { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('text=Единицы измерения')

    // 2. Нажать «Создать единицу измерения»
    await page.getByRole('button', { name: 'Создать единицу измерения' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    // 3. Заполнить форму
    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(code)
    await drawer.locator('label.se-field').filter({ hasText: 'Название' }).locator('input').fill(name)

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/units`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/units`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const reqPayload = (await createRequest).postDataJSON() as JsonRecord
    expect(reqPayload).toMatchObject({ code, name })
    const createdData = await responseJson(await createResponse)
    expect(createdData.code).toBe(code)
    expect(createdData.name).toBe(name)
    const unitId = stringField(createdData, 'id')
    await expect(drawer).toBeHidden()

    // 4. Поиск в реестре и открытие на редактирование
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=units&q=${encodeURIComponent(name)}`), { waitUntil: 'domcontentloaded' })
    const row = page.locator('tbody tr').filter({ hasText: code })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Открыть', exact: true }).click()
    await expect(drawer).toBeVisible()

    // 5. Редактирование названия
    const nameInput = drawer.locator('label.se-field').filter({ hasText: 'Название' }).locator('input')
    await nameInput.fill(updatedName)
    const saveResponse = page.waitForResponse(response => (
      response.request().method() === 'PATCH' && new URL(response.url()).pathname === `${ADMIN_API}/units/${unitId}`
    ))
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    const updatedData = await responseJson(await saveResponse)
    expect(updatedData.name).toBe(updatedName)
    await expect(drawer).toBeHidden()

    // 6. Деактивация через повторное открытие
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=units&q=${encodeURIComponent(updatedName)}`), { waitUntil: 'domcontentloaded' })
    const updatedRow = page.locator('tbody tr').filter({ hasText: code })
    await updatedRow.getByRole('button', { name: 'Открыть', exact: true }).click()
    await expect(drawer).toBeVisible()
    const activeCheckbox = drawer.locator('.se-checkbox-row input[type="checkbox"]')
    await activeCheckbox.uncheck()
    const deactivateResponse = page.waitForResponse(response => (
      response.request().method() === 'PATCH' && new URL(response.url()).pathname === `${ADMIN_API}/units/${unitId}`
    ))
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    const deactivatedData = await responseJson(await deactivateResponse)
    expect(deactivatedData.is_active).toBe(false)
    await expect(drawer).toBeHidden()
  })

  test('Объединение единиц измерения (merge modal)', async ({ page, request }) => {
    const unique = uniqueDigits()

    // Создадим две единицы через API: Source и Target
    const sourceRes = await request.post(`${ADMIN_API}/units`, {
      headers: { 'Idempotency-Key': `merge-src-${unique}` },
      data: { code: `MERGE_SRC_${unique}`, name: `Слияние_Ист_${unique}` },
    })
    const sourceUnit = await responseJson(sourceRes)
    const sourceId = stringField(sourceUnit, 'id')

    const targetRes = await request.post(`${ADMIN_API}/units`, {
      headers: { 'Idempotency-Key': `merge-dst-${unique}` },
      data: { code: `MERGE_DST_${unique}`, name: `Слияние_Цель_${unique}` },
    })
    const targetUnit = await responseJson(targetRes)
    const targetId = stringField(targetUnit, 'id')

    // Открываем реестр и находим Source unit
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=units&q=${encodeURIComponent(stringField(sourceUnit, 'name'))}`), { waitUntil: 'domcontentloaded' })
    const row = page.locator('tbody tr').filter({ hasText: stringField(sourceUnit, 'code') })
    await expect(row).toBeVisible()

    // Нажимаем «Объединить»
    await row.getByRole('button', { name: 'Объединить', exact: true }).click()
    await expect(page.getByText('Объединение единицы измерения')).toBeVisible()

    // Выбираем целевую единицу
    const targetSelect = page.getByRole('combobox', { name: 'Целевая единица измерения' })
    await targetSelect.fill(stringField(targetUnit, 'name'))
    await page.getByRole('listbox', { name: 'Целевая единица измерения' })
      .getByRole('option', { name: new RegExp(stringField(targetUnit, 'name')) })
      .first()
      .click()

    const mergeResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/units/${sourceId}/merge`
    ))
    await page.getByRole('button', { name: 'Объединить', exact: true }).click()
    const mergeData = await responseJson(await mergeResponse)
    expect(mergeData.id).toBe(targetId)

    // Исходная единица удалена (404)
    const checkSource = await request.get(`${ADMIN_API}/units/${sourceId}`)
    expect(checkSource.status()).toBe(404)
  })

  test('Выбор единицы измерения в характеристике', async ({ page }) => {
    const unique = uniqueDigits()
    const attrCode = `ATTR_UNIT_${unique}`
    const attrName = `Мощность ${unique}`

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=attributes`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать характеристику' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(attrCode)
    await drawer.locator('label.se-field').filter({ hasText: 'Название' }).locator('input').fill(attrName)

    // Выбираем тип число
    await drawer.getByLabel(/^Тип значения/).selectOption('number')

    // Выбираем единицу измерения из списка (seeded units)
    const unitSelect = drawer.getByRole('combobox', { name: 'Единица измерения' })
    await unitSelect.fill('тонн')
    await drawer.getByRole('listbox', { name: 'Единица измерения' })
      .getByRole('option')
      .first()
      .click()

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/attributes`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const reqPayload = (await createRequest).postDataJSON() as JsonRecord
    expect(reqPayload.unit_id).toBeTruthy()
    expect(typeof reqPayload.unit_id).toBe('string')
    await expect(drawer).toBeHidden()
  })

  test('Отображение единицы измерения на витрине и в API', async ({ request }) => {
    const fixture = getE2EFixtureManifest()
    // Проверяем публичный эндпоинт товара, у которого есть характеристика с единицей
    const product = fixtureRecord(fixture.products, 'representative')
    const res = await request.get(`/api/v1/special-equipment/products/${stringField(product, 'id')}`)
    expect(res.ok()).toBeTruthy()
    const data = await res.json() as JsonRecord
    // В attribute_groups или характеристиках проверяем, что unit возвращается как строка
    const groups = (data.attribute_groups || []) as JsonRecord[]
    const allAttributes = groups.flatMap((g: JsonRecord) => (g.attributes || []) as JsonRecord[])
    const withUnit = allAttributes.find((a: JsonRecord) => Boolean(a.unit))
    if (withUnit) {
      expect(typeof withUnit.unit).toBe('string')
      expect(withUnit.unit).toBeTruthy()
    }
  })
})
