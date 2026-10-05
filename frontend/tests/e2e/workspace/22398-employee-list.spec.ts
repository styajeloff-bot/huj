import fs from 'node:fs'
import path from 'node:path'
import { expect, test, type APIRequestContext, type Browser, type BrowserContext, type Page } from '@playwright/test'

type ObjectItem = { id: string; name: string }
type EmployeeRow = {
  row_type: 'company' | 'system'
  user_id: string
  user_company_id: string | null
  company_id: string | null
  name: string
  role: string
  brands: ObjectItem[]
  warehouses: ObjectItem[]
  distributors: ObjectItem[]
  can_edit: boolean
  is_active: boolean
}
type Fixture = {
  marker: string
  base_url: string
  companies: Record<string, string>
  brands: Record<string, string>
  warehouses: Record<string, string>
  users: Record<string, { id: string; name: string; user_company_id?: string }>
}

const directory = process.env.E2E_22398_ARTIFACT_DIR
let fixture: Fixture

async function actor(browser: Browser, alias: string): Promise<BrowserContext> {
  return browser.newContext({
    baseURL: fixture.base_url,
    storageState: path.join(directory!, `${alias}.storage.json`),
    viewport: { width: 1440, height: 1000 },
  })
}

async function list(request: APIRequestContext, params: Record<string, string | number> = {}) {
  const response = await request.get('/api/v1/employees', { params: { name: fixture.marker, per_page: 100, ...params } })
  expect(response.status(), await response.text()).toBe(200)
  return await response.json() as { items: EmployeeRow[]; total: number }
}

function ids(objects: ObjectItem[]) {
  return objects.map(object => object.id).sort()
}

async function selectRole(page: Page, role: string) {
  const response = page.waitForResponse(response => {
    const url = new URL(response.url())
    return url.pathname === '/api/v1/employees' && (url.searchParams.get('role') ?? '') === role
  })
  await page.locator('#filter-role').selectOption(role)
  expect((await response).status()).toBe(200)
}

