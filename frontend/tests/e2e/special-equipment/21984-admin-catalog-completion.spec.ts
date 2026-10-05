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

const uniqueDigits = (): string => String(Date.now()).slice(-13).padStart(13, '0')

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

const openCreateProduct = async (page: Page): Promise<Locator> => {
  await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: 'Создать объявление' }).click()
  const drawer = page.locator('.se-drawer[role="dialog"]')
  await expect(drawer).toBeVisible()
  return drawer
}

const selectBaseModification = async (
  drawer: Locator,
  fixture: ReturnType<typeof getE2EFixtureManifest>,
): Promise<void> => {
  await selectSearchableOption(drawer, 'Марка объявления', fixtureRecord(fixture.marks, 'kamaz'))
  await selectSearchableOption(drawer, 'Модель объявления', fixtureRecord(fixture.models, 'kamaz1000'))
  await selectSearchableOption(drawer, 'Модификация объявления', fixtureRecord(fixture.modifications, 'baseWhite'))
}

const codeInput = (drawer: Locator): Locator => drawer.locator('label.se-field')
  .filter({ hasText: 'Код' })
  .first()
  .locator('input')

const relationEditor = (drawer: Locator, heading: string): Locator => drawer.locator('.se-relation-editor')
  .filter({ hasText: heading })

const addRelationProduct = async (
  editor: Locator,
  product: JsonRecord,
): Promise<void> => {
  const code = stringField(product, 'code')
  await editor.locator('input[type="search"]').first().fill(code)
  const candidate = editor.locator('.se-relation-candidates > li').filter({ hasText: code })
  await expect(candidate).toHaveCount(1)
  await candidate.getByRole('button', { name: 'Добавить', exact: true }).click()
  await expect(editor.locator('.se-relation-list')).toContainText(code)
}

const openRegistryResource = async (
  page: Page,
  section: string,
  resource: JsonRecord,
): Promise<Locator> => {
  await page.goto(appUrl(
    `${ADMIN_CATALOG_URL}?section=${section}&q=${encodeURIComponent(stringField(resource, 'name'))}`,
  ), { waitUntil: 'domcontentloaded' })
  await page.locator('.se-entity-name:visible').first().click()
  const drawer = page.locator('.se-drawer[role="dialog"]')
  await expect(drawer).toBeVisible()
  return drawer
}

const adminResource = async (
  request: APIRequestContext,
  entity: string,
  id: string,
): Promise<JsonRecord> => responseJson(await request.get(`${ADMIN_API}/${entity}/${id}`))

