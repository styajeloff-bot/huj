import { randomUUID } from 'node:crypto'
import { expect, test, type Locator, type Page } from '@playwright/test'
import {
  getE2EFixtureManifest,
  resetE2EFixture,
  type JsonRecord,
} from './support/fixtures'
import { appUrl } from './support/runtime'

const PRODUCTS_PATH = '/api/v1/special-equipment/products'
const FACETS_PATH = '/api/v1/special-equipment/facets'

interface NamedFixture {
  id: string
  name: string
}

interface ProductsResponse {
  items: Array<{ id: string, modification: { id: string }, trim: { id: string } | null }>
}

const namedFixture = (source: JsonRecord, key: string): NamedFixture => {
  const value = source[key] as JsonRecord | undefined
  expect(value, `fixture must contain ${key}`).toBeTruthy()
  expect(typeof value?.id, `${key}.id must be a UUID string`).toBe('string')
  expect(typeof value?.name, `${key}.name must be a string`).toBe('string')
  return value as unknown as NamedFixture
}

const catalogFixture = () => {
  const fixture = getE2EFixtureManifest()
  return {
    ...fixture,
    mark: namedFixture(fixture.marks, 'kamaz'),
    model: namedFixture(fixture.models, 'kamaz1000'),
    baseWhite: namedFixture(fixture.modifications, 'baseWhite'),
    baseBlack: namedFixture(fixture.modifications, 'baseBlack'),
    safetyAll: namedFixture(fixture.trims, 'safetyAll'),
    safetyAbsOnly: namedFixture(fixture.trims, 'safetyAbsOnly'),
    safetyNone: namedFixture(fixture.trims, 'safetyNone'),
  }
}

type CatalogFixture = ReturnType<typeof catalogFixture>
type FacetLabel = 'Марка' | 'Модель' | 'Модификация' | 'Комплектация'

const results = (page: Page): Locator => page.locator('#special-equipment-results')
const filters = (page: Page): Locator => page.getByRole('dialog', { name: 'Все фильтры', exact: true })
const trimChips = (page: Page): Locator => results(page).getByRole('button', {
  name: /^Удалить фильтр Комплектация:/,
})
const trigger = (page: Page, label: FacetLabel): Locator => filters(page).getByRole('button', {
  name: new RegExp(`^(Выбрать: ${label.toLocaleLowerCase('ru-RU')}|${label}: выбрано \\d+)$`),
})

const categoryUrl = (fixture: CatalogFixture, params = new URLSearchParams()): string =>
  appUrl(`/special-equipment/categories/${fixture.categories.leaf.path.join('/')}?${params.toString()}`)

const waitForCatalog = async (page: Page): Promise<void> => {
  await expect(results(page)).toHaveAttribute('aria-busy', 'false')
  await expect(results(page).getByRole('alert')).toHaveCount(0)
}

const openCatalog = async (
  page: Page,
  fixture: CatalogFixture,
  params = new URLSearchParams(),
): Promise<void> => {
  await page.goto(categoryUrl(fixture, params), { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => Boolean(
    (document.querySelector('#__nuxt') as HTMLElement & { __vue_app__?: unknown } | null)?.__vue_app__,
  ))
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', {
    name: fixture.categories.leaf.name,
    level: 1,
    exact: true,
  })).toBeVisible()
  await waitForCatalog(page)
}

const openFilters = async (page: Page): Promise<void> => {
  await results(page).getByRole('button', { name: /^Все фильтры/ }).click()
  await expect(filters(page)).toBeVisible()
}

const closeFilters = async (page: Page): Promise<void> => {
  await filters(page).getByRole('button', { name: 'Показать объявления', exact: true }).click()
  await expect(filters(page)).toBeHidden()
  await waitForCatalog(page)
}

const openFacet = async (page: Page, label: FacetLabel): Promise<Locator> => {
  await expect(trigger(page, label)).toBeEnabled()
  await trigger(page, label).click()
  const dialog = page.getByRole('dialog', { name: label, exact: true })
  await expect(dialog).toBeVisible()
  return dialog
}

const optionRow = (dialog: Locator, name: string): Locator => dialog.locator('label').filter({
  has: dialog.page().getByText(name, { exact: true }),
})

