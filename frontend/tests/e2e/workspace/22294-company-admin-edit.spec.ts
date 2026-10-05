import fs from 'node:fs'
import { expect, test, type Browser, type BrowserContext, type Locator, type Page, type Request } from '@playwright/test'

type CompanyFixture = { id: string; inn: string; name: string }
type FixtureManifest = {
  auth: {
    employee: { id: string }
    client_owner: { id: string }
    client_non_owner: { id: string }
  }
  companies: {
    '22294_full_target': CompanyFixture
    '22294_sparse_optional': CompanyFixture
    '22294_duplicate_inn': CompanyFixture
    '22294_legacy_invalid': CompanyFixture
  }
}
const manifestPath = process.env.E2E_MANIFEST
const sparsePhone = `+7${'9900000002'}`
let fixture: FixtureManifest

function requiredManifest(): FixtureManifest {
  if (!manifestPath) throw new Error('E2E_MANIFEST must point to the shared E2E fixture manifest')
  return JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as FixtureManifest
}

async function actor(browser: Browser, storageState: string | undefined): Promise<BrowserContext> {
  if (!storageState) throw new Error('The shared E2E runner must export the required storage-state path')
  return browser.newContext({
    baseURL: process.env.E2E_BASE_URL,
    storageState,
    viewport: { width: 1440, height: 1000 },
  })
}

function editField(dialog: Locator, label: string): Locator {
  return dialog.locator('label').filter({ hasText: new RegExp(`^${label}(?:\\s|$)`) }).locator('..').locator('input, textarea, select')
}

