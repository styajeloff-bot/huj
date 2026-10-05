import { readFileSync } from 'node:fs'
import { expect, test, type Locator, type Page } from '@playwright/test'

interface ModificationFixture {
  marker: string; base_url: string; brand: string; model: string
  cases: Record<string, { modification: string }>
  trims: Record<string, { id: string; name: string; modification_id: string }>
}
interface RuntimeFixture {
  base_url: string; storage_states: Record<string, string>
  companies: Record<string, { name: string }>
}
const enabled = process.env.MONETIZATION_22406_E2E === '1'
const directory = '/tmp/carcraft-22406-e2e'
const fixture: ModificationFixture | null = enabled
  ? JSON.parse(readFileSync(directory + '/modification.manifest.json', 'utf8')) : null
const runtime: RuntimeFixture | null = enabled
  ? JSON.parse(readFileSync(directory + '/manifest.json', 'utf8')) : null
if (fixture && (fixture.marker !== 'monetization-22406-modification'
  || fixture.base_url !== 'http://localhost:18268' || runtime?.base_url !== fixture.base_url)) {
  throw new Error('Task 22406 requires its isolated local fixture')
}
test.skip(!enabled, 'Requires task 22406 isolated Docker fixtures')
test.setTimeout(90_000)

function field(editor: Locator, label: string) {
  return editor.locator('.filter-label').filter({ hasText: new RegExp('^' + label + '$') }).locator('..')
}
async function choose(page: Page, editor: Locator, label: string, value: string) {
  const menu = page.locator('div.custom-scrollbar')
  await expect(menu).toHaveCount(0)
  await field(editor, label).getByRole('button').first().click()
  await menu.getByRole('button', { name: value, exact: true }).click()
  await expect(menu).toHaveCount(0)
}
async function expectChoices(page: Page, editor: Locator, label: string, choices: string[]) {
  const control = field(editor, label).getByRole('button').first()
  const menu = page.locator('div.custom-scrollbar')
  await expect(menu).toHaveCount(0)
  await control.click()
  await expect(menu.getByRole('button')).toHaveText(choices)
  await control.click()
  await expect(menu).toHaveCount(0)
}
async function openEditor(page: Page) {
  await page.goto('/workspace/monetization')
  await page.getByRole('button', { name: 'Создать условия монетизации', exact: true }).click()
  const editor = page.locator('.program-editor')
  await expect(editor).toBeVisible()
  return editor
}

