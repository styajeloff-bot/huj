import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test, type Locator, type Page, type Request, type Route } from '@playwright/test'
import {
  E2E_CATEGORY_KEYS,
  E2E_PRODUCT_KEYS,
  getE2EFixtureManifest,
  type E2EFixtureCategory,
} from './support/fixtures'
import { annotateTraceability, REQUIRED_ACCEPTANCE_CRITERIA } from './support/traceability'
import { appUrl } from './support/runtime'

const NEW_CATALOG_TITLE = 'Каталог транспортных средств и специальной техники'
const OLD_CATALOG_TITLE = 'Каталог спецтехники'
const PRODUCTS_PATH = '/api/v1/special-equipment/products'
const FACETS_PATH = '/api/v1/special-equipment/facets'

const escapeRegex = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const moduleFor = (page: Page): Locator => page.locator('#homepage-catalog')
const resultsFor = (page: Page): Locator => moduleFor(page).locator('#homepage-special-equipment-results')
const categoryCard = (page: Page, category: Pick<E2EFixtureCategory, 'name'>): Locator =>
  moduleFor(page).locator('button[data-homepage-category-identity]').filter({ hasText: category.name }).first()

interface ElementBox {
  width: number
  height: number
}

const expectStableElementSize = (before: ElementBox | null, after: ElementBox | null): void => {
  expect(before, 'element must have layout geometry before the interaction').not.toBeNull()
  expect(after, 'element must preserve layout geometry after the interaction').not.toBeNull()
  expect(after!.width).toBeCloseTo(before!.width, 1)
  expect(after!.height).toBeCloseTo(before!.height, 1)
}

const waitForNuxtHydration = async (page: Page): Promise<void> => {
  await page.waitForFunction(() => Boolean(
    (document.querySelector('#__nuxt') as HTMLElement & { __vue_app__?: unknown } | null)?.__vue_app__,
  ), undefined, { timeout: 10_000 })
  const homepageCatalog = page.locator('#homepage-catalog')
  if (await homepageCatalog.count()) {
    await expect(homepageCatalog).toHaveAttribute('data-homepage-catalog-hydrated', 'true')
  }
}

const openHomepage = async (page: Page): Promise<Locator> => {
  await page.goto(appUrl('/'), { waitUntil: 'domcontentloaded' })
  await waitForNuxtHydration(page)
  const module = moduleFor(page)
  await expect(module.getByRole('heading', { name: NEW_CATALOG_TITLE })).toBeVisible()
  await module.scrollIntoViewIfNeeded()
  return module
}

const waitForCatalog = async (page: Page): Promise<void> => {
  await expect(resultsFor(page)).toBeVisible()
  await expect(resultsFor(page)).toHaveAttribute('aria-busy', 'false')
}

const openFilters = async (page: Page): Promise<Locator> => {
  await resultsFor(page).getByRole('button', { name: /^Все фильтры/ }).click()
  const filters = page.getByRole('dialog', { name: 'Все фильтры', exact: true })
  await expect(filters).toBeVisible()
  return filters
}

const selectRoot = async (page: Page, category: E2EFixtureCategory): Promise<void> => {
  await waitForNuxtHydration(page)
  await categoryCard(page, category).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(resultsFor(page).getByRole('heading', { name: category.name, exact: true })).toBeVisible()
}

const requestTargetsPath = (request: Request, endpoint: string, category: E2EFixtureCategory): boolean => {
  const url = new URL(request.url())
  return url.pathname === endpoint && url.searchParams.get('category_path') === category.path.join('/')
}

interface ApiCategory {
  id: string
  name: string
  sort_order: number
  image_url: string | null
  parent_ids: string[]
  is_attachment_category: boolean
}

interface ApiCategoriesResponse {
  items: ApiCategory[]
}

interface ApiCompatibleAttachment {
  position: number
  primary_category: { id: string, code: string, name: string, slug: string } | null
  product: {
    id: string
    slug: string
    modification: {
      name: string
      model: { name: string, mark: { name: string } }
    }
  }
}

interface ApiCompatibleAttachmentsResponse {
  items: ApiCompatibleAttachment[]
}

interface ApiAttributeFacetOption {
  value: string
  label: string
  count: number
}

interface ApiAttributeFacet {
  id: string
  name: string
  data_type: 'number' | 'text' | 'boolean' | 'select'
  filter_kind: 'exact' | 'range' | 'search'
  options: ApiAttributeFacetOption[]
}

interface ApiFacetsResponse {
  attribute_groups: Array<{ name: string, attributes: ApiAttributeFacet[] }>
}

interface ApiProductsResponse {
  items: Array<{
    id: string
    modification: { id: string }
    trim: { id: string } | null
  }>
}

type DeferredOutcome = 'continue' | 'abort'

const deferNextRequest = async (
  page: Page,
  endpoint: typeof PRODUCTS_PATH | typeof FACETS_PATH,
  category: E2EFixtureCategory,
  outcome: DeferredOutcome,
): Promise<{ started: Promise<void>, release: () => void }> => {
  let signalStarted: () => void = () => undefined
  let signalRelease: () => void = () => undefined
  const started = new Promise<void>((resolve) => { signalStarted = resolve })
  const released = new Promise<void>((resolve) => { signalRelease = resolve })
  let intercepted = false
  const pattern = `**${endpoint}**`

  await page.route(pattern, async (route: Route) => {
    if (intercepted || !requestTargetsPath(route.request(), endpoint, category)) {
      await route.continue()
      return
    }
    intercepted = true
    signalStarted()
    await released
    if (outcome === 'abort') await route.abort('failed')
    else await route.continue()
  })

  return { started, release: signalRelease }
}

const failRequestsUntilReleased = async (
  page: Page,
  endpoint: typeof PRODUCTS_PATH | typeof FACETS_PATH,
  category: E2EFixtureCategory,
): Promise<{ started: Promise<void>, release: () => void }> => {
  let signalStarted: () => void = () => undefined
  const started = new Promise<void>((resolve) => { signalStarted = resolve })
  let released = false
  await page.route(`**${endpoint}**`, async (route) => {
    if (!released && requestTargetsPath(route.request(), endpoint, category)) {
      signalStarted()
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"injected E2E failure"}' })
      return
    }
    await route.continue()
  })
  return { started, release: () => { released = true } }
}