async function openCompany(page: Page, company: CompanyFixture): Promise<Locator> {
  await page.goto('/workspace/companies')
  await expect(page.getByRole('heading', { name: 'Управление компаниями', exact: true })).toBeVisible()
  await page.getByText(company.name, { exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Информация о компании', exact: true })
  await expect(dialog).toBeVisible()
  return dialog
}

function patchRequests(page: Page, companyId: string): { requests: Request[]; dispose: () => void } {
  const requests: Request[] = []
  const listener = (request: Request) => {
    if (request.method() === 'PATCH' && new URL(request.url()).pathname === `/api/v1/admin/companies/${companyId}`) requests.push(request)
  }
  page.on('request', listener)
  return { requests, dispose: () => page.off('request', listener) }
}

type StatusResponse = { status: () => number; text: () => Promise<string> }

async function expectStatus(response: StatusResponse, status: number) {
  expect(response.status(), await response.text()).toBe(status)
}

test.describe('22294: административное редактирование компании', () => {
  test.describe.configure({ mode: 'serial' })
  test.setTimeout(60_000)

  test.beforeAll(() => {
    fixture = requiredManifest()
  })

  test('API: employee scope, duplicate INN, and legacy client-owner PUT remain compatible', async ({ browser }) => {
    const employee = await actor(browser, process.env.E2E_EMPLOYEE_STORAGE_STATE)
    const clientOwner = await actor(browser, process.env.E2E_CLIENT_STORAGE_STATE)
    const clientNonOwner = await actor(browser, process.env.E2E_CLIENT_NON_OWNER_STORAGE_STATE)
    const target = fixture.companies['22294_full_target']
    try {
      const legacyName = `${target.name} client PUT 22294`
      const legacyPut = await clientOwner.request.put(`/api/v1/companies/${target.id}`, { data: { name: legacyName } })
      await expectStatus(legacyPut, 200)
      target.name = legacyName

      await expectStatus(
        await clientNonOwner.request.patch(`/api/v1/admin/companies/${target.id}`, { data: { name: 'forbidden' } }),
        403,
      )
      await expectStatus(
        await employee.request.patch(`/api/v1/admin/companies/${target.id}`, {
          data: { inn: fixture.companies['22294_duplicate_inn'].inn },
        }),
        409,
      )
    } finally {
      await employee.close()
      await clientOwner.close()
      await clientNonOwner.close()
    }
  })

  test('Browser: invalid client input displays an error and sends no PATCH', async ({ browser }) => {
    const context = await actor(browser, process.env.E2E_EMPLOYEE_STORAGE_STATE)
    try {
      const page = await context.newPage()
      const target = fixture.companies['22294_full_target']
      const dialog = await openCompany(page, target)
      await dialog.getByRole('button', { name: 'Редактировать', exact: true }).click()
      const observed = patchRequests(page, target.id)
      await editField(dialog, 'ИНН').fill('123')
      await dialog.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      await expect(dialog.getByText('ИНН должен содержать 10 или 12 цифр', { exact: true })).toBeVisible()
      expect(observed.requests).toHaveLength(0)
      observed.dispose()
    } finally {
      await context.close()
    }
  })

  test('Browser: closing change history keeps the company modal visible and interactive', async ({ browser }) => {
    const context = await actor(browser, process.env.E2E_EMPLOYEE_STORAGE_STATE)
    try {
      const page = await context.newPage()
      const companyDialog = await openCompany(page, fixture.companies['22294_full_target'])
      await companyDialog.getByRole('button', { name: 'Просмотреть историю изменений', exact: true }).click()

      const historyDialog = page.getByRole('dialog', { name: 'История изменений реквизитов компании', exact: true })
      await expect(historyDialog).toBeVisible()
      await historyDialog.getByRole('button', { name: 'Закрыть', exact: true }).click()
      await expect(historyDialog).toHaveCount(0)

      await expect(companyDialog).toBeVisible()
      await expect(companyDialog.getByRole('button', { name: 'Редактировать', exact: true })).toBeEnabled()
      await companyDialog.getByRole('button', { name: 'Редактировать', exact: true }).click()
      await expect(companyDialog.getByRole('button', { name: 'Сохранить изменения', exact: true })).toBeVisible()
    } finally {
      await context.close()
    }
  })

  test('Browser: employee sees edit before history in the aside and no quick status block', async ({ browser }) => {
    const context = await actor(browser, process.env.E2E_EMPLOYEE_STORAGE_STATE)
    try {
      const page = await context.newPage()
      const dialog = await openCompany(page, fixture.companies['22294_full_target'])
      const aside = dialog.locator('aside')
      const actions = aside.getByRole('button')

      await expect(actions.nth(0)).toHaveText('Редактировать')
      await expect(actions.nth(1)).toHaveText('Просмотреть историю изменений')
      await expect(dialog.getByRole('heading', { name: 'Изменить статус', exact: true })).toHaveCount(0)
      await expect(dialog.getByRole('button', { name: /^(Активировать|Деактивировать)$/ })).toHaveCount(0)
    } finally {
      await context.close()
    }
  })

  test('Browser: compare history presents human-readable company types, Было before Стало, and opens both selected snapshots independently', async ({ browser }) => {
    const context = await actor(browser, process.env.E2E_EMPLOYEE_STORAGE_STATE)
    try {
      const target = fixture.companies['22294_full_target']
      const firstVersionName = `${target.name} history leasing 22294`
      const secondVersionName = `${target.name} history other 22294`
      await expectStatus(
        await context.request.patch(`/api/v1/admin/companies/${target.id}`, { data: { name: firstVersionName, company_type: 'leasing_company' } }),
        200,
      )
      await expectStatus(
        await context.request.patch(`/api/v1/admin/companies/${target.id}`, { data: { name: secondVersionName, company_type: 'other' } }),
        200,
      )
      target.name = secondVersionName

      const page = await context.newPage()
      const companyDialog = await openCompany(page, target)
      await companyDialog.getByRole('button', { name: 'Просмотреть историю изменений', exact: true }).click()
      const historyDialog = page.getByRole('dialog', { name: 'История изменений реквизитов компании', exact: true })
      const selects = historyDialog.locator('label > select')
      await expect(selects).toHaveCount(2)
      await expect
        .poll(() => selects.evaluateAll(elements => elements.map(element => element.parentElement?.childNodes[0]?.textContent?.trim())))
        .toEqual(['Было', 'Стало'])
      await expect.poll(() => selects.nth(0).locator('option').count()).toBeGreaterThanOrEqual(1)
      await expect.poll(() => selects.nth(1).locator('option').count()).toBeGreaterThanOrEqual(2)

      const snapshots = historyDialog.locator('details')
      await expect(snapshots).toHaveCount(2)
      await expect(snapshots.nth(0).locator('summary')).toHaveText('Полный снимок версии «Было»')
      await expect(snapshots.nth(1).locator('summary')).toHaveText('Полный снимок версии «Стало»')
      await snapshots.nth(0).locator('summary').click()
      await snapshots.nth(1).locator('summary').click()
      await expect(snapshots.nth(0)).toHaveAttribute('open', '')
      await expect(snapshots.nth(1)).toHaveAttribute('open', '')
      const comparisonRow = historyDialog.locator('tr').filter({ hasText: 'Тип компании' })
      await expect(comparisonRow).toContainText('Лизинговая компания')
      await expect(comparisonRow).toContainText('Другое')
      await expect(snapshots.nth(0)).toContainText('Лизинговая компания')
      await expect(snapshots.nth(1)).toContainText('Другое')
      await expect(historyDialog.getByText('leasing_company', { exact: true })).toHaveCount(0)
      await expect(historyDialog.getByText('other', { exact: true })).toHaveCount(0)
    } finally {
      await context.close()
    }
  })

  test('Browser: employee fills sparse optional contacts, sends only changed fields, and reload preserves them', async ({ browser }) => {
    const context = await actor(browser, process.env.E2E_EMPLOYEE_STORAGE_STATE)
    try {
      const page = await context.newPage()
      const target = fixture.companies['22294_sparse_optional']
      const dialog = await openCompany(page, target)
      await dialog.getByRole('button', { name: 'Редактировать', exact: true }).click()
      await editField(dialog, 'Телефон').fill(sparsePhone)
      await editField(dialog, 'Email').fill('sparse-22294@example.test')
      await editField(dialog, 'Веб-сайт').fill('https://sparse-22294.example.test')
      await editField(dialog, 'Фактический адрес').fill('г. Москва, E2E проезд, д. 3, офис 22294')

      const patch = page.waitForRequest(request =>
        request.method() === 'PATCH' && new URL(request.url()).pathname === `/api/v1/admin/companies/${target.id}`,
      )
      const response = page.waitForResponse(response =>
        response.request().method() === 'PATCH' && new URL(response.url()).pathname === `/api/v1/admin/companies/${target.id}`,
      )
      await dialog.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      const request = await patch
      await expectStatus(await response, 200)
      expect(request.postDataJSON()).toEqual({
        phone: sparsePhone,
        email: 'sparse-22294@example.test',
        website: 'https://sparse-22294.example.test',
        actual_address: 'г. Москва, E2E проезд, д. 3, офис 22294',
      })

      await page.reload()
      const reloaded = await openCompany(page, target)
      await reloaded.getByRole('button', { name: 'Редактировать', exact: true }).click()
      await expect(editField(reloaded, 'Телефон')).toHaveValue(sparsePhone)
      await expect(editField(reloaded, 'Email')).toHaveValue('sparse-22294@example.test')
      await expect(editField(reloaded, 'Веб-сайт')).toHaveValue('https://sparse-22294.example.test')
      await expect(editField(reloaded, 'Фактический адрес')).toHaveValue('г. Москва, E2E проезд, д. 3, офис 22294')
    } finally {
      await context.close()
    }
  })

  test('Browser: unchanged legacy-invalid KPP does not block a different PATCH', async ({ browser }) => {
    const context = await actor(browser, process.env.E2E_EMPLOYEE_STORAGE_STATE)
    try {
      const page = await context.newPage()
      const target = fixture.companies['22294_legacy_invalid']
      const dialog = await openCompany(page, target)
      await dialog.getByRole('button', { name: 'Редактировать', exact: true }).click()
      const changedName = `${target.name} renamed`
      await editField(dialog, 'Название').fill(changedName)
      const patch = page.waitForRequest(request =>
        request.method() === 'PATCH' && new URL(request.url()).pathname === `/api/v1/admin/companies/${target.id}`,
      )
      await dialog.getByRole('button', { name: 'Сохранить изменения', exact: true }).click()
      expect((await patch).postDataJSON()).toEqual({ name: changedName })
      await expect(page.getByText(changedName, { exact: true })).toBeVisible()
    } finally {
      await context.close()
    }
  })

  test('Browser: non-employees can inspect but never see the edit control', async ({ browser }) => {
    const owner = await actor(browser, process.env.E2E_CLIENT_STORAGE_STATE)
    const nonOwner = await actor(browser, process.env.E2E_CLIENT_NON_OWNER_STORAGE_STATE)
    try {
      for (const context of [owner, nonOwner]) {
        const page = await context.newPage()
        const dialog = await openCompany(page, fixture.companies['22294_full_target'])
        await expect(dialog.getByRole('button', { name: 'Редактировать', exact: true })).toHaveCount(0)
      }
    } finally {
      await owner.close()
      await nonOwner.close()
    }
  })
})
