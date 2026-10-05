import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type Locator,
  type Page,
  type Response as PlaywrightResponse,
} from '@playwright/test'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { getE2EFixtureManifest, resetE2EFixture } from './support/fixtures'
import { appUrl } from './support/runtime'
import { annotateTraceability } from './support/traceability'

const ADMIN_CATALOG_URL = '/workspace/special-equipment-catalog'
const PUBLIC_PRODUCTS_URL = '/api/v1/special-equipment/products'
const PUBLIC_FACETS_URL = '/api/v1/special-equipment/facets'

type JsonObject = Record<string, unknown>

const responseJson = async (response: APIResponse): Promise<JsonObject> => {
  expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
  return response.json() as Promise<JsonObject>
}

const listItems = (payload: JsonObject): JsonObject[] => {
  expect(Array.isArray(payload.items)).toBeTruthy()
  return payload.items as JsonObject[]
}

const fixtureRecord = (records: JsonObject, key: string): JsonObject => {
  const value = records[key]
  expect(value, `fixture record ${key}`).toBeTruthy()
  expect(typeof value).toBe('object')
  return value as JsonObject
}

const stringField = (record: JsonObject, key: string): string => {
  const value = record[key]
  expect(typeof value, `${key} must be a string`).toBe('string')
  return value as string
}

const escapeRegExp = (value: string): string =>
  value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const waitForNuxtHydration = async (page: Page): Promise<void> => {
  await page.waitForFunction(() => Boolean(
    (document.querySelector('#__nuxt') as HTMLElement & { __vue_app__?: unknown } | null)?.__vue_app__,
  ), undefined, { timeout: 10_000 })
}

const openPublicFilters = async (page: Page): Promise<Locator> => {
  await page.getByRole('button', { name: /^Все фильтры/ }).click()
  const filters = page.getByRole('dialog', { name: 'Все фильтры', exact: true })
  await expect(filters).toBeVisible()
  return filters
}

const expectFilterOptionsContained = async (group: Locator): Promise<void> => {
  const overflowing = await group.locator('label').evaluateAll(labels => labels.flatMap((label) => {
    const bounds = label.getBoundingClientRect()
    const childOutside = Array.from(label.children)
      .filter(child => !child.classList.contains('sr-only'))
      .some((child) => {
        const childBounds = child.getBoundingClientRect()
        return childBounds.left < bounds.left - 1
          || childBounds.right > bounds.right + 1
          || childBounds.top < bounds.top - 1
          || childBounds.bottom > bounds.bottom + 1
      })
    return label.scrollWidth > label.clientWidth + 1 || childOutside
      ? [label.textContent?.trim() || '<empty>']
      : []
  }))
  expect(overflowing).toEqual([])
}

const authenticateFromCheckout = async (page: Page, phone: string): Promise<void> => {
  const dialog = page.getByRole('dialog').filter({
    has: page.getByRole('heading', { name: 'Вход в личный кабинет' }),
  })
  await expect(dialog).toBeVisible()
  await dialog.getByLabel(/Номер телефона/).fill(phone)
  await dialog.getByRole('button', { name: 'Получить код' }).click()
  await dialog.getByLabel('Код подтверждения').fill('0000')
  await dialog.getByRole('button', { name: 'Подтвердить' }).click()
  await expect(dialog).toBeHidden()
}

const openCartFromProduct = async (page: Page): Promise<void> => {
  await page.getByRole('button', { name: 'Добавить в корзину', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Убрать из корзины', exact: true })).toBeEnabled()
  await page.goto(appUrl('/cart'), { waitUntil: 'domcontentloaded' })
  await waitForNuxtHydration(page)
  await expect(page.getByRole('heading', { name: 'Корзина', exact: true })).toBeVisible()
}

const selectSearchableOption = async (
  scope: Page | Locator,
  label: string,
  option: JsonObject,
): Promise<void> => {
  const input = scope.getByRole('combobox', { name: label, exact: true })
  const name = stringField(option, 'name')
  const code = stringField(option, 'code')
  await input.fill(name)
  const matchingOption = scope.getByRole('listbox', { name: label }).getByRole('option', {
    name: `${name} ${code}`,
    exact: true,
  })
  await expect(matchingOption).toHaveCount(1)
  await matchingOption.click()
  await expect(input).toHaveValue(name)
}

const selectSortAndWaitForProducts = async (
  page: Page,
  select: Locator,
  sort: string,
): Promise<PlaywrightResponse> => {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const responsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return url.pathname === PUBLIC_PRODUCTS_URL && url.searchParams.get('sort') === sort
    }, { timeout: 3_000 }).catch(() => null)
    await select.selectOption(sort)
    const response = await responsePromise
    if (response) return response
  }
  throw new Error(`Products request for sort=${sort} was not observed after hydration retry`)
}

const adminResource = async (
  request: APIRequestContext,
  entity: string,
  id: string,
): Promise<JsonObject> => responseJson(await request.get(
  `/api/v1/admin/special-equipment/${entity}/${id}`,
))

const openRegistryResource = async (
  page: Page,
  section: string,
  resource: JsonObject,
): Promise<Locator> => {
  await page.goto(appUrl(
    `${ADMIN_CATALOG_URL}?section=${section}&q=${encodeURIComponent(stringField(resource, 'name'))}`,
  ), { waitUntil: 'domcontentloaded' })
  await page.locator('.se-entity-name:visible').first().click()
  const drawer = page.locator('.se-drawer[role="dialog"]')
  await expect(drawer).toBeVisible()
  return drawer
}

