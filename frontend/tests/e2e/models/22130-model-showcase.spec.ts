import {
  expect,
  test,
} from '@playwright/test'

import { appUrl } from '../special-equipment/support/runtime'

test.describe('E02 — Отсутствие устаревших страниц /cars и /models (404)', () => {
  test.beforeEach(async ({}, testInfo) => {
    test.skip(
      testInfo.project.name !== 'desktop-chromium',
      'Проверяется только в desktop browser',
    )
  })

  const legacyPaths = [
    '/cars',
    '/cars/some-legacy-car-id',
    '/models',
    '/models/some-legacy-brand-id',
    '/quality/cars',
    '/quality/cars/some-legacy-car-id',
    '/quality/models',
    '/quality/models/some-legacy-brand-id',
  ]

  for (const path of legacyPaths) {
    test(`переход на ${path} возвращает 404 без показа старого каталога`, async ({ page }) => {
      const response = await page.goto(appUrl(path), { waitUntil: 'domcontentloaded' })
      expect(response?.status()).toBe(404)
      await expect(page.locator('body')).toContainText('404')
      await expect(page.locator('section[aria-labelledby="model-showcase-heading"]')).toHaveCount(0)
      await expect(page.locator('section[aria-labelledby="model-brands-heading"]')).toHaveCount(0)
      await expect(page.locator('[data-storefront-block="cars.card"]')).toHaveCount(0)
    })
  }
})