const selectFacet = async (
  page: Page,
  label: FacetLabel,
  selected: NamedFixture[],
): Promise<void> => {
  const dialog = await openFacet(page, label)
  await dialog.getByRole('button', { name: 'Сбросить выбор', exact: true }).click()
  for (const item of selected) await optionRow(dialog, item.name).getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Применить', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(trigger(page, label)).toHaveAccessibleName(selected.length > 0
    ? `${label}: выбрано ${selected.length}`
    : `Выбрать: ${label.toLocaleLowerCase('ru-RU')}`)
  await waitForCatalog(page)
}

const selectModifications = async (
  page: Page,
  fixture: CatalogFixture,
  modifications = [fixture.baseWhite],
): Promise<void> => {
  await selectFacet(page, 'Марка', [fixture.mark])
  await selectFacet(page, 'Модель', [fixture.model])
  await selectFacet(page, 'Модификация', modifications)
}

const expectWhiteTrimOptions = async (page: Page, fixture: CatalogFixture): Promise<Locator> => {
  const dialog = await openFacet(page, 'Комплектация')
  await expect(dialog.getByRole('checkbox')).toHaveCount(3)
  for (const trim of [fixture.safetyAll, fixture.safetyAbsOnly, fixture.safetyNone]) {
    await expect(optionRow(dialog, trim.name).getByRole('checkbox')).toBeVisible()
  }
  return dialog
}

const expectTrimDisabled = async (page: Page): Promise<void> => {
  await expect(trigger(page, 'Комплектация')).toBeVisible()
  await expect(trigger(page, 'Комплектация')).toBeDisabled()
  await expect(trigger(page, 'Комплектация')).toHaveAccessibleDescription('Сначала выберите модификацию')
}

const visibleProductIds = async (page: Page): Promise<string[]> => {
  const hrefs = await results(page).getByRole('link', { name: 'Подробнее', exact: true })
    .evaluateAll(links => links.map(link => link.getAttribute('href') ?? ''))
  return hrefs.map((href) => {
    const id = new URL(href, page.url()).pathname.match(/\/products\/([^/]+)/)?.[1]
    expect(id, `product link must contain its UUID: ${href}`).toBeTruthy()
    return id!
  }).sort()
}

const expectProducts = async (page: Page, productIds: string[]): Promise<void> => {
  await waitForCatalog(page)
  await expect.poll(() => visibleProductIds(page)).toEqual([...productIds].sort())
}

const readProducts = async (
  page: Page,
  fixture: CatalogFixture,
  params = new URLSearchParams(),
): Promise<ProductsResponse> => {
  const query = new URLSearchParams(params)
  query.set('category_path', fixture.categories.leaf.path.join('/'))
  query.set('page_size', '24')
  query.set('sort', 'published_desc')
  query.append('availability', 'available')
  query.append('availability', 'on_order')
  const response = await page.request.get(`${PRODUCTS_PATH}?${query.toString()}`)
  expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
  return response.json() as Promise<ProductsResponse>
}

const selectSafetyAll = async (page: Page, fixture: CatalogFixture): Promise<void> => {
  const responsePromise = page.waitForResponse(response => {
    const url = new URL(response.url())
    return url.pathname === PRODUCTS_PATH
      && url.searchParams.getAll('trim_id').includes(fixture.safetyAll.id)
      && url.searchParams.getAll('modification_id').includes(fixture.baseWhite.id)
  })
  await selectFacet(page, 'Комплектация', [fixture.safetyAll])
  const response = await responsePromise
  expect(response.ok()).toBeTruthy()
  const payload = await response.json() as ProductsResponse
  expect(payload.items.map(product => product.id)).toEqual([fixture.products.trimAbsEsp.id])
  expect(payload.items[0]?.trim?.id).toBe(fixture.safetyAll.id)
  await expect.poll(() => new URL(page.url()).searchParams.getAll('trim_id')).toEqual([fixture.safetyAll.id])
  await closeFilters(page)
  await expectProducts(page, [fixture.products.trimAbsEsp.id])
  await expect(trimChips(page)).toHaveText(`Комплектация: ${fixture.safetyAll.name}`)
}

