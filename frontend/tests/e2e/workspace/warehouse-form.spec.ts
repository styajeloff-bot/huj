import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test, type APIRequestContext, type Locator } from '@playwright/test'

const artifacts = process.env.E2E_WAREHOUSE_FORM_ARTIFACT_DIR || '../artifacts/e2e/warehouse-form'
const ids: Record<string, string> = process.env.E2E_WAREHOUSE_FORM_ARTIFACT_DIR ? JSON.parse(readFileSync(join(artifacts, 'manifest.json'), 'utf8')) : {}
test.skip(!process.env.E2E_WAREHOUSE_FORM_ARTIFACT_DIR, 'Requires isolated warehouse-form suite')
test.use({ storageState: process.env.E2E_WAREHOUSE_FORM_ARTIFACT_DIR ? join(artifacts, 'employee.storage.json') : undefined })
const payload = (name: string) => ({ name, address: 'E2E ул. Проверочная, 1', owner_company_id: ids.owner, is_active: true })
const warehouse = async (api: APIRequestContext, name: string, extra = {}) => {
  const response = await api.post('/api/v1/warehouses', { data: { ...payload(name), ...extra } })
  expect(response.status(), await response.text()).toBe(201)
  return (await response.json()).warehouse
}
const field = (dialog: Locator, label: string) => dialog.locator('label').filter({ hasText: new RegExp(`^\\s*${label}\\s*\\*?\\s*$`) }).locator('..')
const choose = async (dialog: Locator, label: string, placeholder: string, search: string, option: string, multi = false) => {
  await field(dialog, label).getByRole('button').first().click()
  await dialog.getByPlaceholder(placeholder).fill(search)
  if (multi) await dialog.getByRole('checkbox', { name: option, exact: true }).check()
  else await dialog.getByRole('button', { name: option, exact: false }).last().click()
  if (multi) await dialog.getByText(label, { exact: true }).click()
}

test('API: category union/search, persistence, validation atomicity and partial PUT', async ({ request }) => {
  const categories = async (marks: string[], search?: string) => {
    const query = new URLSearchParams(marks.map(id => ['brand_ids', id]))
    if (search) query.set('search', search)
    const response = await request.get(`/api/v1/warehouses/categories?${query}`)
    expect(response.status(), await response.text()).toBe(200)
    return await response.json()
  }
  expect((await categories([])).categories).toEqual([])
  const union = await categories([ids.alpha, ids.beta])
  expect(union.categories.map((c: {id:string}) => c.id).sort()).toEqual([ids.direct, ids.mod, ids['beta-cat']].sort())
  expect((await categories([ids.alpha], 'МОДИФ')).categories.map((c: {id:string}) => c.id)).toEqual([ids.mod])
  expect((await categories([ids['empty-mark']])).categories).toEqual([])
  const paginated = await request.get(`/api/v1/warehouses/categories?brand_ids=${ids.alpha}&limit=1&page=2`)
  expect((await paginated.json()).pagination).toMatchObject({ total: 2, pages: 2, page: 2 })
  const marks = await request.get('/api/v1/warehouses/marks?search=АЛЬ')
  expect((await marks.json()).marks.map((m: {id:string}) => m.id)).toEqual([ids.alpha])
  const legacy = (await (await request.get(`/api/v1/warehouses/${ids.legacy}`)).json()).warehouse
  expect(legacy.brand_ids).toEqual([ids.alpha])
  expect(legacy.category_id).toBeNull()
  const empty = await warehouse(request, 'E2E API empty')
  expect(empty.brand_ids).toEqual([])
  expect(empty.category_id).toBeNull()
  const created = await warehouse(request, 'E2E API configured', { brand_ids: [ids.alpha, ids.beta], category_id: ids.mod })
  expect(created.selected_brands.map((m: {id:string}) => m.id).sort()).toEqual([ids.alpha, ids.beta].sort())
  expect(created.category_name).toBe('E2E Модификаций')
  expect(created.vehicle_marks).toEqual([])
  const path = `/api/v1/warehouses/${created.id}`
  expect((await request.put(path, { data: { address: 'E2E changed address' } })).status()).toBe(200)
  const saved = (await (await request.get(path)).json()).warehouse
  expect(saved.brand_ids.sort()).toEqual([ids.alpha, ids.beta].sort())
  expect(saved.category_id).toBe(ids.mod)
  for (const invalid of [
    { brand_ids: [ids.alpha, ids.alpha] }, { brand_ids: [ids.inactive] },
    { brand_ids: ['invalid'] }, { brand_ids: ['00000000-0000-0000-0000-000000000000'] },
    { category_id: ids.unrelated }, { category_id: ids['inactive-cat'] },
    { brand_ids: [] }, { brand_ids: [ids.beta] },
  ]) {
    const response = await request.put(path, { data: { ...invalid, name: 'Must not be saved' } })
    expect(response.status(), await response.text()).toBe(422)
    const after = (await (await request.get(path)).json()).warehouse
    expect(after.name).toBe(created.name)
    expect(after.brand_ids.sort()).toEqual([ids.alpha, ids.beta].sort())
    expect(after.category_id).toBe(ids.mod)
  }
  const cleared = await request.put(path, { data: { brand_ids: [], category_id: null } })
  expect(cleared.status(), await cleared.text()).toBe(200)
  expect((await cleared.json()).warehouse).toMatchObject({ brand_ids: [], category_id: null })
})

