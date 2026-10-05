import { expect, test } from '@playwright/test'
import { appUrl } from './support/runtime'
import { annotateTraceability } from './support/traceability'

const LEGACY_CATEGORY_ID = '21954000-0000-5000-8000-000000000001'
const LEGACY_PRODUCT_ID = '21954000-0000-5000-8000-000000000005'
const LEGACY_PRODUCT_CODE = 'E2E_21954_PRODUCT'

test('AC-24: migrated legacy catalog row works through public API and Nuxt', async ({ page, request }, testInfo) => {
  test.skip(process.env.E2E_BACKFILL_SMOKE !== 'true', 'Runner owns the disposable migrated legacy row')
  annotateTraceability(testInfo, { task: '21954', ac: 'AC-24', kind: 'full-stack' })

  const categoriesResponse = await request.get('/api/v1/special-equipment/categories')
  expect(categoriesResponse.ok()).toBeTruthy()
  const categories = await categoriesResponse.json() as { items: Array<Record<string, unknown>> }
  expect(categories.items).toContainEqual(expect.objectContaining({
    id: LEGACY_CATEGORY_ID,
    is_attachment_category: false,
  }))

  const productsResponse = await request.get('/api/v1/special-equipment/products', {
    params: { search: LEGACY_PRODUCT_CODE },
  })
  expect(productsResponse.ok()).toBeTruthy()
  const products = await productsResponse.json() as { items: Array<Record<string, unknown>> }
  expect(products.items).toContainEqual(expect.objectContaining({
    id: LEGACY_PRODUCT_ID,
    code: LEGACY_PRODUCT_CODE,
    available_count: 1,
  }))

  await page.goto(appUrl('/special-equipment'), { waitUntil: 'domcontentloaded' })
  const search = page.getByPlaceholder('Название, марка, модель или код')
  await search.fill(LEGACY_PRODUCT_CODE)
  await search.press('Enter')
  const details = page.getByRole('link', { name: 'Подробнее' }).first()
  await expect(details).toHaveAttribute('href', new RegExp(`/products/${LEGACY_PRODUCT_ID}/`))
  await details.click()
  await expect(page).toHaveURL(new RegExp(`/products/${LEGACY_PRODUCT_ID}/`))
  await expect(page.locator('main').last()).toContainText('E2E 21954 Modification')
})
