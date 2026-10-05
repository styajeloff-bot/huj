import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

const runtimeDir = '/tmp/carcraft-notifications35-followup-v2-runtime'
const baseURL = 'http://localhost:18048'
interface Fixture {
  marker: string
  company_id: string
  storefront_slug: string
  applications: Record<'preliminary' | 'documents' | 'final', string>
  events: Record<'preliminary' | 'documents' | 'final' | 'final_other', string>
}
interface Notice { id: string; action_url: string; data: { event_id: string } | null }
function manifest() {
  const state = JSON.parse(readFileSync(`${runtimeDir}/fixtures.secret.json`, 'utf8')) as {
    marker: string; companies: Record<string, string>; users: { client: { email: string } }; context_acceptance: Fixture
  }
  if (process.env.NOTIFICATIONS35_E2E !== '1' || state.marker !== 'tz35-runtime'
    || state.users.client.email !== 'client@notifications35.test'
    || state.context_acceptance?.marker !== 'tz35-context-acceptance'
    || !state.context_acceptance.storefront_slug.startsWith('tz35-context-')) throw new Error('Owned context fixture required')
  return state
}
function permissions(mode: 'context-revoke' | 'context-restore') {
  const compose = resolve('../scripts/e2e/notifications35/compose.yml')
  if (!process.env.NOTIFICATIONS35_COMPOSE || resolve(process.env.NOTIFICATIONS35_COMPOSE) !== compose) throw new Error('Explicit local compose required')
  execFileSync('docker', ['compose', '-p', 'carcraft-notifications35-followup-v2', '-f', compose,
    'exec', '-T', '-e', 'PYTHONPATH=/app', 'backend', 'python', '/e2e/followup.py', mode, '--execute'], { stdio: 'pipe', timeout: 30000 })
}
async function notices(page: Page): Promise<Notice[]> {
  const response = await page.request.get('/api/v1/notifications?limit=100')
  expect(response.status()).toBe(200)
  return (await response.json()).notifications
}
async function clickNotice(page: Page, notice: Notice, surface: 'page' | 'center', slug: string) {
  if (surface === 'page') await page.goto(`/${slug}/notifications`)
  else await page.getByRole('button', { name: /^Уведомления(?:,|$)/ }).first().click()
  const container = surface === 'page' ? page : page.locator('[data-storefront-block="client.notifications"].fixed')
  const link = container.locator(`[data-notification-id="${notice.id}"]`)
  await expect(link).toBeVisible()
  await link.focus(); await link.press('Enter')
}
async function primaryCompany(page: Page) {
  const response = await page.request.get('/api/v1/auth/me')
  expect(response.status()).toBe(200)
  return (await response.json()).user.company_id
}

test.skip(process.env.NOTIFICATIONS35_E2E !== '1', 'Explicit isolated context fixture required')
test.use({ baseURL, storageState: `${runtimeDir}/browser-client.secret.json`, viewport: { width: 1280, height: 900 }, trace: 'off' })
test.describe.configure({ mode: 'serial' })

test('storefront notices open all three sections for the secondary client company without a global switch', async ({ page }) => {
  test.setTimeout(90000)
  const state = manifest()
  const fixture = state.context_acceptance
  const inbox = await notices(page)
  const writes: string[] = []
  page.on('request', request => {
    if (request.method() === 'PUT' && request.url().includes('/questionnaire')) writes.push(request.url())
  })
  expect(await primaryCompany(page)).toBe(state.companies.buyer)
  for (const surface of ['page', 'center'] as const) {
    for (const [kind, title] of [['preliminary', 'Предварительные'], ['documents', 'Доп. документы'], ['final', 'Итоговое']] as const) {
      const notice = inbox.find(item => item.data?.event_id === fixture.events[kind])!
      expect(notice).toBeDefined()
      const target = new URL(notice.action_url, baseURL)
      expect(target.pathname).toBe(`/${fixture.storefront_slug}/application/${fixture.applications[kind]}`)
      expect(target.searchParams.get('notification_company_id')).toBe(fixture.company_id)
      expect(target.searchParams.get('section')).toBe(kind)
      expect(target.searchParams.has('step')).toBe(false)
      await clickNotice(page, notice, surface, fixture.storefront_slug)
      await expect(page.getByRole('heading', { name: `Офферы: ${title}`, exact: true })).toBeVisible({ timeout: 15000 })
      const current = new URL(page.url())
      expect(current.pathname).toBe(target.pathname)
      expect(current.searchParams.get('notification_company_id')).toBe(fixture.company_id)
      if (kind === 'documents') {
        expect(current.searchParams.get('section')).toBe('documents')
        expect(current.searchParams.has('step')).toBe(false)
      } else {
        expect(current.searchParams.get('step')).toBe(kind === 'preliminary' ? '4' : '5')
        expect(current.searchParams.has('section')).toBe(false)
      }
      expect(await primaryCompany(page)).toBe(state.companies.buyer)
      await page.reload()
      await expect(page.getByRole('heading', { name: `Офферы: ${title}`, exact: true })).toBeVisible({ timeout: 15000 })
    }
  }
  expect(writes).toEqual([])
})

test('a real secondary membership revocation removes visible application data on the next notification click', async ({ page }) => {
  test.setTimeout(90000)
  const state = manifest()
  const fixture = state.context_acceptance
  const inbox = await notices(page)
  const first = inbox.find(item => item.data?.event_id === fixture.events.final)!
  const second = inbox.find(item => item.data?.event_id === fixture.events.final_other)!
  expect(first.action_url).toBe(second.action_url)
  expect(first.id).not.toBe(second.id)
  const writes: string[] = []
  page.on('request', request => {
    if (request.method() === 'PUT' && request.url().includes('/applications/')) writes.push(request.url())
  })
  await clickNotice(page, first, 'page', fixture.storefront_slug)
  await expect(page.getByRole('heading', { name: 'Офферы: Итоговое', exact: true })).toBeVisible({ timeout: 15000 })
  try {
    permissions('context-revoke')
    const denied = page.waitForResponse(response => response.request().method() === 'GET'
      && new URL(response.url()).pathname === `/api/v1/storefronts/${fixture.storefront_slug}/applications/${fixture.applications.final}`)
    await clickNotice(page, second, 'center', fixture.storefront_slug)
    expect((await denied).status()).toBe(403)
    await expect(page.getByRole('alert').filter({ hasText: 'Заявка недоступна' })).toBeVisible()
    await expect(page.getByRole('heading', { name: /^Офферы:/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Итоговое КП', exact: true })).toHaveCount(0)
    await page.waitForTimeout(2200)
    expect(writes).toEqual([])
    expect(await primaryCompany(page)).toBe(state.companies.buyer)
  } finally { permissions('context-restore') }
})