test.describe('22398: список сотрудников, эффективные объекты и область видимости', () => {
  test.describe.configure({ mode: 'serial' })
  test.setTimeout(60_000)
  test.beforeAll(() => {
    if (!directory) throw new Error('Set E2E_22398_ARTIFACT_DIR to the directory seeded by scripts/e2e/22398/prepare.py')
    fixture = JSON.parse(fs.readFileSync(path.join(directory, 'manifest.json'), 'utf8')) as Fixture
  })

  test('API: отсутствие JWT, валидация роли, UUID и несовместимых фильтров', async ({ browser }) => {
    const anonymous = await browser.newContext({ baseURL: fixture.base_url })
    const admin = await actor(browser, 'admin')
    try {
      expect((await anonymous.request.get('/api/v1/employees')).status()).toBe(401)
      const invalidQueries: Record<string, string>[] = [
        { role: 'unknown' },
        { role: 'dealer', dealer_id: 'invalid-uuid' },
        { role: 'client', warehouse_id: fixture.warehouses['dealer-a'] },
      ]
      for (const params of invalidQueries) {
        expect((await admin.request.get('/api/v1/employees', { params })).status()).toBe(422)
      }
      const empty = await list(admin.request, { role: 'distributor', brand_id: '11111111-1111-4111-8111-111111111111' })
      expect(empty).toMatchObject({ items: [], total: 0 })
    } finally {
      await anonymous.close()
      await admin.close()
    }
  })

  test('API: all, selected, except_selected, none; полный набор после фильтрации; строки компаний', async ({ browser }) => {
    const admin = await actor(browser, 'admin')
    try {
      const result = await list(admin.request, { role: 'dealer', dealer_id: fixture.companies.dealer })
      const row = (alias: string) => {
        const found = result.items.find(item => item.user_id === fixture.users[alias].id)
        expect(found, `Fixture ${alias} must have a company row`).toBeDefined()
        return found!
      }
      for (const mode of ['default', 'all']) {
        expect(ids(row(mode).brands)).toEqual([fixture.brands.a, fixture.brands.b].sort())
        expect(ids(row(mode).warehouses)).toEqual([fixture.warehouses['dealer-a'], fixture.warehouses['dealer-b']].sort())
        expect(ids(row(mode).distributors)).toEqual([fixture.companies.distributor])
      }
      expect(ids(row('selected').brands)).toEqual([fixture.brands.a])
      expect(ids(row('selected').warehouses)).toEqual([fixture.warehouses['dealer-a']])
      expect(ids(row('except_selected').brands)).toEqual([fixture.brands.b])
      expect(ids(row('except_selected').warehouses)).toEqual([fixture.warehouses['dealer-b']])
      expect(row('none').brands).toEqual([])
      expect(row('none').warehouses).toEqual([])
      expect(row('inactive').is_active).toBe(false)
      expect(row('all').brands.map(item => item.name)).not.toContain('Stale name must not be displayed')
      for (const warehouse of ['dealer-a', 'dealer-b']) {
        const filtered = await list(admin.request, { role: 'dealer', dealer_id: fixture.companies.dealer, warehouse_id: fixture.warehouses[warehouse], distributor_id: fixture.companies.distributor })
        const all = filtered.items.find(item => item.user_id === fixture.users.all.id)!
        expect(ids(all.warehouses)).toEqual(ids(row('all').warehouses))
        expect(filtered.items.some(item => item.user_id === fixture.users.none.id)).toBe(false)
        expect(filtered.items.some(item => item.user_id === fixture.users.selected.id)).toBe(warehouse === 'dealer-a')
        expect(filtered.items.some(item => item.user_id === fixture.users.except_selected.id)).toBe(warehouse === 'dealer-b')
      }
      const foreign = await list(admin.request, { role: 'dealer', dealer_id: fixture.companies.dealer, warehouse_id: fixture.warehouses['outsider-a'] })
      expect(foreign).toMatchObject({ items: [], total: 0 })
      const multi = await list(admin.request, { name: fixture.users.multi.name })
      expect(multi.total).toBe(2)
      expect(new Set(multi.items.map(item => item.user_company_id)).size).toBe(2)
      expect(multi.items.map(item => item.company_id).sort()).toEqual([fixture.companies.dealer, fixture.companies.second].sort())
      for (const [role, alias] of [['client', 'client'], ['leasing_company', 'leasing']] as const) {
        const filtered = await list(admin.request, { role, name: fixture.users[alias].name })
        expect(filtered.items).toHaveLength(1)
        expect(filtered.items[0].role).toBe(role)
      }
      const dealerOptions = await admin.request.get('/api/v1/employees/filter-options', { params: { role: 'dealer' } })
      expect(dealerOptions.status()).toBe(200)
      expect(ids((await dealerOptions.json()).dealers)).toContain(fixture.companies.second)
      const kkCompany = await list(admin.request, { role: 'carcraft_employee', name: fixture.users.kk_company.name })
      expect(kkCompany.items).toHaveLength(1)
      expect(kkCompany.items[0]).toMatchObject({ row_type: 'company', role: 'carcraft_employee', company_id: fixture.companies.client })
      const system = await list(admin.request, { role: 'carcraft_employee', name: fixture.users.admin.name })
      expect(system.items).toHaveLength(1)
      expect(system.items[0]).toMatchObject({ row_type: 'system', user_company_id: null, company_id: null, can_edit: false })
    } finally { await admin.close() }
  })

  test('API: пагинация считает связи, объекты не дублируют строки; фильтр действует до страницы', async ({ browser }) => {
    const admin = await actor(browser, 'admin')
    try {
      const query = { role: 'dealer', dealer_id: fixture.companies.dealer, warehouse_id: fixture.warehouses['dealer-b'] }
      const full = await list(admin.request, query)
      expect(full.total).toBeGreaterThan(2)
      const collected: string[] = []
      for (let page = 1; page <= Math.ceil(full.total / 2); page++) {
        const part = await list(admin.request, { ...query, per_page: 2, page })
        expect(part.total).toBe(full.total)
        collected.push(...part.items.map(item => item.user_company_id!))
      }
      expect(collected).toEqual(full.items.map(item => item.user_company_id))
      expect(new Set(collected).size).toBe(full.total)
      expect((await list(admin.request, { ...query, per_page: 2, page: 100 })).items).toEqual([])
    } finally { await admin.close() }
  })

  test('API: дилер и дистрибьютор видят только разрешённые связи и lookup; права изменения', async ({ browser }) => {
    for (const alias of ['dealer', 'distributor']) {
      const context = await actor(browser, alias)
      try {
        const result = await list(context.request)
        expect(result.items.length).toBeGreaterThan(0)
        expect(result.items.every(item => item.company_id === fixture.companies.dealer || (alias === 'distributor' && item.company_id === fixture.companies.distributor))).toBe(true)
        if (alias === 'distributor') {
          expect(result.items.filter(item => item.company_id === fixture.companies.dealer).every(item => !item.can_edit)).toBe(true)
        }
        const options = await context.request.get('/api/v1/employees/filter-options', { params: { role: 'dealer' } })
        expect(options.status()).toBe(200)
        const body = await options.json()
        expect(JSON.stringify(body)).not.toContain(fixture.companies.outsider)
        expect(JSON.stringify(body)).not.toContain(fixture.brands.foreign)
        expect(JSON.stringify(body)).not.toContain(fixture.warehouses['outsider-a'])
        expect((await list(context.request, { role: 'dealer', dealer_id: fixture.companies.outsider })).total).toBe(0)
        const edit = await context.request.put(`/api/v1/employees/${fixture.users.outsider.id}/${fixture.companies.outsider}`, { data: { name: 'Forbidden mutation', role: 'dealer' } })
        expect(edit.status()).toBe(403)
      } finally { await context.close() }
    }
    const blocked = await actor(browser, 'blocked')
    try { expect((await blocked.request.get('/api/v1/employees')).status()).toBe(403) }
    finally { await blocked.close() }
  })

  test('Браузер: состав таблиц, полный набор, сброс несовместимых фильтров и КК без компании', async ({ browser }) => {
    const context = await actor(browser, 'admin')
    try {
      const page = await context.newPage()
      await page.goto('/workspace/employees')
      await expect(page.locator('#filter-role')).toBeVisible()
      await expect(page.locator('table:visible thead th')).toHaveText(['Роль', 'Компания', 'Должность', 'ФИО', 'Телефон', 'Статус', 'Кнопки'])
      await selectRole(page, 'dealer')
      await expect(page.getByRole('heading', { name: 'Пользователи Дилеры', exact: true })).toBeVisible()
      await expect(page.locator('table:visible thead th')).toHaveText(['Дилер', 'Марка', 'Дистрибьютор', 'Склад дилера', 'Должность', 'ФИО', 'Телефон', 'Статус', 'Кнопки'])
      await page.locator('#filter-name').fill(fixture.users.all.name)
      await page.locator('#filter-name').press('Enter')
      const allRow = page.locator('table:visible tbody tr').filter({ hasText: fixture.users.all.name })
      await expect(allRow).toHaveCount(1)
      await expect(allRow).toContainText('E2E22398 Brand a')
      await expect(allRow).toContainText('E2E22398 Brand b')
      await expect(allRow).toContainText('E2E22398 address dealer-b')
      await expect(allRow).toContainText('Москва E2E22398')
      await page.locator('#filter-warehouse').selectOption(fixture.warehouses['dealer-b'])
      await page.getByRole('button', { name: 'Применить', exact: true }).click()
      await expect(allRow).toContainText('E2E22398 address dealer-a')
      await selectRole(page, 'client')
      await expect(page.locator('#filter-warehouse')).toHaveCount(0)
      await expect(page.locator('table:visible tbody')).toContainText('не найдены')
      await selectRole(page, 'leasing_company')
      await expect(page.locator('table:visible thead th')).toHaveText(['Роль', 'Компания', 'Должность', 'ФИО', 'Телефон', 'Статус', 'Кнопки'])
      await selectRole(page, 'distributor')
      await expect(page.locator('table:visible thead th')).toHaveText(['Дистрибьютор', 'Марка', 'Склад дистрибьютора', 'Должность', 'ФИО', 'Телефон', 'Статус', 'Кнопки'])
      await expect(page.locator('#filter-warehouse')).toHaveValue('')
      await page.getByRole('button', { name: 'Сбросить', exact: true }).click()
      await expect(page.locator('#filter-role')).toHaveValue('')
      await expect(page.locator('#filter-name')).toHaveValue('')
      await expect(page.getByRole('button', { name: 'Вперед', exact: true })).toBeEnabled()
      const nextPage = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/employees' && new URL(response.url()).searchParams.get('page') === '2')
      await page.getByRole('button', { name: 'Вперед', exact: true }).click()
      expect((await nextPage).status()).toBe(200)
      await expect(page.getByRole('button', { name: 'Назад', exact: true })).toBeEnabled()
      await selectRole(page, 'dealer')
      await expect(page.getByRole('button', { name: 'Назад', exact: true })).toBeDisabled()
      await selectRole(page, 'carcraft_employee')
      const system = page.locator('table:visible tbody tr').filter({ hasText: fixture.users.admin.name })
      await expect(system).toHaveCount(1)
      await expect(system.getByRole('button')).toHaveCount(0)
      await expect(system.locator('td').nth(1)).toHaveText('—')
      const linkedKK = page.locator('table:visible tbody tr').filter({ hasText: fixture.users.kk_company.name })
      await expect(linkedKK).toHaveCount(1)
      await linkedKK.getByRole('button', { name: 'Редактировать', exact: true }).click()
      await expect(page.locator('#emp-role')).toHaveValue('client')
      await page.getByRole('button', { name: 'Отмена', exact: true }).click()
      await expect(page.locator('#emp-role')).toHaveCount(0)
    } finally { await context.close() }
  })

  test('Браузер: редактирование и отключение разрешённой связи, блокировка неактивной', async ({ browser }) => {
    const context = await actor(browser, 'admin')
    try {
      const page = await context.newPage()
      await page.goto('/workspace/employees')
      await expect(page.locator('#filter-role')).toBeVisible()
      await selectRole(page, 'dealer')
      await page.locator('#filter-name').fill(fixture.users.mutation.name)
      await page.locator('#filter-name').press('Enter')
      const row = page.locator('table:visible tbody tr').filter({ hasText: fixture.users.mutation.name })
      await expect(row).toHaveCount(1)
      await row.getByRole('button', { name: 'Редактировать', exact: true }).click()
      await expect(page.locator('#emp-name')).toBeVisible()
      const newName = fixture.users.mutation.name + ' updated'
      await page.locator('#emp-name').fill(newName)
      const save = page.waitForResponse(response => response.request().method() === 'PUT' && new URL(response.url()).pathname === `/api/v1/employees/${fixture.users.mutation.id}/${fixture.companies.dealer}`)
      await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
      expect((await save).status()).toBe(200)
      await expect(page.locator('#emp-name')).toHaveCount(0)
      await expect(row).toContainText(newName)
      page.once('dialog', dialog => dialog.accept())
      const deactivate = page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().endsWith('/deactivate'))
      await row.getByRole('button', { name: 'Отключить', exact: true }).click()
      expect((await deactivate).status()).toBe(200)
      await expect(row).toContainText('Неактивен')
      await expect(row.getByRole('button', { name: 'Отключить', exact: true })).toBeDisabled()
      const persisted = await list(context.request, { name: newName })
      expect(persisted.items).toHaveLength(1)
      expect(persisted.items[0]).toMatchObject({ name: newName, is_active: false })
    } finally { await context.close() }
  })


  test('Браузер: просмотр без права управления и отсутствие действий над собой', async ({ browser }) => {
    const readonly = await actor(browser, 'default')
    const manager = await actor(browser, 'dealer')
    try {
      const readPage = await readonly.newPage()
      await readPage.goto('/workspace/employees')
      await expect(readPage.locator('#filter-role')).toBeVisible()
      await readPage.locator('#filter-name').fill(fixture.marker)
      await readPage.locator('#filter-name').press('Enter')
      await expect(readPage.locator('table:visible tbody tr').first()).toContainText(fixture.marker)
      await expect(readPage.getByRole('button', { name: 'Создать сотрудника', exact: true })).toHaveCount(0)
      await expect(readPage.locator('table:visible tbody').getByRole('button', { name: 'Редактировать', exact: true })).toHaveCount(0)
      await expect(readPage.locator('table:visible tbody').getByRole('button', { name: 'Отключить', exact: true })).toHaveCount(0)
      const managePage = await manager.newPage()
      await managePage.goto('/workspace/employees')
      await expect(managePage.getByRole('button', { name: 'Создать сотрудника', exact: true })).toBeVisible()
      await managePage.locator('#filter-name').fill(fixture.users.dealer.name)
      await managePage.locator('#filter-name').press('Enter')
      await expect(managePage.locator('table:visible tbody tr')).toHaveCount(1)
      await expect(managePage.locator('table:visible tbody tr')).toContainText(fixture.users.dealer.name)
      await expect(managePage.locator('table:visible tbody tr').getByRole('button')).toHaveCount(0)
    } finally {
      await readonly.close()
      await manager.close()
    }
  })

})