test.describe('Комплектация зависит от выбранных модификаций — публичный каталог', () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  test.describe.configure({ timeout: 90_000 })

  test.beforeEach(async () => {
    await resetE2EFixture()
  })

  test('комплектация доступна после выбора марки, модели и модификации; чип модификации снимает её', async ({ page }) => {
    const fixture = catalogFixture()
    await openCatalog(page, fixture)
    await openFilters(page)
    await expectTrimDisabled(page)
    await selectFacet(page, 'Марка', [fixture.mark])
    await expectTrimDisabled(page)
    await selectFacet(page, 'Модель', [fixture.model])
    await expectTrimDisabled(page)
    await selectFacet(page, 'Модификация', [fixture.baseWhite])
    const trimDialog = await expectWhiteTrimOptions(page, fixture)
    await trimDialog.getByRole('button', { name: 'Отмена', exact: true }).click()
    await selectSafetyAll(page, fixture)

    await results(page).getByRole('button', {
      name: `Удалить фильтр ${fixture.baseWhite.name}`,
      exact: true,
    }).click()
    await expect(trimChips(page)).toHaveCount(0)
    await expect.poll(() => new URL(page.url()).searchParams.has('trim_id')).toBe(false)
    await expect.poll(() => new URL(page.url()).searchParams.has('modification_id')).toBe(false)
    await waitForCatalog(page)
    await openFilters(page)
    await expectTrimDisabled(page)
  })

  for (const ancestor of ['model', 'mark'] as const) {
    test(`удаление чипа ${ancestor === 'model' ? 'модели' : 'марки'} каскадно снимает комплектацию`, async ({ page }) => {
      const fixture = catalogFixture()
      await openCatalog(page, fixture)
      await openFilters(page)
      await selectModifications(page, fixture)
      await selectSafetyAll(page, fixture)

      await results(page).getByRole('button', {
        name: `Удалить фильтр ${fixture[ancestor].name}`,
        exact: true,
      }).click()
      await expect(trimChips(page)).toHaveCount(0)
      await expect.poll(() => new URL(page.url()).searchParams.has('trim_id')).toBe(false)
      await expect.poll(() => new URL(page.url()).searchParams.has('modification_id')).toBe(false)
      await expect.poll(() => new URL(page.url()).searchParams.has('model_id')).toBe(false)
      if (ancestor === 'mark') {
        await expect.poll(() => new URL(page.url()).searchParams.has('mark_id')).toBe(false)
      }
      await waitForCatalog(page)
      await openFilters(page)
      await expectTrimDisabled(page)
    })
  }

  test('старая ссылка без модификации удаляет trim_id и показывает выдачу без фильтров', async ({ page }) => {
    const fixture = catalogFixture()
    const baseline = await readProducts(page, fixture)
    expect(baseline.items.length).toBeGreaterThan(1)
    const catalogRequests: URL[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if ([PRODUCTS_PATH, FACETS_PATH].includes(url.pathname)) catalogRequests.push(url)
    })

    await openCatalog(page, fixture, new URLSearchParams({ trim_id: fixture.safetyAll.id }))
    await expect.poll(() => new URL(page.url()).searchParams.has('trim_id')).toBe(false)
    await expect(trimChips(page)).toHaveCount(0)
    await expectProducts(page, baseline.items.map(product => product.id))
    for (const requestUrl of catalogRequests) {
      expect(requestUrl.searchParams.has('trim_id'), requestUrl.toString()).toBe(false)
    }
    await openFilters(page)
    await expectTrimDisabled(page)
  })

  test('ссылка с чужой комплектацией оставляет baseBlack и удаляет safetyAll', async ({ page }) => {
    const fixture = catalogFixture()
    const expected = await readProducts(page, fixture, new URLSearchParams({
      modification_id: fixture.baseBlack.id,
    }))
    expect(expected.items.length).toBeGreaterThan(0)
    expect(expected.items.every(product => product.modification.id === fixture.baseBlack.id)).toBe(true)
    const hydrationErrors: string[] = []
    page.on('console', (message) => {
      if (['warning', 'error'].includes(message.type()) && /hydration/i.test(message.text())) {
        hydrationErrors.push(message.text())
      }
    })
    const catalogRequests: URL[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if ([PRODUCTS_PATH, FACETS_PATH].includes(url.pathname)) catalogRequests.push(url)
    })

    const entryParams = new URLSearchParams({
      modification_id: fixture.baseBlack.id,
      trim_id: fixture.safetyAll.id,
    })
    const documentResponse = await page.request.get(categoryUrl(fixture, entryParams))
    expect(documentResponse.ok()).toBeTruthy()
    const documentHtml = await documentResponse.text()
    for (const product of expected.items) {
      expect(documentHtml).toContain('/products/' + product.id + '/')
    }
    expect(documentHtml).not.toContain('Удалить фильтр Комплектация:')

    await openCatalog(page, fixture, entryParams)
    await expect.poll(() => new URL(page.url()).searchParams.has('trim_id')).toBe(false)
    await expect.poll(() => new URL(page.url()).searchParams.getAll('modification_id'))
      .toEqual([fixture.baseBlack.id])
    await expect(trimChips(page)).toHaveCount(0)
    await expectProducts(page, expected.items.map(product => product.id))

    // Ensure both endpoints are exercised in the browser even when entry used SSR.
    await openFilters(page)
    const updatedResponses = [PRODUCTS_PATH, FACETS_PATH].map(endpoint =>
      page.waitForResponse(response => {
        const url = new URL(response.url())
        return url.pathname === endpoint
          && url.searchParams.getAll('availability').join(',') === 'available'
          && url.searchParams.getAll('modification_id').includes(fixture.baseBlack.id)
      }),
    )
    await filters(page).getByRole('checkbox', { name: /^Под заказ \d+$/ }).uncheck()
    for (const response of await Promise.all(updatedResponses)) expect(response.ok()).toBeTruthy()
    await closeFilters(page)
    await expectProducts(page, expected.items.map(product => product.id))
    for (const endpoint of [PRODUCTS_PATH, FACETS_PATH]) {
      expect(catalogRequests.some(url => url.pathname === endpoint)).toBe(true)
    }
    for (const requestUrl of catalogRequests) {
      expect(requestUrl.searchParams.has('trim_id'), requestUrl.toString()).toBe(false)
    }
    expect(hydrationErrors, 'foreign deep link must hydrate without mismatches').toEqual([])
  })

  test('корректная deep link сохраняет комплектацию при SSR, входе и перезагрузке страницы', async ({ page }) => {
    const fixture = catalogFixture()
    const params = new URLSearchParams({
      modification_id: fixture.baseWhite.id,
      trim_id: fixture.safetyAll.id,
    })
    const documentResponse = await page.request.get(categoryUrl(fixture, params))
    expect(documentResponse.ok()).toBeTruthy()
    const documentHtml = await documentResponse.text()
    expect(documentHtml).toContain('/products/' + fixture.products.trimAbsEsp.id + '/')
    expect(documentHtml).toContain('Удалить фильтр Комплектация:')

    await openCatalog(page, fixture, params)
    await expectProducts(page, [fixture.products.trimAbsEsp.id])
    await expect.poll(() => new URL(page.url()).searchParams.getAll('trim_id'))
      .toEqual([fixture.safetyAll.id])
    await expect(trimChips(page)).toHaveText('Комплектация: ' + fixture.safetyAll.name)

    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => Boolean(
      (document.querySelector('#__nuxt') as HTMLElement & { __vue_app__?: unknown } | null)?.__vue_app__,
    ))
    await expectProducts(page, [fixture.products.trimAbsEsp.id])
    await expect.poll(() => new URL(page.url()).searchParams.getAll('modification_id'))
      .toEqual([fixture.baseWhite.id])
    await expect.poll(() => new URL(page.url()).searchParams.getAll('trim_id'))
      .toEqual([fixture.safetyAll.id])
    await expect(trimChips(page)).toHaveText('Комплектация: ' + fixture.safetyAll.name)
  })

  test('нулевая выдача по цене не снимает корректную комплектацию, отсутствующую в фасетах', async ({ page }) => {
    const fixture = catalogFixture()
    const params = new URLSearchParams({
      modification_id: fixture.baseWhite.id,
      trim_id: fixture.safetyAll.id,
      price_min: '999999999',
    })
    const expected = await readProducts(page, fixture, params)
    expect(expected.items).toEqual([])
    const facetsParams = new URLSearchParams(params)
    facetsParams.set('category_path', fixture.categories.leaf.path.join('/'))
    const facetsResponse = await page.request.get(FACETS_PATH + '?' + facetsParams.toString())
    expect(facetsResponse.ok()).toBeTruthy()
    const facetPayload = await facetsResponse.json() as { trims: Array<{ id: string }> }
    expect(facetPayload.trims).toEqual([])

    await openCatalog(page, fixture, params)
    await expectProducts(page, [])
    await expect(results(page).getByRole('heading', { name: 'Ничего не найдено', exact: true }))
      .toBeVisible()
    await expect.poll(() => new URL(page.url()).searchParams.getAll('modification_id'))
      .toEqual([fixture.baseWhite.id])
    await expect.poll(() => new URL(page.url()).searchParams.getAll('trim_id'))
      .toEqual([fixture.safetyAll.id])
    await expect(trimChips(page)).toHaveCount(1)

    await results(page).getByRole('button', { name: /^Удалить фильтр Цена от/ }).click()
    await expectProducts(page, [fixture.products.trimAbsEsp.id])
    await expect.poll(() => new URL(page.url()).searchParams.getAll('trim_id'))
      .toEqual([fixture.safetyAll.id])
    await expect(trimChips(page)).toHaveText('Комплектация: ' + fixture.safetyAll.name)
  })

  test('неизвестная комплектация сохраняется при выбранной модификации, пока владелец не доказан', async ({ page }) => {
    const fixture = catalogFixture()
    const unknownTrimId = randomUUID()
    const params = new URLSearchParams({
      modification_id: fixture.baseWhite.id,
      trim_id: unknownTrimId,
    })
    const expected = await readProducts(page, fixture, params)
    expect(expected.items).toEqual([])

    await openCatalog(page, fixture, params)
    await expectProducts(page, [])
    await expect(results(page).getByRole('heading', { name: 'Ничего не найдено', exact: true }))
      .toBeVisible()
    await expect.poll(() => new URL(page.url()).searchParams.getAll('modification_id'))
      .toEqual([fixture.baseWhite.id])
    await expect.poll(() => new URL(page.url()).searchParams.getAll('trim_id'))
      .toEqual([unknownTrimId])
    await expect(trimChips(page)).toHaveCount(1)

    await trimChips(page).click()
    await expect.poll(() => new URL(page.url()).searchParams.has('trim_id')).toBe(false)
    await expect(trimChips(page)).toHaveCount(0)
    const withoutTrim = await readProducts(page, fixture, new URLSearchParams({
      modification_id: fixture.baseWhite.id,
    }))
    await expectProducts(page, withoutTrim.items.map(product => product.id))
  })

  test('несколько модификаций показывают только свои комплектации; снятие чужой модификации сохраняет выбор', async ({ page }) => {
    const fixture = catalogFixture()
    await openCatalog(page, fixture)
    await openFilters(page)
    await selectModifications(page, fixture, [fixture.baseWhite, fixture.baseBlack])
    const trimDialog = await expectWhiteTrimOptions(page, fixture)
    await trimDialog.getByRole('button', { name: 'Отмена', exact: true }).click()
    await selectSafetyAll(page, fixture)

    await results(page).getByRole('button', {
      // The active trim leaves no baseBlack products in the modification facet.
      name: 'Удалить фильтр Модификация',
      exact: true,
    }).click()
    await expect.poll(() => new URL(page.url()).searchParams.getAll('modification_id'))
      .toEqual([fixture.baseWhite.id])
    await expect.poll(() => new URL(page.url()).searchParams.getAll('trim_id'))
      .toEqual([fixture.safetyAll.id])
    await expect(trimChips(page)).toHaveText(`Комплектация: ${fixture.safetyAll.name}`)
    await expectProducts(page, [fixture.products.trimAbsEsp.id])
  })

  test('изменение модификаций в диалоге снимает прежнюю комплектацию', async ({ page }) => {
    const fixture = catalogFixture()
    await openCatalog(page, fixture)
    await openFilters(page)
    await selectModifications(page, fixture)
    await selectSafetyAll(page, fixture)
    await openFilters(page)
    await selectFacet(page, 'Модификация', [])
    await expectTrimDisabled(page)
    await closeFilters(page)

    await expect.poll(() => new URL(page.url()).searchParams.has('trim_id')).toBe(false)
    await expect.poll(() => new URL(page.url()).searchParams.has('modification_id')).toBe(false)
    await expect(trimChips(page)).toHaveCount(0)
    const expected = await readProducts(page, fixture, new URLSearchParams({
      mark_id: fixture.mark.id,
      model_id: fixture.model.id,
    }))
    await expectProducts(page, expected.items.map(product => product.id))
  })
})
