import { expect, test, type Page } from '@playwright/test'
import { getE2EFixtureManifest } from './support/fixtures'
import { appUrl } from './support/runtime'

interface ApiCategoryLink {
  id: string
  code: string
  name: string
  slug: string
}

interface ApiProductItem {
  id: string
  terminal_category: ApiCategoryLink | null
  categories?: ApiCategoryLink[]
  [key: string]: unknown
}

interface ApiProductsResponse {
  items: ApiProductItem[]
  [key: string]: unknown
}

interface ApiProductDetailResponse {
  id: string
  terminal_category: ApiCategoryLink | null
  categories?: ApiCategoryLink[]
  [key: string]: unknown
}

const waitForNuxtHydration = async (page: Page): Promise<void> => {
  await page.waitForFunction(() => Boolean(
    (document.querySelector('#__nuxt') as HTMLElement & { __vue_app__?: unknown } | null)?.__vue_app__,
  ), undefined, { timeout: 10_000 })
}

const waitForCatalogLoad = async (page: Page): Promise<void> => {
  const results = page.locator('#special-equipment-results')
  await expect(results).toBeVisible()
  await expect(results).toHaveAttribute('aria-busy', 'false')
}

test.describe('Special Equipment — Card Terminal Category (specs/task_2026-09-28_16-34-56_MSK.md)', () => {
  test('1. GET /api/v1/special-equipment/products?category_path=<root> resolves leaf terminal category', async ({ request }) => {
    const fixture = getE2EFixtureManifest()
    const response = await request.get(
      `/api/v1/special-equipment/products?category_path=${fixture.categories.root.slug}`,
    )
    expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
    const data = (await response.json()) as ApiProductsResponse
    const representative = data.items.find(item => item.id === fixture.products.representative.id)
    expect(representative, 'representative product must be present in items').toBeDefined()
    expect(representative?.terminal_category?.id).toBe(fixture.categories.leaf.id)
    expect(representative?.terminal_category?.name).toBe(fixture.categories.leaf.name)
  })

  test('2. GET /api/v1/special-equipment/products?category_path=<dagParentA>/<shared> resolves leaf terminal category via DAG', async ({ request }) => {
    const fixture = getE2EFixtureManifest()
    const response = await request.get(
      `/api/v1/special-equipment/products?category_path=${fixture.categories.dagParentA.slug}/${fixture.categories.shared.slug}`,
    )
    expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
    const data = (await response.json()) as ApiProductsResponse
    const representative = data.items.find(item => item.id === fixture.products.representative.id)
    expect(representative, 'representative product must be present in items').toBeDefined()
    expect(representative?.terminal_category?.id).toBe(fixture.categories.leaf.id)
    expect(representative?.terminal_category?.name).toBe(fixture.categories.leaf.name)
  })

  test('3. GET /api/v1/special-equipment/products?category_path=<root>/<leaf> preserves leaf terminal category', async ({ request }) => {
    const fixture = getE2EFixtureManifest()
    const response = await request.get(
      `/api/v1/special-equipment/products?category_path=${fixture.categories.root.slug}/${fixture.categories.leaf.slug}`,
    )
    expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
    const data = (await response.json()) as ApiProductsResponse
    const representative = data.items.find(item => item.id === fixture.products.representative.id)
    expect(representative, 'representative product must be present in items').toBeDefined()
    expect(representative?.terminal_category?.id).toBe(fixture.categories.leaf.id)
    expect(representative?.terminal_category?.name).toBe(fixture.categories.leaf.name)
  })

  test('4. GET /api/v1/special-equipment/products without category resolves leaf terminal category', async ({ request }) => {
    const fixture = getE2EFixtureManifest()
    const response = await request.get('/api/v1/special-equipment/products')
    expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
    const data = (await response.json()) as ApiProductsResponse
    const representative = data.items.find(item => item.id === fixture.products.representative.id)
    expect(representative, 'representative product must be present in items').toBeDefined()
    expect(representative?.terminal_category?.id).toBe(fixture.categories.leaf.id)
    expect(representative?.terminal_category?.name).toBe(fixture.categories.leaf.name)
  })

  test('5. GET /api/v1/special-equipment/products/{id}?category_path=<root> resolves leaf terminal category', async ({ request }) => {
    const fixture = getE2EFixtureManifest()
    const response = await request.get(
      `/api/v1/special-equipment/products/${fixture.products.representative.id}?category_path=${fixture.categories.root.slug}`,
    )
    expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
    const product = (await response.json()) as ApiProductDetailResponse
    expect(product.terminal_category?.id).toBe(fixture.categories.leaf.id)
    expect(product.terminal_category?.name).toBe(fixture.categories.leaf.name)
  })

  test('6. UI: card in root category displays terminal leaf category and detail page preserves it with root breadcrumbs', async ({ page }) => {
    const fixture = getE2EFixtureManifest()

    // 1. Desktop viewport 1280x800
    await page.setViewportSize({ width: 1280, height: 800 })

    // 2. Navigate to /special-equipment/categories/${fixture.categories.root.slug}
    await page.goto(
      appUrl(`/special-equipment/categories/${fixture.categories.root.slug}`),
      { waitUntil: 'domcontentloaded' },
    )

    // 3. Wait for hydration and catalog load
    await waitForNuxtHydration(page)
    await waitForCatalogLoad(page)

    // 4. Find the card for representative
    const card = page
      .locator('[data-storefront-block="equipment.card"]')
      .filter({
        has: page.locator(`a[href*="/products/${fixture.products.representative.id}"]`),
      })
    await expect(card).toBeVisible()

    // 5. Verify that on the card the category label displays "Конечная категория" (case-insensitive),
    // and does NOT display "Корневой каталог"
    const categoryLabel = card.locator('.pr-12 > p.uppercase').first()
    await expect(categoryLabel).toBeVisible()
    await expect(categoryLabel).toHaveText(new RegExp(`^${fixture.categories.leaf.name}$`, 'i'))
    await expect(categoryLabel).not.toHaveText(new RegExp(fixture.categories.root.name, 'i'))
    await expect(card).not.toContainText(fixture.categories.root.name)

    // 6. Click the product link / card to open the detail page
    const productLink = card
      .locator(`a[href*="/products/${fixture.products.representative.id}"]`)
      .first()
    await productLink.click()

    // 7. On the product detail page:
    await waitForNuxtHydration(page)
    await page.waitForURL(new RegExp(`/categories/${fixture.categories.root.slug}`))

    // Verify that under [data-testid="detail-basic-parameters"], the "Категория" parameter has value "Конечная категория"
    const basicParameters = page.locator('[data-testid="detail-basic-parameters"]')
    await expect(basicParameters).toBeVisible()
    const categoryRow = basicParameters.locator('div').filter({
      has: page.locator('dt', { hasText: 'Категория' }),
    })
    await expect(categoryRow).toBeVisible()
    await expect(categoryRow.locator('dd')).toHaveText(fixture.categories.leaf.name)

    // Verify that the breadcrumbs (nav[aria-label="Хлебные крошки"]) contain "Корневой каталог"
    const breadcrumbs = page.locator('nav[aria-label="Хлебные крошки"]')
    await expect(breadcrumbs).toBeVisible()
    await expect(breadcrumbs).toContainText(fixture.categories.root.name)

    // Verify that the page URL includes /categories/${fixture.categories.root.slug}
    expect(page.url()).toContain(`/categories/${fixture.categories.root.slug}`)
  })
})
