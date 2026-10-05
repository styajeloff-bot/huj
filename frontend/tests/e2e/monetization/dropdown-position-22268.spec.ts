import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { compileScript, compileStyle, parse } from '@vue/compiler-sfc'
import { ModuleKind, ScriptTarget, transpileModule } from 'typescript'
import { expect, test, type Page } from '@playwright/test'

// Mount the real shared SFC in Chromium. The label and scroll container are
// deliberately tall enough to reproduce the user's upward-opening menu.
const filename = resolve(__dirname, '../../../components/ui/SearchableDropdown.vue')
const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
const script = transpileModule(compileScript(descriptor, { id: 'dropdown-regression', inlineTemplate: true }).content, {
  compilerOptions: { target: ScriptTarget.ES2022, module: ModuleKind.CommonJS },
}).outputText
const css = compileStyle({ source: descriptor.styles[0]!.content, filename, id: 'data-v-dropdown-regression', scoped: true }).code

async function mountDropdown(page: Page, props: Record<string, unknown>) {
  await page.setViewportSize({ width: 1000, height: 700 })
  await page.setContent(`<style>
    * { box-sizing: border-box }
    #scroller { position:fixed; top:30px; left:80px; width:700px; height:600px; overflow:auto }
    #mount { width:300px; margin-top:400px; margin-bottom:600px }
    .w-full { width:100% } .p-2 { padding:8px } .px-3 { padding-left:12px; padding-right:12px }
    .py-2 { padding-top:8px; padding-bottom:8px } .overflow-y-auto { overflow-y:auto }
    .relative { position:relative } .absolute { position:absolute } .pl-9 { padding-left:36px }
    .shadow-xl { background:white; border:1px solid gray } .filter-label { line-height:20px }
    .h-4, .w-4 { width:16px; height:16px } button, input { font:14px Arial }
  </style><div id="scroller"><div id="mount"></div></div>`)
  await page.addScriptTag({ path: require.resolve('vue/dist/vue.global.js') })
  await page.addStyleTag({ content: css })
  await page.evaluate(`(() => {
    const component = new Function('Vue', 'const exports={}; const require=()=>Vue; with(Vue){' + ${JSON.stringify(script)} + '}; return exports.default;')(Vue);
    component.__scopeId = 'data-v-dropdown-regression';
    window.dropdownState = Vue.reactive({ loading: true, items: [] });
    Vue.createApp({ render: () => Vue.h(component, {
      label: 'Очень длинная подпись поля выбора марки автомобиля',
      placeholder: 'Все марки', emptyLabel: 'Справочник марок пуст',
      ...${JSON.stringify(props)}, ...window.dropdownState
    }) }).mount('#mount');
  })()`)
  await page.locator('#mount button').first().click()
  await expect(page.locator('.shadow-xl')).toBeVisible()
}

async function position(page: Page) {
  return page.evaluate(() => {
    const control = document.querySelector('#mount button')!.getBoundingClientRect()
    const wrapper = document.querySelector('#mount [data-storefront-block]')!.getBoundingClientRect()
    const menu = document.querySelector('.shadow-xl')!.getBoundingClientRect()
    return { upwardControlGap: control.top - menu.bottom, upwardWrapperGap: wrapper.top - menu.bottom,
      downwardGap: menu.top - control.bottom, horizontalGap: menu.left - control.left,
      widthDelta: menu.width - control.width }
  })
}

test('monetization popup stays 4px from its button with wrapped labels, scrolling and loaded options', async ({ page }) => {
  await mountDropdown(page, { anchorToControl: true })
  await expect.poll(async () => (await position(page)).upwardControlGap).toBeCloseTo(4, 0)
  await page.evaluate(() => { document.querySelector('#scroller')!.scrollTop = 70 })
  await expect.poll(async () => (await position(page)).upwardControlGap).toBeCloseTo(4, 0)
  await page.evaluate('window.dropdownState.loading=false; window.dropdownState.items=[{id:"mark-one",name:"Sollers"},{id:"mark-two",name:"UAZ"}]')
  await expect(page.locator('.shadow-xl')).toContainText('Sollers')
  await expect.poll(async () => (await position(page)).upwardControlGap).toBeCloseTo(4, 0)
  expect((await position(page)).horizontalGap).toBeCloseTo(0, 0)
  expect((await position(page)).widthDelta).toBeCloseTo(0, 0)
  await page.setViewportSize({ width: 1000, height: 1000 })
  await expect.poll(async () => (await position(page)).downwardGap).toBeCloseTo(4, 0)
})

test('existing callers retain the default wrapper anchor', async ({ page }) => {
  await mountDropdown(page, {})
  await expect.poll(async () => (await position(page)).upwardWrapperGap).toBeCloseTo(4, 0)
  expect((await position(page)).upwardControlGap).toBeGreaterThan(20)
})

test('loading, empty catalog and returned options are distinct visible states', async ({ page }) => {
  await mountDropdown(page, { anchorToControl: true })
  await expect(page.getByRole('status')).toHaveText('Загрузка…')
  await expect(page.locator('.shadow-xl')).not.toContainText('Справочник марок пуст')
  await page.evaluate('window.dropdownState.loading=false')
  await expect(page.locator('.shadow-xl')).toContainText('Справочник марок пуст')
  await page.evaluate('window.dropdownState.items=[{id:"mark-one",name:"Sollers"}];window.dropdownState.loading=true')
  await expect(page.locator('.shadow-xl')).not.toContainText('Sollers')
  await page.evaluate('window.dropdownState.loading=false')
  await page.getByRole('button', { name: 'Sollers', exact: true }).click()
  await expect(page.locator('.shadow-xl')).toHaveCount(0)
})