test.describe('Bitrix 21984 — завершение админского каталога', () => {
  test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })
  test.beforeEach(async ({}, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop-chromium', 'Админские FR прогоняются один раз в desktop browser')
    await resetE2EFixture()
  })

  test('FR-4: совместимые надстройки выбираются до первого POST и создаются атомарно', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', fr: 'FR-4', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const unique = uniqueDigits()
    const drawer = await openCreateProduct(page)
    await selectBaseModification(drawer, fixture)
    await codeInput(drawer).fill(`${fixture.prefix}_FR4_${unique}`)
    await drawer.getByLabel(/^VIN/).fill(`2198${unique}`)

    const editor = relationEditor(drawer, 'Совместимые надстройки')
    await addRelationProduct(editor, fixture.products.attachmentCompatible)

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/products`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/products`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()
    const payload = (await createRequest).postDataJSON() as JsonRecord
    expect(payload.compatible_attachments).toEqual([{
      attachment_product_id: fixture.products.attachmentCompatible.id,
      position: 0,
    }])
    const created = await responseJson(await createResponse)
    const compatible = await responseJson(await request.get(
      `${ADMIN_API}/products/${String(created.id)}/compatible-attachments`,
    ))
    expect(compatible.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ attachment_product_id: fixture.products.attachmentCompatible.id }),
    ]))
    await expect(drawer).toBeHidden()
  })

  test('FR-7: изменение data_type в edit mode требует явного подтверждения', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', fr: 'FR-7', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const unique = uniqueDigits()
    const attribute = fixtureRecord(fixture.attributes, 'free')
    const drawer = await openRegistryResource(page, 'attributes', attribute)
    const dataType = drawer.getByLabel(/^Тип значения/)
    await expect(dataType).toHaveValue('text')
    await dataType.selectOption('select')
    let confirmation = page.getByRole('dialog', { name: 'Изменить тип характеристики?' })
    await expect(confirmation).toBeVisible()
    await confirmation.getByRole('button', { name: 'Отмена', exact: true }).click()
    await expect(dataType).toHaveValue('text')

    await dataType.selectOption('select')
    confirmation = page.getByRole('dialog', { name: 'Изменить тип характеристики?' })
    await confirmation.getByRole('button', { name: 'Подтвердить преобразование', exact: true }).click()
    await expect(dataType).toHaveValue('select')
    await drawer.getByRole('button', { name: 'Добавить вариант' }).click()
    const option = drawer.locator('.se-option-row').last()
    await option.locator('label.se-field').filter({ hasText: 'Код варианта' }).locator('input').fill(
      `${fixture.prefix}_E2E_OPTION_${unique}`,
    )
    await option.locator('label.se-field').filter({ hasText: 'Название' }).locator('input').fill(
      `E2E вариант ${unique}`,
    )

    const patchRequest = page.waitForRequest(req => (
      req.method() === 'PATCH'
      && new URL(req.url()).pathname === `${ADMIN_API}/attributes/${stringField(attribute, 'id')}`
    ))
    const patchResponse = page.waitForResponse(response => (
      response.request().method() === 'PATCH'
      && new URL(response.url()).pathname === `${ADMIN_API}/attributes/${stringField(attribute, 'id')}`
    ))
    await drawer.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect((await patchRequest).postDataJSON()).toMatchObject({
      data_type: 'select',
      confirm_type_conversion: true,
    })
    expect((await patchResponse).ok()).toBeTruthy()
    await expect(drawer).toBeHidden()
  })

  test('характеристика с server data_type=select отображается как выбор из вариантов', async ({ page, request }) => {
    const fixture = getE2EFixtureManifest()
    const attribute = fixtureRecord(fixture.attributes, 'color')
    const resource = await adminResource(request, 'attributes', stringField(attribute, 'id'))
    expect(resource.data_type).toBe('select')

    const drawer = await openRegistryResource(page, 'attributes', attribute)
    const dataType = drawer.getByLabel(/^Тип значения/)
    await expect(dataType).toHaveValue('select')
    await expect(dataType.locator('option:checked')).toHaveText('Выбор из вариантов')
    await expect(drawer.getByRole('group', { name: 'Варианты значения' })).toBeVisible()
  })

  test('FR-8: к категориям модификации можно добавить другую совместимую активную категорию', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', fr: 'FR-8', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const unique = uniqueDigits()
    const modification = await adminResource(
      request,
      'modifications',
      stringField(fixtureRecord(fixture.modifications, 'baseWhite'), 'id'),
    )
    const defaultCategoryIds = modification.category_ids as string[]
    const categoriesPayload = await responseJson(await request.get(`${ADMIN_API}/categories`, {
      params: { page_size: '200', sort: 'hierarchy' },
    }))
    const categories = categoriesPayload.items as JsonRecord[]
    const defaultCategory = categories.find(category => category.id === defaultCategoryIds[0])
    expect(defaultCategory).toBeTruthy()
    const ordinaryFixtureCategoryIds = new Set([
      'root', 'emptyRoot', 'dagParentA', 'dagParentB', 'shared', 'siblingA', 'siblingB', 'leaf', 'count25',
    ].map(key => fixture.categories[key as keyof typeof fixture.categories].id))
    const additional = categories.find(category => (
      category.is_active !== false
      && !defaultCategoryIds.includes(String(category.id))
      && ordinaryFixtureCategoryIds.has(String(category.id))
      && category.usage_metric === defaultCategory?.usage_metric
    ))
    expect(additional, 'Нужна активная категория с тем же usage_metric').toBeTruthy()
    const inactive = categories.find(category => (
      category.is_active === false
      && !defaultCategoryIds.includes(String(category.id))
    ))
    expect(inactive, 'Нужна невыбранная неактивная категория для проверки picker').toBeTruthy()

    const drawer = await openCreateProduct(page)
    await selectBaseModification(drawer, fixture)
    await codeInput(drawer).fill(`${fixture.prefix}_FR8_${unique}`)
    await drawer.getByLabel(/^VIN/).fill(`2197${unique}`)
    await drawer.locator('.se-category-picker-trigger').click()
    const picker = page.getByRole('dialog', { name: 'Категории объявления' })
    await picker.getByPlaceholder('Найти категорию').fill(stringField(inactive!, 'name'))
    await expect(picker.getByLabel(stringField(inactive!, 'name'), { exact: false })).toHaveCount(0)
    await picker.getByPlaceholder('Найти категорию').fill(stringField(additional!, 'name'))
    await picker.getByLabel(stringField(additional!, 'name'), { exact: false }).first().check()
    await picker.getByRole('button', { name: 'Готово' }).click()
    await expect(drawer.locator('.se-category-picker-trigger')).toHaveText(
      `Выбрано категорий: ${defaultCategoryIds.length + 1}`,
    )

    const createRequest = page.waitForRequest(req => (
      req.method() === 'POST' && new URL(req.url()).pathname === `${ADMIN_API}/products`
    ))
    const createResponse = page.waitForResponse(response => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === `${ADMIN_API}/products`
    ))
    await drawer.getByRole('button', { name: 'Создать', exact: true }).click()
    const payload = (await createRequest).postDataJSON() as JsonRecord
    expect(payload.category_ids).toEqual(expect.arrayContaining([
      ...defaultCategoryIds,
      stringField(additional!, 'id'),
    ]))
    expect((await createResponse).ok()).toBeTruthy()
    await expect(drawer).toBeHidden()
  })

  test('FR-9: звёздочки, required и aria-required меняются вместе с состоянием формы', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', fr: 'FR-9', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const drawer = await openCreateProduct(page)
    await expect(codeInput(drawer)).toHaveAttribute('required', '')
    await expect(codeInput(drawer)).toHaveAttribute('aria-required', 'true')
    for (const label of ['Марка объявления', 'Модель объявления', 'Модификация объявления']) {
      const input = drawer.getByRole('combobox', { name: label, exact: true })
      await expect(input).toHaveAttribute('required', '')
      await expect(input).toHaveAttribute('aria-required', 'true')
    }
    await selectBaseModification(drawer, fixture)
    await expect(drawer.locator('.se-category-picker-trigger')).toHaveAttribute('aria-required', 'true')
    await expect(drawer.getByLabel('Новое', { exact: true })).toHaveAttribute('required', '')
    await expect(drawer.getByLabel(/^VIN/)).toHaveAttribute('required', '')
    await expect(drawer.getByLabel(/^VIN/)).toHaveAttribute('aria-required', 'true')

    const saleStatus = drawer.locator('label.se-field').filter({ hasText: /^Статус продажи/ }).locator('select')
    await saleStatus.selectOption('on_order')
    const priceField = drawer.locator('label.se-field').filter({ hasText: /^Цена/ })
    await expect(priceField).toContainText('*')
    await expect(priceField.locator('input')).toHaveAttribute('required', '')
    await expect(priceField.locator('input')).toHaveAttribute('aria-required', 'true')

    await drawer.getByLabel('С пробегом', { exact: true }).check()
    const mileage = drawer.getByLabel('Пробег, км', { exact: false })
    const owners = drawer.getByLabel('Количество владельцев', { exact: false })
    for (const input of [mileage, owners]) {
      await expect(input).toHaveAttribute('required', '')
      await expect(input).toHaveAttribute('aria-required', 'true')
    }
  })

  test('FR-11: effective_attribute_links группируются по group_sort_order и не дублируются', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', fr: 'FR-11', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const category = await adminResource(request, 'categories', fixture.categories.leaf.id)
    const links = category.effective_attribute_links as JsonRecord[]
    expect(Array.isArray(links)).toBeTruthy()
    expect(links.length).toBeGreaterThan(0)
    expect(new Set(links.map(link => link.attribute_id)).size).toBe(links.length)

    const kamaz = fixtureRecord(fixture.marks, 'kamaz')
    const model = fixtureRecord(fixture.models, 'kamaz1000')
    await page.goto(appUrl(
      `${ADMIN_CATALOG_URL}?section=modifications&mark_id=${stringField(kamaz, 'id')}&model_id=${stringField(model, 'id')}`,
    ), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать модификацию' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await drawer.getByRole('button', { name: 'Категории не выбраны' }).click()
    const picker = page.getByRole('dialog', { name: 'Категории модификации' })
    await picker.getByPlaceholder('Найти категорию').fill(fixture.categories.leaf.name)
    await picker.getByLabel(fixture.categories.leaf.name, { exact: false }).first().check()
    await picker.getByRole('button', { name: 'Готово' }).click()

    const values = drawer.getByRole('group', { name: 'Значения характеристик' })
    const expectedGroups = [...new Map(links.map(link => [
      link.group_id ?? null,
      {
        name: typeof link.group_name === 'string' ? link.group_name : 'Прочие',
        sort: typeof link.group_sort_order === 'number' ? link.group_sort_order : Number.MAX_SAFE_INTEGER,
      },
    ])).values()].sort((left, right) => left.sort - right.sort || left.name.localeCompare(right.name, 'ru'))
    await expect(values.locator('.se-modification-group > h3')).toHaveText(expectedGroups.map(group => group.name))
    for (const link of links) {
      const field = values.locator('label.se-field').filter({ hasText: stringField(link, 'attribute_name') })
      await expect(field).toHaveCount(1)
      if (link.is_required === true) {
        await expect(field).toContainText('*')
        await expect(field.locator('input, select').first()).toHaveAttribute('required', '')
      }
    }
  })

  test('FR-12: year_from, year_to и manufacture_year хранят string draft и валидируются на blur/submit', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', fr: 'FR-12', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const unique = uniqueDigits()
    const kamaz = fixtureRecord(fixture.marks, 'kamaz')
    const model = fixtureRecord(fixture.models, 'kamaz1000')
    await page.goto(appUrl(
      `${ADMIN_CATALOG_URL}?section=modifications&mark_id=${stringField(kamaz, 'id')}&model_id=${stringField(model, 'id')}`,
    ), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать модификацию' }).click()
    let drawer = page.locator('.se-drawer[role="dialog"]')
    const yearFrom = drawer.getByLabel('Год начала выпуска', { exact: true })
    const yearTo = drawer.getByLabel('Год окончания выпуска', { exact: true })
    for (const input of [yearFrom, yearTo]) {
      await expect(input).toHaveAttribute('type', 'text')
      await expect(input).toHaveAttribute('inputmode', 'numeric')
    }
    await yearFrom.fill('2')
    await yearFrom.press('Tab')
    await expect(drawer.getByText('Введите год от 1900 до 2200.')).toBeVisible()
    await yearFrom.fill('2026')
    await yearFrom.press('ArrowUp')
    await expect(yearFrom).toHaveValue('2027')
    await yearTo.fill('20x6')
    await yearTo.press('Tab')
    await expect(drawer.getByText('Введите год целым числом.')).toBeVisible()

    await drawer.getByRole('button', { name: 'Закрыть' }).click()
    drawer = await openCreateProduct(page)
    await selectBaseModification(drawer, fixture)
    await codeInput(drawer).fill(`${fixture.prefix}_FR12_${unique}`)
    await drawer.getByLabel(/^VIN/).fill(`2196${unique}`)
    const manufactureYear = drawer.getByLabel('Год выпуска', { exact: true })
    await expect(manufactureYear).toHaveAttribute('type', 'text')
    await manufactureYear.fill('1899')
    await manufactureYear.press('Tab')
    await expect(manufactureYear).toHaveAttribute('aria-invalid', 'true')
    await expect(drawer.getByRole('button', { name: 'Создать', exact: true })).toBeDisabled()
    await manufactureYear.fill('2026')
    await manufactureYear.press('Tab')
    await expect(manufactureYear).toHaveAttribute('aria-invalid', 'false')
    await expect(drawer.getByRole('button', { name: 'Создать', exact: true })).toBeEnabled()
  })
})