test.describe('Bitrix 21984 · full-stack homepage catalog', () => {
  test('root renders only published top-level categories before a branch is selected', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-1', fr: 'FR-2', kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    const module = await openHomepage(page)

    await expect(categoryCard(page, categories.root)).toBeVisible()
    await expect(categoryCard(page, categories.emptyRoot)).toBeVisible()
    await expect(module.getByRole('navigation', { name: 'Путь по каталогу' })).toHaveCount(0)
    await expect(module.getByRole('navigation', { name: 'Соседние категории' })).toHaveCount(0)
    await expect(module.getByRole('heading', { name: 'Фильтры', exact: true })).toHaveCount(0)
    await expect(resultsFor(page)).toHaveCount(0)
  })

  test('root cards mirror API order and render lazy images or a stable placeholder', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-2', fr: ['FR-2', 'FR-8', 'FR-12'], kind: 'full-stack' })
    const module = await openHomepage(page)
    const response = await page.request.get('/api/v1/special-equipment/categories')
    expect(response.ok()).toBeTruthy()
    const payload = await response.json() as ApiCategoriesResponse
    const publishedIds = new Set(payload.items.map(category => category.id))
    const expectedRoots = payload.items
      .filter(category => category.parent_ids.every(parentId => !publishedIds.has(parentId)))
      .sort((left, right) => left.sort_order - right.sort_order
        || left.id.localeCompare(right.id))

    const cards = module.locator('button[data-homepage-category-identity]')
    await expect(cards).toHaveCount(expectedRoots.length)
    const renderedCards = await cards.evaluateAll(elements => elements.map(element => element.textContent?.trim() ?? ''))
    expectedRoots.forEach((category, index) => expect(renderedCards[index]).toContain(category.name))

    for (const card of await cards.all()) {
      const mediaBox = card.locator('span.relative.aspect-\\[3\\/2\\]').first()
      const before = await mediaBox.boundingBox()
      const image = card.locator('img')
      if (await image.count()) {
        await image.scrollIntoViewIfNeeded()
        await expect(image).toHaveAttribute('loading', 'lazy')
        await expect.poll(() => image.evaluate(element => ({
          complete: (element as HTMLImageElement).complete,
          width: (element as HTMLImageElement).naturalWidth,
          height: (element as HTMLImageElement).naturalHeight,
        }))).toMatchObject({ complete: true })
        const decoded = await image.evaluate(element => ({
          width: (element as HTMLImageElement).naturalWidth,
          height: (element as HTMLImageElement).naturalHeight,
        }))
        expect(decoded.width).toBeGreaterThan(0)
        expect(decoded.height).toBeGreaterThan(0)
        const src = await image.getAttribute('src')
        expect(src).toMatch(/^\/api\/v1\/special-equipment\//)
        const mediaResponse = await page.request.get(src!)
        expect(mediaResponse.status()).toBe(200)
        expect(mediaResponse.headers()['content-type']).toMatch(/^image\//)
      } else {
        await expect(card.locator('svg').first()).toBeVisible()
      }
      const after = await mediaBox.boundingBox()
      expectStableElementSize(before, after)
    }
  })

  test('mark, model and modification use searchable draft dialogs with apply, cancel and cascading reset', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-2', fr: ['FR-2'], kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)
    await selectRoot(page, categories.root)
    await waitForCatalog(page)
    const filters = await openFilters(page)

    const trigger = (label: string) => filters.getByRole('button', {
      name: new RegExp(`^(Выбрать: ${label.toLocaleLowerCase('ru-RU')}|${label}: выбрано \\d+)$`),
    })
    const fieldLabel = (label: string) => filters.locator('p').filter({ hasText: new RegExp(`^${label}$`) })
    const expectDisabledFacet = async (label: string): Promise<void> => {
      const button = trigger(label)
      await expect(fieldLabel(label)).toHaveClass(/text-gray-500/)
      await expect(button).toBeDisabled()
      await expect(button).toHaveClass(/cursor-not-allowed/)
      await button.click({ force: true })
      await expect(page.getByRole('dialog', { name: label, exact: true })).toHaveCount(0)
      await button.focus()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('dialog', { name: label, exact: true })).toHaveCount(0)
      await page.keyboard.press('Space')
      await expect(page.getByRole('dialog', { name: label, exact: true })).toHaveCount(0)
    }
    const expectEnabledFacet = async (label: string): Promise<void> => {
      await expect(fieldLabel(label)).toHaveClass(/text-gray-950/)
      await expect(trigger(label)).toBeEnabled()
    }
    const openDialog = async (label: string): Promise<Locator> => {
      const button = trigger(label)
      await expect(button).toBeVisible()
      await button.click()
      const dialog = page.getByRole('dialog', { name: label, exact: true })
      await expect(dialog).toBeVisible()
      await expect(dialog.getByPlaceholder(`Найти: ${label.toLocaleLowerCase('ru-RU')}`)).toBeFocused()
      const box = await dialog.boundingBox()
      expect(box).toBeTruthy()
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.width).toBeLessThanOrEqual(520)
      return dialog
    }
    const chooseFirst = async (label: string): Promise<void> => {
      const dialog = await openDialog(label)
      const firstRow = dialog.getByRole('group', { name: `Варианты: ${label.toLocaleLowerCase('ru-RU')}` }).locator('label').first()
      await expect(firstRow).toBeVisible()
      const optionName = await firstRow.locator('span').first().innerText()
      await expect(firstRow.locator('span').last()).toHaveText(/^\d+$/)
      const search = dialog.getByPlaceholder(`Найти: ${label.toLocaleLowerCase('ru-RU')}`)
      await search.fill(optionName)
      await expect(firstRow).toBeVisible()
      await firstRow.getByRole('checkbox').check()
      await dialog.getByRole('button', { name: 'Применить' }).click()
      await expect(dialog).toBeHidden()
      await expect(trigger(label)).toHaveAccessibleName(new RegExp(`^${label}: выбрано 1$`))
    }

    await expectEnabledFacet('Марка')
    await expectDisabledFacet('Модель')
    await expectDisabledFacet('Модификация')

    const markDialog = await openDialog('Марка')
    const markCheckbox = markDialog.getByRole('checkbox').first()
    await markCheckbox.check()
    await markDialog.getByRole('button', { name: 'Отмена' }).click()
    await expect(markDialog).toBeHidden()
    await expect(trigger('Марка')).toBeFocused()
    await expect(trigger('Марка')).toHaveAccessibleName('Выбрать: марка')

    const escapeDialog = await openDialog('Марка')
    await page.keyboard.press('Escape')
    await expect(escapeDialog).toBeHidden()
    await expect(trigger('Марка')).toBeFocused()

    await chooseFirst('Марка')
    await expectEnabledFacet('Модель')
    await expectDisabledFacet('Модификация')
    await chooseFirst('Модель')
    await expectEnabledFacet('Модификация')
    await chooseFirst('Модификация')

    const resetDialog = await openDialog('Марка')
    await resetDialog.getByRole('button', { name: 'Сбросить выбор' }).click()
    await resetDialog.getByRole('button', { name: 'Применить' }).click()
    await expect(resetDialog).toBeHidden()
    await expect(trigger('Марка')).toHaveAccessibleName('Выбрать: марка')
    await expect(trigger('Модель')).toHaveAccessibleName('Выбрать: модель')
    await expect(trigger('Модификация')).toHaveAccessibleName('Выбрать: модификация')
    await expectDisabledFacet('Модель')
    await expectDisabledFacet('Модификация')
  })

  test('parent attachment branch exposes and applies its descendant-only Опоры facet', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-4', fr: ['FR-3'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const category = fixture.categories.attachmentRoot
    const categoryPath = category.path.join('/')
    const stabilizers = fixture.attributes.stabilizers as Record<string, unknown>
    const stabilizersId = String(stabilizers.id)
    const attachmentModification = fixture.modifications.attachment as Record<string, unknown>
    const attachmentModificationId = String(attachmentModification.id)

    const facetsResponse = await page.request.get(FACETS_PATH, {
      params: { category_path: categoryPath },
    })
    expect(facetsResponse.ok()).toBeTruthy()
    const facetsPayload = await facetsResponse.json() as ApiFacetsResponse
    const facetGroup = facetsPayload.attribute_groups.find(group =>
      group.attributes.some(attribute => attribute.id === stabilizersId),
    )
    const facet = facetGroup?.attributes.find(attribute => attribute.id === stabilizersId)
    expect(facet, 'parent branch must aggregate child category attribute rules').toBeTruthy()
    expect(facet!.name).toContain('Опоры')
    expect(facet!.data_type).toBe('boolean')
    expect(facet!.filter_kind).toBe('exact')
    const trueOption = facet!.options.find(option => option.value === 'true')
    expect(trueOption, 'boolean facet must expose the populated true option').toBeTruthy()
    expect(trueOption!.label).toBe('Есть')
    expect(facet!.options.find(option => option.value === 'false')).toBeUndefined()
    expect(trueOption!.count).toBeGreaterThan(0)
    const baselineResponse = await page.request.get(PRODUCTS_PATH, { params: { category_path: categoryPath } })
    expect(baselineResponse.ok()).toBeTruthy()
    const baselinePayload = await baselineResponse.json() as ApiProductsResponse

    await page.goto(appUrl(`/special-equipment/categories/${categoryPath}`), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const panel = page.locator('#special-equipment-results')
    await expect(panel).toHaveAttribute('aria-busy', 'false')
    await panel.getByRole('button', { name: /^Все фильтры/ }).click()
    const filters = page.getByRole('dialog', { name: 'Все фильтры', exact: true })
    await expect(filters).toBeVisible()
    const groupToggle = filters.getByRole('button', { name: facetGroup!.name, exact: true })
    await expect(groupToggle).toHaveAttribute('aria-expanded', 'false')
    await groupToggle.focus()
    await page.keyboard.press('Enter')
    await expect(groupToggle).toHaveAttribute('aria-expanded', 'true')
    const option = filters.getByRole('checkbox', {
      name: new RegExp(`^${escapeRegex(facet!.name)}(?:, .+)? ${trueOption!.count}$`),
    })
    await expect(option).toBeVisible()

    const token = `${stabilizersId}:eq:${trueOption!.value}`
    const filteredResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.get('category_path') === categoryPath
        && url.searchParams.getAll('attribute').includes(token)
    })
    const refreshedFacetsPromise = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return url.pathname === FACETS_PATH
        && url.searchParams.get('category_path') === categoryPath
        && url.searchParams.getAll('attribute').includes(token)
    })
    await option.check()
    const filteredResponse = await filteredResponsePromise
    expect(filteredResponse.status(), 'applying a descendant facet must not return 422').toBe(200)
    const filteredPayload = await filteredResponse.json() as ApiProductsResponse
    expect(filteredPayload.items.length).toBe(trueOption!.count)
    expect(filteredPayload.items.length).toBeGreaterThan(0)
    expect(filteredPayload.items.every(item => item.modification.id === attachmentModificationId)).toBe(true)
    await refreshedFacetsPromise
    await expect(panel).toHaveAttribute('aria-busy', 'false')
    await expect(option).toBeChecked()
    await expect(groupToggle).toHaveAccessibleName(new RegExp(`^${escapeRegex(facetGroup!.name)}\\s+1$`))
    await expect(groupToggle).toHaveAttribute('aria-expanded', 'true')
    const chip = panel.getByRole('button', { name: `Удалить фильтр ${facet!.name}` })
    await expect(chip).toBeVisible()
    const restoredResponsePromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.get('category_path') === categoryPath
        && !url.searchParams.getAll('attribute').includes(token)
    })
    await chip.click()
    const restoredResponse = await restoredResponsePromise
    expect(restoredResponse.ok()).toBeTruthy()
    const restoredPayload = await restoredResponse.json() as ApiProductsResponse
    expect(restoredPayload.items).toEqual(baselinePayload.items)
    await expect(panel).toHaveAttribute('aria-busy', 'false')
    await expect(groupToggle).toHaveAttribute('aria-expanded', 'true')
  })

  test('trim-only ABS and ESP facets intersect, chips restore the catalog, and a legacy false token is removable', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-4', fr: ['FR-3'], kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const category = fixture.categories.leaf
    const categoryPath = category.path.join('/')
    const abs = fixture.attributes.abs as Record<string, unknown>
    const esp = fixture.attributes.esp as Record<string, unknown>
    const safetyAllTrim = fixture.trims.safetyAll as Record<string, unknown>
    const absId = String(abs.id)
    const espId = String(esp.id)
    const absName = String(abs.name)
    const espName = String(esp.name)
    const safetyAllTrimId = String(safetyAllTrim.id)
    const absToken = `${absId}:eq:true`
    const espToken = `${espId}:eq:true`

    const facetsResponse = await page.request.get(FACETS_PATH, { params: { category_path: categoryPath } })
    expect(facetsResponse.ok()).toBeTruthy()
    const facetsPayload = await facetsResponse.json() as ApiFacetsResponse
    const safetyGroup = facetsPayload.attribute_groups.find(group =>
      group.attributes.some(attribute => attribute.id === absId),
    )
    const absFacet = safetyGroup?.attributes.find(attribute => attribute.id === absId)
    const espFacet = safetyGroup?.attributes.find(attribute => attribute.id === espId)
    expect(safetyGroup, 'trim-only boolean facets must be grouped').toBeTruthy()
    for (const facet of [absFacet, espFacet]) {
      expect(facet, 'published trim values must produce their boolean facet').toBeTruthy()
      expect(facet!.data_type).toBe('boolean')
      expect(facet!.filter_kind).toBe('exact')
      expect(facet!.options).toContainEqual(expect.objectContaining({ value: 'true', label: 'Есть' }))
      expect(facet!.options.find(option => option.value === 'false')).toBeUndefined()
    }

    const baselineResponse = await page.request.get(PRODUCTS_PATH, { params: { category_path: categoryPath } })
    expect(baselineResponse.ok()).toBeTruthy()
    const baselinePayload = await baselineResponse.json() as ApiProductsResponse
    expect(baselinePayload.items.some(item =>
      item.id === fixture.products.trimAbsEsp.id && item.trim?.id === safetyAllTrimId,
    ), 'fixture product must be published with a trim_id').toBe(true)

    await page.goto(appUrl(`/special-equipment/categories/${categoryPath}`), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const panel = page.locator('#special-equipment-results')
    await expect(panel).toHaveAttribute('aria-busy', 'false')
    await panel.getByRole('button', { name: /^Все фильтры/ }).click()
    const filters = page.getByRole('dialog', { name: 'Все фильтры', exact: true })
    const groupToggle = filters.getByRole('button', { name: safetyGroup!.name, exact: true })
    await expect(groupToggle).toHaveAttribute('aria-expanded', 'false')
    await groupToggle.focus()
    await page.keyboard.press('Space')
    await expect(groupToggle).toHaveAttribute('aria-expanded', 'true')

    const absOption = filters.getByRole('checkbox', {
      name: new RegExp(`^${escapeRegex(absName)}(?:, .+)? ${absFacet!.options[0]!.count}$`),
    })
    const espOption = filters.getByRole('checkbox', {
      name: new RegExp(`^${escapeRegex(espName)}(?:, .+)? ${espFacet!.options[0]!.count}$`),
    })
    const absResponsePromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.get('category_path') === categoryPath
        && url.searchParams.getAll('attribute').includes(absToken)
    })
    await absOption.check()
    expect((await absResponsePromise).ok()).toBeTruthy()

    const intersectionResponsePromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      const attributes = url.searchParams.getAll('attribute')
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.get('category_path') === categoryPath
        && attributes.includes(absToken)
        && attributes.includes(espToken)
    })
    await espOption.check()
    const intersectionResponse = await intersectionResponsePromise
    expect(intersectionResponse.ok()).toBeTruthy()
    const intersectionPayload = await intersectionResponse.json() as ApiProductsResponse
    expect(intersectionPayload.items.map(item => item.id)).toEqual([fixture.products.trimAbsEsp.id])
    await expect(panel.getByRole('button', { name: `Удалить фильтр ${absName}` })).toBeVisible()
    await expect(panel.getByRole('button', { name: `Удалить фильтр ${espName}` })).toBeVisible()

    const espOnlyResponsePromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      const attributes = url.searchParams.getAll('attribute')
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.get('category_path') === categoryPath
        && !attributes.includes(absToken)
        && attributes.includes(espToken)
    })
    await panel.getByRole('button', { name: `Удалить фильтр ${absName}` }).click()
    expect((await espOnlyResponsePromise).ok()).toBeTruthy()
    const restoredResponsePromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.get('category_path') === categoryPath
        && url.searchParams.getAll('attribute').length === 0
    })
    await panel.getByRole('button', { name: `Удалить фильтр ${espName}` }).click()
    const restoredPayload = await (await restoredResponsePromise).json() as ApiProductsResponse
    expect(restoredPayload.items).toEqual(baselinePayload.items)

    const legacyFalseToken = `${absId}:eq:false`
    await page.goto(
      appUrl(`/special-equipment/categories/${categoryPath}?attribute=${encodeURIComponent(legacyFalseToken)}`),
      { waitUntil: 'domcontentloaded' },
    )
    await waitForNuxtHydration(page)
    await expect(panel).toHaveAttribute('aria-busy', 'false')
    const legacyChip = panel.getByRole('button', { name: `Удалить фильтр ${absName}` })
    await expect(legacyChip).toBeVisible()
    const legacyRestorePromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.get('category_path') === categoryPath
        && !url.searchParams.getAll('attribute').includes(legacyFalseToken)
    })
    await legacyChip.click()
    const legacyRestoredPayload = await (await legacyRestorePromise).json() as ApiProductsResponse
    expect(legacyRestoredPayload.items).toEqual(baselinePayload.items)
  })

  test('compatible attachment exposes leaf category and keeps image, title and selection as separate controls', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-10', fr: ['FR-10'], kind: 'full-stack' })
    const { products } = getE2EFixtureManifest()
    const response = await page.request.get(
      `/api/v1/special-equipment/products/${products.representative.id}/compatible-attachments`,
    )
    expect(response.ok()).toBeTruthy()
    const payload = await response.json() as ApiCompatibleAttachmentsResponse
    const compatible = payload.items.find(item => item.primary_category !== null)
    expect(compatible, 'fixture must expose a compatible attachment with primary leaf category').toBeTruthy()
    const item = compatible!
    const title = [
      item.product.modification.model.mark.name,
      item.product.modification.model.name,
      item.product.modification.name,
    ].filter(Boolean).join(' ')

    await page.goto(appUrl(
      `/special-equipment/products/${products.representative.id}/${String(products.representative.slug)}`,
    ), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const attachments = page.locator('section').filter({
      has: page.getByRole('heading', { name: 'Совместимые надстройки' }),
    })
    const card = attachments.locator('article').filter({
      has: page.locator(`a[href*="/products/${item.product.id}/"]`),
    })
    await expect(card).toBeVisible()
    await expect(card.getByRole('link', { name: `Открыть ${title}`, exact: true })).toHaveAttribute(
      'href',
      new RegExp(`/products/${item.product.id}/`),
    )
    await expect(card.getByRole('link', { name: title, exact: true })).toHaveAttribute(
      'href',
      new RegExp(`/products/${item.product.id}/`),
    )
    await expect(card).toContainText(`Конечная категория: ${item.primary_category!.name}`)
    const checkbox = card.getByRole('checkbox', { name: `Добавить ${title}`, exact: true })
    await expect(checkbox).toBeVisible()
    expect(await checkbox.evaluate(element => element.closest('a') === null)).toBe(true)
  })

  test('selecting a type keeps / and opens a coherent branch catalog without a scroll jump', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: ['AC-3', 'AC-4'], fr: ['FR-3', 'FR-7', 'FR-10'], kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    const productsRequest = page.waitForRequest(request => requestTargetsPath(request, PRODUCTS_PATH, categories.root))
    const facetsRequest = page.waitForRequest(request => requestTargetsPath(request, FACETS_PATH, categories.root))
    await openHomepage(page)
    await categoryCard(page, categories.root).scrollIntoViewIfNeeded()
    const scrollBefore = await page.evaluate(() => window.scrollY)

    await selectRoot(page, categories.root)
    await Promise.all([productsRequest, facetsRequest])
    await waitForCatalog(page)

    await expect(page).toHaveURL(/\/$/)
    await expect(moduleFor(page).getByRole('navigation', { name: 'Путь по каталогу' })).toContainText(categories.root.name)
    await expect(moduleFor(page).getByRole('navigation', { name: 'Соседние категории' })).toBeVisible()
    await expect(resultsFor(page).getByRole('search')).toBeVisible()
    await expect(resultsFor(page).getByRole('heading', { name: 'Фильтры', exact: true }).first()).toBeVisible()
    expect(Math.abs((await page.evaluate(() => window.scrollY)) - scrollBefore)).toBeLessThan(8)
  })

  test('leaf and genuinely empty root preserve navigation while cards and results become empty', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-5', fr: ['FR-7', 'FR-10', 'FR-15'], kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)

    await selectRoot(page, categories.emptyRoot)
    await waitForCatalog(page)
    await expect(resultsFor(page).getByRole('heading', { name: 'Ничего не найдено' })).toBeVisible()
    await expect(moduleFor(page).getByRole('navigation', { name: 'Путь по каталогу' })).toContainText(categories.emptyRoot.name)
    await moduleFor(page).getByRole('button', { name: 'Каталог', exact: true }).click()

    await selectRoot(page, categories.root)
    await categoryCard(page, categories.dagParentA).click()
    await categoryCard(page, categories.shared).click()
    await categoryCard(page, categories.leaf).click()
    await waitForCatalog(page)
    await expect(moduleFor(page).getByRole('heading', { name: 'Категории', exact: true })).toHaveCount(0)
    await expect(moduleFor(page).getByRole('heading', { name: 'Варианты надстроек', exact: true })).toHaveCount(0)
    await expect(moduleFor(page).getByRole('navigation', { name: 'Путь по каталогу' })).toContainText(categories.leaf.name)
  })

  test('Back, breadcrumbs and the root crumb restore the exact previous context and focus', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: ['AC-6', 'AC-13'], fr: ['FR-4', 'FR-5', 'NFR-2'], kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)
    await selectRoot(page, categories.dagParentA)
    await categoryCard(page, categories.shared).click()
    await categoryCard(page, categories.leaf).click()
    await waitForCatalog(page)

    const breadcrumbs = moduleFor(page).getByRole('navigation', { name: 'Путь по каталогу' })
    await expect(breadcrumbs).toContainText(categories.dagParentA.name)
    await expect(breadcrumbs).toContainText(categories.shared.name)
    await expect(breadcrumbs).toContainText(categories.leaf.name)

    await breadcrumbs.getByRole('button', { name: categories.shared.name, exact: true }).click()
    await waitForCatalog(page)
    await expect(breadcrumbs).toContainText(categories.dagParentA.name)
    await expect(breadcrumbs).toContainText(categories.shared.name)
    await expect(breadcrumbs).not.toContainText(categories.leaf.name)
    await expect(resultsFor(page).getByRole('heading', { name: categories.shared.name, exact: true })).toBeVisible()
    await expect(categoryCard(page, categories.leaf)).toBeVisible()
    await expect(breadcrumbs.getByRole('button', { name: categories.shared.name, exact: true })).toBeFocused()

    await moduleFor(page).getByRole('button', { name: 'Назад', exact: true }).click()
    await waitForCatalog(page)
    await expect(breadcrumbs).toContainText(categories.dagParentA.name)
    await expect(breadcrumbs).not.toContainText(categories.shared.name)
    await expect(moduleFor(page).getByRole('tab', { name: categories.dagParentA.name, exact: true })).toBeFocused()
    await moduleFor(page).getByRole('button', { name: 'Каталог', exact: true }).click()
    await expect(resultsFor(page)).toHaveCount(0)
    await expect(categoryCard(page, categories.dagParentA)).toBeFocused()

    await selectRoot(page, categories.root)
    await moduleFor(page).getByRole('button', { name: 'Назад', exact: true }).click()
    await expect(categoryCard(page, categories.root)).toBeFocused()
  })

  test('DAG child derives breadcrumbs and real sibling tabs from the chosen parent placement', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-7', fr: ['FR-4', 'FR-6'], kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)

    await selectRoot(page, categories.root)
    await categoryCard(page, categories.leaf).click()
    const breadcrumbs = moduleFor(page).getByRole('navigation', { name: 'Путь по каталогу' })
    const tabs = moduleFor(page).getByRole('navigation', { name: 'Соседние категории' })
    await expect(breadcrumbs).toContainText(categories.root.name)
    await expect(breadcrumbs).toContainText(categories.leaf.name)
    await expect(breadcrumbs).not.toContainText(categories.shared.name)
    await expect(tabs.getByRole('tab', { name: categories.leaf.name, exact: true })).toHaveAttribute('aria-selected', 'true')
    await expect(tabs.getByRole('tab', { name: categories.siblingA.name, exact: true })).toBeVisible()
    await expect(tabs.getByRole('tab', { name: categories.siblingB.name, exact: true })).toBeVisible()
    await expect(tabs.getByRole('tab', { name: categories.attachmentChild.name, exact: true })).toHaveCount(0)

    await tabs.getByRole('tab', { name: categories.siblingA.name, exact: true }).scrollIntoViewIfNeeded()
    const siblingScrollBefore = await page.evaluate(() => window.scrollY)
    await tabs.getByRole('tab', { name: categories.siblingA.name, exact: true }).click()
    await waitForCatalog(page)
    await expect(breadcrumbs).toContainText(categories.root.name)
    await expect(breadcrumbs).toContainText(categories.siblingA.name)
    await expect(breadcrumbs).not.toContainText(categories.leaf.name)
    const siblingScrollAfter = await page.evaluate(() => window.scrollY)
    expect(
      Math.abs(siblingScrollAfter - siblingScrollBefore),
      `sibling navigation moved document scroll from ${siblingScrollBefore} to ${siblingScrollAfter}`,
    ).toBeLessThan(8)

    await breadcrumbs.getByRole('button', { name: 'Каталог', exact: true }).click()
    await selectRoot(page, categories.dagParentA)
    await categoryCard(page, categories.shared).click()
    await categoryCard(page, categories.leaf).click()
    await waitForCatalog(page)
    await expect(breadcrumbs).toContainText(categories.dagParentA.name)
    await expect(breadcrumbs).toContainText(categories.shared.name)
    await expect(breadcrumbs).toContainText(categories.leaf.name)
    await expect(breadcrumbs).not.toContainText(categories.root.name)
    await expect(moduleFor(page).getByRole('navigation', { name: 'Соседние категории' })).toHaveCount(0)
  })

  test('a lower category card keeps the document position while opening its branch', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: ['AC-4', 'AC-13'], fr: ['FR-3', 'FR-10', 'NFR-2'], kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)
    await selectRoot(page, categories.root)
    await waitForCatalog(page)

    const lowerCategory = categoryCard(page, categories.attachmentChild)
    await lowerCategory.scrollIntoViewIfNeeded()
    const scrollBefore = await page.evaluate(() => window.scrollY)

    await lowerCategory.click()
    await waitForCatalog(page)

    await expect(resultsFor(page).getByRole('heading', { name: categories.attachmentChild.name, exact: true })).toBeVisible()
    const scrollAfter = await page.evaluate(() => window.scrollY)
    expect(
      Math.abs(scrollAfter - scrollBefore),
      `category navigation moved document scroll from ${scrollBefore} to ${scrollAfter}`,
    ).toBeLessThan(8)
  })

  test('attachment DAG nodes stay separated, enter through either parent and continue with the regular catalog', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-8', fr: ['FR-7', 'FR-9', 'FR-10'], kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    expect(categories.attachmentRoot.is_attachment_category).toBe(true)
    expect(categories.attachmentChild.is_attachment_category).toBe(false)
    expect(categories.attachmentDescendant.is_attachment_category).toBe(false)
    const categoriesResponse = await page.request.get('/api/v1/special-equipment/categories')
    expect(categoriesResponse.ok()).toBeTruthy()
    const publicCategories = await categoriesResponse.json() as ApiCategoriesResponse
    const publicById = new Map(publicCategories.items.map(category => [category.id, category]))
    expect(publicById.get(categories.attachmentRoot.id)?.is_attachment_category).toBe(true)
    expect(publicById.get(categories.attachmentChild.id)?.is_attachment_category).toBe(true)
    expect(publicById.get(categories.attachmentDescendant.id)?.is_attachment_category).toBe(true)

    await openHomepage(page)
    await expect(categoryCard(page, categories.attachmentRoot)).toBeVisible()

    await selectRoot(page, categories.root)
    const attachmentSection = moduleFor(page).getByRole('heading', { name: 'Варианты надстроек', exact: true }).locator('..')
    await expect(attachmentSection).toContainText(categories.attachmentChild.name)
    await expect(moduleFor(page).getByRole('heading', { name: 'Категории', exact: true }).locator('..')).toContainText(categories.siblingA.name)
    await categoryCard(page, categories.attachmentChild).click()
    await waitForCatalog(page)

    const breadcrumbs = moduleFor(page).getByRole('navigation', { name: 'Путь по каталогу' })
    await expect(breadcrumbs).toContainText(categories.root.name)
    await expect(breadcrumbs).toContainText(categories.attachmentChild.name)
    await expect(breadcrumbs).not.toContainText(categories.attachmentRoot.name)
    await expect(resultsFor(page).getByRole('heading', { name: categories.attachmentChild.name, exact: true })).toBeVisible()
    await expect(resultsFor(page).getByRole('search')).toBeVisible()
    await expect(moduleFor(page).getByRole('heading', { name: 'Варианты надстроек', exact: true }).locator('..'))
      .toContainText(categories.attachmentDescendant.name)
    await categoryCard(page, categories.attachmentDescendant).click()
    await waitForCatalog(page)
    await expect(breadcrumbs).toContainText(categories.attachmentChild.name)
    await expect(breadcrumbs).toContainText(categories.attachmentDescendant.name)
    await expect(resultsFor(page).getByRole('heading', { name: categories.attachmentDescendant.name, exact: true })).toBeVisible()

    await breadcrumbs.getByRole('button', { name: 'Каталог', exact: true }).click()
    await selectRoot(page, categories.attachmentRoot)
    await expect(moduleFor(page).getByRole('heading', { name: 'Варианты надстроек', exact: true }).locator('..'))
      .toContainText(categories.attachmentChild.name)
    await categoryCard(page, categories.attachmentChild).click()
    await waitForCatalog(page)
    await expect(breadcrumbs).toContainText(categories.attachmentRoot.name)
    await expect(breadcrumbs).toContainText(categories.attachmentChild.name)
    await expect(breadcrumbs).not.toContainText(categories.root.name)
    await categoryCard(page, categories.attachmentDescendant).click()
    await waitForCatalog(page)
    await expect(breadcrumbs).toContainText(categories.attachmentRoot.name)
    await expect(breadcrumbs).toContainText(categories.attachmentChild.name)
    await expect(breadcrumbs).toContainText(categories.attachmentDescendant.name)
    await moduleFor(page).getByRole('button', { name: 'Назад', exact: true }).click()
    await waitForCatalog(page)
    await expect(breadcrumbs).toContainText(categories.attachmentRoot.name)
    await expect(breadcrumbs).toContainText(categories.attachmentChild.name)
    await expect(breadcrumbs).not.toContainText(categories.attachmentDescendant.name)
  })

  test('browser cards expose all required Russian count forms', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-9', fr: 'FR-8', kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    const module = await openHomepage(page)
    let renderedText = await module.innerText()
    const roots = Object.values(categories).filter(category => category.parent_ids.length === 0)
    for (const root of roots) {
      await categoryCard(page, root).click()
      renderedText += `\n${await module.innerText()}`
      await module.getByRole('button', { name: 'Каталог', exact: true }).click()
    }

    const forms = new Map<number, RegExp>([
      [0, /Показать 0 (?:категорий|объявлений)/],
      [1, /Показать 1 (?:категорию|объявление)/],
      [2, /Показать 2 (?:категории|объявления)/],
      [5, /Показать 5 (?:категорий|объявлений)/],
      [11, /Показать 11 (?:категорий|объявлений)/],
      [21, /Показать 21 (?:категорию|объявление)/],
      [22, /Показать 22 (?:категории|объявления)/],
      [25, /Показать 25 (?:категорий|объявлений)/],
    ])
    for (const expression of forms.values()) expect(renderedText).toMatch(expression)
  })

  test('standalone catalog keeps active categories with zero announcements', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-2', fr: 'FR-12', kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    await page.goto(appUrl('/special-equipment'), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    await expect(page.getByRole('heading', { name: NEW_CATALOG_TITLE, exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: new RegExp(`^${escapeRegex(categories.emptyRoot.name)}(?:\\s|$)`) })).toBeVisible()

    const panel = page.locator('#special-equipment-results')
    await expect(panel).toHaveAttribute('aria-busy', 'false')
    await panel.getByRole('button', { name: /^Все фильтры/ }).click()
    const filters = page.getByRole('dialog', { name: 'Все фильтры', exact: true })
    await expect(filters).toBeVisible()
    const availability = filters.getByRole('group', { name: 'Наличие', exact: true })
    const available = availability.getByRole('checkbox', { name: /^В наличии(?:\s+\d+)?$/ })
    const onOrder = availability.getByRole('checkbox', { name: /^Под заказ(?:\s+\d+)?$/ })
    await expect(available).toBeChecked()
    await expect(onOrder).toBeChecked()
    await expect(filters.getByRole('button', { name: 'Сбросить фильтры', exact: true })).toHaveCount(0)

    const explicitAvailability = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.getAll('availability').join(',') === 'on_order'
    })
    await available.uncheck()
    expect((await explicitAvailability).ok()).toBeTruthy()
    const reset = filters.getByRole('button', { name: 'Сбросить фильтры', exact: true })
    await expect(reset).toBeVisible()

    const defaultAvailability = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === PRODUCTS_PATH
        && url.searchParams.getAll('availability').join(',') === 'available,on_order'
    })
    await reset.click()
    expect((await defaultAvailability).ok()).toBeTruthy()
    await expect(available).toBeChecked()
    await expect(onOrder).toBeChecked()
    await expect(reset).toHaveCount(0)
  })

  test('branch change resets filters and page, preserves sort, and does not duplicate requests', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-10', fr: 'FR-11', kind: 'full-stack' })
    const fixture = getE2EFixtureManifest()
    const { categories, prefix } = fixture
    await openHomepage(page)
    await selectRoot(page, categories.count25)
    await waitForCatalog(page)
    await resultsFor(page).locator('select:visible').first().selectOption('published_asc')
    await waitForCatalog(page)

    await resultsFor(page).getByRole('navigation', { name: 'Пагинация каталога' })
      .getByRole('button', { name: 'Страница 2', exact: true }).click()
    await waitForCatalog(page)
    await expect(resultsFor(page).getByRole('button', { name: 'Страница 2', exact: true })).toHaveAttribute('aria-current', 'page')

    const pageResetProducts = page.waitForRequest(request => requestTargetsPath(request, PRODUCTS_PATH, categories.emptyRoot))
    await moduleFor(page).getByRole('tab', { name: categories.emptyRoot.name, exact: true }).click()
    const pageResetUrl = new URL((await pageResetProducts).url())
    await waitForCatalog(page)
    expect(pageResetUrl.searchParams.get('page')).toBe('1')
    expect(pageResetUrl.searchParams.get('sort')).toBe('published_asc')

    await moduleFor(page).getByRole('tab', { name: categories.root.name, exact: true }).click()
    await waitForCatalog(page)
    const rootRequests: Request[] = []
    page.on('request', request => {
      if (requestTargetsPath(request, PRODUCTS_PATH, categories.root)) rootRequests.push(request)
    })

    const search = resultsFor(page).getByPlaceholder('Название, марка, модель или код')
    await search.fill(prefix)
    await search.press('Enter')
    await waitForCatalog(page)

    const filters = await openFilters(page)
    const filterByName = async (groupName: string, optionName: string): Promise<void> => {
      await filters.getByRole('button', {
        name: new RegExp(`^(Выбрать: ${groupName.toLocaleLowerCase('ru-RU')}|${groupName}: выбрано \\d+)$`),
      }).click()
      const dialog = page.getByRole('dialog', { name: groupName, exact: true })
      await expect(dialog).toBeVisible()
      await dialog.getByPlaceholder(`Найти: ${groupName.toLocaleLowerCase('ru-RU')}`).fill(optionName)
      await dialog.getByRole('checkbox', {
        name: new RegExp(`^${escapeRegex(optionName)}(?:\\s+\\d+)?$`),
      }).check()
      await dialog.getByRole('button', { name: 'Применить', exact: true }).click()
      await expect(dialog).toBeHidden()
      await waitForCatalog(page)
    }
    const markName = String((fixture.marks.kamaz as { name: string }).name)
    const modelName = String((fixture.models.kamaz1000 as { name: string }).name)
    const modificationName = String((fixture.modifications.baseWhite as { name: string }).name)
    const capacityName = String((fixture.attributes.capacity as { name: string }).name)

    await filterByName('Марка', markName)
    await filterByName('Модель', modelName)
    await filterByName('Модификация', modificationName)
    await filters.getByRole('group', { name: 'Наличие', exact: true })
      .getByRole('checkbox', { name: /^Под заказ(?:\s+\d+)?$/ }).uncheck()
    await waitForCatalog(page)
    const usedRadio = filters.getByRole('group', { name: 'Состояние', exact: true })
      .getByRole('radio', { name: /^С пробегом(?:\s+\d+)?$/ })
    await usedRadio.locator('..').click()
    await waitForCatalog(page)

    await filters.getByLabel('Минимальная стоимость').fill('1')
    await filters.getByLabel('Минимальная стоимость').press('Tab')
    await waitForCatalog(page)
    await filters.getByLabel('Максимальная стоимость').fill('20000000')
    await filters.getByLabel('Максимальная стоимость').press('Tab')
    await waitForCatalog(page)
    await filters.getByLabel('Минимум: Пробег, км').fill('1')
    await filters.getByLabel('Минимум: Пробег, км').press('Tab')
    await waitForCatalog(page)
    await filters.getByLabel('Максимум: Пробег, км').fill('200000')
    await filters.getByLabel('Максимум: Пробег, км').press('Tab')
    await waitForCatalog(page)
    await filters.getByRole('group', { name: new RegExp(escapeRegex(capacityName)) })
      .getByLabel(new RegExp(`Минимум: ${escapeRegex(capacityName)}`)).fill('1')
    await filters.getByRole('group', { name: new RegExp(escapeRegex(capacityName)) })
      .getByLabel(new RegExp(`Минимум: ${escapeRegex(capacityName)}`)).press('Tab')
    await waitForCatalog(page)

    const activeFilters = resultsFor(page).getByLabel('Активные фильтры')
    await expect(activeFilters.getByRole('button')).toHaveCount(10)
    await expect(activeFilters).toContainText(markName)
    await expect(activeFilters).toContainText(modelName)
    await expect(activeFilters).toContainText(modificationName)
    await expect(activeFilters).toContainText(capacityName)
    const filteredRootUrl = new URL(rootRequests.at(-1)!.url())
    for (const parameter of [
      'search', 'mark_id', 'model_id', 'modification_id', 'availability', 'condition',
      'price_min', 'price_max', 'mileage_min', 'mileage_max', 'attribute',
    ]) expect(filteredRootUrl.searchParams.has(parameter), `expected ${parameter} before branch change`).toBeTruthy()

    const observed: Request[] = []
    page.on('request', request => {
      if (requestTargetsPath(request, PRODUCTS_PATH, categories.emptyRoot)
        || requestTargetsPath(request, FACETS_PATH, categories.emptyRoot)) observed.push(request)
    })
    await moduleFor(page).getByRole('tab', { name: categories.emptyRoot.name, exact: true }).click()
    await waitForCatalog(page)

    await expect(search).toHaveValue('')
    await expect(resultsFor(page).locator('select:visible').first()).toHaveValue('published_asc')
    await expect(resultsFor(page).getByLabel('Активные фильтры')).toHaveCount(0)
    const products = observed.filter(request => new URL(request.url()).pathname === PRODUCTS_PATH)
    const facets = observed.filter(request => new URL(request.url()).pathname === FACETS_PATH)
    expect(products).toHaveLength(1)
    expect(facets).toHaveLength(1)
    for (const request of observed) {
      const url = new URL(request.url())
      for (const parameter of [
        'search', 'mark_id', 'model_id', 'modification_id', 'condition',
        'price_min', 'price_max', 'mileage_min', 'mileage_max', 'engine_hours_min',
        'engine_hours_max', 'attribute',
      ]) expect(url.searchParams.has(parameter), `${parameter} leaked into ${url.pathname}`).toBeFalsy()
      expect(url.searchParams.getAll('availability')).toEqual(['available', 'on_order'])
    }
    expect(new URL(products[0]!.url()).searchParams.get('page')).toBe('1')
    expect(new URL(products[0]!.url()).searchParams.get('sort')).toBe('published_asc')
  })

  test('desktop keyboard tabs wrap adjacent categories without horizontal scrolling', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-13', fr: ['FR-16', 'NFR-2'], kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)
    await selectRoot(page, categories.root)

    const active = moduleFor(page).getByRole('tab', { name: categories.root.name, exact: true })
    await active.focus()
    await page.keyboard.press('ArrowRight')
    const selected = moduleFor(page).getByRole('tab', { selected: true })
    await expect(selected).toBeFocused()
    await expect(selected).toHaveCount(1)
    const tabs = moduleFor(page).getByRole('navigation', { name: 'Соседние категории' })
    const tablist = tabs.getByRole('tablist')
    await expect(tablist).toHaveCSS('flex-wrap', 'wrap')
    const dimensions = await tabs.evaluate(element => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }))
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1)
    const rowPositions = await tablist.getByRole('tab').evaluateAll(tabs => (
      [...new Set(tabs.map(tab => Math.round(tab.getBoundingClientRect().top)))]
    ))
    expect(rowPositions.length).toBeGreaterThan(1)
  })

  test('the renamed catalog label is consistent in empty, SEO, catalog and product contexts', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', fr: 'FR-13', kind: 'full-stack' })
    const { categories } = getE2EFixtureManifest()
    const module = await openHomepage(page)
    await expect(page.locator('body')).not.toContainText(OLD_CATALOG_TITLE)
    await expect(page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: NEW_CATALOG_TITLE })).toBeVisible()

    await selectRoot(page, categories.emptyRoot)
    await waitForCatalog(page)
    await expect(resultsFor(page).getByRole('heading', { name: 'Ничего не найдено', exact: true })).toBeVisible()
    await expect(module.getByRole('heading', { name: NEW_CATALOG_TITLE, exact: true })).toBeVisible()
    await expect(module).not.toContainText(OLD_CATALOG_TITLE)

    await page.goto(appUrl('/special-equipment'), { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: NEW_CATALOG_TITLE }).first()).toBeVisible()
    await expect(page).toHaveURL(/\/special-equipment\/?$/)
    await expect(page).toHaveTitle(`${NEW_CATALOG_TITLE} — CarCraft Multileasing`)
    const metaDescription = page.locator('head meta[name="description"]')
    await expect(metaDescription).toHaveAttribute(
      'content',
      /Транспортные средства и специальная техника/,
    )
    expect(await metaDescription.getAttribute('content')).not.toContain(OLD_CATALOG_TITLE)
    await expect(page.locator('head')).not.toContainText(OLD_CATALOG_TITLE)

    await page.goto(appUrl('/'), { waitUntil: 'domcontentloaded' })
    await selectRoot(page, categories.root)
    await waitForCatalog(page)
    const details = resultsFor(page).getByRole('link', { name: 'Подробнее' }).first()
    await expect(details).toHaveAttribute('href', new RegExp(`/categories/${categories.root.path.map(escapeRegex).join('/')}/products/`))
    await details.click()
    await expect(page.getByRole('navigation', { name: 'Хлебные крошки' }).getByRole('link', { name: NEW_CATALOG_TITLE })).toBeVisible()
    await expect(page.locator('body')).not.toContainText(OLD_CATALOG_TITLE)
  })

  test('homepage query/cart state is isolated and each resource fingerprint is requested once', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: ['AC-15', 'AC-18'], fr: ['FR-9', 'FR-10', 'NFR-3'], kind: 'full-stack' })
    const { categories, prefix } = getE2EFixtureManifest()
    const requests: Request[] = []
    page.on('request', request => {
      const pathname = new URL(request.url()).pathname
      if (pathname === PRODUCTS_PATH || pathname === FACETS_PATH) requests.push(request)
    })
    await openHomepage(page)
    await selectRoot(page, categories.root)
    await waitForCatalog(page)

    for (const image of await moduleFor(page).locator('img').all()) await expect(image).toHaveAttribute('loading', 'lazy')
    const details = resultsFor(page).getByRole('link', { name: 'Подробнее' }).first()
    await expect(details).toHaveAttribute('href', /\/special-equipment\/categories\/.+\/products\//)
    const cartButton = resultsFor(page).locator('article').first().getByRole('button', { name: /корзин/ })
    await cartButton.click()
    await expect(cartButton).toHaveAttribute('aria-pressed', 'true')
    await expect(cartButton).toHaveAccessibleName('Убрать из корзины')

    await resultsFor(page).getByPlaceholder('Название, марка, модель или код').fill(prefix)
    await resultsFor(page).getByPlaceholder('Название, марка, модель или код').press('Enter')
    await page.goto(appUrl('/special-equipment'), { waitUntil: 'domcontentloaded' })
    await expect(page.getByPlaceholder('Название, марка, модель или код')).toHaveValue('')

    await page.goto(appUrl('/'), { waitUntil: 'domcontentloaded' })
    await expect(resultsFor(page)).toHaveCount(0)
    const branchRequests = requests.filter(request => requestTargetsPath(request, new URL(request.url()).pathname, categories.root))
    const fingerprints = branchRequests.map(request => request.url())
    expect(new Set(fingerprints).size).toBe(fingerprints.length)
  })

  test('fixture and traceability schemas are explicit executable contracts', async ({}, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: ['AC-16', 'AC-17'], fr: 'NFR-3', kind: 'contract-guard' })
    const fixture = getE2EFixtureManifest()
    expect(fixture.schema_version).toBe(1)
    expect(Object.keys(fixture.categories).sort()).toEqual([...E2E_CATEGORY_KEYS].sort())
    expect(Object.keys(fixture.products).sort()).toEqual([...E2E_PRODUCT_KEYS].sort())
    expect(REQUIRED_ACCEPTANCE_CRITERIA['21984']).toEqual(Array.from({ length: 18 }, (_, index) => `AC-${index + 1}`))

    const migrationsDirectory = resolve(process.cwd(), '../backend/alembic/versions')
    const migrationFiles = readdirSync(migrationsDirectory).filter(name => /^\d{3}_.+\.py$/.test(name)).sort()
    expect(migrationFiles.filter(name => name.includes('21984'))).toEqual([])
    expect(migrationFiles.filter(name => readFileSync(resolve(migrationsDirectory, name), 'utf8').includes('21984'))).toEqual([])
    expect(migrationFiles).toContain('087_special_equipment_idempotency_snapshot.py')
    expect(readFileSync(resolve(migrationsDirectory, '086_special_equipment_attachments.py'), 'utf8'))
      .toContain('special_equipment_product_attachments')
    expect(readFileSync(resolve(migrationsDirectory, '087_special_equipment_idempotency_snapshot.py'), 'utf8'))
      .toContain('response_snapshot')

    const homepageModule = readFileSync(
      resolve(process.cwd(), 'features/specialEquipment/components/SpecialEquipmentHomepageModule.vue'),
      'utf8',
    )
    const catalogPage = readFileSync(
      resolve(process.cwd(), 'features/specialEquipment/components/SpecialEquipmentCatalogPage.vue'),
      'utf8',
    )
    for (const source of [homepageModule, catalogPage]) {
      expect(source).toContain("import SpecialEquipmentCatalogPanel from './SpecialEquipmentCatalogPanel.vue'")
      expect(source).toContain('<SpecialEquipmentCatalogPanel')
      expect(source).not.toContain('api.getProducts(')
      expect(source).not.toContain('api.getFacets(')
    }
  })
})

