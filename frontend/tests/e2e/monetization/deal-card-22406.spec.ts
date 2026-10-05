import { readFileSync } from 'node:fs'
import { expect, test, type Browser } from '@playwright/test'

type Role = 'admin' | 'dealer' | 'leasing' | 'distributor' | 'outsider'
interface Fixture {
  marker: string; base_url: string; storage_states: Record<Role, string>
  deal_id: string; application_id: string; application_number: string
  exchange_deal_id: string; exchange_request_id: string; leasing_company_id: string
  companies: Record<string, { id: string; company_id: string; name: string }>
}
const enabled = process.env.MONETIZATION_DEAL_CARD_E2E === '1'
const fixture: Fixture | null = enabled
  ? JSON.parse(readFileSync(process.env.MONETIZATION_DEAL_CARD_FIXTURE ?? '/tmp/carcraft-22406-e2e/deal-card.manifest.json', 'utf8')) : null
if (fixture && (fixture.marker !== 'monetization-22406-deal-card' || !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(fixture.base_url))) throw new Error('Use isolated task 22406 fixtures')
test.skip(!enabled, 'Requires isolated task 22406 app')

async function session(browser: Browser, role: Role, width = 1440) {
  const context = await browser.newContext({ baseURL: fixture!.base_url, storageState: fixture!.storage_states[role], viewport: { width, height: 1000 } })
  const page = await context.newPage()
  return { context, page }
}

for (const width of [768, 1440]) {
  test('dealer sees only recipients of own expense at ' + width + 'px', async ({ browser }) => {
    const { context, page } = await session(browser, 'dealer', width)
    try {
      await page.goto('/workspace/monetization?deal=' + fixture!.deal_id)
      const modal = page.getByRole('dialog')
      await expect(modal.locator('.expense-amount')).toHaveCount(1)
      await expect(modal.locator('.deal-incomes .deal-amount')).toHaveCount(3)
      await expect(modal.locator('.deal-incomes')).toContainText('Платформа МЛ (Доход)')
      await expect(modal.locator('.deal-incomes')).toContainText('Лизинговая компания (Доход)')
      await expect(modal.locator('.deal-incomes')).toContainText('Дистрибьютор (Доход)')
      await expect(modal.locator('.deal-incomes')).toContainText(fixture!.companies.leasing_company!.name)
      await expect(modal.locator('.deal-incomes')).toContainText(fixture!.companies.distributor!.name)
      await expect(modal.getByRole('button', { name: 'Изменить суммы', exact: true })).toHaveCount(0)
      expect(await modal.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    } finally { await context.close() }
  })
}

for (const role of ['admin', 'dealer', 'leasing', 'distributor'] as const) {
  test(role + ' opens the linked platform application', async ({ browser }) => {
    const { context, page } = await session(browser, role)
    try {
      const companyContext = role === 'admin' ? '' : '&notification_company_id=' + fixture!.companies[role === 'leasing' ? 'leasing_company' : role]!.company_id
      await page.goto('/workspace/monetization?deal=' + fixture!.deal_id + companyContext)
      const link = page.getByRole('dialog').getByRole('link', { name: 'Перейти к заявке', exact: true })
      await expect(link).toBeVisible()
      const response = page.waitForResponse(item => item.request().method() === 'GET'
        && item.url().includes(fixture!.application_id) && item.url().includes('/api/v1/')
        && !item.url().includes('/monetization/'))
      await link.click()
      expect((await response).status()).toBe(200)
      if (role === 'leasing') {
        await expect(page).toHaveURL(new RegExp('/workspace/leasing-applications/' + fixture!.application_id))
        expect(new URL(page.url()).searchParams.get('leasing_company_id')).toBe(fixture!.leasing_company_id)
      } else {
        await expect(page).toHaveURL(new RegExp('/workspace/applications\\?.*application=' + fixture!.application_id))
        if (role === 'admin') await expect(page.getByRole('button', { name: 'Закрыть переход', exact: true })).toBeVisible()
        else await expect(page.getByText('Детальная информация по заявке', { exact: true })).toBeVisible()
      }
      await expect(page.getByText(new RegExp(fixture!.application_number)).first()).toBeVisible()
    } finally { await context.close() }
  })

  test(role === 'admin' ? 'admin has no exchange link' : role + ' opens the linked exchange request', async ({ browser }) => {
    const { context, page } = await session(browser, role)
    try {
      await page.goto('/workspace/monetization?deal=' + fixture!.exchange_deal_id)
      await expect(page.getByRole('dialog')).toBeVisible()
      const link = page.getByRole('dialog').getByRole('link', { name: 'Перейти к заявке', exact: true })
      if (role === 'admin') {
        await expect(link).toHaveCount(0)
        return
      }
      await expect(link).toBeVisible()
      const response = page.waitForResponse(item => item.request().method() === 'GET'
        && item.url().includes('/api/v1/exchange/') && item.url().includes(fixture!.exchange_request_id))
      await link.click()
      expect((await response).status()).toBe(200)
      await expect(page).toHaveURL(new RegExp('/workspace/exchange\\?.*request=' + fixture!.exchange_request_id))
      await expect(page.getByText('Заявка № 2226801-1', { exact: true })).toBeVisible()

    } finally { await context.close() }
  })
}

test('existing exchange ownership permissions remain unchanged', async ({ browser }) => {
  const { context } = await session(browser, 'admin')
  const dealer = await session(browser, 'dealer')
  try {
    const endpoint = '/api/v1/exchange/requests/' + fixture!.exchange_request_id
    const response = await context.request.get(endpoint)
    expect(response.status()).toBe(403)
    expect((await dealer.context.request.get(endpoint)).status()).toBe(403)
  } finally { await context.close(); await dealer.context.close() }
})
