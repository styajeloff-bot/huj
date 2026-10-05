import {
  expect,
  test,
  type APIResponse,
  type Locator,
  type Page,
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

const selectSearchableOption = async (
  scope: Page | Locator,
  label: string,
  option: JsonRecord,
): Promise<void> => {
  const input = scope.getByRole('combobox', { name: label, exact: true })
  const name = stringField(option, 'name')
  const code = stringField(option, 'code')
  await input.fill(name)
  await scope.getByRole('listbox', { name: label }).getByRole('option', {
    name: `${name} ${code}`,
    exact: true,
  }).click()
  await expect(input).toHaveValue(name)
}

const selectChassisCategory = async (
  page: Page,
  drawer: Locator,
  category: JsonRecord,
): Promise<void> => {
  await drawer.locator('.se-category-picker-trigger').first().click()
  const picker = page.getByRole('dialog', { name: 'Категории шасси' })
  await expect(picker).toBeVisible()
  await picker.getByPlaceholder('Найти категорию').fill(stringField(category, 'name'))
  await picker.getByLabel(stringField(category, 'name'), { exact: false }).first().check()
  await picker.getByRole('button', { name: 'Готово' }).click()
  await expect(picker).toBeHidden()
}

const selectKitCategory = async (
  page: Page,
  drawer: Locator,
  category: JsonRecord,
): Promise<void> => {
  await drawer.locator('.se-kit-categories-field .se-category-picker-trigger').click()
  const picker = page.getByRole('dialog', { name: 'Категории комплекта' })
  await expect(picker).toBeVisible()
  await picker.getByPlaceholder('Найти категорию').fill(stringField(category, 'name'))
  await picker.getByLabel(stringField(category, 'name'), { exact: false }).first().check()
  await picker.getByRole('button', { name: 'Готово' }).click()
  await expect(picker).toBeHidden()
}

test.describe('Комплекты с техникой и справочник надстроек (kits & superstructures)', () => {
  test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })
  test.beforeEach(async ({}, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop-chromium', 'Админские проверки прогоняются один раз в desktop browser')
    await resetE2EFixture()
  })

  test('CRUD справочника надстроек: создание, открытие, редактирование', async ({ page }) => {
    const unique = uniqueDigits()
    const code = `SS_${unique}`
    const name = `Кран-манипулятор_${unique}`
    const updatedName = `Кран-манипулятор-мод_${unique}`

    // 1. Открыть раздел «Надстройки»
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=superstructures`), { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('text=Надстройки')

    // 2. Нажать «Создать тип надстройки»
    await page.getByRole('button', { name: 'Создать тип надстройки' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    // 3. Заполнить основные поля (без марки/модели — отвязаны в Задаче 4)
    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(code)
    await drawer.locator('label.se-field').filter({ hasText: 'Название' }).locator('input').fill(name)

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/superstructures`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/superstructures`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const reqPayload = (await createRequest).postDataJSON() as JsonRecord
    expect(reqPayload.code).toBe(code)
    expect(reqPayload.name).toBe(name)
    expect(reqPayload.model_id).toBeUndefined()

    const createdData = await responseJson(await createResponse)
    const superstructureId = stringField(createdData, 'id')
    await expect(drawer).toBeHidden()

    // 4. Открыть на редактирование
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=superstructures&q=${encodeURIComponent(name)}`), { waitUntil: 'domcontentloaded' })
    const row = page.locator('tbody tr').filter({ hasText: code })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Открыть', exact: true }).click()
    await expect(drawer).toBeVisible()

    // 5. Изменить название
    const nameInput = drawer.locator('label.se-field').filter({ hasText: 'Название' }).locator('input')
    await nameInput.fill(updatedName)
    const saveResponse = page.waitForResponse(response => (
      response.request().method() === 'PATCH' && new URL(response.url()).pathname === `${ADMIN_API}/superstructures/${superstructureId}`
    ))
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    const updatedData = await responseJson(await saveResponse)
    expect(updatedData.name).toBe(updatedName)
    await expect(drawer).toBeHidden()
  })

  test('Создание «Комплект с техникой» с модификацией шасси', async ({ page, request }) => {
    const fixture = getE2EFixtureManifest()
    const kamazMark = fixtureRecord(fixture.marks, 'kamaz')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const baseWhiteMod = fixtureRecord(fixture.modifications, 'baseWhite')
    const rootCategory = fixtureRecord(fixture.categories, 'root')
    const unique = uniqueDigits()
    const code = `KIT_MOD_${unique}`

    // Создаём тип надстройки для выбора с разрешенной категорией
    const ssRes = await request.post(`${ADMIN_API}/superstructures`, {
      data: {
        code: `SS_TYPE_${unique}`,
        name: `Тип надстройки ${unique}`,
        category_ids: [stringField(rootCategory, 'id')],
      },
    })
    expect(ssRes.ok()).toBeTruthy()
    const ssData = await ssRes.json() as JsonRecord

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать объявление' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    // 1. Выбрать тип: Создание надстройки -> Комплект с техникой
    await drawer.locator('input[name="product-creation-kind"][value="attachment"]').check()
    await drawer.locator('input[name="attachment-create-mode"][value="kit"]').check()

    // 2. Блок 1. Шасси (Категория шасси вынесена наверх, цвета кузова и салона, VIN шасси)
    await selectChassisCategory(page, drawer, rootCategory)

    await selectSearchableOption(drawer, 'Марка шасси', kamazMark)
    await selectSearchableOption(drawer, 'Модель шасси', kamazModel)
    await selectSearchableOption(drawer, 'Модификация шасси', baseWhiteMod)

    await expect(drawer.getByRole('combobox', { name: 'Цвет кузова' })).toBeVisible()
    await expect(drawer.getByRole('combobox', { name: 'Цвет салона' })).toBeVisible()
    await expect(drawer.locator('label.se-field').filter({ hasText: 'VIN шасси' })).toBeVisible()

    // 3. Блок 2. Надстройка (режим «Ввести самим» по умолчанию)
    await selectSearchableOption(drawer, 'Тип надстройки', ssData)
    await drawer.locator('input[placeholder="Например, АТЗ-10"]').fill(`КМУ_${unique}`)
    await drawer.locator('input[placeholder="Например, Palfinger или НПО Вектор"]').fill('Palfinger')

    // Выбрать категорию размещения комплекта (B2)
    await selectKitCategory(page, drawer, rootCategory)

    // 4. Параметры объявления
    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(code)
    await drawer.getByLabel(/^Цена/).fill('3500000')
    await drawer.getByLabel(/нет vin/i).check()

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/products`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/products`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const payload = (await createRequest).postDataJSON() as JsonRecord
    expect(payload.is_kit).toBe(true)
    expect(payload.model_id).toBe(stringField(kamazModel, 'id'))
    expect(payload.modification_id).toBe(stringField(baseWhiteMod, 'id'))
    expect(payload.superstructure_id).toBe(stringField(ssData, 'id'))
    expect(payload.superstructure_name).toBe(`КМУ_${unique}`)
    expect(payload.superstructure_manufacturer).toBe('Palfinger')
    expect(payload.category_ids).toEqual([stringField(rootCategory, 'id')])

    const created = await responseJson(await createResponse)
    expect(created.is_kit).toBe(true)
    expect(created.kind).toBe('kit')
    await expect(drawer).toBeHidden()
  })

  test('Создание «Комплект с техникой» без модификации шасси', async ({ page, request }) => {
    const fixture = getE2EFixtureManifest()
    const kamazMark = fixtureRecord(fixture.marks, 'kamaz')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const rootCategory = fixtureRecord(fixture.categories, 'root')
    const unique = uniqueDigits()
    const code = `KIT_NOMOD_${unique}`

    // Создаём тип надстройки для выбора с разрешенной категорией
    const ssRes = await request.post(`${ADMIN_API}/superstructures`, {
      data: {
        code: `SS_TYPE_${unique}`,
        name: `Тип надстройки ${unique}`,
        category_ids: [stringField(rootCategory, 'id')],
      },
    })
    expect(ssRes.ok()).toBeTruthy()
    const ssData = await ssRes.json() as JsonRecord

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать объявление' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    // 1. Выбрать тип: Создание надстройки -> Комплект с техникой
    await drawer.locator('input[name="product-creation-kind"][value="attachment"]').check()
    await drawer.locator('input[name="attachment-create-mode"][value="kit"]').check()

    // 2. Блок 1. Шасси (Категория вынесена наверх, цвета кузова и салона, VIN шасси)
    await selectChassisCategory(page, drawer, rootCategory)

    await selectSearchableOption(drawer, 'Марка шасси', kamazMark)
    await selectSearchableOption(drawer, 'Модель шасси', kamazModel)

    await expect(drawer.getByRole('combobox', { name: 'Цвет кузова' })).toBeVisible()
    await expect(drawer.getByRole('combobox', { name: 'Цвет салона' })).toBeVisible()
    await expect(drawer.locator('label.se-field').filter({ hasText: 'VIN шасси' })).toBeVisible()

    // 3. Блок 2. Надстройка (режим «Ввести самим» по умолчанию: только тип, название, производитель, VIN надстройки)
    await expect(drawer.getByRole('combobox', { name: 'Тип надстройки' })).toBeVisible()
    await expect(drawer.getByPlaceholder('Например, АТЗ-10')).toBeVisible()
    await expect(drawer.getByPlaceholder('Например, Palfinger или НПО Вектор')).toBeVisible()
    await expect(drawer.locator('label.se-field').filter({ hasText: 'VIN надстройки' })).toBeVisible()
    await expect(drawer.getByRole('combobox', { name: 'Модель надстройки' })).toBeHidden()

    await selectSearchableOption(drawer, 'Тип надстройки', ssData)
    await drawer.locator('input[placeholder="Например, АТЗ-10"]').fill(`Борт_${unique}`)
    await drawer.locator('input[placeholder="Например, Palfinger или НПО Вектор"]').fill('Palfinger')

    // Выбрать категорию размещения комплекта (B2)
    await selectKitCategory(page, drawer, rootCategory)

    // 4. Параметры объявления
    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(code)
    await drawer.getByLabel(/^Цена/).fill('4200000')
    await drawer.getByLabel(/нет vin/i).check()

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/products`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/products`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const payload = (await createRequest).postDataJSON() as JsonRecord
    expect(payload.is_kit).toBe(true)
    expect(payload.modification_id).toBeNull()
    expect(payload.model_id).toBe(stringField(kamazModel, 'id'))
    expect(payload.superstructure_id).toBe(stringField(ssData, 'id'))
    expect(payload.superstructure_name).toBe(`Борт_${unique}`)
    expect(payload.superstructure_manufacturer).toBe('Palfinger')
    expect(payload.category_ids).toEqual([stringField(rootCategory, 'id')])

    const created = await responseJson(await createResponse)
    expect(created.is_kit).toBe(true)
    expect(created.modification_id).toBeNull()
    await expect(drawer).toBeHidden()
  })

  test('Создание «Комплект с техникой» с выбором существующего объявления-надстройки (Задача 2)', async ({ page, request }) => {
    const fixture = getE2EFixtureManifest()
    const kamazMark = fixtureRecord(fixture.marks, 'kamaz')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const baseWhiteMod = fixtureRecord(fixture.modifications, 'baseWhite')
    const rootCategory = fixtureRecord(fixture.categories, 'root')
    const attachmentCategory = fixtureRecord(fixture.categories, 'attachmentRoot')
    const unique = uniqueDigits()
    const kitCode = `KIT_EXIST_${unique}`
    const sourceAdCode = `SRC_AD_${unique}`

    // 1. Создаём тип надстройки с разрешенной категорией
    const ssRes = await request.post(`${ADMIN_API}/superstructures`, {
      data: {
        code: `SS_SRC_${unique}`,
        name: `Тип источника ${unique}`,
        category_ids: [stringField(rootCategory, 'id')],
      },
    })
    expect(ssRes.ok()).toBeTruthy()
    const ssData = await ssRes.json() as JsonRecord

    // 2. Создаём исходное объявление навесного оборудования (в ветке навесного)
    const srcAdRes = await request.post(`${ADMIN_API}/products`, {
      data: {
        code: sourceAdCode,
        is_attachment: true,
        is_kit: false,
        category_ids: [stringField(attachmentCategory, 'id')],
        modification_id: stringField(baseWhiteMod, 'id'),
        price: '1500000',
        no_vin: true,
      },
    })
    expect(srcAdRes.ok()).toBeTruthy()
    const srcAdData = await srcAdRes.json() as JsonRecord
    const srcAdId = stringField(srcAdData, 'id')

    // 3. Открываем создание комплекта
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать объявление' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    // Комплект с техникой
    await drawer.locator('input[name="product-creation-kind"][value="attachment"]').check()
    await drawer.locator('input[name="attachment-create-mode"][value="kit"]').check()

    // Шасси (Категория вынесена наверх)
    await selectChassisCategory(page, drawer, rootCategory)

    await selectSearchableOption(drawer, 'Марка шасси', kamazMark)
    await selectSearchableOption(drawer, 'Модель шасси', kamazModel)
    await selectSearchableOption(drawer, 'Модификация шасси', baseWhiteMod)

    // Блок 2. Надстройка: переключаем в режим «Выбрать существующую»
    await drawer.locator('input[name="superstructure-source-mode"][value="existing"]').check()

    // Каскадный выбор: тип -> производитель надстройки -> модель
    await selectSearchableOption(drawer, 'Тип надстройки', ssData)
    await selectSearchableOption(drawer, 'Производитель надстройки', kamazMark)
    await selectSearchableOption(drawer, 'Модель надстройки', kamazModel)
    await expect(drawer.locator('label.se-field').filter({ hasText: 'VIN надстройки' })).toBeVisible()

    // Выбираем созданное объявление из списка источников
    const sourceItem = drawer.locator('.se-source-item').filter({ hasText: sourceAdCode })
    await expect(sourceItem).toBeVisible()
    await sourceItem.click()

    // Карточка выбранного объявления должна появиться
    const sourceCard = drawer.locator('.se-source-card')
    await expect(sourceCard).toBeVisible()
    await expect(sourceCard.locator('.se-source-card__code')).toHaveText(sourceAdCode)
    await expect(sourceCard.getByRole('button', { name: 'Изменить' })).toBeVisible()

    // Выбрать категорию размещения комплекта (B2)
    await selectKitCategory(page, drawer, rootCategory)

    // 4. Параметры комплекта
    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(kitCode)
    await drawer.getByLabel(/^Цена/).fill('5500000')
    await drawer.getByLabel(/нет vin/i).check()

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/products`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/products`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const payload = (await createRequest).postDataJSON() as JsonRecord
    expect(payload.is_kit).toBe(true)
    expect(payload.superstructure_source_product_id).toBe(srcAdId)
    expect(payload.superstructure_id).toBe(stringField(ssData, 'id'))
    expect(payload.category_ids).toEqual([stringField(rootCategory, 'id')])

    const created = await responseJson(await createResponse)
    expect(created.is_kit).toBe(true)
    expect(created.superstructure_source_product_id).toBe(srcAdId)
    await expect(drawer).toBeHidden()
  })

  test('Редактирование комплекта в админке', async ({ page }) => {
    const fixture = getE2EFixtureManifest()
    const kitProduct = fixtureRecord(fixture.products, 'kitWithMod')
    const updatedPrice = '7770000'

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products&q=${encodeURIComponent(stringField(kitProduct, 'code'))}`), { waitUntil: 'domcontentloaded' })
    const row = page.locator('tbody tr').filter({ hasText: stringField(kitProduct, 'code') })
    await expect(row).toBeVisible()

    // B3: Название комплекта в реестре отображается как составное доменное название
    await expect(row).toContainText('PK 23500 на базе КАМАЗ 1000')

    // B4: Открытие комплекта не вызывает GET /attachments с 422 KIT_COMPATIBILITY_FORBIDDEN
    let attachmentsRequested = false
    page.on('request', req => {
      if (req.url().includes('/attachments') && req.url().includes(stringField(kitProduct, 'id'))) {
        attachmentsRequested = true
      }
    })

    await row.getByRole('button', { name: 'Открыть', exact: true }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()
    expect(attachmentsRequested).toBe(false)

    const priceInput = drawer.getByLabel(/^Цена/)
    await priceInput.fill(updatedPrice)

    const patchResponse = page.waitForResponse(response => (
      response.request().method() === 'PATCH' && new URL(response.url()).pathname === `${ADMIN_API}/products/${stringField(kitProduct, 'id')}`
    ))
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    const updated = await responseJson(await patchResponse)
    expect(String(updated.price)).toContain(updatedPrice)
    await expect(drawer).toBeHidden()
  })

  test('Витрина: заголовок комплекта, карточка, детальная страница и фильтры', async ({ page, request }) => {
    const fixture = getE2EFixtureManifest()
    const kit = fixtureRecord(fixture.products, 'kitWithMod')

    // 1. Проверяем API витрины
    const apiRes = await request.get(`/api/v1/special-equipment/products/${stringField(kit, 'id')}`)
    expect(apiRes.ok()).toBeTruthy()
    const data = await apiRes.json() as JsonRecord
    expect(data.kind).toBe('kit')
    expect(data.superstructure).toBeTruthy()
    expect(stringField(data, 'display_heading')).toContain('+')

    // 2. Проверяем детальную страницу в браузере
    await page.goto(appUrl(`/special-equipment/product/${stringField(kit, 'id')}`), { waitUntil: 'domcontentloaded' })
    await expect(page.locator('[data-testid="detail-chassis-section"]')).toBeVisible()
    await expect(page.locator('[data-testid="detail-superstructure-section"]')).toBeVisible()
    await expect(page.locator('[data-testid="detail-superstructure-section"]')).toContainText('Надстройка')

    // 3. Проверяем фасеты каталога
    const facetsRes = await request.get('/api/v1/special-equipment/facets')
    expect(facetsRes.ok()).toBeTruthy()
    const facets = await facetsRes.json() as JsonRecord
    expect(Array.isArray(facets.superstructures)).toBe(true)
  })

  test('Регрессия: создание самостоятельного объявления техники', async ({ page }) => {
    const fixture = getE2EFixtureManifest()
    const kamazMark = fixtureRecord(fixture.marks, 'kamaz')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const baseWhiteMod = fixtureRecord(fixture.modifications, 'baseWhite')
    const unique = uniqueDigits()
    const code = `STD_VEHICLE_${unique}`

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать объявление' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    // По умолчанию выбран «Создание техники»
    await selectSearchableOption(drawer, 'Марка объявления', kamazMark)
    await selectSearchableOption(drawer, 'Модель объявления', kamazModel)
    await selectSearchableOption(drawer, 'Модификация объявления', baseWhiteMod)

    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(code)
    await drawer.getByLabel(/^Цена/).fill('5000000')
    await drawer.getByLabel(/нет vin/i).check()

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/products`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/products`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const payload = (await createRequest).postDataJSON() as JsonRecord
    expect(payload.is_kit).toBeFalsy()
    expect(payload.is_attachment).toBe(false)
    expect(payload.modification_id).toBe(stringField(baseWhiteMod, 'id'))

    const created = await responseJson(await createResponse)
    expect(created.kind).toBe('vehicle')
    await expect(drawer).toBeHidden()
  })

  test('Вкладки реестра каталога: прокрутка стрелками и видимость активной вкладки', async ({ page }) => {
    // 1. Установить ширину 1280 px
    await page.setViewportSize({ width: 1280, height: 800 })

    // 2. Открыть каталог на начальной странице
    await page.goto(appUrl(ADMIN_CATALOG_URL), { waitUntil: 'domcontentloaded' })
    const rightArrow = page.getByRole('button', { name: 'Прокрутить вкладки вправо' })
    const leftArrow = page.getByRole('button', { name: 'Прокрутить вкладки влево' })

    // Стрелка вправо видна при переполнении, стрелка влево скрыта
    await expect(rightArrow).toBeVisible()
    await expect(leftArrow).toBeHidden()

    // 3. Клик по правой стрелке прокручивает вкладки и делает видимой вкладку «Надстройки»
    await rightArrow.click()
    const superstructureTab = page.getByRole('button', { name: /^Надстройки/ })
    await expect(superstructureTab).toBeVisible()
    await expect(leftArrow).toBeVisible()

    // 4. Открытие ?entity=superstructures сразу показывает активную вкладку
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?entity=superstructures`), { waitUntil: 'domcontentloaded' })
    const activeTab = page.getByRole('button', { name: /^Надстройки/ })
    await expect(activeTab).toBeVisible()
    await expect(activeTab).toHaveAttribute('aria-current', 'page')
  })

  test('Логика VIN: блокировка и очистка всех трех VIN при чекбоксе «Нет VIN»', async ({ page }) => {
    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать объявление' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    // Переключаем в комплект
    await drawer.locator('input[name="product-creation-kind"][value="attachment"]').check()
    await drawer.locator('input[name="attachment-create-mode"][value="kit"]').check()

    const vinVehicle = drawer.locator('label.se-field').filter({ hasText: 'VIN Транспортного средства' }).locator('input')
    const vinChassis = drawer.locator('label.se-field').filter({ hasText: 'VIN шасси' }).locator('input')
    const vinSuper = drawer.locator('label.se-field').filter({ hasText: 'VIN надстройки' }).locator('input')
    const noVinCheckbox = drawer.getByLabel(/нет vin/i)

    // Заполняем все три поля
    await vinVehicle.fill('VIN_VEHICLE_123')
    await vinChassis.fill('VIN_CHASSIS_456')
    await vinSuper.fill('VIN_SUPER_789')

    expect(await vinVehicle.inputValue()).toBe('VIN_VEHICLE_123')
    expect(await vinChassis.inputValue()).toBe('VIN_CHASSIS_456')
    expect(await vinSuper.inputValue()).toBe('VIN_SUPER_789')

    // Включаем чекбокс «Нет VIN»
    await noVinCheckbox.check()

    // Все три поля должны быть заблокированы и очищены
    await expect(vinVehicle).toBeDisabled()
    await expect(vinChassis).toBeDisabled()
    await expect(vinSuper).toBeDisabled()
    expect(await vinVehicle.inputValue()).toBe('')
    expect(await vinChassis.inputValue()).toBe('')
    expect(await vinSuper.inputValue()).toBe('')

    // Снимаем чекбокс
    await noVinCheckbox.uncheck()
    await expect(vinVehicle).toBeEnabled()
    await expect(vinChassis).toBeEnabled()
    await expect(vinSuper).toBeEnabled()
  })

  test('Создание модели с обязательной категорией и привязкой', async ({ page }) => {
    const fixture = getE2EFixtureManifest()
    const kamazMark = fixtureRecord(fixture.marks, 'kamaz')
    const rootCategory = fixtureRecord(fixture.categories, 'root')
    const unique = uniqueDigits()
    const modelCode = `MODEL_${unique}`
    const modelName = `Тестовая модель ${unique}`

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?entity=models`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать модель' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(modelCode)
    await drawer.locator('label.se-field').filter({ hasText: 'Название' }).locator('input').fill(modelName)

    await selectSearchableOption(drawer, 'Марка модели', kamazMark)
    await selectSearchableOption(drawer, 'Категория модели', rootCategory)

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/models`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/models`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const payload = (await createRequest).postDataJSON() as JsonRecord
    expect(payload.code).toBe(modelCode)
    expect(payload.mark_id).toBe(stringField(kamazMark, 'id'))
    expect(payload.category_id).toBe(stringField(rootCategory, 'id'))

    const created = await responseJson(await createResponse)
    expect(created.category_id).toBe(stringField(rootCategory, 'id'))
    await expect(drawer).toBeHidden()
  })

  test('Создание категории с флагом «Отображать в каталоге»', async ({ page }) => {
    const unique = uniqueDigits()
    const catCode = `CAT_VIS_${unique}`
    const catName = `Категория видимости ${unique}`

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?entity=categories`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать категорию' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()

    await drawer.locator('label.se-field').filter({ hasText: 'Код' }).locator('input').fill(catCode)
    await drawer.locator('label.se-field').filter({ hasText: 'Название' }).locator('input').fill(catName)

    const visibleCheckbox = drawer.locator('label.se-checkbox-row').filter({ hasText: 'Отображать в каталоге' }).locator('input[type="checkbox"]')
    await expect(visibleCheckbox).toBeChecked()

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/categories`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/categories`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()

    const payload = (await createRequest).postDataJSON() as JsonRecord
    expect(payload.is_visible_in_catalog).toBe(true)

    const created = await responseJson(await createResponse)
    expect(created.is_visible_in_catalog).toBe(true)
    await expect(drawer).toBeHidden()
  })

  test('Открытие отдельной надстройки не запрашивает compatible-attachments (B4)', async ({ page }) => {
    const fixture = getE2EFixtureManifest()
    const attachment = fixtureRecord(fixture.products, 'attachmentStandalone')

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products&q=${encodeURIComponent(stringField(attachment, 'code'))}`), { waitUntil: 'domcontentloaded' })
    const row = page.locator('tbody tr').filter({ hasText: stringField(attachment, 'code') })
    await expect(row).toBeVisible()

    let attachmentsRequested = false
    page.on('request', req => {
      if (req.url().includes('/attachments') && req.url().includes(stringField(attachment, 'id'))) {
        attachmentsRequested = true
      }
    })

    await row.getByRole('button', { name: 'Открыть', exact: true }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()
    expect(attachmentsRequested).toBe(false)
  })

  test('Серверная валидация категорий комплекта и типа надстройки (B2)', async ({ request }) => {
    const fixture = getE2EFixtureManifest()
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const baseWhiteMod = fixtureRecord(fixture.modifications, 'baseWhite')
    const rootCategory = fixtureRecord(fixture.categories, 'root')
    const attachmentCategory = fixtureRecord(fixture.categories, 'attachmentRoot')
    const unique = uniqueDigits()

    // Создаём тип надстройки с разрешенной категорией rootCategory
    const ssRes = await request.post(`${ADMIN_API}/superstructures`, {
      data: {
        code: `SS_VAL_${unique}`,
        name: `Тип валидации ${unique}`,
        category_ids: [stringField(rootCategory, 'id')],
      },
    })
    expect(ssRes.ok()).toBeTruthy()
    const ssData = await ssRes.json() as JsonRecord

    // 1. Попытка создать комплект с категорией из ветки надстроек -> 422
    const resAttCat = await request.post(`${ADMIN_API}/products`, {
      data: {
        code: `KIT_ERR_ATT_${unique}`,
        is_kit: true,
        model_id: stringField(kamazModel, 'id'),
        modification_id: stringField(baseWhiteMod, 'id'),
        superstructure_id: stringField(ssData, 'id'),
        superstructure_name: 'Тест',
        superstructure_manufacturer: 'Тест',
        category_ids: [stringField(attachmentCategory, 'id')],
        price: '5000000',
        no_vin: true,
      },
    })
    expect(resAttCat.status()).toBe(422)

    // 2. Попытка создать комплект с пустой категорией -> 422
    const resEmptyCat = await request.post(`${ADMIN_API}/products`, {
      data: {
        code: `KIT_ERR_EMPTY_${unique}`,
        is_kit: true,
        model_id: stringField(kamazModel, 'id'),
        modification_id: stringField(baseWhiteMod, 'id'),
        superstructure_id: stringField(ssData, 'id'),
        superstructure_name: 'Тест',
        superstructure_manufacturer: 'Тест',
        category_ids: [],
        price: '5000000',
        no_vin: true,
      },
    })
    expect(resEmptyCat.status()).toBe(422)
  })
})