test.describe('Bitrix 21984 · authenticated catalog label', () => {
  test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })

  test('section counters are visible on first load without visiting tabs', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', kind: 'full-stack' })
    const sections = [
      ['products', 'Объявления'],
      ['categories', 'Категории'],
      ['marks', 'Марки'],
      ['models', 'Модели'],
      ['modifications', 'Модификации'],
      ['trims', 'Комплектации'],
      ['attributes', 'Характеристики'],
      ['attribute_groups', 'Группы характеристик'],
      ['colors', 'Цвета'],
    ] as const

    const countsResponsePromise = page.waitForResponse(response =>
      response.request().method() === 'GET'
      && new URL(response.url()).pathname === '/api/v1/admin/special-equipment/section-counts')
    await page.goto(appUrl('/workspace/special-equipment-catalog?section=products'), { waitUntil: 'domcontentloaded' })
    const countsResponse = await countsResponsePromise
    expect(countsResponse.status()).toBe(200)
    const counts = await countsResponse.json() as Record<string, unknown>
    const navigation = page.getByRole('navigation', { name: 'Разделы каталога' })
    await expect(navigation.getByRole('button')).toHaveCount(sections.length)
    await expect(navigation.getByRole('button', { name: /^Объявления/ })).toHaveAttribute('aria-current', 'page')

    for (const [key, label] of sections) {
      const value = counts[key]
      expect(typeof value, `section count ${key}`).toBe('number')
      const tab = navigation.getByRole('button').filter({ hasText: label })
      await expect(tab.getByText(String(value), { exact: true })).toBeVisible()
    }
  })

  test('admin catalog uses the same renamed label without changing its route', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', fr: 'FR-13', kind: 'full-stack' })
    await page.goto(appUrl('/workspace/special-equipment-catalog'), { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/\/workspace\/special-equipment-catalog\/?$/)
    await expect(page.getByText(NEW_CATALOG_TITLE, { exact: true }).first()).toBeVisible()
    await expect(page.locator('body')).not.toContainText(OLD_CATALOG_TITLE)
  })

  test('характеристика select в админке отображается как выбор из вариантов', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-14', kind: 'full-stack' })
    const attribute = getE2EFixtureManifest().attributes.color
    if (!attribute || typeof attribute !== 'object' || !('name' in attribute) || typeof attribute.name !== 'string') {
      throw new Error('E2E fixture attributes.color must contain a string name')
    }
    await page.goto(appUrl(
      `/workspace/special-equipment-catalog?section=attributes&q=${encodeURIComponent(attribute.name)}`,
    ), { waitUntil: 'domcontentloaded' })
    await page.locator('.se-entity-name:visible').first().click()
    const drawer = page.locator('.se-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()
    const dataType = drawer.getByLabel(/^Тип значения/)
    await expect(dataType).toHaveValue('select')
    await expect(dataType.locator('option:checked')).toHaveText('Выбор из вариантов')
    await expect(drawer.getByRole('group', { name: 'Варианты значения' })).toBeVisible()
  })
})