for (const width of [768, 1440]) {
  test('real trims depend on modification and survive creation at ' + width + 'px', async ({ browser }) => {
    const context = await browser.newContext({
      baseURL: fixture!.base_url, storageState: runtime!.storage_states.admin,
      viewport: { width, height: 1000 },
    })
    const page = await context.newPage()
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    try {
      const editor = await openEditor(page)
      expect(await editor.locator('.program-grid-five .filter-label').allTextContents())
        .toEqual(['Марка', 'Модель', 'Модификация', 'Комплектация'])
      await expect(field(editor, 'Модификация').getByRole('button').first()).toBeDisabled()
      await expect(field(editor, 'Комплектация').getByRole('button').first()).toBeDisabled()
      await choose(page, editor, 'Марка', fixture!.brand)
      await choose(page, editor, 'Модель', fixture!.model)
      await expect(field(editor, 'Комплектация').getByRole('button').first()).toBeDisabled()
      const modificationA = fixture!.cases.specific_a!.modification
      const modificationB = fixture!.cases.specific_b!.modification
      const emptyModification = fixture!.cases.generic!.modification
      const trimA = fixture!.trims.trim_a!
      const trimB = fixture!.trims.trim_b!
      const otherTrim = fixture!.trims.trim_other!
      await choose(page, editor, 'Модификация', modificationA)
      await expectChoices(page, editor, 'Комплектация', [
        'Все комплектации', ...[trimA.name, trimB.name].sort(),
      ])
      await choose(page, editor, 'Комплектация', trimA.name)
      await choose(page, editor, 'Комплектация', 'Все комплектации')
      await expect(field(editor, 'Модификация')).toContainText(modificationA)
      await choose(page, editor, 'Комплектация', trimA.name)
      await choose(page, editor, 'Модификация', modificationB)
      await expect(field(editor, 'Комплектация')).toContainText('Все комплектации')
      await expectChoices(page, editor, 'Комплектация', ['Все комплектации', otherTrim.name])
      await choose(page, editor, 'Комплектация', otherTrim.name)
      await choose(page, editor, 'Модификация', 'Все модификации')
      await expect(field(editor, 'Комплектация')).toContainText('Все комплектации')
      await expect(field(editor, 'Комплектация').getByRole('button').first()).toBeDisabled()
      await choose(page, editor, 'Модификация', emptyModification)
      await field(editor, 'Комплектация').getByRole('button').first().click()
      await expect(page.locator('div.custom-scrollbar').getByRole('button')).toHaveText(['Все комплектации'])
      await expect(page.locator('div.custom-scrollbar')).toContainText('Ничего не найдено')
      await field(editor, 'Комплектация').getByRole('button').first().click()
      await expect(page.locator('div.custom-scrollbar')).toHaveCount(0)
      await choose(page, editor, 'Модификация', modificationA)
      await choose(page, editor, 'Комплектация', trimB.name)
      await choose(page, editor, 'Модель', 'Все модели')
      await expect(field(editor, 'Модификация')).toContainText('Все модификации')
      await expect(field(editor, 'Комплектация')).toContainText('Все комплектации')
      await expect(field(editor, 'Комплектация').getByRole('button').first()).toBeDisabled()
      await choose(page, editor, 'Модель', fixture!.model)
      await choose(page, editor, 'Модификация', modificationA)
      await choose(page, editor, 'Комплектация', trimA.name)
      const savedTrim = width === 768 ? null : trimA.name
      if (savedTrim === null) await choose(page, editor, 'Комплектация', 'Все комплектации')
      const name = '22406 UI real trim ' + width + ' ' + Date.now()
      await editor.getByLabel('Название *', { exact: true }).fill(name)
      const leasing = editor.locator('.filter-label').filter({ hasText: 'Лизинговая компания *' }).locator('..')
      await leasing.getByRole('button').first().click()
      await page.getByPlaceholder('Название или ИНН', { exact: true }).last().fill(runtime!.companies.leasing_company!.name)
      await page.locator('div.custom-scrollbar').getByRole('button', {
        name: new RegExp('^' + runtime!.companies.leasing_company!.name + ' ·'),
      }).click()
      await editor.getByLabel('Дата начала *', { exact: true }).fill('2026-01-01')
      await editor.getByLabel('Неактивна', { exact: true }).check()
      await editor.locator('.condition-row').first().getByLabel('Значение (%)', { exact: true }).fill('5')
      await editor.locator('.condition-row').nth(1).getByLabel('Значение (%)', { exact: true }).fill('5')
      const posted = page.waitForResponse(response => response.request().method() === 'POST'
        && response.url().endsWith('/admin/monetization/programs'))
      await editor.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
      const saved = await posted
      expect(saved.status(), await saved.text()).toBe(201)
      expect(saved.request().postDataJSON().modification).toBe(modificationA)
      expect(saved.request().postDataJSON().trim).toBe(savedTrim)
      const program = await saved.json()
      expect(program.modification).toBe(modificationA)
      expect(program.trim).toBe(savedTrim)
      await expect(page.locator('.program-detail')).toContainText(modificationA)
      if (savedTrim !== null) await expect(page.locator('.program-detail')).toContainText(savedTrim)
      await page.reload()
      await page.locator('.programs-table tr').filter({ hasText: name }).getByRole('button', { name: 'Карточка', exact: true }).click()
      await expect(page.locator('.program-detail')).toContainText(modificationA)
      if (savedTrim !== null) await expect(page.locator('.program-detail')).toContainText(savedTrim)
      expect(await page.locator('.program-detail').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
      await page.locator('.program-detail').screenshot({ path: test.info().outputPath('real-trim-' + width + '.png') })
      expect(errors).toEqual([])
    } finally { await context.close() }
  })
}

test('late real trim lookup cannot restore choices from a previous modification', async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: fixture!.base_url, storageState: runtime!.storage_states.admin,
    viewport: { width: 1440, height: 1000 },
  })
  const page = await context.newPage()
  let release = () => {}
  const gate = new Promise<void>(resolve => { release = resolve })
  let fetched = () => {}
  const actualResponseFetched = new Promise<void>(resolve => { fetched = resolve })
  let fulfilled = () => {}
  const responseFulfilled = new Promise<void>(resolve => { fulfilled = resolve })
  try {
    const editor = await openEditor(page)
    await choose(page, editor, 'Марка', fixture!.brand)
    await choose(page, editor, 'Модель', fixture!.model)
    const trimA = fixture!.trims.trim_a!
    const otherTrim = fixture!.trims.trim_other!
    await page.route('**/monetization/lookups/catalog?**', async route => {
      const query = new URL(route.request().url()).searchParams
      if (query.get('fields') !== 'trims' || query.get('modification_id') !== trimA.modification_id) {
        await route.fallback()
        return
      }
      const response = await route.fetch()
      expect(response.status()).toBe(200)
      fetched()
      await gate
      await route.fulfill({ response })
      fulfilled()
    })
    await choose(page, editor, 'Модификация', fixture!.cases.specific_a!.modification)
    await actualResponseFetched
    await expect(field(editor, 'Комплектация').getByRole('button').first()).toBeDisabled()
    await choose(page, editor, 'Модификация', fixture!.cases.specific_b!.modification)
    await expectChoices(page, editor, 'Комплектация', ['Все комплектации', otherTrim.name])
    release()
    await responseFulfilled
    await page.waitForLoadState('networkidle')
    await expectChoices(page, editor, 'Комплектация', ['Все комплектации', otherTrim.name])
    await expect(field(editor, 'Модификация')).toContainText(fixture!.cases.specific_b!.modification)
  } finally {
    release()
    await context.close()
  }
})