import { expect, test, type APIRequestContext } from '@playwright/test'

test.use({
  baseURL: 'http://localhost',
})

const authenticate = async (
  request: APIRequestContext,
  phone: string,
): Promise<void> => {
  const login = await request.post('/api/v1/auth/login', { data: { phone } })
  expect([200, 403]).toContain(login.status())
  const verification = await request.post('/api/v1/auth/verify-phone', {
    data: { phone, code: '0000' },
  })
  expect(verification.status()).toBe(200)
}

test.describe('Сокрытие раздела Профиль для роли carcraft_employee', () => {
  test('carcraft_employee не видит профиль в sidebar и dropdown, и редиректится при прямом переходе', async ({
    page,
  }) => {
    await authenticate(page.request, '+76660000001')

    await page.goto('/workspace', { waitUntil: 'networkidle' })

    const workspaceNav = page.getByRole('navigation', {
      name: 'Навигация рабочего кабинета',
    })
    await expect(workspaceNav).toBeVisible()
    await expect(workspaceNav.getByRole('link', { name: 'Профиль' })).toHaveCount(0)

    const userMenuContainer = page.locator('[data-storefront-block="client.auth"]')
    await expect(userMenuContainer).toBeVisible()
    await userMenuContainer.locator('button').click()
    await expect(userMenuContainer.getByRole('link', { name: 'Профиль' })).toHaveCount(0)

    await page.goto('/workspace/profile', { waitUntil: 'networkidle' })
    expect(page.url()).not.toContain('/workspace/profile')
  })

  test('dealer видит профиль в sidebar и dropdown, и может открыть /workspace/profile', async ({
    page,
  }) => {
    await authenticate(page.request, '+76660000003')

    await page.goto('/workspace', { waitUntil: 'networkidle' })

    const workspaceNav = page.getByRole('navigation', {
      name: 'Навигация рабочего кабинета',
    })
    await expect(workspaceNav).toBeVisible()
    await expect(workspaceNav.getByRole('link', { name: 'Профиль' })).toBeVisible()

    const userMenuContainer = page.locator('[data-storefront-block="client.auth"]')
    await expect(userMenuContainer).toBeVisible()
    await userMenuContainer.locator('button').click()
    await expect(userMenuContainer.getByRole('link', { name: 'Профиль' })).toBeVisible()

    await page.goto('/workspace/profile', { waitUntil: 'networkidle' })
    await expect(page).toHaveURL(/\/workspace\/profile/)
    await expect(page.getByRole('heading', { name: 'Профиль дилера' })).toBeVisible()
  })
})
