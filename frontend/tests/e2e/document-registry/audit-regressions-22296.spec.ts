import { readFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { expect, test, type APIRequestContext, type Browser, type Locator } from '@playwright/test'
import type { ReferenceDocument } from '../../../features/documentRegistry'

interface Fixture {
  marker: string
  base_url: string
  storage_states: Record<string, string>
  companies: Record<string, { company_id: string; leasing_company_id?: string; name: string }>
  catalog: { mark_id: string; model_id: string; brand: string; model: string }
}
const enabled = process.env.DOCUMENT_REGISTRY_E2E === '1'
const fixture: Fixture | null = enabled ? JSON.parse(readFileSync(process.env.DOCUMENT_REGISTRY_E2E_FIXTURE ?? '/tmp/carcraft-22296-e2e/manifest.json', 'utf8')) : null
if (fixture && (fixture.marker !== 'document-registry-22296' || !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(fixture.base_url))) throw new Error('Use the isolated 22296 fixture only')
test.skip(!enabled, 'Requires the isolated document registry fixture')
const pdf = (text = 'original') => Buffer.from(`%PDF-1.4\n% ${text}\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n`)
const upload = (name = 'contract.pdf', text = 'original') => ({ name, mimeType: 'application/pdf', buffer: pdf(text) })
async function session(browser: Browser, role = 'admin') {
  const path = fixture!.storage_states[role]!
  const csrf = JSON.parse(readFileSync(path, 'utf8')).cookies.find((cookie: { name: string }) => cookie.name === 'csrfToken').value
  return browser.newContext({ baseURL: fixture!.base_url, storageState: path, extraHTTPHeaders: { Origin: fixture!.base_url, 'X-CSRF-Token': csrf }, locale: 'ru-RU', timezoneId: 'Europe/Moscow', viewport: { width: 1280, height: 1000 } })
}
async function create(request: APIRequestContext, name: string, number: string, extra: object = {}, groupId?: string) {
  const response = await request.post(`/api/v1/document-registry/${groupId ? `groups/${groupId}/documents` : 'documents'}`, { multipart: { metadata: JSON.stringify({ document_type: 'contract', contract_number: number, name, valid_from: '2026-01-01', ...(groupId ? {} : { participants: { platform_ml: true } }), ...extra }), files: upload() } })
  expect(response.status(), await response.text()).toBe(201)
  return await response.json() as ReferenceDocument
}
async function remove(request: APIRequestContext, id: string) {
  const impact = await request.get(`/api/v1/document-registry/documents/${id}/monetization-usages`)
  if (impact.status() === 404) return
  expect(impact.status()).toBe(200)
  const { fingerprint } = await impact.json() as { fingerprint: string }
  expect((await request.delete(`/api/v1/document-registry/documents/${id}`, { headers: { 'If-Match': fingerprint } })).status()).toBe(204)
}
async function fillForm(dialog: Locator, name: string, number: string) {
  await dialog.getByLabel('Номер документа', { exact: false }).fill(number)
  await dialog.getByLabel('Название', { exact: true }).fill(name)
  await dialog.getByLabel('Действует с', { exact: true }).fill('2026-01-01')
  await dialog.getByRole('group', { name: 'Участники связки', exact: true }).getByRole('checkbox', { name: 'Платформа МЛ' }).check()
  await dialog.locator('input[type=file]').setInputFiles(upload())
}

test('an occupied contract number blocks saving without POST and changing it permits one new document', async ({ browser }) => {
  const context = await session(browser); const page = await context.newPage(); const key = randomUUID().slice(0, 8)
  const original = await create(context.request, `Duplicate-${key}`, `DUP-${key}`)
  let createdId: string | undefined
  try {
    await page.goto('/workspace/document-registry', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.dr-group').filter({ hasText: original.name })).toBeVisible()
    await page.getByRole('button', { name: 'Добавить документ', exact: true }).click()
    const dialog = page.getByRole('dialog'); const save = dialog.getByRole('button', { name: 'Сохранить документ', exact: true })
    const posts: string[] = []
    page.on('request', request => { if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/document-registry/documents') posts.push(request.url()) })
    await fillForm(dialog, `Recovered-${key}`, ` d u p - ${key} `)
    await expect(dialog).toContainText('Номер используется')
    await expect(save).toBeDisabled()
    await dialog.getByLabel('Название', { exact: true }).press('Enter')
    expect(posts).toHaveLength(0)
    await dialog.getByLabel('Номер документа', { exact: false }).fill(`FREE-${key}`)
    await dialog.getByLabel('Название', { exact: true }).focus()
    await expect(dialog).not.toContainText('Номер используется')
    await expect(save).toBeEnabled()
    const saved = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/document-registry/documents')
    await save.click(); const response = await saved
    expect(response.status(), await response.text()).toBe(201)
    const created = await response.json() as ReferenceDocument; createdId = created.id
    expect(created.contract_number).toBe(`FREE-${key}`); expect(created.id).not.toBe(original.id)
    expect(posts).toHaveLength(1)
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { if (createdId) await remove(context.request, createdId); await remove(context.request, original.id); await context.close() }
})

for (const view of ['cards', 'table'] as const) test(`filters update automatically in ${view}, combine conditions and export the displayed selection`, async ({ browser }) => {
  test.setTimeout(90_000)
  const context = await session(browser); const page = await context.newPage(); const key = `Auto-${randomUUID().slice(0, 8)}`
  const alpha = await create(context.request, `${key} Alpha`, `${key}-A`, { participants: { platform_ml: true, mark_id: fixture!.catalog.mark_id, model_id: fixture!.catalog.model_id } })
  const beta = await create(context.request, `${key} Beta`, `${key}-B`, { document_type: 'act', valid_from: '2000-01-01', valid_to: '2000-01-02', participants: { platform_ml: true, mark_id: fixture!.catalog.mark_id } })
  const gamma = await create(context.request, `${key} Gamma`, `${key}-C`)
  try {
    await page.goto('/workspace/document-registry', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.dr-group').filter({ hasText: gamma.name })).toBeVisible()
    if (view === 'table') await page.getByRole('button', { name: 'Таблица', exact: true }).click()
    const rows = view === 'cards' ? page.locator('.dr-group') : page.locator('.dr-table tbody tr')
    await page.getByPlaceholder('Поиск документов').fill(key)
    await expect(rows).toHaveCount(3)
    await page.getByRole('combobox', { name: 'Статус', exact: true }).selectOption('expired')
    await expect(rows).toHaveCount(1); await expect(rows).toContainText(beta.name)
    await page.getByRole('combobox', { name: 'Тип документа', exact: true }).selectOption('contract')
    await expect(rows).toHaveCount(0)
    await page.getByRole('combobox', { name: 'Тип документа', exact: true }).selectOption('')
    await expect(rows).toHaveCount(1)
    await page.getByRole('combobox', { name: 'Статус', exact: true }).selectOption('')
    await expect(rows).toHaveCount(3)
    await page.getByRole('combobox', { name: 'Марка', exact: true }).selectOption(fixture!.catalog.mark_id)
    await expect(rows).toHaveCount(2)
    await page.getByRole('combobox', { name: 'Модель', exact: true }).selectOption(fixture!.catalog.model_id)
    await expect(rows).toHaveCount(1); await expect(rows).toContainText(alpha.name)
    await page.getByRole('combobox', { name: 'Марка', exact: true }).selectOption('')
    await expect(page.getByRole('combobox', { name: 'Модель', exact: true })).toHaveValue('')
    await expect(page.getByRole('combobox', { name: 'Модель', exact: true })).toBeDisabled()
    await expect(rows).toHaveCount(3)
    await page.getByPlaceholder('Поиск документов').fill(beta.contract_number)
    await expect(rows).toHaveCount(1); await expect(rows).toContainText(beta.name)
    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/document-registry/table/export')
    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Скачать Excel', exact: true }).click()
    const response = await responsePromise; const downloaded = await downloadPromise
    expect(response.status()).toBe(200)
    expect(new URL(response.url()).searchParams.get('search')).toBe(beta.contract_number)
    expect(new URL(response.url()).searchParams.has('mark_id')).toBe(false)
    expect(new URL(response.url()).searchParams.has('model_id')).toBe(false)
    expect(downloaded.suggestedFilename()).toBe('Справочник документов.xlsx')
    expect((await response.body()).subarray(0, 2).toString()).toBe('PK')
  } finally { for (const document of [alpha, beta, gamma]) await remove(context.request, document.id); await context.close() }
})

test('a new monetization draft clears documents that stop matching and does not select an expired inline upload', async ({ browser }) => {
  test.setTimeout(90_000)
  const context = await session(browser); const page = await context.newPage(); const key = `Context-${randomUUID().slice(0, 8)}`
  const first = await create(context.request, `${key}-first`, `${key}-A`, { participants: { leasing_company_ids: [fixture!.companies.leasing!.leasing_company_id] } })
  const second = await create(context.request, `${key}-second`, `${key}-B`, { participants: { leasing_company_ids: [fixture!.companies.leasing2!.leasing_company_id] } })
  let uploadedId: string | undefined
  try {
    await page.goto('/workspace/monetization', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать условия монетизации', exact: true }).click()
    const editor = page.locator('.program-editor'); const picker = editor.locator('.dr-picker')
    for (const alias of ['leasing', 'leasing2']) {
      await editor.locator('.filter-label').filter({ hasText: 'Лизинговая компания *' }).locator('..').getByRole('button').click()
      await page.getByPlaceholder('Название или ИНН', { exact: true }).fill(fixture!.companies[alias]!.name)
      await page.locator('.custom-scrollbar').getByRole('button', { name: new RegExp('^' + fixture!.companies[alias]!.name + ' ·') }).click()
      const expected = alias === 'leasing' ? first : second
      await expect(picker.locator(`[data-document-id="${expected.id}"]`)).toBeVisible()
      if (alias === 'leasing') await picker.locator(`[data-document-id="${first.id}"]`).getByRole('checkbox').check()
    }
    await expect(picker.locator(`[data-document-id="${first.id}"]`)).toHaveCount(0)
    await expect(picker.getByRole('checkbox', { checked: true })).toHaveCount(0)
    await picker.getByRole('tab', { name: 'Загрузить новый файл', exact: true }).click()
    await picker.getByRole('button', { name: 'Загрузить документ', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Продолжить', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Номер документа', { exact: false }).fill(`${key}-EXPIRED`)
    await dialog.getByLabel('Название', { exact: true }).fill(`${key}-expired`)
    await dialog.getByLabel('Действует с', { exact: true }).fill('2000-01-01')
    await dialog.getByLabel('Действует по', { exact: false }).fill('2000-01-02')
    await dialog.locator('input[type=file]').setInputFiles(upload())
    const saved = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/document-registry/documents')
    await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click()
    const response = await saved; expect(response.status(), await response.text()).toBe(201)
    uploadedId = (await response.json() as ReferenceDocument).id
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(picker.locator(`[data-document-id="${uploadedId}"]`)).toHaveCount(0)
    await expect(picker.getByRole('checkbox', { checked: true })).toHaveCount(0)
    await expect(picker).toContainText('не подходит')
    expect((await context.request.get(`/api/v1/document-registry/documents/${uploadedId}`)).status()).toBe(200)
  } finally { for (const id of [first.id, second.id, uploadedId]) if (id) await remove(context.request, id); await context.close() }
})

test('one leasing-company match selects both documents from a group with six criteria and persists after reload', async ({ browser }, testInfo) => {
  test.setTimeout(120_000)
  const context = await session(browser); const page = await context.newPage(); const key = `Any-match-${randomUUID().slice(0, 8)}`
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message))
  const participants = {
    leasing_company_ids: [fixture!.companies.leasing!.leasing_company_id],
    dealer_company_ids: [fixture!.companies.dealer!.company_id],
    distributor_company_ids: [fixture!.companies.distributor!.company_id],
    mark_id: fixture!.catalog.mark_id,
    model_id: fixture!.catalog.model_id,
    platform_ml: true,
  }
  const main = await create(context.request, key + '-main', key + '-MAIN', { participants })
  try {
    const child = await create(context.request, key + '-child', key + '-CHILD', { document_type: 'act' }, main.group_id)
    await page.goto('/workspace/monetization', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Создать условия монетизации', exact: true }).click()
    const editor = page.locator('.program-editor'); const picker = editor.locator('.dr-picker')
    await editor.getByLabel('Название *', { exact: true }).fill(key)
    await editor.getByLabel('Дата начала *', { exact: true }).fill('2026-01-01')
    await editor.getByRole('radio', { name: 'Неактивна', exact: true }).check()
    await editor.getByRole('button', { name: 'Удалить доход 1 из связки 1', exact: true }).click()
    await editor.getByPlaceholder('0', { exact: true }).fill('1')
    async function selectLeasing(alias: 'leasing' | 'leasing2') {
      const company = fixture!.companies[alias]!
      await editor.locator('.filter-label').filter({ hasText: 'Лизинговая компания *' }).locator('..').getByRole('button').click()
      await page.getByPlaceholder('Название или ИНН', { exact: true }).fill(company.name)
      const pending = page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname === '/api/v1/document-registry/monetization-candidates'
        && response.request().postDataJSON().context?.leasing_company_id === company.leasing_company_id)
      await page.locator('.custom-scrollbar').getByRole('button', { name: new RegExp('^' + company.name + ' ·') }).click()
      const response = await pending
      expect(response.status(), await response.text()).toBe(200)
      expect(response.request().postDataJSON()).toEqual({ context: {
        leasing_company_id: company.leasing_company_id, dealer_company_id: null, distributor_company_id: null,
        mark_id: null, model_id: null, platform_ml: false,
      } })
      return await response.json() as { items: ReferenceDocument[]; groups: { group_id: string; participants: unknown }[] }
    }
    const matched = await selectLeasing('leasing')
    expect(matched.groups.find(group => group.group_id === main.group_id)?.participants).toMatchObject(participants)
    expect(matched.items.map(document => document.id)).toEqual(expect.arrayContaining([main.id, child.id]))
    await expect(picker).toContainText('Для подбора достаточно одного совпадения')
    for (const document of [main, child]) {
      const checkbox = picker.locator(`[data-document-id="${document.id}"]`).getByRole('checkbox')
      await expect(checkbox).toBeVisible(); await checkbox.check(); await expect(checkbox).toBeChecked()
    }
    const unmatched = await selectLeasing('leasing2')
    expect(unmatched.groups.map(group => group.group_id)).not.toContain(main.group_id)
    for (const document of [main, child]) {
      expect(unmatched.items.map(item => item.id)).not.toContain(document.id)
      await expect(picker.locator(`[data-document-id="${document.id}"]`)).toHaveCount(0)
    }
    await expect(picker.getByRole('checkbox', { checked: true })).toHaveCount(0)
    await selectLeasing('leasing')
    for (const document of [main, child]) {
      const checkbox = picker.locator(`[data-document-id="${document.id}"]`).getByRole('checkbox')
      await expect(checkbox).not.toBeChecked(); await checkbox.check()
    }
    const pending = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/admin/monetization/programs' && response.request().method() === 'POST')
    await editor.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
    const response = await pending; expect(response.status(), await response.text()).toBe(201)
    const saved = await response.json() as { id: string }
    expect(response.request().postDataJSON()).toMatchObject({
      leasing_company_id: fixture!.companies.leasing!.leasing_company_id,
      dealer_company_id: null, distributor_company_id: null, brand: null, model: null,
      sources: [{ source_type: 'platform', expenses: [{ participant_type: 'leasing' }], incomes: [] }],
    })
    expect(response.request().postDataJSON().reference_document_ids.sort()).toEqual([main.id, child.id].sort())
    await expect(editor).toHaveCount(0)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('.programs-table tbody tr').filter({ hasText: key }).getByRole('button', { name: 'Карточка', exact: true }).click()
    const savedPicker = page.locator('.dr-picker')
    for (const document of [main, child]) await expect(savedPicker.locator(`[data-document-id="${document.id}"]`).getByRole('checkbox')).toBeChecked()
    const linked = await context.request.get(`/api/v1/admin/monetization/programs/${saved.id}/reference-documents`)
    expect(linked.status()).toBe(200)
    expect((await linked.json() as { items: ReferenceDocument[] }).items.map(document => document.id).sort()).toEqual([main.id, child.id].sort())
    await savedPicker.getByRole('heading', { name: 'Приложить договор', exact: true }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath('one-leasing-match.png') })
    expect(errors).toEqual([])
  } finally { await remove(context.request, main.id); await context.close() }
})

test('a first version has no history link and a second version enables history', async ({ browser }) => {
  const context = await session(browser); const page = await context.newPage(); const key = `History-${randomUUID().slice(0, 8)}`
  const document = await create(context.request, key, key)
  try {
    await page.goto(`/workspace/document-registry?document=${document.id}`, { waitUntil: 'domcontentloaded' })
    const detail = page.getByRole('dialog').first()
    await expect(detail).toContainText(key)
    await expect(detail.getByRole('button', { name: /История версий/ })).toHaveCount(0)
    await detail.getByRole('button', { name: 'Редактировать', exact: true }).click()
    const editor = page.getByRole('dialog').last()
    await editor.getByLabel('Название', { exact: true }).fill(key + '-v2')
    await editor.getByRole('button', { name: 'Сохранить документ', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(1)
    await expect(detail.getByRole('button', { name: 'История версий (2)', exact: true })).toBeVisible()
  } finally { await remove(context.request, document.id); await context.close() }
})

test('number availability remains blocked while pending, ignores an older answer and recovers from transport failure', async ({ browser }) => {
  const context = await session(browser); const page = await context.newPage(); const key = randomUUID().slice(0, 8)
  const existing = await create(context.request, `Race-${key}`, `TAKEN-${key}`)
  let release!: () => void; let received!: () => void; let delivered!: () => void
  const held = new Promise<void>(resolve => { release = resolve }); const started = new Promise<void>(resolve => { received = resolve }); const finished = new Promise<void>(resolve => { delivered = resolve })
  let failTransport = true
  await page.route('**/api/v1/document-registry/check-contract-number?**', async route => {
    const number = new URL(route.request().url()).searchParams.get('number')
    if (number === `OLD-FREE-${key}`) { const response = await route.fetch(); received(); await held; await route.fulfill({ response }); delivered() }
    else if (number === `RETRY-${key}` && failTransport) await route.abort('failed')
    else await route.continue()
  })
  try {
    await page.goto('/workspace/document-registry', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Добавить документ', exact: true }).click()
    const dialog = page.getByRole('dialog'); const number = dialog.getByLabel('Номер документа', { exact: false }); const save = dialog.getByRole('button', { name: 'Сохранить документ', exact: true })
    await fillForm(dialog, `Race-new-${key}`, `OLD-FREE-${key}`); await started
    await expect(save).toBeDisabled(); await expect(dialog).toContainText('Проверяем номер')
    await number.fill(existing.contract_number); await dialog.getByLabel('Название', { exact: true }).focus()
    await expect(dialog).toContainText('Номер используется'); await expect(save).toBeDisabled()
    release(); await finished
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
    await expect(dialog).toContainText('Номер используется'); await expect(save).toBeDisabled()
    await number.fill(`RETRY-${key}`); await dialog.getByLabel('Название', { exact: true }).focus()
    await expect(dialog.getByRole('button', { name: 'Повторить проверку номера', exact: true })).toBeVisible(); await expect(save).toBeDisabled()
    failTransport = false
    await dialog.getByRole('button', { name: 'Повторить проверку номера', exact: true }).click()
    await expect(save).toBeEnabled(); await expect(dialog).not.toContainText('Номер используется')
  } finally { release(); await remove(context.request, existing.id); await context.close() }
})

for (const view of ['cards', 'table'] as const) test(`an older filter response cannot replace the current ${view} selection`, async ({ browser }) => {
  const context = await session(browser); const page = await context.newPage(); const key = `Race-list-${randomUUID().slice(0, 8)}`
  const alpha = await create(context.request, key + '-alpha', key + '-A'); const beta = await create(context.request, key + '-beta', key + '-B')
  let release!: () => void; let received!: () => void; let delivered!: () => void
  const held = new Promise<void>(resolve => { release = resolve }); const started = new Promise<void>(resolve => { received = resolve }); const finished = new Promise<void>(resolve => { delivered = resolve })
  await page.route(`**/api/v1/document-registry/${view === 'cards' ? 'groups' : 'table'}?**`, async route => {
    if (new URL(route.request().url()).searchParams.get('search') !== alpha.contract_number) return route.continue()
    const response = await route.fetch(); received(); await held; await route.fulfill({ response }); delivered()
  })
  try {
    await page.goto('/workspace/document-registry', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.dr-group').filter({ hasText: beta.name })).toBeVisible()
    if (view === 'table') await page.getByRole('button', { name: 'Таблица', exact: true }).click()
    await page.getByPlaceholder('Поиск документов').fill(alpha.contract_number); await started
    await expect(page.getByRole('button', { name: 'Скачать Excel', exact: true })).toBeDisabled()
    await page.getByPlaceholder('Поиск документов').fill(beta.contract_number)
    const rows = view === 'cards' ? page.locator('.dr-group') : page.locator('.dr-table tbody tr')
    await expect(rows).toHaveCount(1); await expect(rows).toContainText(beta.name)
    release(); await finished
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))))
    await expect(rows).toHaveCount(1); await expect(rows).toContainText(beta.name); await expect(rows).not.toContainText(alpha.name)
  } finally { release(); await remove(context.request, alpha.id); await remove(context.request, beta.id); await context.close() }
})

test('all card, table and child pages contain the exact documents and same-name children stay distinct', async ({ browser }) => {
  test.setTimeout(150_000)
  const context = await session(browser); const page = await context.newPage(); const key = `Pages-${randomUUID().slice(0, 8)}`
  const roots: ReferenceDocument[] = []; const children: ReferenceDocument[] = []
  try {
    for (let index = 0; index < 22; index++) roots.push(await create(context.request, `${key}-group-${index}`, `${key}-ROOT-${index}`))
    const main = roots.at(-1)!
    for (let index = 0; index < 22; index++) children.push(await create(context.request, index < 2 ? `${key}-same-name` : `${key}-child-${index}`, `${key}-CHILD-${index}`, {}, main.group_id))
    expect(children[0]!.id).not.toBe(children[1]!.id); expect(children.slice(0, 2).map(document => document.version_count)).toEqual([1, 1])
    await page.goto('/workspace/document-registry', { waitUntil: 'domcontentloaded' })
    await page.getByPlaceholder('Поиск документов').fill(key)
    const cards = page.locator('.dr-group > [data-document-id]')
    await expect(cards).toHaveCount(20)
    const seen = await cards.evaluateAll(nodes => nodes.map(node => node.getAttribute('data-document-id')))
    await page.getByRole('button', { name: 'Вперёд', exact: true }).click(); await expect(page.locator('.dr-pagination')).toContainText('Страница 2 из 2'); await expect(cards).toHaveCount(2)
    seen.push(...await cards.evaluateAll(nodes => nodes.map(node => node.getAttribute('data-document-id'))))
    expect(seen.sort()).toEqual(roots.map(document => document.id).sort()); expect(new Set(seen).size).toBe(22)
    await page.getByPlaceholder('Поиск документов').fill(main.contract_number)
    await expect(cards).toHaveCount(1); await expect(cards).toHaveAttribute('data-document-id', main.id)
    await page.getByPlaceholder('Поиск документов').fill(key); await expect(cards).toHaveCount(20); await expect(page.locator('.dr-pagination')).toContainText('Страница 1 из 2')
    const group = page.locator('.dr-group').filter({ has: page.locator(`[data-document-id="${main.id}"]`) })
    await group.getByRole('button', { name: 'Показать ещё 22 документ(а/ов)', exact: true }).click()
    const panel = group.getByRole('tabpanel'); const childCards = panel.locator('[data-document-id]')
    await expect(childCards).toHaveCount(19)
    await panel.getByRole('button', { name: 'Показать ещё', exact: true }).click(); await expect(childCards).toHaveCount(22)
    expect((await childCards.evaluateAll(nodes => nodes.map(node => node.getAttribute('data-document-id')))).sort()).toEqual(children.map(document => document.id).sort())
    await expect(group.getByRole('tab', { name: 'Все (22)', exact: true })).toBeVisible(); await expect(group.getByRole('tab', { name: 'Договор (22)', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Таблица', exact: true }).click()
    const rows = page.locator('.dr-table tbody tr'); await expect(rows).toHaveCount(10)
    await page.getByRole('button', { name: 'Показать ещё 10', exact: true }).click(); await expect(rows).toHaveCount(20)
    await page.getByRole('button', { name: 'Показать ещё 10', exact: true }).click(); await expect(rows).toHaveCount(22)
    expect((await rows.locator('td:nth-child(2) button').allTextContents()).sort()).toEqual(roots.map(document => document.contract_number).sort())
    await expect(page.getByRole('button', { name: 'Показать ещё 10', exact: true })).toHaveCount(0)
    const mainRow = rows.filter({ hasText: main.contract_number }); await expect(mainRow.getByRole('link')).toHaveCount(22)
    expect((await mainRow.getByRole('link').evaluateAll(nodes => nodes.map(node => new URL((node as HTMLAnchorElement).href).searchParams.get('document')))).sort()).toEqual(children.map(document => document.id).sort())
  } finally { for (const document of roots) await remove(context.request, document.id); await context.close() }
})

test('a new program retains its selected document through expense edits and keeps brand, model and document after reload', async ({ browser }) => {
  test.setTimeout(90_000)
  const context = await session(browser); const page = await context.newPage(); const key = `Program-${randomUUID().slice(0, 8)}`
  const document = await create(context.request, key + '-doc', key + '-number', { participants: { leasing_company_ids: [fixture!.companies.leasing!.leasing_company_id], mark_id: fixture!.catalog.mark_id, model_id: fixture!.catalog.model_id } })
  try {
    await page.goto('/workspace/monetization', { waitUntil: 'domcontentloaded' }); await page.getByRole('button', { name: 'Создать условия монетизации', exact: true }).click()
    const editor = page.locator('.program-editor')
    await editor.getByLabel('Название *', { exact: true }).fill(key)
    await editor.locator('.filter-label').filter({ hasText: 'Лизинговая компания *' }).locator('..').getByRole('button').click()
    await page.getByPlaceholder('Название или ИНН', { exact: true }).fill(fixture!.companies.leasing!.name)
    await page.locator('.custom-scrollbar').getByRole('button', { name: new RegExp('^' + fixture!.companies.leasing!.name + ' ·') }).click()
    for (const [label, placeholder, value] of [['Марка', 'Найти марку...', fixture!.catalog.brand], ['Модель', 'Найти модель...', fixture!.catalog.model]]) {
      await editor.locator('.filter-label').filter({ hasText: new RegExp('^' + label + '$') }).locator('..').getByRole('button').click()
      await page.getByPlaceholder(placeholder!, { exact: true }).fill(value!)
      await page.locator('.custom-scrollbar').getByRole('button', { name: value!, exact: true }).click()
    }
    await editor.getByLabel('Дата начала *', { exact: true }).fill('2026-01-01')
    await editor.getByRole('radio', { name: 'Неактивна', exact: true }).check()
    await editor.getByRole('button', { name: 'Удалить доход 1 из связки 1', exact: true }).click()
    await editor.getByPlaceholder('0', { exact: true }).fill('1')
    const selectedDocument = editor.locator(`[data-document-id="${document.id}"]`).getByRole('checkbox')
    await selectedDocument.check()
    const expense = editor.locator('.condition-row').filter({ has: page.getByRole('heading', { name: 'Расход', exact: true }) })
    for (const [label, value] of [['Значение (%)', '2'], ['Минимум, ₽', '100'], ['Максимум, ₽', '500']]) {
      await expense.getByLabel(label!, { exact: true }).fill(value!)
      await expect(expense.getByLabel(label!, { exact: true })).toHaveValue(value!)
      await expect(selectedDocument).toBeChecked()
    }
    await expense.getByRole('checkbox', { name: 'Не включён НДС', exact: true }).check()
    await expect(selectedDocument).toBeChecked()
    const pending = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/admin/monetization/programs' && response.request().method() === 'POST')
    await editor.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
    const response = await pending; expect(response.status(), await response.text()).toBe(201)
    const saved = await response.json() as { id: string; brand: string; model: string }
    expect(saved.brand).toBe(fixture!.catalog.brand); expect(saved.model).toBe(fixture!.catalog.model)
    expect(response.request().postDataJSON().reference_document_ids).toEqual([document.id])
    expect(response.request().postDataJSON().sources[0].expenses[0]).toMatchObject({ value: '2', min: '100', max: '500', vat_excluded: true })
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('.programs-table tbody tr').filter({ hasText: key }).getByRole('button', { name: 'Карточка', exact: true }).click()
    await expect(page.locator('.program-detail')).toContainText(fixture!.catalog.brand)
    await expect(page.locator('.program-detail')).toContainText(fixture!.catalog.model)
    await expect(page.locator('.dr-picker').locator(`[data-document-id="${document.id}"]`).getByRole('checkbox')).toBeChecked()
    const linked = await context.request.get(`/api/v1/admin/monetization/programs/${saved.id}/reference-documents`)
    expect(linked.status()).toBe(200); expect((await linked.json() as { items: ReferenceDocument[] }).items.map(item => item.id)).toEqual([document.id])
  } finally { await remove(context.request, document.id); await context.close() }
})

test('a fresh expiry notification opens its document from the dealer inbox and downloads the real file', async ({ browser }, testInfo) => {
  test.setTimeout(90_000)
  const admin = await session(browser); const dealer = await session(browser, 'dealer')
  await dealer.setExtraHTTPHeaders({})
  const page = await dealer.newPage()
  const key = `Inbox-${randomUUID().slice(0, 8)}`
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  const dueDate = new Date(`${today}T12:00:00Z`); dueDate.setUTCDate(dueDate.getUTCDate() + 10)
  const validTo = dueDate.toISOString().slice(0, 10)
  const document = await create(admin.request, key, key + '-number', { valid_from: today, valid_to: validTo, participants: { leasing_company_ids: [fixture!.companies.leasing!.leasing_company_id], dealer_company_ids: [fixture!.companies.dealer!.company_id] } })
  const errors: string[] = []; const warnings: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); if (message.type() === 'warning') warnings.push(message.text()) })
  type InboxItem = { id: string; title: string; message: string; is_read: boolean; action_url: string; data?: { event_type?: string; entity_id?: string; version_id?: string } }
  async function inbox() {
    const response = await dealer.request.get('/api/v1/notifications?notification_type=document_status&limit=100')
    expect(response.status()).toBe(200)
    return (await response.json() as { notifications: InboxItem[] }).notifications
  }
  let notification: InboxItem | undefined
  try {
    await expect.poll(async () => {
      notification = (await inbox()).find(item => item.data?.event_type === 'document_registry.expiring' && item.data.entity_id === document.id)
      return notification?.id
    }, { timeout: 45_000, intervals: [200, 500, 1000], message: 'The running notification pipeline must deliver this new document to its dealer' }).toBeTruthy()
    if (!notification) throw new Error('The fresh expiry notification was not delivered')
    expect(notification.is_read).toBe(false)
    expect(notification.data?.version_id).toBe(document.current_version.id)
    const expectedTitle = 'Истекает срок действия документа'
    const expectedMessage = `Срок действия документа «Договор» №${document.contract_number} «${document.name}» заканчивается ${validTo.split('-').reverse().join('.')}.`
    expect(notification.title).toBe(expectedTitle); expect(notification.message).toBe(expectedMessage)
    const target = new URL(notification.action_url, fixture!.base_url)
    expect(target.pathname).toBe('/workspace/document-registry'); expect(target.searchParams.get('document')).toBe(document.id)
    expect(target.searchParams.get('notification_company_id')).toBe(fixture!.companies.dealer!.company_id)
    await page.goto('/workspace', { waitUntil: 'domcontentloaded' })
    const bell = page.getByRole('button', { name: /^Уведомления(?:,|$)/ }).first()
    await expect(bell).toHaveAttribute('aria-label', /^Уведомления, \d+ непрочитанных$/)
    await bell.click()
    const center = page.locator('[data-storefront-block="client.notifications"].fixed')
    await expect(center.getByRole('heading', { name: 'Уведомления', exact: true })).toBeVisible()
    await center.getByRole('combobox', { name: 'Тип уведомлений', exact: true }).selectOption('document_status')
    const row = center.locator(`[data-notification-id="${notification.id}"]`)
    await expect(row).toBeVisible(); await expect(row).toContainText(expectedTitle); await expect(row).toContainText(expectedMessage)
    await page.screenshot({ path: testInfo.outputPath('expiry-inbox.png'), fullPage: true })
    const markRead = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/notifications/${notification!.id}` && response.request().method() === 'PATCH')
    await row.click(); expect((await markRead).status()).toBe(200)
    await expect(page).toHaveURL(url => url.pathname === target.pathname && url.searchParams.get('document') === document.id && url.searchParams.get('notification_company_id') === fixture!.companies.dealer!.company_id)
    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText(document.name); await expect(dialog).toContainText(document.contract_number)
    const file = document.current_version.files[0]!
    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === file.download_url && response.request().method() === 'GET')
    const downloadPromise = page.waitForEvent('download')
    await dialog.getByRole('button', { name: file.name, exact: true }).click()
    const response = await responsePromise; const download = await downloadPromise
    expect(response.status()).toBe(200); expect(await response.body()).toEqual(pdf())
    expect(new URL(response.url()).searchParams.get('notification_company_id')).toBe(fixture!.companies.dealer!.company_id)
    expect(download.suggestedFilename()).toBe(file.name)
    const stream = await download.createReadStream(); const chunks: Buffer[] = []
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
    expect(Buffer.concat(chunks)).toEqual(pdf())
    await expect.poll(async () => (await inbox()).find(item => item.id === notification!.id)?.is_read).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('expiry-document.png'), fullPage: true })
    await testInfo.attach('browser-console', { body: JSON.stringify({ errors, warnings }, null, 2), contentType: 'application/json' })
    expect(errors).toEqual([])
  } finally { await remove(admin.request, document.id); await dealer.close(); await admin.close() }
})

for (const role of ['admin', 'dealer']) test(`direct registry entry hydrates without console errors for ${role}`, async ({ browser }, testInfo) => {
  const admin = await session(browser); const context = await session(browser, role)
  await context.setExtraHTTPHeaders({})
  const page = await context.newPage(); const key = `Hydration-${randomUUID().slice(0, 8)}`
  const document = await create(admin.request, key, key, { participants: { dealer_company_ids: [fixture!.companies.dealer!.company_id] } })
  const errors: string[] = []; const warnings: string[] = []; const markup: { path: string; server: string | null; client: string }[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); if (message.type() === 'warning') warnings.push(message.text()) })
  try {
    for (const path of ['/workspace/document-registry', `/workspace/document-registry?document=${document.id}`]) {
      const response = await page.goto(path, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('.dr-workspace').getByRole('heading', { name: 'Справочник документов', exact: true })).toBeVisible()
      if (path.includes('?')) await expect(page.getByRole('dialog')).toContainText(document.name)
      else await expect(page.locator(`[data-document-id="${document.id}"]`)).toBeVisible()
      markup.push({ path, server: (await response!.text()).match(/<main\b[^>]*>([\s\S]*?)<\/main>/)?.[1] ?? null, client: await page.locator('main').innerHTML() })
    }
    await testInfo.attach('hydration-markup', { body: JSON.stringify({ errors, warnings, markup }, null, 2), contentType: 'application/json' })
    expect(errors).toEqual([])
    expect(warnings.filter(message => /hydrat/i.test(message))).toEqual([])
  } finally { await remove(admin.request, document.id); await context.close(); await admin.close() }
})
