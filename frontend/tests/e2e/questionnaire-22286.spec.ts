import { test, expect, type Browser, type BrowserContext, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const runtime = process.env.QUESTIONNAIRE_E2E_RUNTIME || '/runtime'
const manifestPath = path.join(runtime, 'manifest.json')
interface Manifest { application_id: string; ui_application_id?: string; purpose_ui_application_id?: string; purpose_ui_line_id?: string; companies: Record<string, { company_id: string; leasing_company_id?: string }> }
const manifest: Manifest | null = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : null
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:18286'
const sessions: BrowserContext[] = []
const serverErrors: string[] = []
async function actor(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: path.join(runtime, `${role}.storage.json`), baseURL, viewport: { width: 1440, height: 1000 } })
  sessions.push(context)
  const page = await context.newPage()
  page.on('response', response => {
    const url = new URL(response.url())
    if (url.pathname.startsWith('/api/v1/') && response.status() >= 500) serverErrors.push(`${response.status()} ${url.pathname}`)
  })
  return page
}
async function questionnaire(page: Page, applicationId: string): Promise<Record<string, unknown>> {
  const response = await page.request.get(`/api/v1/questionnaire/${applicationId}`)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).questionnaire
}

test.describe('22286 application questionnaire — real API and database', () => {
  test.setTimeout(90_000)
  test.skip(!manifest, 'Run scripts/e2e/22286 acceptance fixture first')
  test.afterEach(async () => { await Promise.all(sessions.splice(0).map(context => context.close())); expect(serverErrors.splice(0)).toEqual([]) })

  test('client saves organisation, one contact, postal address and EDO, then reloads', async ({ browser }) => {
    test.skip(!manifest?.ui_application_id, 'Create independent editable UI application fixture')
    const page = await actor(browser, 'client')
    const appId = manifest!.ui_application_id!
    await page.goto(`/questionnaire/${appId}`)
    await expect(page.locator('[name="company_phone"]')).toBeEnabled({ timeout: 30_000 })
    await expect(page.getByRole('button', { name: 'Добавить контакт', exact: true })).toHaveCount(0)
    await page.locator('[name="foreign_company_name"]').fill('Questionnaire Company International')
    await page.locator('[name="company_phone"]').fill('+79991234567')
    await page.locator('[name="company_email"]').fill('office@questionnaire22286.test')
    await page.locator('[name="company_website"]').fill('company.test')
    await page.locator('[name="contact_person.name"]').fill('Тестовый основной контакт')
    await page.locator('[name="contact_person.position"]').fill('Директор')
    await page.locator('[name="legal_address"]').fill('Москва, Тестовая улица, 22286')
    await page.locator('[name="postal_address_matches_legal"]').check()
    await expect(page.locator('[name="postal_address"]')).toBeDisabled()
    await expect(page.locator('[name="postal_address"]')).toHaveValue('Москва, Тестовая улица, 22286')
    await page.locator('[name="edo.sbis"]').check()
    await page.locator('[name="edo.other"]').check()
    await page.locator('[name="edo.other_name"]').fill('Тестовая ЭДО')
    await expect.poll(async () => (await questionnaire(page, appId)).company_website, { timeout: 15_000 }).toBe('company.test')
    await expect.poll(async () => (await questionnaire(page, appId)).electronic_document_management_systems, { timeout: 15_000 }).toMatchObject({ sbis: true, other: true, other_name: 'Тестовая ЭДО', not_used: false })
    await page.reload()
    await expect(page.locator('[name="company_website"]')).toHaveValue('company.test', { timeout: 30_000 })
    await expect(page.locator('[name="foreign_company_name"]')).toHaveValue('Questionnaire Company International')
    await expect(page.locator('[name="contact_person.name"]')).toHaveValue('Тестовый основной контакт')
    await expect(page.locator('[name="postal_address"]')).toBeDisabled()
    await page.locator('[name="edo.not_used"]').check()
    await expect(page.locator('[name="edo.sbis"]')).not.toBeChecked()
    await expect(page.locator('[name="edo.other_name"]')).toHaveCount(0)
    await expect.poll(async () => (await questionnaire(page, appId)).electronic_document_management_systems, { timeout: 15_000 }).toMatchObject({ sbis: false, other: false, other_name: null, not_used: true })
    await page.screenshot({ path: path.join(runtime, 'questionnaire-edited.png'), fullPage: true })
    await page.locator('[name="company_website"]').fill('invalid site')
    await expect(page.getByRole('alert').filter({ hasText: 'Сайт организации: укажите корректный адрес сайта' })).toBeVisible()
    await expect.poll(async () => (await questionnaire(page, appId)).company_website).toBe('company.test')
  })

  test('client preserves the actual-address link after reload and can unlink the address', async ({ browser }) => {
    test.skip(!manifest?.ui_application_id, 'Create independent editable UI application fixture')
    const page = await actor(browser, 'client')
    const appId = manifest!.ui_application_id!
    const legal = page.locator('[name="legal_address"]')
    const actual = page.locator('[name="actual_address"]')
    const linked = page.locator('[name="actual_address_same_as_legal"]')
    await page.goto(`/questionnaire/${appId}`)
    await expect(legal).toBeEnabled({ timeout: 30_000 })
    await legal.fill('Москва, Связанный адрес, 1')
    await linked.check()
    await expect(actual).toBeDisabled()
    await expect(actual).toHaveValue('Москва, Связанный адрес, 1')
    await expect.poll(async () => await questionnaire(page, appId), { timeout: 15_000 }).toMatchObject({ actual_address_same_as_legal: true, actual_address: 'Москва, Связанный адрес, 1' })
    await page.reload()
    await expect(linked).toBeChecked({ timeout: 30_000 })
    await expect(actual).toBeDisabled()
    await expect(actual).toHaveValue('Москва, Связанный адрес, 1')

    await legal.fill('Москва, Новый юридический адрес, 2')
    await expect(actual).toHaveValue('Москва, Новый юридический адрес, 2')
    await expect.poll(async () => await questionnaire(page, appId), { timeout: 15_000 }).toMatchObject({ actual_address_same_as_legal: true, legal_address: 'Москва, Новый юридический адрес, 2', actual_address: 'Москва, Новый юридический адрес, 2' })
    await page.reload()
    await expect(linked).toBeChecked({ timeout: 30_000 })
    await expect(actual).toHaveValue('Москва, Новый юридический адрес, 2')

    await linked.uncheck()
    await expect(actual).toBeEnabled()
    await actual.fill('Казань, Самостоятельный адрес, 3')
    await expect.poll(async () => await questionnaire(page, appId), { timeout: 15_000 }).toMatchObject({ actual_address_same_as_legal: false, actual_address: 'Казань, Самостоятельный адрес, 3' })
    await legal.fill('Москва, Другой юридический адрес, 4')
    await expect(actual).toHaveValue('Казань, Самостоятельный адрес, 3')
    await expect.poll(async () => await questionnaire(page, appId), { timeout: 15_000 }).toMatchObject({ actual_address_same_as_legal: false, legal_address: 'Москва, Другой юридический адрес, 4', actual_address: 'Казань, Самостоятельный адрес, 3' })
    await page.reload()
    await expect(linked).not.toBeChecked({ timeout: 30_000 })
    await expect(legal).toHaveValue('Москва, Другой юридический адрес, 4')
    await expect(actual).toBeEnabled()
    await expect(actual).toHaveValue('Казань, Самостоятельный адрес, 3')
    await page.screenshot({ path: path.join(runtime, 'questionnaire-address-unlinked.png'), fullPage: true })
  })

  test('passport hides only the edited percentage and preserves it after save and reload', async ({ browser }) => {
    test.skip(!manifest?.ui_application_id, 'Create UI technical passport fixture')
    const page = await actor(browser, 'client')
    await page.goto(`/questionnaire/${manifest!.ui_application_id}`)
    const passport = page.getByRole('heading', { name: 'Проверка паспортных данных', exact: true }).locator('..').locator('..')
    await expect(passport.getByText('0%', { exact: true })).toBeVisible({ timeout: 30_000 })
    await expect(passport.locator('label').filter({ hasText: 'Фамилия' })).toContainText('98%')
    await passport.getByLabel(/Место рождения/).fill('Казань')
    await expect(passport.getByText('0%', { exact: true })).toHaveCount(0)
    await expect(passport.locator('label').filter({ hasText: 'Фамилия' })).toContainText('98%')
    await passport.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
    await expect.poll(async () => (await questionnaire(page, manifest!.ui_application_id!)).director_birth_place, { timeout: 15_000 }).toBe('Казань')
    await page.reload()
    const reloaded = page.getByRole('heading', { name: 'Проверка паспортных данных', exact: true }).locator('..').locator('..')
    await expect(reloaded.getByLabel(/Место рождения/)).toHaveValue('Казань', { timeout: 30_000 })
    await expect(reloaded.getByText('0%', { exact: true })).toHaveCount(0)
    await expect(reloaded.locator('label').filter({ hasText: 'Фамилия' })).toContainText('98%')
    await reloaded.screenshot({ path: path.join(runtime, 'passport-edited-confidence.png') })
  })

  test('female beneficiary stores UUID, PDL flags and manually entered passport without OCR', async ({ browser }) => {
    test.skip(!manifest?.ui_application_id, 'Create UI application fixture')
    const page = await actor(browser, 'client')
    const appId = manifest!.ui_application_id!
    await page.goto(`/questionnaire/${appId}`)
    const absent = page.getByRole('checkbox', { name: 'Бенефициарный владелец отсутствует', exact: true })
    await expect(absent).toBeVisible({ timeout: 30_000 })
    await absent.uncheck()
    await page.getByRole('button', { name: 'Добавить бенефициара', exact: true }).click()
    const beneficiary = page.locator('article').filter({ has: page.getByRole('heading', { name: 'Бенефициар 1', exact: true }) })
    await beneficiary.locator('[name="beneficiaries.0.full_name"]').fill('Бенефициарова Анна Ивановна')
    await beneficiary.locator('[name="beneficiaries.0.share_percentage"]').fill('40')
    await beneficiary.getByRole('button', { name: 'Сохранить и заполнить паспорт' }).click()
    await beneficiary.getByLabel('Является ПДЛ или родственником ПДЛ', { exact: true }).check()
    await beneficiary.getByLabel(/ФИО ПДЛ или родственника ПДЛ/).fill('Тестовый родственник')
    await beneficiary.getByLabel('Имеется ли отметка о смене ФИО', { exact: true }).check()
    await beneficiary.getByRole('button', { name: 'Ввести паспорт вручную', exact: true }).click()
    const passport = beneficiary.getByRole('heading', { name: 'Проверка паспортных данных', exact: true }).locator('..').locator('..')
    await expect(passport.getByLabel(/^Гражданство/)).toHaveValue('')
    const citizenship = passport.getByRole('combobox', { name: /^Гражданство/ })
    await citizenship.fill('Российская')
    await passport.getByRole('option', { name: 'Российская Федерация', exact: true }).click()
    await expect(citizenship).toHaveValue('Российская Федерация')
    for (const [label, value] of [['Имя', 'Анна'], ['Фамилия', 'Бенефициарова'], ['Отчество', 'Ивановна'], ['Дата рождения', '01.01.1980'], ['Место рождения', 'Казань'], ['Серия документа', '1234'], ['Номер документа', '123457'], ['Дата выдачи', '01.01.2020'], ['Код подразделения', '123-456'], ['Кем выдан', 'УМВД России']]) await passport.getByLabel(new RegExp(`^${label}`)).fill(value)
    await passport.getByLabel(/^Пол/).selectOption('female')
    await passport.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
    await expect.poll(async () => (await questionnaire(page, appId)).beneficiaries, { timeout: 15_000 }).toEqual(expect.arrayContaining([expect.objectContaining({ full_name: 'Бенефициарова Анна Ивановна', sex: 'female', is_pdl: true, name_changed: true, pdl_related_person_name: 'Тестовый родственник', passport_number: '123457' })]))
    const saved = ((await questionnaire(page, appId)).beneficiaries as Array<{ id: string }>)[0]
    expect(saved.id).toMatch(/^[0-9a-f-]{36}$/)
    await expect.poll(async () => ((await questionnaire(page, appId)).beneficiaries as Array<{ share_percentage: number | null }>)[0].share_percentage).toBe(40)
    await beneficiary.locator('[name="beneficiaries.0.share_percentage"]').fill('')
    await expect.poll(async () => ((await questionnaire(page, appId)).beneficiaries as Array<{ share_percentage: number | null }>)[0].share_percentage).toBeNull()
    await expect.poll(async () => (await questionnaire(page, appId)).beneficiaries).toEqual(expect.arrayContaining([expect.objectContaining({ id: saved.id, share_percentage: null, is_pdl: true, name_changed: true, pdl_related_person_name: 'Тестовый родственник', passport_number: '123457' })]))
    await page.reload()
    await expect(page.locator('[name="beneficiaries.0.full_name"]')).toHaveValue('Бенефициарова Анна Ивановна', { timeout: 30_000 })
    await expect(passport.getByLabel(/^Пол/)).toHaveValue('female')
    await expect(beneficiary.locator('[name="beneficiaries.0.share_percentage"]')).toHaveValue('')
    const candidates = await page.request.get(`/api/v1/applications/${appId}/sopd-signer-candidates`)
    expect(candidates.ok()).toBeTruthy()
    expect((await candidates.json()).candidates).toEqual(expect.arrayContaining([expect.objectContaining({ key: `beneficiary:${saved.id}`, role: 'beneficiary' })]))
    await expect(page.getByText('Не удалось загрузить список подписантов СОПД', { exact: true })).toHaveCount(0)
    await expect(beneficiary.getByLabel('Имеется ли отметка о смене ФИО', { exact: true })).toBeChecked()
    await expect(passport).not.toContainText('%')
    await page.screenshot({ path: path.join(runtime, 'beneficiary-manual-passport.png'), fullPage: true })
    await beneficiary.getByRole('button', { name: 'Удалить', exact: true }).click()
    await expect.poll(async () => (await questionnaire(page, appId)).beneficiaries).toEqual([])
  })

  test('administrator manages visibility and ordinary requirements while document-request requirements stay unavailable', async ({ browser }) => {
    const page = await actor(browser, 'admin')
    await page.setViewportSize({ width: 768, height: 1000 })
    await page.goto('/workspace/questionnaire-settings')
    await expect(page.getByRole('main').getByRole('heading', { name: 'Настройки анкет' })).toBeVisible({ timeout: 30_000 })
    await page.getByRole('combobox', { name: 'Лизинговая компания', exact: true }).selectOption(manifest!.companies.lc_a.leasing_company_id!)
    const phoneVisibility = page.getByRole('checkbox', { name: 'Доступно: Телефон организации', exact: true })
    const phoneRequired = page.getByRole('checkbox', { name: 'Обязательно: Телефон организации', exact: true })
    await expect(phoneVisibility).toBeEnabled()
    await expect(phoneVisibility).toBeChecked()
    await expect(phoneRequired).toBeEnabled()
    await expect(phoneRequired).toBeChecked()
    for (const label of ['Подпись руководителя или представителя', 'Оттиск печати']) {
      const required = page.getByRole('checkbox', { name: `Обязательно: ${label}`, exact: true })
      await expect(required).toBeDisabled()
      await expect(required).not.toBeChecked()
      await expect(required).toHaveAccessibleDescription('Поле не заполняется в текущей анкете, поэтому его нельзя сделать обязательным.')
      await expect(page.getByRole('checkbox', { name: `Доступно: ${label}`, exact: true })).toBeEnabled()
    }
    const requestedFieldLabels = [
      'Документ о назначении руководителя',
      'Наличие гособоронзаказа',
      'Лицензии и членство в СРО',
      'Кредиты, займы и лизинг',
      'Поручительства за третьих лиц',
      'Возможность дополнительного обеспечения',
      'СНИЛС руководителя',
      'Открытые расчётные счета',
      'Выгодоприобретатель по сделке',
    ]
    for (const label of requestedFieldLabels) {
      const required = page.getByRole('checkbox', { name: `Обязательно: ${label}`, exact: true })
      await expect(required).toBeDisabled()
      await expect(required).not.toBeChecked()
      await expect(required).toHaveAccessibleDescription('Сведения заполняются по дозапросу после назначения ЛК, поэтому их нельзя сделать обязательными до назначения.')
      await expect(page.getByRole('checkbox', { name: `Доступно: ${label}`, exact: true })).toBeEnabled()
    }
    const savedSettings = async () => {
      const response = await page.request.get(`/api/v1/leasing/companies/${manifest!.companies.lc_a.leasing_company_id}/questionnaire-settings`)
      expect(response.ok()).toBeTruthy()
      const settings = await response.json() as { fields: Array<{ field: string; enabled: boolean; required: boolean }> }
      return Object.fromEntries(settings.fields.map(({ field, enabled, required }) => [field, { enabled, required }]))
    }
    const website = page.getByRole('checkbox', { name: 'Доступно: Сайт организации', exact: true })
    const appointmentVisibility = page.getByRole('checkbox', { name: 'Доступно: Документ о назначении руководителя', exact: true })
    const appointmentInitiallyVisible = await appointmentVisibility.isChecked()
    await website.uncheck()
    await phoneRequired.uncheck()
    await appointmentVisibility.setChecked(!appointmentInitiallyVisible)
    await page.getByRole('button', { name: 'Сохранить настройки', exact: true }).click()
    await expect.poll(savedSettings).toMatchObject({
      company_website: { enabled: false },
      company_phone: { enabled: true, required: false },
      director_appointment_document: { enabled: !appointmentInitiallyVisible, required: false },
    })
    await website.check()
    await phoneRequired.check()
    await appointmentVisibility.setChecked(appointmentInitiallyVisible)
    await page.getByRole('button', { name: 'Сохранить настройки', exact: true }).click()
    await expect.poll(savedSettings).toMatchObject({
      company_website: { enabled: true },
      company_phone: { enabled: true, required: true },
      director_appointment_document: { enabled: appointmentInitiallyVisible, required: false },
    })
    await expect(page.getByRole('status').filter({ hasText: 'Изменения сохранены' })).toBeVisible()
    await page.getByRole('button', { name: 'Причины отсутствия бенефициара', exact: true }).click()
    const code = `ui_reason_${Date.now()}`
    await page.getByLabel('Код', { exact: true }).fill(code)
    await page.getByLabel('Наименование', { exact: true }).fill('Причина из браузерного сценария')
    await page.getByRole('button', { name: 'Добавить', exact: true }).click()
    const row = page.locator('form').filter({ has: page.getByLabel(`Название: ${code}`, { exact: true }) })
    await expect(row).toBeVisible()
    await row.getByLabel('Активно', { exact: true }).uncheck()
    await row.getByRole('button', { name: 'Сохранить', exact: true }).click()
    await expect(page.getByRole('status').filter({ hasText: 'Изменения сохранены' })).toBeVisible()
    await page.reload()
    await page.getByRole('button', { name: 'Причины отсутствия бенефициара', exact: true }).click()
    await expect(page.locator('form').filter({ has: page.getByLabel(`Название: ${code}`, { exact: true }) }).getByLabel('Активно', { exact: true })).not.toBeChecked()
  })

  test('client answers additional requests without files and with a document title', async ({ browser }) => {
    const lc = await actor(browser, 'lc_a')
    const client = await actor(browser, 'client')
    const appId = manifest!.application_id
    const csrf = (await lc.context().cookies()).find(cookie => cookie.name === 'csrfToken')!.value
    const requestDocuments = async () => {
      const response = await lc.request.put(`/api/v1/leasing/applications/${appId}/request-documents`, { headers: { Origin: baseURL, 'X-CSRF-Token': csrf }, data: { requestedDocuments: [{ source: 'catalog', document_type: 'loans_docs', display_name: 'Кредиты E2E браузера' }] } })
      expect(response.ok()).toBeTruthy()
    }
    const openResponse = async () => {
      await client.goto(`/application/${appId}`)
      await client.getByRole('button', { name: 'Ответить на запрос', exact: true }).click()
      return client.getByRole('dialog')
    }
    await requestDocuments()
    const empty = await openResponse()
    await expect(empty.getByText('Без файла в анкете будет указано:', { exact: false })).toBeVisible()
    await expect(empty.getByRole('checkbox')).toHaveCount(0)
    await empty.getByRole('button', { name: 'Отправить', exact: true }).click()
    await expect(empty).toHaveCount(0)
    await expect.poll(async () => (await questionnaire(client, appId)).loans_credits_leasing).toMatchObject({ status: 'missing' })
    await requestDocuments()
    const modal = await openResponse()
    await modal.locator('input[type="file"]').setInputFiles({ name: 'technical-original.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic document for questionnaire E2E') })
    await modal.getByLabel('Название документа в анкете', { exact: true }).fill('Сведения о кредитах для лизинга')
    await modal.getByRole('button', { name: 'Отправить', exact: true }).click()
    await expect(modal).toHaveCount(0)
    await expect.poll(async () => (await questionnaire(client, appId)).loans_credits_leasing).toMatchObject({ status: 'attached', documents: [expect.objectContaining({ user_title: 'Сведения о кредитах для лизинга' })] })
    await client.screenshot({ path: path.join(runtime, 'additional-documents-response.png'), fullPage: true })
  })


  test('counterparty comments are optional and survive response history and the assembled questionnaire', async ({ browser }) => {
    const lc = await actor(browser, 'lc_a')
    const client = await actor(browser, 'client')
    const admin = await actor(browser, 'admin')
    await client.setViewportSize({ width: 768, height: 1000 })
    const appId = manifest!.application_id
    const csrf = (await lc.context().cookies()).find(cookie => cookie.name === 'csrfToken')!.value
    const requested = await lc.request.put(`/api/v1/leasing/applications/${appId}/request-documents`, {
      headers: { Origin: baseURL, 'X-CSRF-Token': csrf },
      data: { requestedDocuments: [{ source: 'catalog', document_type: 'main_counterparties', display_name: 'Контрагенты с комментарием E2E' }] },
    })
    expect(requested.ok()).toBeTruthy()
    const requestId = (await requested.json()).items[0].id as string
    await client.goto(`/application/${appId}`)
    await client.getByRole('button', { name: 'Ответить на запрос', exact: true }).click({ timeout: 30_000 })
    const dialog = client.getByRole('dialog')
    const comment = 'Поставка техники по договору № 41'
    await dialog.getByLabel(/^ИНН/).fill('7700000000')
    await dialog.getByLabel(/^Название/).fill('Контрагент с комментарием')
    await dialog.getByLabel('Комментарий (необязательно)', { exact: true }).fill(`  ${comment}  `)
    await dialog.getByRole('button', { name: 'Добавить ещё контрагента', exact: true }).click()
    await dialog.getByLabel(/^ИНН/).nth(1).fill('770000000001')
    await dialog.getByLabel(/^Название/).nth(1).fill('Контрагент без комментария')
    await expect(dialog.getByLabel('Комментарий (необязательно)', { exact: true }).nth(1)).toHaveValue('')
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBeTruthy()
    await client.screenshot({ path: path.join(runtime, 'counterparty-comment-form-768.png'), fullPage: true })
    const submitted = client.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/documents' && response.request().method() === 'POST')
    await dialog.getByRole('button', { name: 'Отправить', exact: true }).click()
    expect((await submitted).status()).toBe(201)
    await expect(dialog).toHaveCount(0)
    const expected = [
      { name: 'Контрагент с комментарием', inn: '7700000000', comment },
      { name: 'Контрагент без комментария', inn: '770000000001' },
    ]
    await expect.poll(async () => (await questionnaire(client, appId)).main_counterparties).toEqual(expected)
    const historyResponse = await client.request.get(`/api/v1/applications/${appId}/document-requests`)
    expect(historyResponse.ok()).toBeTruthy()
    const history = await historyResponse.json() as { batches: Array<{ items: Array<{ id: string; form_data: unknown; attachments: unknown[] }> }> }
    expect(history.batches.flatMap(batch => batch.items).find(item => item.id === requestId)).toMatchObject({ form_data: { counterparties: expected }, attachments: [] })
    await client.reload()
    await expect(client.getByText(`Комментарий: ${comment}`, { exact: false }).first()).toBeVisible({ timeout: 30_000 })
    await expect(client.getByText('Контрагент без комментария', { exact: false }).first()).toBeVisible()
    await client.screenshot({ path: path.join(runtime, 'counterparty-comment-history-768.png'), fullPage: true })
    await admin.goto(`/workspace/questionnaire/${appId}`)
    const assembled = admin.getByTestId('application-questionnaire')
    await expect(assembled).toContainText(comment, { timeout: 30_000 })
    await expect(assembled).toContainText('Комментарий')
    await admin.screenshot({ path: path.join(runtime, 'counterparty-comment-assembled.png'), fullPage: true })
  })

  test('LC sees only its allowed questionnaire fields; outsider is denied', async ({ browser }) => {
    const admin = await actor(browser, 'admin')
    const csrf = (await admin.context().cookies()).find(cookie => cookie.name === 'csrfToken')!.value
    const saved = await admin.request.put(`/api/v1/questionnaire/${manifest!.application_id}`, { headers: { Origin: baseURL, 'X-CSRF-Token': csrf }, data: { foreign_company_name: 'Foreign Name Visible To LC' } })
    expect(saved.ok()).toBeTruthy()
    for (const [role, visible, hidden] of [['lc_a', 'Телефон организации', 'Email организации'], ['lc_b', 'Email организации', 'Телефон организации']]) {
      const page = await actor(browser, role)
      await page.goto(`/workspace/leasing-applications/${manifest!.application_id}?leasing_company_id=${manifest!.companies[role].leasing_company_id}`)
      await page.getByRole('link', { name: 'Открыть анкету', exact: true }).click()
      await expect(page).toHaveURL(new RegExp(`/workspace/questionnaire/${manifest!.application_id}\\?`))
      const section = page.getByTestId('application-questionnaire')
      await expect(section).toBeVisible({ timeout: 30_000 })
      await expect(section.locator('dt').filter({ hasText: new RegExp(`^${visible}$`) })).toBeVisible()
      await expect(section.locator('dt').filter({ hasText: new RegExp(`^${hidden}$`) })).toHaveCount(0)
      await expect(section.locator('dt').filter({ hasText: /^Наименование на иностранном языке$/ })).toBeVisible()
      await expect(section).toContainText('Foreign Name Visible To LC')
      await expect(section).not.toContainText('confidence')
      await page.getByRole('link', { name: 'Вернуться к заявке', exact: true }).click()
      await expect(page).toHaveURL(new RegExp(`/workspace/leasing-applications/${manifest!.application_id}\\?`))
      expect(new URL(page.url()).searchParams.get('leasing_company_id')).toBe(manifest!.companies[role].leasing_company_id)
    }
    const outsider = await actor(browser, 'outsider')
    const forbidden = await outsider.request.get(`/api/v1/questionnaire/${manifest!.application_id}`)
    expect([403, 404]).toContain(forbidden.status())
    await outsider.goto('/workspace/questionnaire-settings')
    await expect(outsider.getByRole('heading', { name: 'Настройки анкет' })).toHaveCount(0)
  })

  test('client selects all transport purposes, reloads and clears the persisted projection', async ({ browser }) => {
    expect(manifest?.purpose_ui_application_id, 'Purpose API fixture must prepare the transport form').toBeTruthy()
    const page = await actor(browser, 'client')
    const appId = manifest!.purpose_ui_application_id!
    const lineId = manifest!.purpose_ui_line_id!
    // A previous run clears these purposes at the end. Restore only this
    // fixture line's selections while preserving its other editable data.
    const detail = await page.request.get(`/api/v1/applications/${appId}`)
    expect(detail.ok()).toBeTruthy()
    const vehicles = (await detail.json()).vehicles as Array<{ id: string; regions?: string[]; region?: string | null; comment?: string | null }>
    const line = vehicles.find(item => item.id === lineId)
    expect(line, 'Purpose fixture line must remain in its application').toBeDefined()
    const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrfToken')!.value
    const prepared = await page.request.put(`/api/v1/applications/${appId}/items`, {
      headers: { Origin: baseURL, 'X-CSRF-Token': csrf },
      data: { items: [{
        line_id: lineId,
        kind: 'vehicle',
        leasing_purposes: ['taxi', 'business'],
        regions: line!.regions ?? [],
        region: line!.region ?? null,
        comment: line!.comment ?? null,
      }] },
    })
    expect(prepared.ok()).toBeTruthy()
    const response = await page.request.get('/api/v1/applications/leasing-purposes')
    expect(response.ok()).toBeTruthy()
    const dictionary = (await response.json()).purposes as Array<{ purpose_name: string; purpose_display_name: string }>
    const label = (code: string) => dictionary.find(item => item.purpose_name === code)!.purpose_display_name
    const openPurposes = async () => {
      await page.goto(`/application/${appId}?step=items`)
      const control = page.locator('article').first().locator('label').filter({ hasText: /^Цель приобретения$/ }).locator('..').getByRole('button')
      await control.click()
    }
    await openPurposes()
    await expect(page.getByRole('checkbox', { name: label('taxi'), exact: true })).toBeChecked()
    await expect(page.getByRole('checkbox', { name: label('business'), exact: true })).toBeChecked()
    await page.getByRole('checkbox', { name: label('taxi'), exact: true }).uncheck()
    await page.getByRole('checkbox', { name: label('staff'), exact: true }).check()
    await page.getByRole('heading', { name: 'Оформление заявки на лизинг', exact: true }).click()
    await page.getByRole('button', { name: 'Создать заявку', exact: true }).click()
    await expect.poll(async () => (await questionnaire(page, appId)).vehicle_purchase_purpose).toEqual({ vehicles: [{ vehicle_id: lineId, purposes: ['business', 'staff'] }] })
    await openPurposes()
    await expect(page.getByRole('checkbox', { name: label('business'), exact: true })).toBeChecked()
    await expect(page.getByRole('checkbox', { name: label('staff'), exact: true })).toBeChecked()
    await page.screenshot({ path: path.join(runtime, 'multiple-transport-purposes.png'), fullPage: true })
    await page.getByRole('checkbox', { name: label('business'), exact: true }).uncheck()
    await page.getByRole('checkbox', { name: label('staff'), exact: true }).uncheck()
    await page.getByRole('heading', { name: 'Оформление заявки на лизинг', exact: true }).click()
    await page.getByRole('button', { name: 'Создать заявку', exact: true }).click()
    await expect.poll(async () => (await questionnaire(page, appId)).vehicle_purchase_purpose).toEqual({ vehicles: [{ vehicle_id: lineId, purposes: [] }] })
    await openPurposes()
    await expect(page.getByRole('checkbox', { name: label('business'), exact: true })).not.toBeChecked()
    await expect(page.getByRole('checkbox', { name: label('staff'), exact: true })).not.toBeChecked()
  })

})