test.describe('Bitrix 21984 · deterministic fault injection', () => {
  test('category proxy image is decoded after 200 and a 404 switches to a stable fallback', async ({ page, context }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-2', fr: ['FR-1'], kind: 'fault-injection' })
    await page.goto(appUrl('/'), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const publicApiBase = await page.evaluate(() => String((window as typeof window & {
      __NUXT__?: { config?: { public?: { apiBase?: string } } }
    }).__NUXT__?.config?.public?.apiBase || window.location.origin))
    const categoriesResponse = await page.request.get(new URL(
      '/api/v1/special-equipment/categories',
      publicApiBase,
    ).toString())
    expect(categoriesResponse.ok()).toBeTruthy()
    const payload = await categoriesResponse.json() as ApiCategoriesResponse
    const publishedIds = new Set(payload.items.map(category => category.id))
    const roots = payload.items.filter(category => category.parent_ids.every(parentId => !publishedIds.has(parentId)))
    expect(roots.length).toBeGreaterThanOrEqual(2)
    const successCategory = roots[0]!
    const missingCategory = roots[1]!
    const successUrl = `/api/v1/special-equipment/categories/${successCategory.id}/image/content`
    const missingUrl = `/api/v1/special-equipment/categories/${missingCategory.id}/image/content`
    const injected = {
      ...payload,
      items: payload.items.map(category => ({
        ...category,
        image_url: category.id === successCategory.id
          ? successUrl
          : category.id === missingCategory.id
            ? missingUrl
            : category.image_url,
      })),
    }
    const validPng = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl5ZegAAAAASUVORK5CYII=',
      'base64',
    )
    const mediaResponses: Array<{ url: string, status: number, contentType: string }> = []
    page.on('response', (response) => {
      if (!response.url().includes('/image/content')) return
      mediaResponses.push({
        url: response.url(),
        status: response.status(),
        contentType: response.headers()['content-type'] ?? '',
      })
    })
    await page.route('**/api/v1/special-equipment/categories', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(injected),
    }))
    await page.route('**/api/v1/special-equipment/categories/*/image/content', async (route) => {
      if (route.request().url().includes(successCategory.id)) {
        await route.fulfill({ status: 200, contentType: 'image/png', body: validPng })
        return
      }
      await route.fulfill({
        status: 404,
        contentType: 'application/problem+json',
        body: '{"detail":"injected missing image"}',
      })
    })

    const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1'
    await context.addCookies([{ name: 'e2e_fault_categories', value: '1', url: baseURL }])
    await page.goto(appUrl('/'), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const error = moduleFor(page).getByRole('alert').filter({ hasText: 'Не удалось загрузить категории' })
    await expect(error).toBeVisible()
    await context.clearCookies({ name: 'e2e_fault_categories' })
    expect((await context.cookies(baseURL)).some(cookie => cookie.name === 'e2e_fault_categories')).toBe(false)
    const retryResponsePromise = page.waitForResponse(response =>
      new URL(response.url()).pathname === '/api/v1/special-equipment/categories')
    await error.getByRole('button', { name: 'Повторить' }).click()
    expect((await retryResponsePromise).status()).toBe(200)
    await expect(error).toHaveCount(0)

    const successCard = categoryCard(page, successCategory)
    const missingCard = categoryCard(page, missingCategory)
    const successMedia = successCard.locator('span.relative.aspect-\\[3\\/2\\]').first()
    const missingMedia = missingCard.locator('span.relative.aspect-\\[3\\/2\\]').first()
    const successBefore = await successMedia.boundingBox()
    const missingBefore = await missingMedia.boundingBox()
    await successCard.scrollIntoViewIfNeeded()
    const image = successCard.locator('img')
    await expect.poll(() => image.evaluate(element => ({
      complete: (element as HTMLImageElement).complete,
      width: (element as HTMLImageElement).naturalWidth,
      height: (element as HTMLImageElement).naturalHeight,
      opacity: getComputedStyle(element).opacity,
    }))).toEqual({ complete: true, width: 1, height: 1, opacity: '1' })
    await missingCard.scrollIntoViewIfNeeded()
    await expect(missingCard.locator('img')).toHaveCount(0)
    await expect(missingCard.locator('svg').first()).toBeVisible()
    expectStableElementSize(successBefore, await successMedia.boundingBox())
    expectStableElementSize(missingBefore, await missingMedia.boundingBox())
    expect(mediaResponses.find(item => item.url.includes(successCategory.id))).toMatchObject({
      status: 200,
      contentType: 'image/png',
    })
    expect(mediaResponses.find(item => item.url.includes(missingCategory.id))).toMatchObject({
      status: 404,
    })
  })

  test('independent delayed products and facets expose skeletons and aria-busy', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-4', fr: ['FR-14', 'NFR-2'], kind: 'fault-injection' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)
    const products = await deferNextRequest(page, PRODUCTS_PATH, categories.root, 'continue')
    const facets = await deferNextRequest(page, FACETS_PATH, categories.root, 'continue')
    await categoryCard(page, categories.root).click()
    await Promise.all([products.started, facets.started])

    await expect(resultsFor(page)).toHaveAttribute('aria-busy', 'true')
    await expect(resultsFor(page).getByLabel('Загрузка объявлений')).toBeVisible()
    await expect(resultsFor(page).getByLabel('Загрузка фильтров').first()).toBeVisible()
    products.release()
    facets.release()
    await waitForCatalog(page)
  })

  for (const endpoint of [PRODUCTS_PATH, FACETS_PATH] as const) {
    const resource = endpoint === PRODUCTS_PATH ? 'products' : 'facets'
    for (const outcome of ['continue', 'abort'] as const) {
      test(`stale ${resource} ${outcome === 'continue' ? 'success' : 'error'} cannot overwrite the new branch`, async ({ page }, testInfo) => {
        annotateTraceability(testInfo, { task: '21984', ac: 'AC-11', fr: 'NFR-1', kind: 'fault-injection' })
        const { categories } = getE2EFixtureManifest()
        await openHomepage(page)
        const deferred = await deferNextRequest(page, endpoint, categories.root, outcome)
        await categoryCard(page, categories.root).click()
        await deferred.started
        await moduleFor(page).getByRole('tab', { name: categories.emptyRoot.name, exact: true }).click()
        await waitForCatalog(page)
        const staleFinished = outcome === 'continue'
          ? page.waitForResponse(response => requestTargetsPath(response.request(), endpoint, categories.root))
          : page.waitForEvent('requestfailed', request => requestTargetsPath(request, endpoint, categories.root))
        deferred.release()
        await staleFinished

        await expect(resultsFor(page).getByRole('heading', { name: categories.emptyRoot.name, exact: true })).toBeVisible()
        await expect(resultsFor(page).getByRole('heading', { name: categories.root.name, exact: true })).toHaveCount(0)
        await expect(resultsFor(page).getByRole('alert')).toHaveCount(0)
      })
    }
  }

  test('products failure is localized and Retry returns to the real backend', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-12', fr: 'FR-15', kind: 'fault-injection' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)
    const failure = await failRequestsUntilReleased(page, PRODUCTS_PATH, categories.root)
    await selectRoot(page, categories.root)
    await failure.started
    const error = resultsFor(page).getByRole('alert').filter({ hasText: 'Не удалось загрузить каталог' })
    await expect(error).toBeVisible()
    failure.release()
    await error.getByRole('button', { name: 'Повторить' }).click()
    await waitForCatalog(page)
    await expect(error).toHaveCount(0)
  })

  test('facets failure and Retry are localized in the catalog filters', async ({ page }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-12', fr: 'FR-15', kind: 'fault-injection' })
    const { categories } = getE2EFixtureManifest()
    await openHomepage(page)
    const failure = await failRequestsUntilReleased(page, FACETS_PATH, categories.root)
    await selectRoot(page, categories.root)
    await failure.started

    const error = resultsFor(page).getByRole('alert').filter({ hasText: 'Не удалось загрузить фильтры' })
    await expect(error).toBeVisible()
    failure.release()
    await error.getByRole('button', { name: 'Повторить' }).click()
    await expect(error).toHaveCount(0)
    await expect(resultsFor(page).getByRole('heading', { name: categories.root.name, exact: true })).toBeVisible()
  })

  test('category SSR failure is localized and Retry returns to the real backend', async ({ page, context }, testInfo) => {
    annotateTraceability(testInfo, { task: '21984', ac: 'AC-12', fr: 'FR-15', kind: 'fault-injection' })
    const { categories } = getE2EFixtureManifest()
    const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1'
    await context.addCookies([{ name: 'e2e_fault_categories', value: '1', url: baseURL }])
    await page.goto(appUrl('/'), { waitUntil: 'domcontentloaded' })
    await waitForNuxtHydration(page)
    const error = moduleFor(page).getByRole('alert').filter({ hasText: 'Не удалось загрузить категории' })
    await expect(error).toBeVisible()
    await expect(resultsFor(page)).toHaveCount(0)

    await context.clearCookies({ name: 'e2e_fault_categories' })
    expect((await context.cookies(baseURL)).some(cookie => cookie.name === 'e2e_fault_categories')).toBe(false)
    const retryResponsePromise = page.waitForResponse(response =>
      new URL(response.url()).pathname === '/api/v1/special-equipment/categories')
    await error.getByRole('button', { name: 'Повторить' }).click()
    expect((await retryResponsePromise).status()).toBe(200)
    await expect(categoryCard(page, categories.root)).toBeVisible()
    await expect(error).toHaveCount(0)
  })
})
