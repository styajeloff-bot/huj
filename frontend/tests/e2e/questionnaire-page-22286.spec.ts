import { test, expect, type Browser, type BrowserContext, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'

const runtime = process.env.QUESTIONNAIRE_E2E_RUNTIME || '/runtime'
const manifestPath = path.join(runtime, 'manifest.json')
interface Manifest {
  application_id: string
  ui_application_id?: string
  companies: Record<string, { company_id: string; leasing_company_id?: string }>
}
const fixture: Manifest | null = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : null
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:18286'
const sessions: BrowserContext[] = []
const serverErrors: string[] = []
const companyName = 'ООО Отдельная анкета 22286'
let applicationId: string
let secondApplicationId: string
let untouchedApplicationId: string
let emptyFieldsApplicationId: string
const emptyFieldsCompanyName = 'ООО Анкета с незаполненными полями'
const emptyEditableFields: Record<string, string> = {
  foreign_company_name: 'Наименование на иностранном языке',
  short_company_name: 'Сокращённое наименование',
  okpo: 'ОКПО',
  okato: 'ОКАТО',
  okved_main: 'Основной ОКВЭД',
  okved_additional: 'Дополнительные ОКВЭД',
  company_email: 'Email организации',
  company_website: 'Сайт организации',
  director_position: 'Должность руководителя',
  director_birth_date: 'Дата рождения руководителя',
  director_passport_series: 'Серия паспорта',
  director_passport_number: 'Номер паспорта',
  director_passport_issue_date: 'Дата выдачи паспорта',
  director_email: 'Email руководителя',
  director_birth_country: 'Страна рождения руководителя',
  director_registration_country: 'Страна регистрации руководителя',
  director_registration_postal_code: 'Почтовый индекс регистрации руководителя',
  director_registration_house: 'Дом по адресу регистрации руководителя',
  director_registration_apartment: 'Квартира по адресу регистрации руководителя',
  director_registration_date: 'Дата регистрации руководителя по месту жительства',
  director_actual_address: 'Фактический адрес руководителя',
  director_actual_country: 'Страна фактического проживания руководителя',
  director_actual_postal_code: 'Почтовый индекс фактического проживания руководителя',
  director_actual_house: 'Дом по фактическому адресу руководителя',
  director_actual_apartment: 'Квартира по фактическому адресу руководителя',
  bank_name: 'Наименование банка',
  bik: 'БИК',
  settlement_account: 'Расчётный счёт',
  correspondent_account: 'Корреспондентский счёт',
  electronic_document_management_systems: 'Используемые системы ЭДО',
}

async function actor(browser: Browser, role?: string, width = 1440): Promise<Page> {
  const context = await browser.newContext({
    storageState: role ? path.join(runtime, `${role}.storage.json`) : undefined,
    baseURL,
    viewport: { width, height: 1000 },
  })
  sessions.push(context)
  context.on('response', response => {
    const url = new URL(response.url())
    if (url.pathname.startsWith('/api/v1/') && response.status() >= 500) {
      serverErrors.push(`${response.status()} ${url.pathname}`)
    }
  })
  return context.newPage()
}

async function readQuestionnaire(page: Page, id = applicationId): Promise<Record<string, unknown>> {
  const response = await page.request.get(`/api/v1/questionnaire/${id}`)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).questionnaire
}

async function activeCompany(page: Page): Promise<string | null> {
  const response = await page.request.get('/api/v1/auth/me')
  expect(response.ok()).toBeTruthy()
  return (await response.json()).user.active_company_id
}