test.describe('Bitrix 21940 — управление каталогом', () => {
  test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })
  test.beforeEach(async () => { await resetE2EFixture() })

  test('AC-1 AC-2: DAG, уровневый фильтр и две согласованные сортировки', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: ['AC-1', 'AC-2'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=categories&sort=hierarchy`), { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('main').getByRole('heading', { name: 'Управление каталогом' })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Категории/ })).toHaveAttribute('aria-current', 'page')
    await expect(page.getByLabel('Фильтр категорий, уровень 1')).toBeVisible()
    await expect(page.getByLabel('Фильтр категорий, уровень 2')).toHaveCount(0)
    await expect(page.getByText(fixture.categories.root.name, { exact: true }).filter({ visible: true }).first()).toBeVisible()

    await selectSearchableOption(page, 'Фильтр категорий, уровень 1', fixture.categories.root)
    await expect(page).toHaveURL(new RegExp(`level_1_id=${fixture.categories.root.id}`))
    await expect(page.getByLabel('Фильтр категорий, уровень 2')).toBeVisible()
    await selectSearchableOption(page, 'Фильтр категорий, уровень 2', fixture.categories.leaf)
    await expect(page).toHaveURL(new RegExp(`level_2_id=${fixture.categories.leaf.id}`))
    await expect(page.getByLabel('Фильтр категорий, уровень 3')).toBeVisible()

    const leafResource = await adminResource(request, 'categories', fixture.categories.leaf.id)
    const canonicalPath = stringField(leafResource, 'canonical_path')
    const search = page.getByPlaceholder('Поиск: категории')
    await search.fill(canonicalPath)
    await search.press('Enter')
    await expect(page.getByText(fixture.categories.leaf.name, { exact: true }).filter({ visible: true }).first()).toBeVisible()

    const sort = page.getByLabel('Сортировка')
    await expect(sort.locator('option')).toHaveText(['По дате', 'По иерархии'])
    await expect(page.locator('input[type="date"]')).toHaveCount(0)
    await expect(sort).toHaveValue('hierarchy')
    await sort.selectOption('updated_desc')
    await expect(page).toHaveURL(/(?:\?|&)sort=updated_desc(?:&|$)/)
    await sort.selectOption('hierarchy')
    await expect(page).toHaveURL(/(?:\?|&)sort=hierarchy(?:&|$)/)

    const hierarchyItems = listItems(await responseJson(await request.get(
      '/api/v1/admin/special-equipment/categories',
      { params: { sort: 'hierarchy', page_size: '200' } },
    )))
    const hierarchyIds = hierarchyItems.map(item => item.id)
    expect(hierarchyIds.indexOf(fixture.categories.root.id)).toBeLessThan(
      hierarchyIds.indexOf(fixture.categories.siblingA.id),
    )
    expect(hierarchyIds.indexOf(fixture.categories.siblingA.id)).toBeLessThan(
      hierarchyIds.indexOf(fixture.categories.siblingB.id),
    )
    const updatedItems = listItems(await responseJson(await request.get(
      '/api/v1/admin/special-equipment/categories',
      { params: { sort: 'updated_desc', page_size: '200' } },
    )))
    const updatedTimestamps = updatedItems.map(item => Date.parse(stringField(item, 'updated_at')))
    expect(updatedTimestamps).toEqual([...updatedTimestamps].sort((left, right) => right - left))

    const leafDrawer = await openRegistryResource(page, 'categories', fixture.categories.leaf)
    await leafDrawer.locator('.se-category-picker-trigger').first().click()
    const parentPicker = page.getByRole('dialog', { name: 'Выберите родительские категории' })
    await parentPicker.getByPlaceholder('Найти категорию').fill(
      `${fixture.categories.root.name} ${fixture.categories.leaf.name}`,
    )
    const currentCategory = parentPicker.getByLabel(new RegExp(fixture.categories.leaf.name)).first()
    await expect(currentCategory).toBeVisible()
    await expect(currentCategory).toBeDisabled()
    await expect(parentPicker.getByText(
      `${fixture.categories.root.name} → ${fixture.categories.leaf.name}`,
      { exact: false },
    )).toBeVisible()
    await parentPicker.getByRole('button', { name: 'Закрыть выбор категорий' }).click()

    const categories = listItems(await responseJson(await request.get('/api/v1/special-equipment/categories')))
    const shared = categories.find(item => item.id === fixture.categories.shared.id)
    expect(shared?.parent_ids).toEqual(expect.arrayContaining([
      fixture.categories.dagParentA.id,
      fixture.categories.dagParentB.id,
    ]))
    expect(shared?.parent_ids).toHaveLength(2)

    const dagParent = await request.get(
      `/api/v1/admin/special-equipment/categories/${fixture.categories.dagParentA.id}`,
    )
    const cycle = await request.put(
      `/api/v1/admin/special-equipment/categories/${fixture.categories.dagParentA.id}/parents`,
      {
        headers: dagParent.headers().etag ? { 'If-Match': dagParent.headers().etag } : undefined,
        data: { parent_ids: [fixture.categories.shared.id] },
      },
    )
    expect([400, 409, 422, 428]).toContain(cycle.status())
  })

  test('AC-3 AC-10: registry и форма объявления наследуют контекст и очищают несовместимый каскад', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: ['AC-3', 'AC-10'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const kamaz = fixtureRecord(fixture.marks, 'kamaz')
    const excavator = fixtureRecord(fixture.marks, 'excavator')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const excavatorModel = fixtureRecord(fixture.models, 'excavator200')
    const whiteModification = fixtureRecord(fixture.modifications, 'baseWhite')
    const hoursModification = fixtureRecord(fixture.modifications, 'hours')

    await page.goto(appUrl(
      `${ADMIN_CATALOG_URL}?section=models&mark_id=${stringField(kamaz, 'id')}`,
    ), { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('combobox', { name: 'Фильтр по марке', exact: true })).toHaveValue(stringField(kamaz, 'name'))
    await expect(page.getByText(stringField(kamazModel, 'name'), { exact: true }).filter({ visible: true }).first()).toBeVisible()
    await expect(page.getByText(stringField(excavatorModel, 'name'), { exact: true }).filter({ visible: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Создать модель' }).click()
    let drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer.getByRole('combobox', { name: 'Марка модели', exact: true })).toHaveValue(stringField(kamaz, 'name'))

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=models`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать модель' }).click()
    drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer.getByRole('combobox', { name: 'Марка модели', exact: true })).toBeVisible()
    await expect(drawer.getByRole('combobox', { name: 'Марка модели', exact: true })).toHaveValue('')

    await page.goto(appUrl(
      `${ADMIN_CATALOG_URL}?section=modifications&mark_id=${stringField(kamaz, 'id')}&model_id=${stringField(kamazModel, 'id')}`,
    ), { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('combobox', { name: 'Фильтр по марке', exact: true })).toHaveValue(stringField(kamaz, 'name'))
    await expect(page.getByRole('combobox', { name: 'Фильтр по модели', exact: true })).toHaveValue(stringField(kamazModel, 'name'))
    await page.getByRole('button', { name: 'Создать модификацию' }).click()
    drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer.getByRole('combobox', { name: 'Марка модификации', exact: true })).toHaveValue(stringField(kamaz, 'name'))
    await expect(drawer.getByRole('combobox', { name: 'Модель модификации', exact: true })).toHaveValue(stringField(kamazModel, 'name'))

    await page.goto(appUrl(
      `${ADMIN_CATALOG_URL}?section=modifications&mark_id=${stringField(kamaz, 'id')}&model_id=${stringField(kamazModel, 'id')}`,
    ), { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('button', { name: 'Создать модификацию' })).toBeEnabled()
    await page.getByRole('button', { name: 'Очистить поле «Фильтр по марке»' }).click()
    await expect(page.getByRole('combobox', { name: 'Фильтр по марке', exact: true })).toHaveValue('')
    await expect(page).not.toHaveURL(/(?:\?|&)mark_id=/)
    await expect(page).not.toHaveURL(/(?:\?|&)model_id=/)
    await selectSearchableOption(page, 'Фильтр по марке', excavator)
    await expect(page).toHaveURL(new RegExp(`mark_id=${stringField(excavator, 'id')}`))
    await expect(page).not.toHaveURL(/(?:\?|&)model_id=/)
    await expect(page.getByRole('combobox', { name: 'Фильтр по модели', exact: true })).toHaveValue('')

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать объявление' }).click()
    drawer = page.locator('.se-drawer[role="dialog"]')
    const mark = drawer.getByRole('combobox', { name: 'Марка объявления', exact: true })
    const model = drawer.getByRole('combobox', { name: 'Модель объявления', exact: true })
    const modification = drawer.getByRole('combobox', { name: 'Модификация объявления', exact: true })
    await expect(model).toBeDisabled()
    await expect(modification).toBeDisabled()

    await selectSearchableOption(drawer, 'Марка объявления', kamaz)
    await expect(model).toBeEnabled()
    await selectSearchableOption(drawer, 'Модель объявления', kamazModel)
    await expect(modification).toBeEnabled()
    await selectSearchableOption(drawer, 'Модификация объявления', whiteModification)
    const inheritedCategories = drawer.getByRole('button', { name: /Выбрано категорий: \d+/ })
    await expect(inheritedCategories).toBeVisible()
    await inheritedCategories.click()
    const categoryPicker = page.getByRole('dialog', { name: 'Категории объявления' })
    await expect(categoryPicker.getByRole('checkbox', {
      name: new RegExp(fixture.categories.leaf.name),
    }).first()).toBeChecked()
    await categoryPicker.getByRole('button', { name: 'Готово' }).click()

    await selectSearchableOption(drawer, 'Марка объявления', excavator)
    await expect(model).toHaveValue('')
    await expect(modification).toHaveValue('')
    await expect(modification).toBeDisabled()
    await expect(drawer.getByRole('button', { name: 'Категории не выбраны' })).toBeVisible()
    await selectSearchableOption(drawer, 'Модель объявления', excavatorModel)
    await selectSearchableOption(drawer, 'Модификация объявления', hoursModification)
    await expect(drawer.getByRole('button', { name: new RegExp(fixture.categories.siblingB.name) })).toBeVisible()
  })

  test('AC-4: legacy-модификация без default category раскрывает разрешённые категории объявления', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-4', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const kamaz = fixtureRecord(fixture.marks, 'kamaz')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const noCategoryModification = fixtureRecord(fixture.modifications, 'noCategory')

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products`), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать объявление' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await selectSearchableOption(drawer, 'Марка объявления', kamaz)
    await selectSearchableOption(drawer, 'Модель объявления', kamazModel)
    await selectSearchableOption(drawer, 'Модификация объявления', noCategoryModification)
    await expect(drawer.getByRole('button', { name: 'Категории не выбраны' })).toBeVisible()

    await drawer.getByRole('button', { name: 'Категории не выбраны' }).click()
    const picker = page.getByRole('dialog', { name: 'Категории объявления' })
    await picker.getByPlaceholder('Найти категорию').fill(fixture.categories.leaf.name)
    const leaf = picker.getByLabel(fixture.categories.leaf.name, { exact: false }).first()
    await expect(leaf).toBeEnabled()
    await leaf.check()
    await picker.getByRole('button', { name: 'Готово' }).click()
    await expect(drawer.getByRole('button', { name: new RegExp(fixture.categories.leaf.name) })).toBeVisible()
  })

  test('AC-5: эффективные характеристики DAG уникальны, очистка заполненного значения требует подтверждения', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-5', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const kamaz = fixtureRecord(fixture.marks, 'kamaz')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const capacity = fixtureRecord(fixture.attributes, 'capacity')
    const color = fixtureRecord(fixture.attributes, 'color')
    const description = fixtureRecord(fixture.attributes, 'description')

    const effective = await responseJson(await request.get(PUBLIC_FACETS_URL, {
      params: { category_path: fixture.categories.leaf.path.join('/') },
    }))
    const groups = Array.isArray(effective.attribute_groups)
      ? effective.attribute_groups as JsonObject[]
      : []
    const effectiveIds = groups.flatMap((group) => {
      const attributes = Array.isArray(group.attributes) ? group.attributes as JsonObject[] : []
      return attributes.map(item => item.id)
    })
    expect(effectiveIds.length).toBeGreaterThan(0)
    expect(new Set(effectiveIds).size).toBe(effectiveIds.length)
    expect(effectiveIds).toEqual(expect.arrayContaining([
      stringField(capacity, 'id'),
      stringField(color, 'id'),
      stringField(description, 'id'),
    ]))

    await page.goto(appUrl(
      `${ADMIN_CATALOG_URL}?section=modifications&mark_id=${stringField(kamaz, 'id')}&model_id=${stringField(kamazModel, 'id')}`,
    ), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать модификацию' }).click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer.getByRole('combobox', { name: 'Марка модификации', exact: true })).toHaveValue(stringField(kamaz, 'name'))
    await expect(drawer.getByRole('combobox', { name: 'Модель модификации', exact: true })).toHaveValue(stringField(kamazModel, 'name'))

    await drawer.getByRole('button', { name: 'Категории не выбраны' }).click()
    let picker = page.getByRole('dialog', { name: 'Категории модификации' })
    await picker.getByPlaceholder('Найти категорию').fill(fixture.categories.leaf.name)
    await picker.getByLabel(fixture.categories.leaf.name, { exact: false }).first().check()
    await picker.getByRole('button', { name: 'Готово' }).click()

    const modificationValues = drawer.getByRole('group', { name: 'Характеристики модификации' })
    for (const attribute of [capacity, color, description]) {
      await expect(modificationValues.getByText(stringField(attribute, 'name'), { exact: false })).toHaveCount(1)
    }
    const descriptionInput = modificationValues.locator('label.se-field')
      .filter({ hasText: stringField(description, 'name') })
      .locator('input')
    await descriptionInput.fill('Временное назначение для проверки очистки')

    await drawer.getByRole('button', { name: fixture.categories.leaf.name, exact: true }).click()
    picker = page.getByRole('dialog', { name: 'Категории модификации' })
    await picker.getByRole('button', { name: 'Очистить' }).click()
    await picker.getByPlaceholder('Найти категорию').fill(fixture.categories.attachmentChild.name)
    await picker.getByLabel(fixture.categories.attachmentChild.name, { exact: false }).first().check()
    await picker.getByRole('button', { name: 'Готово' }).click()

    let confirmation = page.getByRole('dialog', { name: 'Очистить несовместимые характеристики?' })
    await expect(confirmation).toContainText(stringField(description, 'name'))
    const cancelConfirmation = confirmation.getByRole('button', { name: 'Отмена', exact: true })
    const confirmCategoryChange = confirmation.getByRole('button', { name: 'Очистить и продолжить', exact: true })
    await expect(cancelConfirmation).toBeFocused()
    await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden')
    expect(await drawer.evaluate(element => element.closest('.se-overlay-root')?.hasAttribute('inert'))).toBe(true)
    await page.keyboard.press('Shift+Tab')
    await expect(confirmCategoryChange).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(cancelConfirmation).toBeFocused()
    await cancelConfirmation.click()
    await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden')
    expect(await drawer.evaluate(element => element.closest('.se-overlay-root')?.hasAttribute('inert'))).toBe(false)
    await expect.poll(() => drawer.evaluate(element => {
      const active = document.activeElement
      return active instanceof HTMLElement
        && element.contains(active)
        && active.getClientRects().length > 0
    })).toBe(true)
    await expect(descriptionInput).toHaveValue('Временное назначение для проверки очистки')
    await expect(drawer.getByRole('button', { name: fixture.categories.leaf.name, exact: true })).toBeVisible()

    await drawer.getByRole('button', { name: fixture.categories.leaf.name, exact: true }).click()
    picker = page.getByRole('dialog', { name: 'Категории модификации' })
    await picker.getByRole('button', { name: 'Очистить' }).click()
    await picker.getByPlaceholder('Найти категорию').fill(fixture.categories.attachmentChild.name)
    await picker.getByLabel(fixture.categories.attachmentChild.name, { exact: false }).first().check()
    await picker.getByRole('button', { name: 'Готово' }).click()
    confirmation = page.getByRole('dialog', { name: 'Очистить несовместимые характеристики?' })
    await confirmation.getByRole('button', { name: 'Очистить и продолжить', exact: true }).click()
    await expect(descriptionInput).toHaveCount(0)

    await drawer.getByRole('button', { name: fixture.categories.attachmentChild.name, exact: true }).click()
    picker = page.getByRole('dialog', { name: 'Категории модификации' })
    await picker.getByRole('button', { name: 'Очистить' }).click()
    await picker.getByPlaceholder('Найти категорию').fill(fixture.categories.leaf.name)
    await picker.getByLabel(fixture.categories.leaf.name, { exact: false }).first().check()
    await picker.getByRole('button', { name: 'Готово' }).click()
    const restoredDescription = modificationValues.locator('label.se-field')
      .filter({ hasText: stringField(description, 'name') })
      .locator('input')
    await expect(restoredDescription).toHaveValue('')
  })

  test('AC-6 AC-7 AC-8: bulk assign/unassign, category apply, override и открытый multiselect сохраняют post-state', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: ['AC-6', 'AC-7', 'AC-8'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const technical = fixtureRecord(fixture.attribute_groups, 'technical')
    const appearance = fixtureRecord(fixture.attribute_groups, 'appearance')
    const capacity = fixtureRecord(fixture.attributes, 'capacity')
    const description = fixtureRecord(fixture.attributes, 'description')
    const stabilizers = fixtureRecord(fixture.attributes, 'stabilizers')
    const free = fixtureRecord(fixture.attributes, 'free')

    let drawer = await openRegistryResource(page, 'attribute-groups', technical)
    const groupList = drawer.locator('.se-checkbox-picker__list')
    const descriptionCheckbox = groupList.getByLabel(stringField(description, 'name'), { exact: false })
    const freeCheckbox = groupList.getByLabel(stringField(free, 'name'), { exact: false })
    await expect(descriptionCheckbox).not.toBeChecked()
    await expect(freeCheckbox).toBeChecked()
    await descriptionCheckbox.check()
    await freeCheckbox.uncheck()
    await drawer.getByRole('button', { name: 'Сохранить' }).click()
    await expect(drawer).toBeHidden()

    const assignedDescription = await adminResource(
      request,
      'attributes',
      stringField(description, 'id'),
    )
    const unassignedFree = await adminResource(request, 'attributes', stringField(free, 'id'))
    expect(assignedDescription.attribute_group_id).toBe(stringField(technical, 'id'))
    expect(unassignedFree.attribute_group_id).toBeNull()

    drawer = await openRegistryResource(page, 'categories', fixture.categories.siblingA)
    const categoryPicker = drawer.locator('.se-category-attribute-picker')
    await categoryPicker.getByLabel('Группа характеристик').selectOption(stringField(technical, 'id'))
    const optionList = categoryPicker.locator('[aria-label="Характеристики выбранной группы"]')
    const capacityCheckbox = optionList.getByLabel(stringField(capacity, 'name'), { exact: false })
    const stabilizersCheckbox = optionList.getByLabel(stringField(stabilizers, 'name'), { exact: false })
    await capacityCheckbox.check()
    await expect(optionList).toBeVisible()
    await expect(capacityCheckbox).toBeChecked()
    await stabilizersCheckbox.check()
    await expect(optionList).toBeVisible()
    await expect(stabilizersCheckbox).toBeChecked()
    await categoryPicker.getByRole('button', { name: 'Применить (2)' }).click()

    const bindings = drawer.locator('.se-attribute-binding')
    await expect(bindings).toHaveCount(2)
    for (const label of ['Обязательно', 'В фильтре', 'На карточке', 'Порядок']) {
      await expect(bindings.first().getByText(label, { exact: false })).toBeVisible()
    }
    await categoryPicker.getByLabel('Группа характеристик').selectOption(stringField(technical, 'id'))
    await expect(categoryPicker.getByLabel(stringField(capacity, 'name'), { exact: false })).toHaveCount(0)
    await expect(categoryPicker.getByLabel(stringField(stabilizers, 'name'), { exact: false })).toHaveCount(0)

    const capacityBinding = bindings.filter({ hasText: stringField(capacity, 'name') })
    await selectSearchableOption(
      capacityBinding,
      `Группа характеристики «${stringField(capacity, 'name')}»`,
      appearance,
    )
    await drawer.getByRole('button', { name: 'Сохранить' }).click()
    await expect(drawer).toBeHidden()

    const savedCategory = await adminResource(request, 'categories', fixture.categories.siblingA.id)
    const links = Array.isArray(savedCategory.attribute_links)
      ? savedCategory.attribute_links as JsonObject[]
      : []
    expect(links).toHaveLength(2)
    expect(new Set(links.map(link => link.attribute_id)).size).toBe(2)
    const capacityLink = links.find(link => link.attribute_id === stringField(capacity, 'id'))
    expect(capacityLink?.group_id).toBe(stringField(appearance, 'id'))
    for (const key of ['is_required', 'is_filterable', 'is_visible', 'sort_order']) {
      expect(capacityLink).toHaveProperty(key)
    }
    const capacityResource = await adminResource(request, 'attributes', stringField(capacity, 'id'))
    expect(capacityResource.attribute_group_id).toBe(stringField(technical, 'id'))
  })

  test('AC-9: условный PATCH не падает с 500, зависимое удаление возвращает конфликт', async ({ request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-9', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const attribute = fixture.attributes.capacity as JsonObject | undefined
    const freeAttribute = fixture.attributes.free as JsonObject | undefined
    expect(typeof attribute?.id).toBe('string')
    expect(typeof freeAttribute?.id).toBe('string')

    const resource = await request.get(`/api/v1/admin/special-equipment/attributes/${attribute!.id as string}`)
    expect(resource.ok()).toBeTruthy()
    const etag = resource.headers().etag
    expect(etag).toBeTruthy()
    const current = await resource.json() as JsonObject
    const patch = await request.patch(
      `/api/v1/admin/special-equipment/attributes/${attribute!.id as string}`,
      {
        headers: { 'If-Match': etag! },
        data: { name: current.name },
      },
    )
    expect(patch.status()).not.toBe(500)
    expect([200, 409, 422]).toContain(patch.status())

    const usedDeletion = await request.delete(
      `/api/v1/admin/special-equipment/attributes/${attribute!.id as string}`,
      { headers: { 'If-Match': patch.headers().etag ?? etag! } },
    )
    expect(usedDeletion.status()).toBe(409)

    const freeResource = await request.get(
      `/api/v1/admin/special-equipment/attributes/${freeAttribute!.id as string}`,
    )
    expect(freeResource.ok()).toBeTruthy()
    const freeDeletion = await request.delete(
      `/api/v1/admin/special-equipment/attributes/${freeAttribute!.id as string}`,
      { headers: { 'If-Match': freeResource.headers().etag! } },
    )
    expect(freeDeletion.status()).toBe(204)
  })

  test('AC-11 AC-12: состояние, владельцы, VIN и «Под заказ» работают совместно', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: ['AC-11', 'AC-12'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const usedResponse = await request.get(
      `/api/v1/admin/special-equipment/products/${fixture.products.usedMileage.id}`,
    )
    const used = await responseJson(usedResponse)
    expect(used.condition).toBe('used')
    expect(used.owners_count).toBe(0)

    const invalidOwners = await request.patch(
      `/api/v1/admin/special-equipment/products/${fixture.products.usedMileage.id}`,
      {
        headers: { 'If-Match': usedResponse.headers().etag! },
        data: { condition: 'used', owners_count: null },
      },
    )
    expect(invalidOwners.status()).toBe(422)

    const invalidVin = await request.patch(
      `/api/v1/admin/special-equipment/products/${fixture.products.usedMileage.id}`,
      {
        headers: { 'If-Match': usedResponse.headers().etag! },
        data: { no_vin: false, vin: 'X'.repeat(18) },
      },
    )
    expect(invalidVin.status()).toBe(422)

    const withoutVin = await responseJson(await request.get(
      `/api/v1/admin/special-equipment/products/${fixture.products.noVin.id}`,
    ))
    expect(withoutVin.no_vin).toBe(true)
    expect(withoutVin.vin).toBeNull()

    const onOrder = await responseJson(await request.get(
      `/api/v1/admin/special-equipment/products/${fixture.products.onOrder.id}`,
    ))
    expect(onOrder.sale_status).toBe('on_order')

    await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=products&q=${encodeURIComponent(String(fixture.products.usedMileage.code))}`), { waitUntil: 'domcontentloaded' })
    await page.locator('.se-entity-name:visible').first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('С пробегом', { exact: false })).toBeVisible()
    const owners = dialog.getByLabel(/Количество владельцев/i)
    await expect(owners).toHaveValue('0')
    const mileageField = dialog.locator('label.se-field:has(input[aria-label="Пробег, км"])')
    await expect(mileageField).toBeVisible()
    await expect(mileageField.locator('+ label.se-field')).toContainText('Количество владельцев')

    const save = dialog.getByRole('button', { name: 'Сохранить', exact: true })
    await owners.fill('')
    await expect(save).toBeDisabled()
    await owners.fill('1')
    await dialog.getByLabel('Новое', { exact: true }).check()
    await expect(owners).toHaveCount(0)
    await dialog.getByLabel('С пробегом', { exact: true }).check()
    await expect(dialog.getByLabel(/Количество владельцев/i)).toHaveValue('')
    await expect(save).toBeDisabled()

    const vin = dialog.getByLabel(/^VIN/)
    await expect(vin).toHaveAttribute('maxlength', '17')
    const noVin = dialog.getByRole('checkbox', { name: /Нет VIN/ })
    await noVin.check()
    await expect(vin).toBeDisabled()
    await expect(vin).toHaveValue('')
    await expect(dialog.getByText('Заводской номер не затрагивается.', { exact: false })).toBeVisible()
    const saleStatus = dialog.locator('label.se-field')
      .filter({ hasText: /^Статус продажи/ })
      .getByRole('combobox')
    await expect(saleStatus).toContainText('Под заказ')
  })

  test('удаление доступно только из карточки каталога', async ({ page }) => {
    const fixture = getE2EFixtureManifest()
    const category = fixture.categories.emptyRoot

    for (const section of ['colors', 'categories']) {
      await page.goto(appUrl(`${ADMIN_CATALOG_URL}?section=${section}`), { waitUntil: 'domcontentloaded' })
      await expect(page.locator('tbody tr')).not.toHaveCount(0)
      await expect(page.locator('tbody').getByRole('button', { name: 'Удалить', exact: true })).toHaveCount(0)
    }

    await page.goto(appUrl(
      `${ADMIN_CATALOG_URL}?section=categories&q=${encodeURIComponent(category.name)}`,
    ), { waitUntil: 'domcontentloaded' })
    const categoryTab = page.getByRole('button', { name: /^Категории/ })
    const countBefore = Number((await categoryTab.textContent())?.match(/\d+/)?.[0])
    expect(countBefore).toBeGreaterThan(0)

    const categoryRow = page.locator('tbody tr').filter({
      has: page.getByRole('button', { name: category.name, exact: true }),
    })
    await expect(categoryRow).toHaveCount(1)
    await categoryRow.getByRole('button', { name: 'Открыть', exact: true }).click()

    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()
    await drawer.getByRole('button', { name: 'Удалить', exact: true }).click()

    const deleteDialog = page.getByRole('dialog').filter({
      has: page.getByRole('button', { name: 'Удалить навсегда', exact: true }),
    })
    await expect(deleteDialog).toBeVisible()
    await deleteDialog.getByPlaceholder('УДАЛИТЬ').fill('УДАЛИТЬ')
    await deleteDialog.getByRole('button', { name: 'Удалить навсегда', exact: true }).click()

    await expect(page.getByText(/Удалено записей: \d+/, { exact: true })).toBeVisible()
    await expect(categoryRow).toHaveCount(0)
    await expect.poll(async () => Number((await categoryTab.textContent())?.match(/\d+/)?.[0])).toBe(countBefore - 1)
  })
})