test('API: form directories use warehouse administration permissions', async ({ playwright }) => {
  for (const state of [undefined, join(artifacts, 'client.storage.json')]) {
    const api = await playwright.request.newContext({ baseURL: process.env.E2E_BASE_URL, storageState: state })
    for (const endpoint of ['/api/v1/warehouses/marks', '/api/v1/warehouses/categories']) {
      const response = await api.get(endpoint)
      expect([401, 403]).toContain(response.status())
    }
    await api.dispose()
  }
  for (const role of ['dealer', 'distributor']) {
    const api = await playwright.request.newContext({ baseURL: process.env.E2E_BASE_URL, storageState: join(artifacts, role + '.storage.json') })
    for (const endpoint of ['/api/v1/warehouses/marks', `/api/v1/warehouses/categories?brand_ids=${ids.alpha}`]) {
      const response = await api.get(endpoint)
      expect(response.status(), await response.text()).toBe(200)
    }
    if (role === 'distributor') {
      const foreign = await api.put(`/api/v1/warehouses/${ids.legacy}`, { data: { name: 'Forbidden overwrite' } })
      expect([400, 403, 404]).toContain(foreign.status())
    }
    await api.dispose()
  }
})

test('API: cascade deletes isolated selected mark and preserves mark selected elsewhere', async ({ request }) => {
  const first = await warehouse(request, 'E2E cascade first', { brand_ids: [ids.cascade, ids.shared] })
  const second = await warehouse(request, 'E2E cascade second', { brand_ids: [ids.shared] })
  const previewResponse = await request.get(`/api/v1/warehouses/${first.id}/delete-preview`)
  expect(previewResponse.status(), await previewResponse.text()).toBe(200)
  const preview = await previewResponse.json()
  expect(preview.can_delete).toBe(true)
  expect(preview.counts.marks).toBe(1)
  const deleted = await request.post(`/api/v1/warehouses/${first.id}/cascade-delete`, { data: { confirmation: 'УДАЛИТЬ', preview_token: preview.preview_token } })
  expect(deleted.status(), await deleted.text()).toBe(200)
  expect((await request.get(`/api/v1/warehouses/${first.id}`)).status()).toBe(404)
  const survivor = (await (await request.get(`/api/v1/warehouses/${second.id}`)).json()).warehouse
  expect(survivor.brand_ids).toEqual([ids.shared])
  const marks = await request.get('/api/v1/warehouses/marks?search=E2E')
  const remaining = (await marks.json()).marks.map((mark: {id:string}) => mark.id)
  expect(remaining).not.toContain(ids.cascade)
  expect(remaining).toContain(ids.shared)
})