test.describe('22286 standalone questionnaire — navigation and access on real API', () => {
  test.setTimeout(90_000)
  test.skip(!fixture, 'Run scripts/e2e/22286 acceptance fixture first')

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({
      storageState: path.join(runtime, 'client.storage.json'),
      baseURL,
    })
    try {
      const csrf = (await context.cookies()).find(cookie => cookie.name === 'csrfToken')!.value
      const headers = { Origin: baseURL, 'X-CSRF-Token': csrf }
      for (const index of [0, 1, 2, 3]) {
        const created = await context.request.post('/api/v1/applications', {
          headers: { ...headers, 'Idempotency-Key': randomUUID() },
          data: {
            company_id: fixture!.companies.client.company_id,
            source_type: 'platform',
            name: `Отдельная анкета: браузерная проверка ${index + 1}`,
            vehicles: [{ modification_id: 'questionnaire22286-model', custom_price: '1000000', is_model_order: true }],
          },
        })
        expect(created.status()).toBe(201)
        const id: string = (await created.json()).application_id
        if (index === 0) applicationId = id
        else if (index === 1) secondApplicationId = id
        else if (index === 2) {
          untouchedApplicationId = id
          continue
        }
        else emptyFieldsApplicationId = id
        const saved = await context.request.put(`/api/v1/questionnaire/${id}`, {
          headers,
          data: index === 3 ? {
            ...Object.fromEntries(Object.keys(emptyEditableFields).map(field => [field, null])),
            full_company_name: emptyFieldsCompanyName,
            company_phone: '+74951234567',
            // The real API normalizes an empty scalar string to null, while
            // an empty nested contact string remains an empty string.
            company_website: '',
            employee_count: 0,
            director_is_pdl: false,
            director_name_changed: true,
            director_actual_same_as_registration: false,
            main_counterparties: [],
            open_bank_accounts: [],
            contact_person: { name: 'Контакт незаполненной анкеты', position: '', phone: null, email: 'empty-fields@example.test' },
          } : {
            full_company_name: index === 0 ? companyName : 'ООО Вторая независимая анкета',
            legal_address: 'Казань, улица Анкетная, 41',
            company_phone: '+74951234567',
            company_email: 'questionnaire-page@example.test',
            director_full_name: 'Иванова Анна Сергеевна',
            director_sex: 'female',
            director_name_changed: true,
            has_beneficiary: true,
            contact_person: { name: index === 0 ? 'Петрова Мария Ивановна' : 'Контакт второй анкеты', position: 'Менеджер', phone: '+74951234568', email: 'contact@example.test' },
          },
        })
        expect(saved.ok()).toBeTruthy()
      }
    } finally {
      await context.close()
    }
  })

  test.afterEach(async () => {
    await Promise.all(sessions.splice(0).map(context => context.close()))
    expect(serverErrors.splice(0)).toEqual([])
  })

  test('client opens via Continue without a duplicate questionnaire link, saves, and returns through the stepper and back controls', async ({ browser }) => {
    const page = await actor(browser, 'client')
    const companyId = await activeCompany(page)
    expect(companyId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)
    await page.goto('/cabinet')
    const entry = page.getByRole('link', { name: 'Продолжить', exact: true }).and(page.locator(`[href="/application/${applicationId}"]`))
    await expect(entry).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole('link', { name: 'Анкета заявки', exact: true })).toHaveCount(0)
    await page.locator('[data-storefront-block="client.application"]').filter({ has: entry }).screenshot({
      path: path.join(runtime, 'client-application-with-continue.png'),
    })
    await entry.click()
    await expect(page).toHaveURL(url => url.pathname === `/questionnaire/${applicationId}`)
    expect(await activeCompany(page)).toBe(companyId)
    expect((await readQuestionnaire(page)).full_company_name).toBe(companyName)
    await expect(page.getByRole('heading', { name: 'Заполнение анкеты', exact: true })).toBeVisible()
    const website = page.locator('[name="company_website"]')
    await expect(website).toBeEnabled({ timeout: 30_000 })
    await website.fill('invalid site')
    await page.getByRole('button', { name: 'Сохранить и продолжить', exact: true }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'Сайт организации: укажите корректный адрес сайта' })).toBeVisible()
    await expect(page).toHaveURL(url => url.pathname === `/questionnaire/${applicationId}`)
    expect((await readQuestionnaire(page)).company_website).not.toBe('invalid site')

    await website.fill('questionnaire-page.test')
    const email = 'saved-before-continue@example.test'
    await page.locator('[name="company_email"]').fill(email)
    await page.getByRole('button', { name: 'Сохранить и продолжить', exact: true }).click()
    await expect(page).toHaveURL(url => url.pathname === `/application/${applicationId}` && url.searchParams.get('step') === 'company')
    expect(await activeCompany(page)).toBe(companyId)
    expect(await readQuestionnaire(page)).toMatchObject({ company_email: email, company_website: 'questionnaire-page.test' })
    await expect(page.locator('[name="company_phone"]')).toHaveCount(0)

    await page.getByRole('button', { name: 'Назад', exact: true }).click()
    await expect(page).toHaveURL(url => url.pathname === `/questionnaire/${applicationId}`)
    await expect(page.locator('[name="company_email"]')).toHaveValue(email, { timeout: 30_000 })
    await page.getByRole('button', { name: 'Сохранить и продолжить', exact: true }).click()
    await expect(page).toHaveURL(url => url.searchParams.get('step') === 'company')
    await page.getByTestId('application-step-1').click()
    await expect(page).toHaveURL(url => url.pathname === `/questionnaire/${applicationId}`)
    await expect(page.locator('[name="company_email"]')).toHaveValue(email, { timeout: 30_000 })

    // Leaving immediately must flush the pending change rather than cancel its debounce.
    const contact = 'Сохранённый контакт после перехода к заявке'
    await page.locator('[name="contact_person.name"]').fill(contact)
    await page.getByRole('link', { name: 'К заявке', exact: true }).click()
    await expect(page).toHaveURL(url => url.pathname === `/application/${applicationId}` && url.searchParams.get('step') === 'company')
    expect((await readQuestionnaire(page)).contact_person).toMatchObject({ name: contact })
  })

  test('client edits and reloads the standalone questionnaire at 768px and legacy links return to the editor', async ({ browser }) => {
    const page = await actor(browser, 'client', 768)
    await page.goto(`/questionnaire/${applicationId}`)
    await expect(page.locator('[name="company_phone"]')).toBeEnabled({ timeout: 30_000 })
    for (const field of ['company_email', 'legal_address', 'actual_address', 'postal_address']) {
      await expect(page.locator(`[name="${field}"]`)).toBeVisible()
    }
    await expect(page.getByRole('button', { name: 'Добавить бенефициара', exact: true })).toBeVisible()
    await expect(page.locator('[name="edo.not_used"]')).toBeVisible()
    const contact = 'Петрова Мария Ивановна после редактирования'
    const email = 'autosaved-at-768@example.test'
    await page.locator('[name="contact_person.name"]').fill(contact)
    await page.locator('[name="company_email"]').fill(email)
    await expect.poll(async () => await readQuestionnaire(page), { timeout: 15_000 }).toMatchObject({
      company_email: email,
      contact_person: { name: contact },
      director_sex: 'female',
    })
    await page.reload()
    await expect(page.locator('[name="company_email"]')).toHaveValue(email, { timeout: 30_000 })
    await expect(page.locator('[name="contact_person.name"]')).toHaveValue(contact)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: path.join(runtime, 'questionnaire-editor-768.png'), fullPage: true })
    await page.getByRole('link', { name: 'Назад', exact: true }).click()
    await expect(page).toHaveURL(url => url.pathname === `/application/${applicationId}` && url.searchParams.get('step') === 'items')

    for (const query of ['section=questionnaire', 'step=1']) {
      await page.goto(`/application/${applicationId}?${query}&notification_company_id=${fixture!.companies.client.company_id}`)
      await expect(page).toHaveURL(url => url.pathname === `/questionnaire/${applicationId}`)
      expect(new URL(page.url()).searchParams.get('notification_company_id')).toBe(fixture!.companies.client.company_id)
      await expect(page.locator('[name="company_email"]')).toHaveValue(email, { timeout: 30_000 })
    }
  })

  test('assigned application opens the client questionnaire read-only and never writes on load or navigation', async ({ browser }) => {
    const page = await actor(browser, 'client')
    const id = fixture!.application_id
    const before = await readQuestionnaire(page, id)
    const mutations: string[] = []
    page.on('request', request => {
      const pathname = new URL(request.url()).pathname
      if ([`/api/v1/questionnaire/${id}`, `/api/v1/applications/${id}/questionnaire`].includes(pathname)
        && !['GET', 'HEAD'].includes(request.method())) mutations.push(request.method())
    })
    await page.goto(`/questionnaire/${id}`)
    await expect(page.locator('[name="company_phone"]')).toBeDisabled({ timeout: 30_000 })
    await expect(page.locator('[name="company_email"]')).toBeDisabled()
    await expect(page.locator('[name="no_beneficial_owner"]')).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Сохранить и продолжить', exact: true })).toHaveCount(0)
    // Observe delayed writes too: readonly hydration must not start autosave.
    await page.waitForTimeout(2_000)
    await page.reload()
    await expect(page.locator('[name="company_phone"]')).toBeDisabled({ timeout: 30_000 })
    await page.getByRole('button', { name: 'Далее', exact: true }).click()
    await expect(page).toHaveURL(url => url.pathname === `/application/${id}` && url.searchParams.get('step') === 'company')
    expect(await readQuestionnaire(page, id)).toEqual(before)
    expect(mutations).toEqual([])
  })

  test('untouched questionnaire preserves automatic contact data and exits after hydration without another write', async ({ browser }) => {
    const page = await actor(browser, 'client')
    const id = untouchedApplicationId
    const before = await readQuestionnaire(page, id)
    const profile = await page.request.get('/api/v1/auth/me')
    expect(profile.ok()).toBeTruthy()
    const user = (await profile.json()).user as { name: string; phone: string; email: string }
    const mutations: string[] = []
    const isQuestionnaireWrite = (url: string, method: string) =>
      [`/api/v1/questionnaire/${id}`, `/api/v1/applications/${id}/questionnaire`].includes(new URL(url).pathname)
      && !['GET', 'HEAD'].includes(method)
    page.on('request', request => {
      if (isQuestionnaireWrite(request.url(), request.method())) mutations.push(request.method())
    })

    await page.goto(`/questionnaire/${id}`)
    await expect(page.locator('[name="company_phone"]')).toBeEnabled({ timeout: 30_000 })
    await page.getByRole('link', { name: 'Назад', exact: true }).click()
    await expect(page).toHaveURL(url => url.pathname === `/application/${id}` && url.searchParams.get('step') === 'items')
    const autofilled = await readQuestionnaire(page, id)
    const contact = autofilled.contact_person as { name: string; position: string; phone: string; email: string }
    expect(contact).toMatchObject({ name: user.name, position: '', email: user.email })
    expect(contact.phone.replace(/\D/g, '')).toBe(user.phone.replace(/\D/g, ''))
    // Existing form hydration fills the signed-in contact and normalizes ОСНО to ОСН.
    // No other questionnaire fields may change on an untouched exit.
    expect(autofilled).toEqual({
      ...before,
      contact_person: contact,
      phone: contact.phone,
      email: contact.email,
      tax_system: 'ОСН',
      updated_at: autofilled.updated_at,
    })

    // Existing tax/SOPD hydration emits a save on mount. Once that real save has
    // completed, leaving an untouched editor must not enqueue another PUT.
    const hydrationSaved = page.waitForResponse(response =>
      isQuestionnaireWrite(response.url(), response.request().method()) && response.status() === 200,
    )
    await page.goto(`/questionnaire/${id}`)
    await expect(page.locator('[name="contact_person.name"]')).toHaveValue(contact.name, { timeout: 30_000 })
    await (await hydrationSaved).finished()
    await page.waitForLoadState('networkidle')
    const hydrated = await readQuestionnaire(page, id)
    expect(hydrated).toEqual({ ...autofilled, updated_at: hydrated.updated_at })
    const writesAfterHydration = mutations.length
    await page.getByRole('link', { name: 'К заявке', exact: true }).click()
    await expect(page).toHaveURL(url => url.pathname === `/application/${id}` && url.searchParams.get('step') === 'company')
    expect(await readQuestionnaire(page, id)).toEqual(hydrated)
    expect(mutations).toHaveLength(writesAfterHydration)
  })

  test('failed immediate save keeps the editor and its input, then a retry persists before leaving', async ({ browser }) => {
    const page = await actor(browser, 'client')
    await page.goto(`/questionnaire/${applicationId}`)
    const email = page.locator('[name="company_email"]')
    await expect(email).toBeEnabled({ timeout: 30_000 })
    const before = await readQuestionnaire(page)
    const endpoint = (url: URL) => url.pathname === `/api/v1/applications/${applicationId}/questionnaire`
    let blockedWrites = 0
    await page.route(endpoint, async route => {
      if (route.request().method() !== 'PUT') return route.continue()
      blockedWrites += 1
      await route.abort('failed')
    })
    const pendingEmail = 'retry-after-network-error@example.test'
    await email.fill(pendingEmail)
    await page.getByRole('link', { name: 'К заявке', exact: true }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'Не удалось сохранить анкету' })).toBeVisible()
    expect(blockedWrites).toBeGreaterThan(0)
    await expect(page).toHaveURL(url => url.pathname === `/questionnaire/${applicationId}`)
    await expect(email).toHaveValue(pendingEmail)
    expect((await readQuestionnaire(page)).company_email).toBe(before.company_email)

    await page.unroute(endpoint)
    await page.getByRole('button', { name: 'Повторить сохранение', exact: true }).click()
    await expect.poll(async () => (await readQuestionnaire(page)).company_email, { timeout: 15_000 }).toBe(pendingEmail)
    await page.getByRole('link', { name: 'К заявке', exact: true }).click()
    await expect(page).toHaveURL(url => url.pathname === `/application/${applicationId}` && url.searchParams.get('step') === 'company')
    expect((await readQuestionnaire(page)).company_email).toBe(pendingEmail)
  })

  test('editing two applications keeps their contacts isolated after reopening and reload', async ({ browser }) => {
    const page = await actor(browser, 'client')
    const names = ['Первая анкета: собственный контакт', 'Вторая анкета: другой контакт']
    const ids = [applicationId, secondApplicationId]
    for (const [index, id] of ids.entries()) {
      await page.goto(`/questionnaire/${id}`)
      const contact = page.locator('[name="contact_person.name"]')
      await expect(contact).toBeEnabled({ timeout: 30_000 })
      if (index === 1) await expect(contact).toHaveValue('Контакт второй анкеты')
      await contact.fill(names[index])
      await expect.poll(async () => (await readQuestionnaire(page, id)).contact_person, { timeout: 15_000 }).toMatchObject({ name: names[index] })
    }
    for (const [index, id] of ids.entries()) {
      await page.goto(`/questionnaire/${id}`)
      await expect(page.locator('[name="contact_person.name"]')).toHaveValue(names[index], { timeout: 30_000 })
      await page.reload()
      await expect(page.locator('[name="contact_person.name"]')).toHaveValue(names[index], { timeout: 30_000 })
      expect((await readQuestionnaire(page, id)).contact_person).toMatchObject({ name: names[index] })
    }
  })

  test('administrator reads the same page and returns to the selected application', async ({ browser }) => {
    const page = await actor(browser, 'admin')
    await page.goto(`/workspace/questionnaire/${applicationId}?source=applications`)
    await expect(page.getByTestId('application-questionnaire')).toContainText(companyName, { timeout: 30_000 })
    await page.reload()
    await expect(page.getByTestId('application-questionnaire')).toContainText('Иванова Анна Сергеевна', { timeout: 30_000 })
    await page.getByRole('link', { name: 'Вернуться к заявке', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/workspace/applications\\?.*application=${applicationId}`))
    const entry = page.getByRole('link', { name: 'Открыть анкету', exact: true }).and(page.locator(`[href*="${applicationId}"]`))
    await expect(entry).toBeVisible({ timeout: 30_000 })
    await entry.click()
    await expect(page.getByTestId('application-questionnaire')).toContainText(companyName, { timeout: 30_000 })
  })

  test('administrator sees all empty questionnaire fields and preserves filled, false and zero values after reload at 768px', async ({ browser }) => {
    const page = await actor(browser, 'admin', 768)
    const before = await readQuestionnaire(page, emptyFieldsApplicationId)
    const emptyFields = {
      ...emptyEditableFields,
      consent_validity_period: 'Срок действия согласий',
      consent_revocation_procedure: 'Порядок отзыва согласий',
      questionnaire_completed_at: 'Дата и время заполнения анкеты',
    }
    for (const field of Object.keys(emptyFields)) expect(before[field], field).toBeNull()
    expect(before).toMatchObject({
      full_company_name: emptyFieldsCompanyName,
      company_phone: '+74951234567',
      employee_count: 0,
      director_is_pdl: false,
      director_name_changed: true,
      director_actual_same_as_registration: false,
      main_counterparties: [],
      open_bank_accounts: [],
      contact_person: { name: 'Контакт незаполненной анкеты', position: '', phone: null, email: 'empty-fields@example.test' },
    })
    const section = page.getByTestId('application-questionnaire')
    const rowValue = (label: string) => section.locator(':scope > dl > div')
      .filter({ has: page.getByText(label, { exact: true }) }).locator(':scope > dd')
    const assertVisibleValues = async () => {
      await expect(section).toContainText(emptyFieldsCompanyName, { timeout: 30_000 })
      for (const label of Object.values(emptyFields)) {
        await expect(rowValue(label), label).toBeVisible()
        await expect(rowValue(label), label).toHaveText('Не указано')
      }
      for (const [label, value] of [
        ['Полное наименование компании', emptyFieldsCompanyName],
        ['Телефон организации', '+74951234567'],
        ['Среднесписочная численность сотрудников', '0'],
        ['Руководитель является ПДЛ или родственником ПДЛ', 'Нет'],
        ['Отметка о смене ФИО', 'Да'],
        ['Фактический адрес руководителя совпадает с адресом регистрации', 'Нет'],
        ['Основные контрагенты', 'Нет сведений'],
        ['Открытые расчётные счета', 'Нет сведений'],
        ['Документ о назначении руководителя', 'Документ о назначении руководителя не предоставлен'],
      ]) await expect(rowValue(label), label).toHaveText(value)
      const contact = rowValue('ФИО, должность, телефон и email контактного лица')
      await expect(contact).toContainText('Контакт незаполненной анкеты')
      await expect(contact).toContainText('empty-fields@example.test')
      for (const label of ['Должность', 'Телефон контактного лица']) {
        await expect(contact.locator('dl > div').filter({ has: page.getByText(label, { exact: true }) }).locator(':scope > dd')).toHaveText('Не указано')
      }
      await expect(section.locator('dt').filter({ hasText: /^Дата (создания|изменения) анкеты$/ })).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
    }
    await page.goto(`/workspace/questionnaire/${emptyFieldsApplicationId}?source=applications`)
    await assertVisibleValues()
    await page.reload()
    await assertVisibleValues()
    expect(await readQuestionnaire(page, emptyFieldsApplicationId)).toEqual(before)
    await page.screenshot({ path: path.join(runtime, 'questionnaire-empty-fields-768.png'), fullPage: true })
  })

  test('LC navigation preserves both company contexts without changing the active company', async ({ browser }) => {
    const page = await actor(browser, 'lc_a')
    const id = fixture!.application_id
    const company = fixture!.companies.lc_a
    const before = await activeCompany(page)
    expect(before).toBe(company.company_id)
    const query = new URLSearchParams({
      leasing_company_id: company.leasing_company_id!,
      notification_company_id: company.company_id,
    })
    await page.goto(`/workspace/leasing-applications/${id}?${query}`)
    await page.getByRole('link', { name: 'Открыть анкету', exact: true }).click()
    await expect(page.getByTestId('application-questionnaire')).toBeVisible({ timeout: 30_000 })
    for (const [key, value] of query) expect(new URL(page.url()).searchParams.get(key)).toBe(value)
    await page.reload()
    const section = page.getByTestId('application-questionnaire')
    await expect(section.locator('dt').filter({ hasText: /^Телефон организации$/ })).toBeVisible({ timeout: 30_000 })
    await expect(section.locator('dt').filter({ hasText: /^Email организации$/ })).toHaveCount(0)
    expect(await activeCompany(page)).toBe(before)
    await page.getByRole('link', { name: 'Вернуться к заявке', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/workspace/leasing-applications/${id}\\?`))
    for (const [key, value] of query) expect(new URL(page.url()).searchParams.get(key)).toBe(value)
    expect(await activeCompany(page)).toBe(before)
    await page.goto(`/questionnaire/${id}?${query}&source=leasing`)
    await expect(page).toHaveURL(new RegExp(`/workspace/questionnaire/${id}\\?`))
    for (const [key, value] of query) expect(new URL(page.url()).searchParams.get(key)).toBe(value)
    await expect(page.getByTestId('application-questionnaire').locator('dt').filter({ hasText: /^Телефон организации$/ })).toBeVisible({ timeout: 30_000 })
    expect(await activeCompany(page)).toBe(before)
  })

  test('outsider and unassigned LC cannot read the standalone questionnaire', async ({ browser }) => {
    for (const [role, route] of [['outsider', '/questionnaire/'], ['lc_a', '/workspace/questionnaire/']]) {
      const page = await actor(browser, role)
      await page.goto(`${route}${applicationId}`)
      const error = page.getByRole('alert').filter({ hasText: /доступ|найден|не удалось/i })
      await expect(error).toBeVisible({ timeout: 30_000 })
      await expect(page.locator('[name="company_phone"]')).toHaveCount(0)
      await expect(page.getByTestId('application-questionnaire').locator('dt')).toHaveCount(0)
      await expect(page.locator('body')).not.toContainText(companyName)
      await expect(page.locator('body')).not.toContainText('Иванова Анна Сергеевна')
    }
  })

  test('missing and malformed links show a useful error without retaining the previous data', async ({ browser }) => {
    const page = await actor(browser, 'client')
    await page.goto(`/questionnaire/${applicationId}`)
    await expect(page.locator('[name="company_email"]')).toBeEnabled({ timeout: 30_000 })
    for (const id of [randomUUID(), 'not-a-uuid']) {
      await page.goto(`/questionnaire/${id}`)
      const error = page.getByRole('alert').filter({ hasText: /найден|некоррект|неверн|доступ|не удалось/i })
      await expect(error).toBeVisible({ timeout: 30_000 })
      await expect(page.locator('body')).not.toContainText(companyName)
      await expect(page.locator('[name="company_phone"]')).toHaveCount(0)
      await expect(page.getByTestId('application-questionnaire').locator('dt')).toHaveCount(0)
    }
  })

  test('anonymous direct link requests authentication and keeps its destination', async ({ browser }) => {
    const page = await actor(browser)
    const destination = `/questionnaire/${applicationId}?source=application`
    await page.goto(destination)
    await expect(page).toHaveURL(/\/auth\?/, { timeout: 30_000 })
    expect(new URL(page.url()).searchParams.get('redirect')).toBe(destination)
    await expect(page.locator('body')).not.toContainText(companyName)
  })
})
