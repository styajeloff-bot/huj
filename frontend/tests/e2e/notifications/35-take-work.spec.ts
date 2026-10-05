import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

const runtimeDir = '/tmp/carcraft-notifications35-followup-v2-runtime'
const baseURL = 'http://localhost:18048'
interface FollowupManifest {
  marker: string
  users: { leasing_company: { email: string } }
  followup: {
    take_application_id: string
    take_application_number: string
    take_event_id: string
    take_final_application_id: string
    take_final_application_number: string
    take_final_event_id: string
  }
}
interface Notice { event_id: string; title: string; message: string; action_url: string }

test.skip(process.env.NOTIFICATIONS35_E2E !== '1', 'Requires the isolated notifications35 follow-up fixture')
test.use({ baseURL, viewport: { width: 1280, height: 900 }, trace: 'off' })
test.describe.configure({ mode: 'serial' })

for (const kind of ['preliminary', 'final'] as const) {
  test(`LC ${kind}: notification → draft and PDF → one injected transport failure → explicit take → real decision`, async ({ browser }) => {
    const fixture: FollowupManifest = JSON.parse(readFileSync(`${runtimeDir}/fixtures.secret.json`, 'utf8'))
    if (fixture.marker !== 'tz35-runtime' || fixture.users.leasing_company.email !== 'leasing_company@notifications35.test') {
      throw new Error('Only synthetic local fixtures are allowed')
    }
    const applicationId = kind === 'preliminary' ? fixture.followup.take_application_id : fixture.followup.take_final_application_id
    const applicationNumber = kind === 'preliminary' ? fixture.followup.take_application_number : fixture.followup.take_final_application_number
    const eventId = kind === 'preliminary' ? fixture.followup.take_event_id : fixture.followup.take_final_event_id
    if (!applicationId || !eventId) throw new Error(`Missing ${kind} submitted-application fixture`)
    const context = await browser.newContext({ baseURL,
      storageState: `${runtimeDir}/browser-leasing_company.secret.json`, viewport: { width: 1280, height: 900 } })
    const page = await context.newPage()
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    const takeRequests: string[] = []
    page.on('request', request => { if (request.method() === 'POST' && request.url().includes(`/${applicationId}/take-in-work`)) takeRequests.push(request.url()) })
    try {
      const inbox = await page.request.get('/api/v1/notifications?limit=100')
      expect(inbox.status()).toBe(200)
      const notice = ((await inbox.json()).notifications as Notice[]).find(item => item.event_id === eventId)
      expect(notice).toBeDefined()
      if (!notice) throw new Error('Assigned application notification is absent')
      const target = new URL(notice.action_url, baseURL)
      expect(target.origin).toBe(baseURL)
      const selector = target.searchParams.get('leasing_company_id')
      expect(selector).toBeTruthy()
      const apiPath = `/api/v1/leasing/applications/${applicationId}`
      const suffix = `?leasing_company_id=${selector}`

      await page.goto('/workspace/leasing-applications')
      await page.getByRole('button', { name: /^Уведомления/ }).click()
      const center = page.locator('[data-storefront-block="client.notifications"]')
      const item = center.getByRole('link').filter({ has: page.getByText(notice.message, { exact: true }) }).first()
      await expect(item).toBeVisible()
      await item.click()
      await expect(page).toHaveURL(target.toString())
      await expect(page.getByRole('heading', { name: `Заявка ${applicationNumber}`, exact: true })).toBeVisible()
      const header = page.locator('section').filter({ has: page.getByRole('heading', { level: 1 }) })
      await expect(header.getByText('Подана', { exact: true })).toBeVisible()
      const take = page.getByRole('button', { name: 'Взять в работу', exact: true })
      await expect(take).toBeVisible()
      expect(takeRequests).toEqual([])
      await page.reload()
      await expect(take).toBeVisible()
      expect(takeRequests).toEqual([])
      const pristineResponse = await page.request.get(`${apiPath}/response${suffix}`)
      expect(pristineResponse.status()).toBe(200)
      expect((await pristineResponse.json()).proposals).toEqual([])

      await page.getByRole('button', { name: 'КП', exact: true }).click()
      if (kind === 'final') await page.getByRole('radio', { name: 'Итоговое КП', exact: true }).click()
      const formName = kind === 'preliminary' ? 'Предварительное КП' : 'Итоговое КП'
      const form = page.getByRole('form', { name: formName, exact: true })
      const amount = form.getByRole('spinbutton', { name: 'Размер ежемесячного платежа', exact: true })
      await amount.fill('15000')
      const draftResponse = page.waitForResponse(response => response.request().method() === 'PUT' && new URL(response.url()).pathname === `${apiPath}/proposals/${kind}`)
      const pdfResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === `${apiPath}/proposals/${kind}/pdf`)
      await form.locator('input[type="file"]').setInputFiles({ name: `${kind}-quote.pdf`, mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n% local synthetic quote\n%%EOF') })
      const savedDraft = await draftResponse
      expect(savedDraft.status()).toBe(200)
      expect(savedDraft.request().postDataJSON()).toMatchObject({ monthly_payment: 15000, lease_term_months: 36 })
      expect((await pdfResponse).status()).toBe(200)
      await expect(form.getByText(`${kind}-quote.pdf`, { exact: true })).toBeVisible()
      const savedBeforeTake = await page.request.get(`${apiPath}/response${suffix}`)
      expect(savedBeforeTake.status()).toBe(200)
      expect((await savedBeforeTake.json()).link.status).toBe('submitted')
      expect(takeRequests).toEqual([])
      const send = form.getByRole('button', { name: kind === 'preliminary' ? 'Отправить предварительный расчёт' : 'Отправить итоговый расчёт', exact: true })
      await expect(send).toBeDisabled()
      await expect(form.getByText('Сначала возьмите заявку в работу', { exact: true })).toBeVisible()

      // Negative UI fault injection only: abort one outgoing transport request.
      // The successful retry, database transition, draft/PDF and decision use real services.
      await page.route(`**${apiPath}/take-in-work?*`, route => route.abort('failed'), { times: 1 })
      await take.click()
      await expect(header.getByRole('alert')).toContainText('Не удалось взять заявку в работу')
      await expect(amount).toHaveValue('15000')
      await expect(form.getByText(`${kind}-quote.pdf`, { exact: true })).toBeVisible()
      await expect(take).toBeEnabled()

      const taken = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === `${apiPath}/take-in-work`)
      await take.click()
      const takenResponse = await taken
      expect(takenResponse.status()).toBe(200)
      expect(await takenResponse.json()).toMatchObject({ lca_status: 'under_review', replayed: false })
      await expect(header.getByText('На рассмотрении', { exact: true })).toBeVisible()
      await expect(take).toHaveCount(0)
      await expect(amount).toHaveValue('15000')
      await expect(form.getByText(`${kind}-quote.pdf`, { exact: true })).toBeVisible()
      await expect(send).toBeEnabled()
      expect(takeRequests).toHaveLength(2)
      expect(takeRequests.every(url => new URL(url).searchParams.get('leasing_company_id') === selector)).toBe(true)

      const replay = await page.request.post(`${apiPath}/take-in-work${suffix}`)
      expect(replay.status()).toBe(200)
      expect(await replay.json()).toMatchObject({ lca_status: 'under_review', replayed: true })
      const decision = page.waitForResponse(response => response.request().method() === 'PUT' && new URL(response.url()).pathname === `${apiPath}/decision`)
      await send.click()
      expect((await decision).status()).toBe(200)
      const expectedStatus = kind === 'preliminary' ? 'approved_scoring' : 'approved_final'
      const persisted = await page.request.get(`${apiPath}/response${suffix}`)
      expect(persisted.status()).toBe(200)
      const state = await persisted.json()
      expect(state.link.status).toBe(expectedStatus)
      expect(state.proposals).toHaveLength(1)
      expect(state.proposals[0].kind).toBe(kind)
      expect(state.proposals[0].pdf_file_name).toBe(`${kind}-quote.pdf`)
      expect(Number(state.proposals[0].monthly_payment)).toBe(15000)
      const stale = await page.request.post(`${apiPath}/take-in-work${suffix}`)
      expect(stale.status()).toBe(200)
      expect(await stale.json()).toMatchObject({ lca_status: expectedStatus, replayed: true })
      await page.reload()
      await expect(take).toHaveCount(0)
      await expect(header.getByText(kind === 'preliminary' ? 'Скоринг одобрен' : 'Финально одобрено', { exact: true })).toBeVisible()
      expect(errors).toEqual([])
    } finally {
      await context.close()
    }
  })
}
