import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test'

const runtimeDir = '/tmp/carcraft-notifications35-followup-v2-runtime'
const baseURL = 'http://localhost:18048'
const roles = ['client', 'dealer', 'distributor', 'leasing_company', 'carcraft_employee'] as const
type Role = typeof roles[number]
interface Manifest {
  marker: string
  application_id: string
  application_number?: string
  editable_application_id: string
  exchange_request_id: string
  companies: Record<string, string>
  events: Record<string, string>
  users: Record<Role, { id: string; email: string }>
}
interface Notice {
  id: string
  event_id: string
  action_url: string
  title: string
  message: string
  is_read: boolean
  data: { event_type: string }
}

// Opt-in suite: never contact a default project or remote deployment.
test.skip(process.env.NOTIFICATIONS35_E2E !== '1', 'Run through scripts/e2e/notifications35/run.sh')
test.use({ baseURL, viewport: { width: 1280, height: 900 }, trace: 'off' })
test.describe.configure({ mode: 'serial' })

function manifest(): Manifest {
  if (process.env.NOTIFICATIONS35_E2E !== '1') throw new Error('Local fixture opt-in is required')
  const value: Manifest = JSON.parse(readFileSync(`${runtimeDir}/fixtures.secret.json`, 'utf8'))
  if (value.marker !== 'tz35-runtime') throw new Error('Unexpected runtime marker')
  for (const role of roles) {
    if (value.users[role]?.email !== `${role}@notifications35.test`) throw new Error('Non-fixture user')
  }
  return value
}

async function rolePage(browser: Browser, role: Role) {
  const context = await browser.newContext({
    baseURL, storageState: `${runtimeDir}/browser-${role}.secret.json`,
    viewport: { width: 1280, height: 900 },
  })
  const page = await context.newPage()
  return { context, page }
}

async function inbox(page: Page): Promise<Notice[]> {
  const response = await page.request.get('/api/v1/notifications?limit=100')
  expect(response.status()).toBe(200)
  const body: { notifications: Notice[] } = await response.json()
  return body.notifications
}

async function openNotice(page: Page, notice: Notice) {
  await page.goto('/notifications')
  const href = new URL(notice.action_url, baseURL)
  expect(href.origin).toBe(baseURL)
  const link = page.getByRole('link')
    .filter({ has: page.getByRole('heading', { name: notice.title, exact: true }) })
    .filter({ has: page.getByText(notice.message, { exact: true }) }).first()
  await expect(link).toBeVisible()
  await link.click()
  await expect(page).toHaveURL(href.toString())
}

function isolatedCompose(): string[] {
  const composePath = process.env.NOTIFICATIONS35_COMPOSE
  const expected = resolve('../scripts/e2e/notifications35/compose.yml')
  if (!composePath || resolve(composePath) !== expected) throw new Error('Explicit repository E2E Compose file is required')
  return ['compose', '-p', 'carcraft-notifications35-followup-v2', '-f', expected]
}

function fixtureRuntime(mode: string, timeout = 30000) {
  execFileSync('docker', [...isolatedCompose(), 'exec', '-T', '-e', 'PYTHONPATH=/app', 'backend',
    'python', '/e2e/runtime.py', mode, '--execute'], { stdio: 'pipe', timeout })
}

test('new inbox entries affect unread count, filtering and mark-all through the browser', async ({ browser }) => {
  const state = manifest()
  const { context, page } = await rolePage(browser, 'client')
  const employee = await rolePage(browser, 'carcraft_employee')
  try {
    const beforeResponse = await page.request.get('/api/v1/notifications?fields=count')
    expect(beforeResponse.status()).toBe(200)
    const before: { total_count: number; unread_count: number } = await beforeResponse.json()
    const title = `ТЗ35 unread regression ${randomUUID()}`
    const created = await employee.page.request.post('/api/v1/notifications', {
      data: { user_id: state.users.client.id, type: 'system', title, message: 'Local migrated-schema regression' },
    })
    expect(created.status()).toBe(201)
    const afterResponse = await page.request.get('/api/v1/notifications?fields=count')
    expect(afterResponse.status()).toBe(200)
    expect(await afterResponse.json()).toEqual({ total_count: before.total_count + 1, unread_count: before.unread_count + 1 })
    await page.goto('/notifications')
    const filtered = page.waitForResponse(response => response.request().method() === 'GET'
      && response.url().includes('/api/v1/notifications?') && new URL(response.url()).searchParams.get('is_read') === 'false')
    await page.getByRole('combobox').filter({ has: page.locator('option[value="false"]') }).selectOption('false')
    expect((await filtered).status()).toBe(200)
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
    const marked = page.waitForResponse(response => response.request().method() === 'PATCH'
      && new URL(response.url()).pathname === '/api/v1/notifications')
    await page.getByRole('button', { name: 'Прочитать все', exact: true }).click()
    expect((await marked).status()).toBe(204)
    await page.reload()
    await expect(page.getByRole('button', { name: 'Прочитать все', exact: true })).toHaveCount(0)
    const counts = await page.request.get('/api/v1/notifications?fields=count')
    expect(counts.status()).toBe(200)
    expect((await counts.json()).unread_count).toBe(0)
    const unread = await page.request.get('/api/v1/notifications?is_read=false')
    expect(unread.status()).toBe(200)
    expect((await unread.json()).notifications).toEqual([])
  } finally {
    await employee.context.close()
    await context.close()
  }
})