test('UI: all searches, two marks, category reset, save and reopen', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 1000 })
  await page.goto('/workspace/warehouses')
  await page.getByRole('button', { name: 'Создать склад', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Сначала выберите марку ТС')).toBeVisible()
  await expect(field(dialog, 'Категория ТС').getByRole('button').first()).toBeDisabled()
  await dialog.getByPlaceholder('Например: Центральный склад ТС').fill('E2E UI searchable warehouse')
  await dialog.getByPlaceholder('г. Москва, ул. Примерная, д. 1').fill('E2E UI address')
  await choose(dialog, 'Компания-владелец', 'Поиск по названию или ИНН...', 'складов', 'E2E Складовладелец')
  await choose(dialog, 'Марки ТС', 'Поиск по названию марки...', 'АЛЬ', 'E2E Альфа', true)
  await choose(dialog, 'Марки ТС', 'Поиск по названию марки...', 'бЕт', 'E2E Бета', true)
  await expect(dialog.getByRole('button', { name: 'Убрать марку E2E Альфа' })).toBeVisible()
  await choose(dialog, 'Категория ТС', 'Поиск по названию категории...', 'мОДИФ', 'E2E Модификаций')
  await choose(dialog, 'Город', 'Поиск города...', 'теСТО', 'E2E Тестоград')
  await dialog.getByRole('button', { name: 'Создать', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  const listed = await request.get('/api/v1/warehouses?search=E2E UI searchable warehouse')
  const saved = (await listed.json()).warehouses.find((w: {name:string}) => w.name === 'E2E UI searchable warehouse')
  expect(saved.brand_ids.sort()).toEqual([ids.alpha, ids.beta].sort())
  expect(saved.category_id).toBe(ids.mod)
  expect(saved.city_id).toBe(ids.city)
  await page.reload()
  const row = page.getByRole('row').filter({ hasText: saved.name })
  await row.getByRole('button', { name: 'Редактировать' }).click()
  await expect(dialog.getByRole('button', { name: 'Убрать марку E2E Альфа' })).toBeVisible()
  await expect(field(dialog, 'Категория ТС').getByRole('button').first()).toHaveText(/E2E Модификаций/)
  await dialog.getByRole('button', { name: 'Убрать марку E2E Бета' }).click()
  await expect(field(dialog, 'Категория ТС').getByRole('button').first()).toHaveText(/E2E Модификаций/)
  await dialog.getByRole('button', { name: 'Убрать марку E2E Альфа' }).click()
  await expect(field(dialog, 'Категория ТС').getByRole('button').first()).toBeDisabled()
  await choose(dialog, 'Марки ТС', 'Поиск по названию марки...', 'Без моделей', 'E2E Без моделей', true)
  await expect(dialog.getByText('Для выбранных марок категории не найдены', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: 'Очистить марки' }).click()
  await dialog.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  const cleared = (await (await request.get(`/api/v1/warehouses/${saved.id}`)).json()).warehouse
  expect(cleared).toMatchObject({ brand_ids: [], category_id: null })
})

test('UI: 768px, failed search retry, empty results and late search response', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1000 })
  await page.route('**/api/v1/warehouses/marks?**', route => route.abort())
  await page.goto('/workspace/warehouses')
  await page.getByRole('button', { name: 'Создать склад', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const marks = field(dialog, 'Марки ТС')
  await expect(marks.getByRole('alert')).toContainText('Не удалось загрузить марки ТС')
  await page.unroute('**/api/v1/warehouses/marks?**')
  await marks.getByRole('button', { name: 'Повторить' }).click()
  await expect(marks.getByRole('alert')).toHaveCount(0)
  await marks.getByRole('button').first().click()
  await dialog.getByPlaceholder('Поиск по названию марки...').fill('Аль')
  await dialog.getByRole('checkbox', { name: 'E2E Альфа', exact: true }).check()
  await dialog.getByPlaceholder('Поиск по названию марки...').fill('NoSuchMarkXYZ')
  await expect(dialog.getByText('Марки не найдены', { exact: true }).first()).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Убрать марку E2E Альфа' })).toBeVisible()
  await expect(dialog.getByRole('checkbox', { name: 'E2E Альфа', exact: true })).toHaveCount(0)
  await dialog.getByText('Марки ТС', { exact: true }).click()
  await marks.getByRole('button').first().click()
  let release: (() => void) | undefined
  const held = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/warehouses/marks?**', async route => {
    if (new URL(route.request().url()).searchParams.get('search') === 'Аль') {
      await held
    }
    await route.continue()
  })
  const alphaRequest = page.waitForRequest(request => new URL(request.url()).searchParams.get('search') === 'Аль')
  await dialog.getByPlaceholder('Поиск по названию марки...').fill('Аль')
  await alphaRequest
  await dialog.getByPlaceholder('Поиск по названию марки...').fill('Бет')
  await expect(dialog.getByRole('checkbox', { name: 'E2E Бета', exact: true })).toBeVisible()
  const alphaResponse = page.waitForResponse(response => new URL(response.url()).searchParams.get('search') === 'Аль')
  release?.()
  await alphaResponse
  await expect(dialog.getByRole('checkbox', { name: 'E2E Бета', exact: true })).toBeVisible()
  await expect(dialog.getByRole('checkbox', { name: 'E2E Альфа', exact: true })).toHaveCount(0)
  await dialog.getByText('Марки ТС', { exact: true }).click()
  await dialog.getByRole('button', { name: 'Отмена', exact: true }).click()
  await expect(dialog).toHaveCount(0)
})
