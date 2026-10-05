import { test, expect, type Browser, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const runtime = process.env.QUESTIONNAIRE_E2E_RUNTIME || '/runtime'
const fixturePath = path.join(runtime, 'beneficiary-address-fixture.json')
interface AddressFixture {
  application_id: string
  person_id: string
  initial_address: string | null
  recognized_address: string
}
interface Beneficiary {
  id: string
  registration_address: string | null
  share_percentage: number | null
}
const fixtures: Record<string, AddressFixture> | null = fs.existsSync(fixturePath)
  ? JSON.parse(fs.readFileSync(fixturePath, 'utf8')) : null
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:18286'

async function openFixture(browser: Browser, fixture: AddressFixture) {
  const context = await browser.newContext({
    storageState: path.join(runtime, 'client.storage.json'), baseURL,
    viewport: { width: 1280, height: 1000 }
  })
  const page = await context.newPage()
  await page.goto('/questionnaire/' + fixture.application_id)
  const card = page.locator('article').filter({ has: page.getByRole('heading', { name: 'Бенефициар 1', exact: true }) })
  const address = card.locator('[name="beneficiaries.0.registration_address"]')
  await expect(address).toHaveValue(fixture.initial_address ?? '', { timeout: 30_000 })
  const passport = card.getByRole('heading', { name: 'Проверка паспортных данных', exact: true }).locator('..').locator('..')
  await expect(passport.getByLabel(/^Пол/)).toHaveValue('female')
  return { context, page, card, address, passport }
}

async function savedPerson(page: Page, fixture: AddressFixture): Promise<Beneficiary> {
  const response = await page.request.get('/api/v1/questionnaire/' + fixture.application_id)
  expect(response.ok()).toBeTruthy()
  const people = (await response.json()).questionnaire.beneficiaries as Beneficiary[]
  expect(people).toHaveLength(1)
  expect(people[0].id).toBe(fixture.person_id)
  return people[0]
}

async function changeShareAndCheck(page: Page, fixture: AddressFixture, address: string | null) {
  const save = page.waitForResponse(response => response.request().method() === 'PUT'
    && new URL(response.url()).pathname === '/api/v1/applications/' + fixture.application_id + '/questionnaire')
  await page.locator('[name="beneficiaries.0.share_percentage"]').fill('41')
  const response = await save
  expect(response.ok()).toBeTruthy()
  const sent = response.request().postDataJSON().beneficiaries as Beneficiary[]
  expect(sent.find(person => person.id === fixture.person_id)).toMatchObject({ registration_address: address, share_percentage: 41 })
  await expect.poll(() => savedPerson(page, fixture)).toMatchObject({ registration_address: address, share_percentage: 41 })
  await page.reload()
  await expect(page.locator('[name="beneficiaries.0.registration_address"]')).toHaveValue(address ?? '', { timeout: 30_000 })
  await expect(page.locator('[name="beneficiaries.0.share_percentage"]')).toHaveValue('41')
}

test.describe('22286 beneficiary registration address after passport confirmation', () => {
  test.setTimeout(60_000)
  test.skip(!fixtures, 'Run beneficiary_address_acceptance.py in the isolated 22286 stack first')

  for (const scenario of ['automatic', 'manual', 'manual_clear']) {
    test(scenario + ': confirmed address survives ownership-share edit and reload', async ({ browser }) => {
      const fixture = fixtures![scenario]
      const { context, page, address, passport } = await openFixture(browser, fixture)
      try {
        const expected = scenario === 'automatic' ? fixture.recognized_address : fixture.initial_address
        const refresh = page.waitForResponse(response => response.request().method() === 'GET'
          && new URL(response.url()).pathname === '/api/v1/questionnaire/' + fixture.application_id)
        await passport.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
        const response = await refresh
        expect(response.ok()).toBeTruthy()
        const people = (await response.json()).questionnaire.beneficiaries as Beneficiary[]
        expect(people.find(person => person.id === fixture.person_id)?.registration_address).toBe(expected)
        await expect(address, 'Confirmed OCR address must reach the form before another card edit').toHaveValue(expected ?? '')
        await changeShareAndCheck(page, fixture, expected)
      } finally {
        await context.close()
      }
    })
  }

  test('manual edit while the real confirmation refresh is pending keeps priority', async ({ browser }) => {
    const fixture = fixtures!.concurrent
    const { context, page, address, passport } = await openFixture(browser, fixture)
    let release = () => {}
    const gate = new Promise<void>(resolve => { release = resolve })
    let refreshStarted = () => {}
    const started = new Promise<void>(resolve => { refreshStarted = resolve })
    const qUrl = '/api/v1/questionnaire/' + fixture.application_id
    try {
      // Hold the genuine server response so the edit races with the UI refresh.
      await page.route(url => url.pathname === qUrl, async route => {
        const response = await route.fetch()
        expect(response.ok()).toBeTruthy()
        const people = (await response.json()).questionnaire.beneficiaries as Beneficiary[]
        expect(people.find(person => person.id === fixture.person_id)?.registration_address).toBe(fixture.recognized_address)
        refreshStarted()
        await gate
        await route.fulfill({ response })
      }, { times: 1 })
      await passport.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      await started
      const manualAddress = 'Тверь, Правка во время обновления, 4'
      await address.fill(manualAddress)
      const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === qUrl)
      release()
      await refreshed
      await expect(address).toHaveValue(manualAddress)
      await changeShareAndCheck(page, fixture, manualAddress)
    } finally {
      release()
      await context.close()
    }
  })

  test('share edit waits for a slow confirmation refresh and saves the new OCR address', async ({ browser }) => {
    const fixture = fixtures!.concurrent_share
    const { context, page, address, passport } = await openFixture(browser, fixture)
    let release = () => {}
    const gate = new Promise<void>(resolve => { release = resolve })
    let refreshStarted = () => {}
    const started = new Promise<void>(resolve => { refreshStarted = resolve })
    const qUrl = '/api/v1/questionnaire/' + fixture.application_id
    const saveUrl = '/api/v1/applications/' + fixture.application_id + '/questionnaire'
    const writes: Beneficiary[][] = []
    page.on('request', request => {
      if (request.method() === 'PUT' && new URL(request.url()).pathname === saveUrl) {
        writes.push(request.postDataJSON().beneficiaries as Beneficiary[])
      }
    })
    try {
      await page.route(url => url.pathname === qUrl, async route => {
        const response = await route.fetch()
        expect(response.ok()).toBeTruthy()
        const people = (await response.json()).questionnaire.beneficiaries as Beneficiary[]
        expect(people.find(person => person.id === fixture.person_id)?.registration_address).toBe(fixture.recognized_address)
        refreshStarted()
        await gate
        await route.fulfill({ response })
      }, { times: 1 })
      await passport.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      await started
      await page.locator('[name="beneficiaries.0.share_percentage"]').fill('41')
      // Simulate network latency longer than the 1500ms autosave debounce.
      await page.waitForTimeout(2200)
      expect(writes, 'Autosave must not submit a stale card while confirmed passport fields are pending').toEqual([])
      const save = page.waitForResponse(response => response.request().method() === 'PUT'
        && new URL(response.url()).pathname === saveUrl)
      release()
      await expect(address).toHaveValue(fixture.recognized_address)
      const response = await save
      expect(response.ok()).toBeTruthy()
      expect(writes).toHaveLength(1)
      expect(writes[0].find(person => person.id === fixture.person_id)).toMatchObject({
        registration_address: fixture.recognized_address, share_percentage: 41
      })
      await expect.poll(() => savedPerson(page, fixture)).toMatchObject({
        registration_address: fixture.recognized_address, share_percentage: 41
      })
      await page.reload()
      await expect(address).toHaveValue(fixture.recognized_address, { timeout: 30_000 })
      await expect(page.locator('[name="beneficiaries.0.share_percentage"]')).toHaveValue('41')
    } finally {
      release()
      await context.close()
    }
  })

  test('failed confirmation refresh blocks stale autosaves until reopening the questionnaire', async ({ browser }) => {
    const fixture = fixtures!.failed_refresh
    const { context, page, address, passport } = await openFixture(browser, fixture)
    let release = () => {}
    const gate = new Promise<void>(resolve => { release = resolve })
    let refreshStarted = () => {}
    const started = new Promise<void>(resolve => { refreshStarted = resolve })
    const qUrl = '/api/v1/questionnaire/' + fixture.application_id
    const saveUrl = '/api/v1/applications/' + fixture.application_id + '/questionnaire'
    const writes: string[] = []
    page.on('request', request => {
      if (request.method() === 'PUT' && new URL(request.url()).pathname === saveUrl) writes.push(request.url())
    })
    try {
      // Abort the refresh and its retries, never fabricate a server response.
      await page.route(url => url.pathname === qUrl, async route => {
        refreshStarted()
        await gate
        await route.abort('connectionfailed')
      })
      const confirmed = page.waitForResponse(response => response.request().method() === 'PATCH'
        && new URL(response.url()).pathname.includes('/sopd-signers/')
        && new URL(response.url()).pathname.endsWith('/passport'))
      await passport.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      expect((await confirmed).ok()).toBeTruthy()
      await started
      await page.locator('[name="beneficiaries.0.share_percentage"]').fill('41')
      // A slow failed refresh must also prevent the debounce from sending stale data.
      await page.waitForTimeout(2200)
      expect(writes).toEqual([])
      release()
      await expect(page.getByRole('alert').filter({ hasText: 'Паспорт сохранён, но не удалось обновить анкету на экране' })).toBeVisible({ timeout: 15_000 })
      await page.locator('[name="beneficiaries.0.share_percentage"]').fill('42')
      await page.waitForTimeout(2200)
      expect(writes, 'An unresolved refresh failure must also block later stale autosaves').toEqual([])
      await page.getByRole('button', { name: 'Добавить бенефициара', exact: true }).click()
      await page.locator('[name="beneficiaries.1.full_name"]').fill('Вторая Анна Тестовая')
      await page.getByRole('button', { name: 'Сохранить и заполнить паспорт', exact: true }).click()
      await expect(page.getByRole('alert').filter({ hasText: 'Паспорт сохранён, но не удалось обновить анкету на экране' })).toBeVisible()
      await page.waitForTimeout(2200)
      expect(writes, 'Saving a new beneficiary must not bypass the failed-refresh guard').toEqual([])
      expect(await savedPerson(page, fixture)).toMatchObject({ registration_address: fixture.recognized_address, share_percentage: 40 })
      await page.unrouteAll({ behavior: 'wait' })
      await page.reload()
      await expect(address).toHaveValue(fixture.recognized_address, { timeout: 30_000 })
      await expect(page.locator('[name="beneficiaries.0.share_percentage"]')).toHaveValue('40')
    } finally {
      release()
      await context.close()
    }
  })
})