test.describe('Bitrix 21940 — публичный каталог', () => {
  test('AC-14: model/modification/availability и text/number/select multiselect одинаково применяются к products и facets', async ({ page, request }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-14', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const path = fixture.categories.leaf.path.join('/')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const whiteModification = fixtureRecord(fixture.modifications, 'baseWhite')
    const capacity = fixtureRecord(fixture.attributes, 'capacity')
    const color = fixtureRecord(fixture.attributes, 'color')
    const description = fixtureRecord(fixture.attributes, 'description')

    const baseFacets = await responseJson(await request.get(PUBLIC_FACETS_URL, {
      params: { category_path: path },
    }))
    const facetGroups = Array.isArray(baseFacets.attribute_groups)
      ? baseFacets.attribute_groups as JsonObject[]
      : []
    const facetAttributes = facetGroups.flatMap((group) => {
      return Array.isArray(group.attributes) ? group.attributes as JsonObject[] : []
    })
    const capacityFacet = facetAttributes.find(item => item.id === stringField(capacity, 'id'))
    const colorFacet = facetAttributes.find(item => item.id === stringField(color, 'id'))
    const descriptionFacet = facetAttributes.find(item => item.id === stringField(description, 'id'))
    expect(capacityFacet).toMatchObject({ data_type: 'number', filter_kind: 'range' })
    expect(colorFacet).toMatchObject({ data_type: 'select', filter_kind: 'exact' })
    expect(descriptionFacet).toMatchObject({ data_type: 'text', filter_kind: 'search' })
    const colorOptions = Array.isArray(colorFacet?.options) ? colorFacet.options as JsonObject[] : []
    expect(colorOptions).toHaveLength(2)
    const colorValues = colorOptions.map(option => stringField(option, 'value'))
    const whiteOption = fixtureRecord(fixture.options, 'white')
    const whiteValue = stringField(whiteOption, 'code')
    expect(colorValues).toContain(whiteValue)

    const assertProductsAndFacets = async (
      query: Record<string, string | string[]>,
      assertItems: (items: JsonObject[]) => void,
      categoryPath = path,
      expectFacetReduction = true,
    ): Promise<void> => {
      const params = new URLSearchParams({ category_path: categoryPath })
      for (const [key, value] of Object.entries(query)) {
        if (Array.isArray(value)) {
          for (const item of value) params.append(key, item)
        } else {
          params.set(key, value)
        }
      }
      const productParams = new URLSearchParams(params)
      productParams.set('sort', 'published_desc')
      productParams.set('page', '1')
      productParams.set('page_size', '100')
      const [productsPayload, facetsPayload] = await Promise.all([
        responseJson(await request.get(`${PUBLIC_PRODUCTS_URL}?${productParams.toString()}`)),
        responseJson(await request.get(`${PUBLIC_FACETS_URL}?${params.toString()}`)),
      ])
      const items = listItems(productsPayload)
      assertItems(items)
      const physicalCount = (item: JsonObject): number => {
        expect(typeof item.available_count).toBe('number')
        return item.available_count as number
      }
      if (query.availability === undefined) {
        const availability = facetsPayload.availability as JsonObject
        expect(typeof availability.available).toBe('number')
        expect(typeof availability.on_order).toBe('number')
        const facetTotal = (availability.available as number) + (availability.on_order as number)
        const groupedCapacity = items.reduce((total, item) => total + physicalCount(item), 0)
        expect(facetTotal).toBeGreaterThanOrEqual(groupedCapacity)
        const unfilteredFacets = categoryPath === path
          ? baseFacets
          : await responseJson(await request.get(PUBLIC_FACETS_URL, {
              params: { category_path: categoryPath },
            }))
        const unfilteredAvailability = unfilteredFacets.availability as JsonObject
        const unfilteredTotal = (unfilteredAvailability.available as number)
          + (unfilteredAvailability.on_order as number)
        expect(facetTotal).toBeLessThanOrEqual(unfilteredTotal)
        if (items.length === 0) expect(facetTotal).toBe(0)
        else if (expectFacetReduction) expect(facetTotal).toBeLessThan(unfilteredTotal)
      } else {
        const expectedModels = new Map<string, number>()
        for (const item of items) {
          const modification = item.modification as JsonObject
          const model = modification.model as JsonObject
          const modelId = stringField(model, 'id')
          expectedModels.set(modelId, (expectedModels.get(modelId) ?? 0) + physicalCount(item))
        }
        expect(Array.isArray(facetsPayload.models)).toBeTruthy()
        const actualModels = new Map(
          (facetsPayload.models as JsonObject[]).map(model => [
            stringField(model, 'id'),
            model.count as number,
          ]),
        )
        expect(actualModels).toEqual(expectedModels)
      }
      expect(Array.isArray(facetsPayload.modifications)).toBeTruthy()
    }

    const rootPath = fixture.categories.root.path.join('/')
    await assertProductsAndFacets({ model_id: stringField(kamazModel, 'id') }, (items) => {
      expect(items.length).toBeGreaterThan(0)
      for (const item of items) {
        const modification = item.modification as JsonObject
        const model = modification.model as JsonObject
        expect(model.id).toBe(stringField(kamazModel, 'id'))
      }
    }, rootPath)
    await assertProductsAndFacets({ modification_id: stringField(whiteModification, 'id') }, (items) => {
      expect(items.length).toBeGreaterThan(0)
      for (const item of items) {
        expect((item.modification as JsonObject).id).toBe(stringField(whiteModification, 'id'))
      }
    }, rootPath)
    await assertProductsAndFacets({ availability: 'on_order' }, (items) => {
      expect(items.length).toBeGreaterThan(0)
      for (const item of items) expect(item.sale_status).toBe('on_order')
    }, rootPath)
    await assertProductsAndFacets({
      attribute: `${stringField(capacity, 'id')}:gte:1001`,
    }, items => expect(items).toHaveLength(0))
    await assertProductsAndFacets({
      attribute: colorValues.map(value => `${stringField(color, 'id')}:eq:${value}`),
    }, (items) => {
      const modificationIds = new Set(items.map(item => (item.modification as JsonObject).id))
      expect(modificationIds).toEqual(new Set([
        stringField(fixtureRecord(fixture.modifications, 'baseWhite'), 'id'),
        stringField(fixtureRecord(fixture.modifications, 'baseWhiteTwin'), 'id'),
        stringField(fixtureRecord(fixture.modifications, 'baseBlack'), 'id'),
      ]))
    }, path, false)
    await assertProductsAndFacets({
      attribute: `${stringField(color, 'id')}:eq:${whiteValue}`,
    }, (items) => {
      const modificationIds = new Set(items.map(item => (item.modification as JsonObject).id))
      expect(modificationIds).toEqual(new Set([
        stringField(fixtureRecord(fixture.modifications, 'baseWhite'), 'id'),
        stringField(fixtureRecord(fixture.modifications, 'baseWhiteTwin'), 'id'),
      ]))
    })
    const missingText = 'отсутствующее-e2e-назначение'
    await assertProductsAndFacets({
      attribute: `${stringField(description, 'id')}:search:${missingText}`,
    }, items => expect(items).toHaveLength(0))
    const existingText = `${fixture.prefix} магистральное`
    await assertProductsAndFacets({
      attribute: `${stringField(description, 'id')}:search:${existingText}`,
    }, (items) => {
      expect(items.length).toBeGreaterThan(0)
      for (const item of items) {
        expect((item.modification as JsonObject).model).toBeTruthy()
      }
    }, path, false)

    const query = new URLSearchParams()
    query.append('mark_id', stringField(fixtureRecord(fixture.marks, 'kamaz'), 'id'))
    query.append('model_id', stringField(kamazModel, 'id'))
    query.append('modification_id', stringField(whiteModification, 'id'))
    query.append('availability', 'available')
    query.append('attribute', `${stringField(capacity, 'id')}:gte:1000`)
    query.append('attribute', `${stringField(color, 'id')}:eq:${whiteValue}`)
    query.append('attribute', `${stringField(description, 'id')}:search:${existingText}`)
    await page.goto(appUrl(`/special-equipment/categories/${path}?${query.toString()}`), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const filterScope = await openPublicFilters(page)
    const expectFacetDialogSelection = async (label: string, optionName: string): Promise<void> => {
      const trigger = filterScope.getByRole('button', {
        name: new RegExp(`^${label}: выбрано \\d+$`),
      })
      await expect(trigger).toBeVisible()
      await trigger.click()
      const facetDialog = page.getByRole('dialog', { name: label, exact: true })
      await expect(facetDialog).toBeVisible()
      await facetDialog.getByPlaceholder(`Найти: ${label.toLocaleLowerCase('ru-RU')}`).fill(optionName)
      await expect(facetDialog.getByRole('checkbox', {
        name: new RegExp(`^${escapeRegExp(optionName)}(?:\\s+\\d+)?$`),
      })).toBeChecked()
      await facetDialog.getByRole('button', { name: 'Отмена', exact: true }).click()
      await expect(facetDialog).toBeHidden()
    }
    await expectFacetDialogSelection('Модель', stringField(kamazModel, 'name'))
    await expectFacetDialogSelection('Модификация', stringField(whiteModification, 'name'))
    await expect(filterScope.getByRole('group', { name: 'Наличие' }).getByLabel('В наличии', { exact: false })).toBeChecked()
    await expectFilterOptionsContained(filterScope)
    await expectFilterOptionsContained(filterScope.getByRole('group', { name: 'Наличие', exact: true }))
    await expectFilterOptionsContained(filterScope.getByRole('group', { name: 'Состояние', exact: true }))
    const horizontalOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    )
    expect(horizontalOverflow).toBe(false)
    await expect(filterScope.getByLabel(`Минимум: ${stringField(capacity, 'name')}`)).toHaveValue('1000')
    await expect(filterScope.getByPlaceholder(`Найти: ${stringField(description, 'name').toLocaleLowerCase('ru-RU')}`)).toHaveValue(existingText)
    await expect(filterScope.getByLabel(stringField(whiteOption, 'name'), { exact: false })).toBeChecked()
    await page.setViewportSize({ width: 768, height: 1000 })
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    await expectFilterOptionsContained(filterScope)
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.evaluate(() => { document.documentElement.style.fontSize = '' })

    const multiColorQuery = new URLSearchParams()
    for (const value of colorValues) {
      multiColorQuery.append('attribute', `${stringField(color, 'id')}:eq:${value}`)
    }
    await page.goto(appUrl(`/special-equipment/categories/${path}?${multiColorQuery.toString()}`), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const multiColorFilterScope = await openPublicFilters(page)
    for (const option of colorOptions) {
      await expect(multiColorFilterScope.getByLabel(stringField(option, 'label'), { exact: false })).toBeChecked()
    }
    const availabilityGroup = multiColorFilterScope.getByRole('group', { name: 'Наличие', exact: true })
    const availableCheckbox = availabilityGroup.getByLabel('В наличии', { exact: false })
    const onOrderCheckbox = availabilityGroup.getByLabel('Под заказ', { exact: false })
    await expect(availableCheckbox).toBeChecked()
    await expect(onOrderCheckbox).toBeChecked()
    const onOrderResponse = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PUBLIC_PRODUCTS_URL
        && url.searchParams.getAll('availability').includes('on_order')
        && !url.searchParams.getAll('availability').includes('available')
    })
    await availableCheckbox.click()
    expect((await onOrderResponse).ok()).toBeTruthy()
    await expect(availableCheckbox).not.toBeChecked()
    await expect(onOrderCheckbox).toBeChecked()
    await expect(page).toHaveURL(/(?:\?|&)availability=on_order(?:&|$)/)
    const allAvailabilityResponse = page.waitForResponse(response => {
      const values = new URL(response.url()).searchParams.getAll('availability')
      return new URL(response.url()).pathname === PUBLIC_PRODUCTS_URL
        && values.includes('available')
        && values.includes('on_order')
    })
    await onOrderCheckbox.click()
    expect((await allAvailabilityResponse).ok()).toBeTruthy()
    await expect(availableCheckbox).toBeChecked()
    await expect(onOrderCheckbox).toBeChecked()
  })

  test('AC-14: публичный каскад не открывает потомков до выбора родителя и очищает их при смене марки', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-14', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const kamaz = fixtureRecord(fixture.marks, 'kamaz')
    const kamazModel = fixtureRecord(fixture.models, 'kamaz1000')
    const excavatorModel = fixtureRecord(fixture.models, 'excavator200')
    const whiteModification = fixtureRecord(fixture.modifications, 'baseWhite')

    await page.goto(appUrl(`/special-equipment/categories/${fixture.categories.leaf.path.join('/')}`), {
      waitUntil: 'domcontentloaded',
    })
    await waitForNuxtHydration(page)
    const filters = await openPublicFilters(page)
    const trigger = (label: string) => filters.getByRole('button', {
      name: new RegExp(`^(?:${label}:|Выбрать: ${label.toLocaleLowerCase('ru-RU')})`),
    })
    const applySelection = async (label: string, option: JsonObject): Promise<void> => {
      await trigger(label).click()
      const dialog = page.getByRole('dialog', { name: label, exact: true })
      const optionName = stringField(option, 'name')
      await dialog.getByPlaceholder(`Найти: ${label.toLocaleLowerCase('ru-RU')}`).fill(optionName)
      await dialog.getByRole('checkbox', {
        name: new RegExp(`^${escapeRegExp(optionName)}(?:\\s+\\d+)?$`),
      }).check()
      await dialog.getByRole('button', { name: 'Применить', exact: true }).click()
      await expect(dialog).toBeHidden()
    }

    await expect(trigger('Модель')).toBeDisabled()
    await expect(trigger('Модификация')).toBeDisabled()
    await applySelection('Марка', kamaz)
    await expect(trigger('Модель')).toBeEnabled()
    await expect(trigger('Модификация')).toBeDisabled()

    await trigger('Модель').click()
    const models = page.getByRole('dialog', { name: 'Модель', exact: true })
    await expect(models.getByRole('checkbox', {
      name: new RegExp(`^${escapeRegExp(stringField(kamazModel, 'name'))}(?:\\s+\\d+)?$`),
    })).toBeVisible()
    await expect(models.getByRole('checkbox', {
      name: new RegExp(`^${escapeRegExp(stringField(excavatorModel, 'name'))}(?:\\s+\\d+)?$`),
    })).toHaveCount(0)
    await models.getByRole('button', { name: 'Отмена', exact: true }).click()

    await applySelection('Модель', kamazModel)
    await expect(trigger('Модификация')).toBeEnabled()
    await applySelection('Модификация', whiteModification)

    await trigger('Марка').click()
    const marks = page.getByRole('dialog', { name: 'Марка', exact: true })
    await marks.getByRole('checkbox', {
      name: new RegExp(`^${escapeRegExp(stringField(kamaz, 'name'))}(?:\\s+\\d+)?$`),
    }).uncheck()
    await marks.getByRole('button', { name: 'Применить', exact: true }).click()
    await expect(marks).toBeHidden()
    await expect(trigger('Модель')).toHaveAccessibleName('Выбрать: модель')
    await expect(trigger('Модификация')).toHaveAccessibleName('Выбрать: модификация')
    await expect(trigger('Модификация')).toBeDisabled()
  })

  test('AC-15: поиск, фильтр, все сортировки и page 2 меняют query/results без document reload', async ({ page, request }, testInfo) => {
    test.setTimeout(90_000)
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-15', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const categories = listItems(await responseJson(await request.get('/api/v1/special-equipment/categories')))
    const count25 = categories.find(item => item.name === `${fixture.prefix} Счётчик 25`)
    expect(count25).toBeTruthy()
    const count25Path = stringField(count25!, 'slug')
    await page.goto(appUrl(`/special-equipment/categories/${count25Path}`), { waitUntil: 'domcontentloaded' })
    const navigationEntries = await page.evaluate(() => performance.getEntriesByType('navigation').length)
    const visibleSort = page.getByLabel('Сортировка').filter({ visible: true })
    const mileageSorts = [
      'published_asc',
      'published_desc',
      'price_asc',
      'price_desc',
      'name_asc',
      'mileage_asc',
      'mileage_desc',
    ] as const
    for (const sort of mileageSorts) {
      expect((await selectSortAndWaitForProducts(page, visibleSort, sort)).ok()).toBeTruthy()
      await expect(visibleSort).toHaveValue(sort)
      if (sort === 'published_desc') await expect(page).not.toHaveURL(/(?:\?|&)sort=/)
      else await expect(page).toHaveURL(new RegExp(`(?:\\?|&)sort=${sort}(?:&|$)`))
      expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(navigationEntries)
    }

    const pageTwoResponse = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PUBLIC_PRODUCTS_URL && url.searchParams.get('page') === '2'
    })
    await page.getByRole('button', { name: 'Страница 2' }).click()
    const pageTwoResult = await pageTwoResponse
    expect(pageTwoResult.ok()).toBeTruthy()
    const pageTwoPayload = await pageTwoResult.json() as JsonObject
    expect(listItems(pageTwoPayload).length).toBeGreaterThan(0)
    await expect(page).toHaveURL(/(?:\?|&)page=2(?:&|$)/)
    await expect(page.getByRole('button', { name: 'Страница 2' })).toHaveAttribute('aria-current', 'page')
    expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(navigationEntries)

    const searchResponse = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PUBLIC_PRODUCTS_URL && url.searchParams.get('search') === fixture.prefix
    })
    const search = page.getByPlaceholder('Название, марка, модель или код')
    await search.fill(fixture.prefix)
    await search.press('Enter')
    expect((await searchResponse).ok()).toBeTruthy()
    await expect(page).not.toHaveURL(/(?:\?|&)page=2(?:&|$)/)
    await expect(page.getByRole('button', { name: `Удалить фильтр Поиск: ${fixture.prefix}` })).toBeVisible()
    expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(navigationEntries)

    const filterScope = await openPublicFilters(page)
    const filterResponse = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PUBLIC_PRODUCTS_URL && url.searchParams.get('availability') === 'on_order'
    })
    const availabilityGroup = filterScope.getByRole('group', { name: 'Наличие' })
    await availabilityGroup.getByLabel('В наличии', { exact: false }).uncheck()
    expect((await filterResponse).ok()).toBeTruthy()
    await expect(availabilityGroup.getByLabel('Под заказ', { exact: false })).toBeChecked()
    await expect(page).toHaveURL(/(?:\?|&)availability=on_order(?:&|$)/)
    expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(navigationEntries)

    const hoursPath = fixture.categories.siblingB.path.join('/')
    await page.goto(appUrl(`/special-equipment/categories/${hoursPath}`), { waitUntil: 'domcontentloaded' })
    const hoursNavigationEntries = await page.evaluate(() => performance.getEntriesByType('navigation').length)
    const hoursSort = page.getByLabel('Сортировка').filter({ visible: true })
    for (const sort of ['engine_hours_asc', 'engine_hours_desc'] as const) {
      expect((await selectSortAndWaitForProducts(page, hoursSort, sort)).ok()).toBeTruthy()
      await expect(hoursSort).toHaveValue(sort)
      await expect(page).toHaveURL(new RegExp(`(?:\\?|&)sort=${sort}(?:&|$)`))
      expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(hoursNavigationEntries)
    }
  })

  test('AC-16 AC-17: страница ведёт к покупке через корзину и не показывает пустые значения', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: ['AC-16', 'AC-17'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const product = fixture.products.representative
    await page.goto(appUrl(`/special-equipment/categories/${fixture.categories.root.path.join('/')}`), { waitUntil: 'domcontentloaded' })
    const search = page.getByPlaceholder('Название, марка, модель или код')
    await search.fill(String(product.code))
    await search.press('Enter')
    await page.getByRole('link', { name: 'Подробнее' }).first().click()

    const detail = page.locator('[data-storefront-block="equipment.detail"]')
    await expect(detail.getByRole('button', { name: 'Добавить в корзину', exact: true })).toHaveCount(1)
    await expect(detail.getByRole('button', { name: 'Купить онлайн', exact: true })).toHaveCount(0)
    await expect(detail.getByRole('button', { name: 'Оформить в лизинг', exact: true })).toHaveCount(0)
    await expect(detail.getByText(/VIN/i)).toHaveCount(0)
    await expect(detail.getByText(/\.0{2,}\b/)).toHaveCount(0)
    await expect(detail.getByText(/^(?:None|null|undefined)$/i)).toHaveCount(0)
    expect(await detail.locator('dd').evaluateAll(nodes => nodes
      .map(node => node.textContent?.trim() ?? '')
      .filter(value => value.length === 0))).toEqual([])
  })

  test('AC-16: покупка из корзины продолжается после входа с сохранением гостевого выбора', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-16', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const product = fixture.products.nonEquivalent
    const client = fixtureRecord(fixture.auth, 'client')

    await page.goto(appUrl(`/special-equipment/products/${product.id}/${product.slug}`), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    await openCartFromProduct(page)
    const purchase = page.getByRole('button', { name: 'Купить', exact: true })
    await expect(purchase).toBeEnabled()
    await purchase.click()
    await authenticateFromCheckout(page, stringField(client, 'phone'))

    const purchaseDialog = page.getByRole('dialog', { name: 'Покупка техники' })
    await expect(purchaseDialog).toBeVisible()
    await expect(purchaseDialog.getByRole('heading', { name: 'Как оформить технику', exact: true })).toBeVisible()
  })

  test('AC-16: лизинг из корзины продолжается после входа с сохранением гостевого выбора', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-16', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const product = fixture.products.usedMileage
    const client = fixtureRecord(fixture.auth, 'client')

    await page.goto(appUrl(`/special-equipment/products/${product.id}/${product.slug}`), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    await openCartFromProduct(page)
    const leasing = page.getByRole('button', { name: 'Получить специальное предложение', exact: true })
    await expect(leasing).toBeEnabled()
    await leasing.click()
    const registration = page.getByRole('dialog').filter({
      has: page.getByRole('heading', { name: 'Регистрация', exact: true }),
    })
    await expect(registration).toBeVisible()
    await registration.getByRole('button', { name: 'Уже есть аккаунт? Войти', exact: true }).click()
    await authenticateFromCheckout(page, stringField(client, 'phone'))

    await expect(page).toHaveURL(/\/application\/new(?:\?|$)/)
    await expect(page.getByRole('heading', { name: 'Оформление заявки на лизинг' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Запрашиваемые условия', exact: true })).toBeVisible()
  })

  test('AC-18 AC-19: backend/frontend coverage и последовательность зависимостей закреплены исполняемыми проверками', async ({}, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: ['AC-18', 'AC-19'], kind: 'contract-guard' })
    expect(testInfo.project.name).toBe('desktop-chromium')

    const repositoryRoot = resolve(__dirname, '../../../..')
    const backendContracts = readFileSync(
      resolve(repositoryRoot, 'backend/tests/test_special_equipment_management.py'),
      'utf8',
    )
    for (const contractTest of [
      'test_used_owner_validation_uses_public_condition_name_and_zero_minimum',
      'test_product_with_no_default_modification_category_accepts_active_category',
      'test_modification_values_must_belong_to_selected_categories',
    ]) {
      expect(backendContracts).toContain(`def ${contractTest}`)
    }
    const publicContracts = readFileSync(
      resolve(repositoryRoot, 'backend/tests/integration/test_special_equipment_catalog_router.py'),
      'utf8',
    )
    expect(publicContracts).toContain('test_multi_value_exact_attributes_use_or_within_one_attribute')
    expect(publicContracts).toContain('test_contextual_catalog_uses_dag_and_live_modification_values')

  })
})

test.describe('Bitrix 21940 — workspace desktop', () => {
  test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })

  test('AC-13: полная подпись загрузки автомобилей не обрезается при поддерживаемой ширине', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21940', ac: 'AC-13', kind: 'full-stack' })
    await page.goto(appUrl('/workspace/warehouses'), { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('load')
    expect(testInfo.project.name).toBe('desktop-chromium')
    // The workspace sidebar is permanently visible from Tailwind's desktop
    // breakpoint (`lg`, 1024px). Below it the sidebar is a transient drawer,
    // which is not the surface whose label width this acceptance criterion
    // verifies.
    await page.setViewportSize({ width: 1024, height: 1000 })
    const label = page.getByRole('link', { name: 'Загрузка автомобилей', exact: true }).filter({ visible: true })
    await expect(label).toBeVisible({ timeout: 10_000 })
    expect(await label.evaluate(element => element.scrollWidth <= element.clientWidth)).toBeTruthy()
  })
})