test('first email settings save succeeds without a seeded preferences row', async ({ browser }) => {
  let context: BrowserContext | undefined
  try {
    fixtureRuntime('first-preferences-cleanup')
    fixtureRuntime('first-preferences-prepare')
    context = await browser.newContext({ baseURL,
      storageState: `${runtimeDir}/browser-first-preferences.secret.json`, viewport: { width: 1280, height: 900 } })
    const page = await context.newPage()
    await page.goto('/settings/email')
    await expect(page.getByRole('radio', { name: 'Немедленно Получать уведомления сразу после событий', exact: true })).toBeChecked()
    await page.getByRole('radio', { name: 'Ежедневная сводка Получать сводку один раз в день', exact: true }).check()
    await page.getByRole('checkbox', { name: /Уведомления Биржи Заявки, ставки/ }).uncheck()
    const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/email-preferences')
      && response.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Сохранить настройки', exact: true }).click()
    expect((await saved).status()).toBe(200)
    await page.reload()
    await expect(page.getByRole('radio', { name: 'Ежедневная сводка Получать сводку один раз в день', exact: true })).toBeChecked()
    await expect(page.getByRole('checkbox', { name: /Уведомления Биржи Заявки, ставки/ })).not.toBeChecked()
  } finally {
    try { await context?.close() }
    finally { fixtureRuntime('first-preferences-cleanup') }
  }
})

for (const role of roles) {
  test(`${role}: inbox deep-link opens the exact authorized application`, async ({ browser }) => {
    const state = manifest()
    const { context, page } = await rolePage(browser, role)
    const errors: string[] = []
    const autosaves: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => {
      if (request.method() === 'PUT' && request.url().includes('/questionnaire')) autosaves.push(request.url())
    })
    page.on('response', response => {
      if (response.status() >= 400 && /\/api\/v1\/(cart|client\/favorites)/.test(response.url())) {
        errors.push(`Unexpected client-widget ${response.status()}`)
      }
    })
    try {
      const notice = (await inbox(page)).find(item => item.event_id === state.events.finalized)
      expect(notice).toBeDefined()
      if (!notice) throw new Error('Finalized notification absent')
      await openNotice(page, notice)
      await expect(page.getByText(`Заявка ${state.application_number ?? 'TZ35-RUNTIME-001'}`, { exact: true }).first()).toBeVisible()
      if (role !== 'client') {
        await expect(page.getByText('ТЗ35 runtime buyer', { exact: true }).first()).toBeVisible({ timeout: 15000 })
      }
      if (role === 'client') {
        await expect(page.getByText('Тестовый Директор ТЗ35', { exact: true })).toBeVisible()
        // Exceed the former 1500ms debounce: hydration must never write a readonly form.
        await page.waitForTimeout(2200)
        expect(autosaves).toEqual([])
      }
      if (role === 'dealer') {
        expect(new URL(page.url()).searchParams.get('notification_company_id')).toBe(state.companies.dealer)
      }
      expect(errors).toEqual([])
    } finally {
      await context.close()
    }
  })
}

test('email preference and daily frequency persist without affecting inbox', async ({ browser }) => {
  const state = manifest()
  const { context, page } = await rolePage(browser, 'client')
  try {
    await page.goto('/settings/email')
    await page.getByRole('radio', { name: 'Ежедневная сводка Получать сводку один раз в день', exact: true }).check()
    await page.getByRole('checkbox', { name: /Уведомления Биржи Заявки, ставки/ }).uncheck()
    const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/email-preferences') && response.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Сохранить настройки', exact: true }).click()
    expect((await saved).status()).toBe(200)
    await page.reload()
    await expect(page.getByRole('radio', { name: 'Ежедневная сводка Получать сводку один раз в день', exact: true })).toBeChecked()
    await expect(page.getByRole('checkbox', { name: /Уведомления Биржи Заявки, ставки/ })).not.toBeChecked()
    expect((await inbox(page)).some(item => item.event_id === state.events.finalized)).toBe(true)
  } finally {
    const restored = await page.request.put('/api/v1/email-preferences', { data: { email_frequency: 'immediate', exchange_emails: true } })
    expect(restored.status()).toBe(200)
    await context.close()
  }
})

