import { test, expect, type Browser, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const runtime = process.env.QUESTIONNAIRE_E2E_RUNTIME || '/runtime'
const fixturePath = path.join(runtime, 'passport-refresh-fixture.json')
interface RefreshFixture {
  application_id: string
  person_id: string
  role: 'founder' | 'representative' | 'director_applicant' | 'beneficiary'
  collection: 'founders' | 'other_representatives' | 'beneficiaries'
  full_name: string
  old_number: string
  new_number: string
}
interface Person { id: string; passport_number: string; name_changed: boolean }
interface Questionnaire {
  founders?: Person[]
  beneficiaries?: Person[]
  other_representatives?: Person[]
  director_passport_number?: string
  director_name_changed?: boolean
}
const fixtures: Record<string, RefreshFixture> | null = fs.existsSync(fixturePath)
  ? JSON.parse(fs.readFileSync(fixturePath, 'utf8')) : null
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:18286'
const qUrl = (fixture: RefreshFixture) => '/api/v1/questionnaire/' + fixture.application_id
const saveUrl = (fixture: RefreshFixture) => '/api/v1/applications/' + fixture.application_id + '/questionnaire'
const flagsLabel = 'Имеется ли отметка о смене ФИО'

function personFields(q: Questionnaire, fixture: RefreshFixture) {
  if (fixture.role === 'director_applicant') return {
    passport_number: q.director_passport_number, name_changed: q.director_name_changed
  }
  const person = q[fixture.collection]?.find(row => row.id === fixture.person_id)
  expect(person, 'The same UUID person must be preserved').toBeDefined()
  return { passport_number: person?.passport_number, name_changed: person?.name_changed }
}
async function savedFields(page: Page, fixture: RefreshFixture) {
  const response = await page.request.get(qUrl(fixture))
  expect(response.ok()).toBeTruthy()
  return personFields((await response.json()).questionnaire, fixture)
}
async function openFixture(browser: Browser, fixture: RefreshFixture) {
  const context = await browser.newContext({ storageState: path.join(runtime, 'client.storage.json'),
    baseURL, viewport: { width: 1280, height: 1000 } })
  const page = await context.newPage()
  await page.goto('/questionnaire/' + fixture.application_id)
  const card = page.locator('article').filter({ has: page.getByRole('heading', { name: fixture.full_name, exact: true }) }).last()
  await expect(card).toHaveCount(1, { timeout: 30_000 })
  const number = card.getByLabel(/^Номер документа/)
  await expect(number).toHaveValue(fixture.old_number, { timeout: 30_000 })
  await expect(card.getByLabel(/^Пол/)).toHaveValue('female')
  await expect(card.getByLabel(flagsLabel)).not.toBeChecked()
  return { context, page, card, number }
}

// Responses remain genuine: only delivery latency or connection failure is controlled.
function gate() {
  let release = () => {}
  const promise = new Promise<void>(resolve => { release = resolve })
  return { promise, release }
}

test.describe('22286 all signer roles keep confirmed passports during questionnaire autosave', () => {
  test.setTimeout(60_000)
  test.skip(!fixtures, 'Run passport_refresh_acceptance.py in the isolated 22286 stack first')

  for (const scenario of ['founder_slow', 'founder_quick', 'representative_slow', 'director_slow']) {
    test(scenario + ': changing name-change flag while refresh is pending preserves the confirmed passport', async ({ browser }) => {
      const fixture = fixtures![scenario]
      const { context, page, card, number } = await openFixture(browser, fixture)
      const delivery = gate()
      const started = gate()
      const writes: Questionnaire[] = []
      page.on('request', request => {
        if (request.method() === 'PUT' && new URL(request.url()).pathname === saveUrl(fixture)) {
          writes.push(request.postDataJSON() as Questionnaire)
        }
      })
      try {
        await page.route(url => url.pathname === qUrl(fixture), async route => {
          const response = await route.fetch()
          expect(response.ok()).toBeTruthy()
          expect(personFields((await response.json()).questionnaire, fixture).passport_number).toBe(fixture.new_number)
          started.release()
          await delivery.promise
          await route.fulfill({ response })
        }, { times: 1 })
        await number.fill(fixture.new_number)
        await card.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
        await started.promise
        // Verify the correct passport already exists on the real server before the flag edit.
        expect((await savedFields(page, fixture)).passport_number).toBe(fixture.new_number)
        await card.getByLabel(flagsLabel).check()
        if (scenario.endsWith('_slow')) {
          await page.waitForTimeout(2200) // Exceed the actual 1500ms autosave debounce.
          expect.soft(writes, 'No stale questionnaire may be sent while its confirmed passport refresh is pending').toEqual([])
        }
        const refreshed = page.waitForResponse(response => response.request().method() === 'GET'
          && new URL(response.url()).pathname === qUrl(fixture))
        delivery.release()
        await refreshed
        await expect.poll(async () => (await savedFields(page, fixture)).name_changed).toBe(true)
        const final = await savedFields(page, fixture)
        expect.soft(final, 'Changing only name_changed must not revert the confirmed passport').toEqual({
          passport_number: fixture.new_number, name_changed: true
        })
        if (fixture.role !== 'director_applicant') {
          expect(writes.length).toBeGreaterThan(0)
          for (const body of writes) {
            if (body[fixture.collection]) expect.soft(personFields(body, fixture).passport_number).toBe(fixture.new_number)
          }
        }
        await expect(card.getByLabel(flagsLabel)).toBeChecked()
        await page.reload()
        await expect(number).toHaveValue(fixture.new_number, { timeout: 30_000 })
        await expect(card.getByLabel(flagsLabel)).toBeChecked()
        expect(await savedFields(page, fixture)).toEqual({ passport_number: fixture.new_number, name_changed: true })
      } finally {
        delivery.release()
        await context.close()
      }
    })
  }

  test('name-change edit made before confirmation is retained before its debounce has fired', async ({ browser }) => {
    const fixture = fixtures!.founder_pending
    const { context, page, card, number } = await openFixture(browser, fixture)
    const email = 'pending-passport@questionnaire22286.test'
    try {
      await page.clock.install({ time: new Date('2026-10-02T12:00:00Z') })
      await page.clock.pauseAt(new Date('2026-10-02T12:00:01Z'))
      await page.locator('[name=company_email]').fill(email)
      const refreshed = page.waitForResponse(response => response.request().method() === 'GET'
        && new URL(response.url()).pathname === qUrl(fixture))
      await card.getByLabel(flagsLabel).check()
      await number.fill(fixture.new_number)
      await card.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      expect((await refreshed).ok()).toBeTruthy()
      await expect(card.getByLabel(flagsLabel), 'Passport refresh must retain local edits queued before confirmation').toBeChecked()
      await expect(page.locator('[name=company_email]')).toHaveValue(email)
      await page.clock.runFor(2200)
      await page.clock.resume()
      await expect.poll(() => savedFields(page, fixture)).toEqual({ passport_number: fixture.new_number, name_changed: true })
      await page.reload()
      await expect(number).toHaveValue(fixture.new_number, { timeout: 30_000 })
      await expect(card.getByLabel(flagsLabel)).toBeChecked()
      expect(await savedFields(page, fixture)).toEqual({ passport_number: fixture.new_number, name_changed: true })
      await expect(page.locator('[name=company_email]')).toHaveValue(email)
      const saved = await page.request.get(qUrl(fixture))
      expect((await saved.json()).questionnaire.company_email).toBe(email)
    } finally {
      await context.close()
    }
  })

  test('manual beneficiary address entered before passport confirmation retains priority', async ({ browser }) => {
    const fixture = fixtures!.beneficiary_pending
    const { context, page, card, number } = await openFixture(browser, fixture)
    const address = page.locator('[name="beneficiaries.0.registration_address"]')
    const manualAddress = 'Тверь, Ручной адрес до подтверждения, 9'
    try {
      await expect(address).toHaveValue('Москва, Прежний адрес, 1')
      await page.clock.install({ time: new Date('2026-10-02T12:00:00Z') })
      await page.clock.pauseAt(new Date('2026-10-02T12:00:01Z'))
      const refreshed = page.waitForResponse(response => response.request().method() === 'GET'
        && new URL(response.url()).pathname === qUrl(fixture))
      await address.fill(manualAddress)
      await number.fill(fixture.new_number)
      await card.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      expect((await refreshed).ok()).toBeTruthy()
      await expect(address, 'Confirmation must not erase a manual address queued before it started').toHaveValue(manualAddress)
      await page.clock.runFor(2200)
      await page.clock.resume()
      await expect.poll(async () => {
        const response = await page.request.get(qUrl(fixture))
        return (await response.json()).questionnaire.beneficiaries.find((person: Person) => person.id === fixture.person_id)
      }).toMatchObject({ registration_address: manualAddress, passport_number: fixture.new_number })
      await page.reload()
      await expect(address).toHaveValue(manualAddress, { timeout: 30_000 })
      await expect(number).toHaveValue(fixture.new_number)
    } finally {
      await context.close()
    }
  })

  test('passport confirmation waits for an earlier questionnaire save already in flight', async ({ browser }) => {
    const fixture = fixtures!.founder_prior_save
    const { context, page, card, number } = await openFixture(browser, fixture)
    const delivery = gate()
    const started = gate()
    const confirmations: string[] = []
    page.on('request', request => {
      if (request.method() === 'PATCH' && new URL(request.url()).pathname.endsWith('/passport')) confirmations.push(request.url())
    })
    try {
      await page.route(url => url.pathname === saveUrl(fixture), async route => {
        const response = await route.fetch()
        expect(response.ok()).toBeTruthy()
        expect(personFields(route.request().postDataJSON(), fixture)).toEqual({ passport_number: fixture.old_number, name_changed: true })
        started.release()
        await delivery.promise
        await route.fulfill({ response })
      }, { times: 1 })
      await card.getByLabel(flagsLabel).check()
      await started.promise
      await number.fill(fixture.new_number)
      await card.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      await page.waitForTimeout(2200)
      expect(confirmations, 'Confirmation must wait for an older in-flight questionnaire write').toEqual([])
      const confirmed = page.waitForResponse(response => response.request().method() === 'PATCH'
        && new URL(response.url()).pathname.endsWith('/passport'))
      delivery.release()
      expect((await confirmed).ok()).toBeTruthy()
      await expect.poll(() => savedFields(page, fixture)).toEqual({ passport_number: fixture.new_number, name_changed: true })
      await expect(card.getByLabel(flagsLabel)).toBeChecked()
      await page.reload()
      await expect(number).toHaveValue(fixture.new_number, { timeout: 30_000 })
      await expect(card.getByLabel(flagsLabel)).toBeChecked()
      expect(await savedFields(page, fixture)).toEqual({ passport_number: fixture.new_number, name_changed: true })
    } finally {
      delivery.release()
      await context.close()
    }
  })

  test('failed founder refresh blocks old-card autosave and explicit retry until reload', async ({ browser }) => {
    const fixture = fixtures!.founder_failed
    const { context, page, card, number } = await openFixture(browser, fixture)
    const delivery = gate()
    const started = gate()
    const writes: Questionnaire[] = []
    page.on('request', request => {
      if (request.method() === 'PUT' && new URL(request.url()).pathname === saveUrl(fixture)) {
        writes.push(request.postDataJSON() as Questionnaire)
      }
    })
    try {
      await page.route(url => url.pathname === qUrl(fixture), async route => {
        started.release()
        await delivery.promise
        await route.abort('connectionfailed')
      })
      await number.fill(fixture.new_number)
      await card.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      await started.promise
      expect((await savedFields(page, fixture)).passport_number).toBe(fixture.new_number)
      await card.getByLabel(flagsLabel).check()
      await page.waitForTimeout(2200)
      expect.soft(writes, 'A slow failing refresh must block stale autosave too').toEqual([])
      delivery.release()
      await expect(page.getByRole('alert').filter({ hasText: 'Паспорт сохранён' })).toBeVisible({ timeout: 15_000 })
      await card.getByLabel(flagsLabel).uncheck()
      await page.waitForTimeout(2200)
      expect.soft(writes, 'An unresolved failed refresh must also block later edits').toEqual([])
      await page.getByRole('button', { name: 'Повторить сохранение', exact: true }).click()
      await page.waitForTimeout(2200)
      expect.soft(writes, 'Explicit retry must not bypass the failed-refresh guard').toEqual([])
      expect(await savedFields(page, fixture)).toEqual({ passport_number: fixture.new_number, name_changed: false })
      await page.unrouteAll({ behavior: 'wait' })
      await page.reload()
      await expect(number).toHaveValue(fixture.new_number, { timeout: 30_000 })
      await expect(card.getByLabel(flagsLabel)).not.toBeChecked()
      await card.getByLabel(flagsLabel).check()
      await expect.poll(() => savedFields(page, fixture)).toEqual({ passport_number: fixture.new_number, name_changed: true })
    } finally {
      delivery.release()
      await context.close()
    }
  })
})