test('editable questionnaire still autosaves and survives reload', async ({ browser }) => {
  const state = manifest()
  const { context, page } = await rolePage(browser, 'client')
  const address = 'ТЗ35 E2E фактический адрес, дом 35'
  try {
    await page.goto(`/application/${state.editable_application_id}`)
    const actualAddress = page.getByPlaceholder('Введите фактический адрес', { exact: true })
    await expect(actualAddress).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('Тестовый Директор ТЗ35', { exact: true })).toBeVisible()
    const saved = page.waitForResponse(response => response.request().method() === 'PUT'
      && response.url().includes(`/${state.editable_application_id}/questionnaire`)
      && response.request().postData()?.includes(address) === true)
    await actualAddress.fill(address)
    expect((await saved).status()).toBe(200)
    await page.reload()
    await expect(page.getByPlaceholder('Введите фактический адрес', { exact: true })).toHaveValue(address)
  } finally {
    await context.close()
  }
})

test('secondary dealer company with read-only access cannot offer mutations', async ({ browser }) => {
  const state = manifest()
  const { context, page } = await rolePage(browser, 'dealer')
  try {
    fixtureRuntime('dealer-readonly')
    const notice = (await inbox(page)).find(item => item.event_id === state.events.published)
    if (!notice) throw new Error('Exchange notification absent')
    const permissions = page.waitForResponse(response => response.url().includes('/api/v1/users/me/companies'))
    await openNotice(page, notice)
    expect((await permissions).status()).toBe(200)
    await expect(page.getByText('Ваша ставка', { exact: true }).first()).toBeVisible()
    expect(new URL(page.url()).searchParams.get('notification_company_id')).toBe(state.companies.dealer)
    await expect(page.getByRole('button', { name: /Обновить ставку|Отозвать ставку|Отправить ставку/ })).toHaveCount(0)
    const rejected = await page.request.post(`/api/v1/exchange/bids/?notification_company_id=${state.companies.dealer}`, {
      data: { request_id: state.exchange_request_id, price: '915000.00' },
    })
    expect(rejected.status()).toBe(403)
  } finally {
    fixtureRuntime('dealer-write-restore')
    await context.close()
  }
})

test('dealer mutation survives SMTP outage; consumers and scheduler retry without duplicate mail', async ({ browser }) => {
  test.setTimeout(240000)
  const state = manifest()
  const { context, page } = await rolePage(browser, 'dealer')
  const composeArgs = isolatedCompose()
  // Confirm ownership before any fault injection. Never pause a user service.
  const container = execFileSync('docker', [...composeArgs, 'ps', '-q', 'smtp'], { encoding: 'utf8' }).trim()
  const owner = execFileSync('docker', ['inspect', '--format', '{{index .Config.Labels "com.docker.compose.project"}}/{{index .Config.Labels "com.docker.compose.service"}}', container], { encoding: 'utf8' }).trim()
  expect(owner).toBe('carcraft-notifications35-followup-v2/smtp')
  try {
    const notice = (await inbox(page)).find(item => item.event_id === state.events.published)
    if (!notice) throw new Error('Exchange notification absent')
    await openNotice(page, notice)
    await expect(page.getByRole('button', { name: 'Обновить ставку', exact: true })).toBeVisible()
    execFileSync('docker', ['pause', container], { stdio: 'pipe' })
    try {
      const updated = page.waitForResponse(response => response.request().method() === 'PUT'
        && response.url().includes('/api/v1/exchange/bids/'))
      await page.getByPlaceholder('Введите цену', { exact: true }).fill('910000')
      await page.getByRole('button', { name: 'Обновить ставку', exact: true }).click()
      expect((await updated).status()).toBe(200)
      await expect(page.getByText(/910\s*000/).first()).toBeVisible()
      fixtureRuntime('outage-wait', 95000)
    } finally {
      execFileSync('docker', ['unpause', container], { stdio: 'pipe' })
    }
    fixtureRuntime('outage-recovered', 130000)
  } finally {
    await context.close()
  }
})

test('distributor Exchange is read-only and LC sees the new bid price', async ({ browser }) => {
  const state = manifest()
  for (const role of ['distributor', 'leasing_company'] as const) {
    const { context, page } = await rolePage(browser, role)
    try {
      const notice = (await inbox(page)).find(item => item.data.event_type === 'exchange.bid_updated'
        && item.action_url.includes(state.exchange_request_id))
      if (!notice) throw new Error('Bid update notification absent')
      await openNotice(page, notice)
      await expect(page.getByText(/910\s*000/).first()).toBeVisible()
      if (role === 'distributor') {
        await expect(page.getByText('Заявки связанных дилеров. Только просмотр.', { exact: true })).toBeVisible()
        await expect(page.getByRole('button', { name: /Обновить ставку|Выбрать ставку|Отправить ставку/ })).toHaveCount(0)
      }
    } finally {
      await context.close()
    }
  }
})
