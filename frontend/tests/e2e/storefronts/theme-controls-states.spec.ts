import { test, expect, type Locator, type Page } from '@playwright/test'
import { build } from 'esbuild'
import { compileScript, compileStyle, parse } from '@vue/compiler-sfc'
import { readFileSync } from 'node:fs'
import { basename, dirname, resolve } from 'node:path'
import { createRequire } from 'node:module'
import postcss from 'postcss'
import tailwindcss from 'tailwindcss'
import registry from '../../../features/storefront/colorRegistry.json'

const frontend = resolve(__dirname, '../../..')
const load = createRequire(resolve(frontend, 'package.json'))
const palette = {
  normal: ['#112233', '#223344', '#334455', '#445566'],
  hover: ['#551122', '#662233', '#773344', '#884455'],
  focus: ['#115522', '#226633', '#337744', '#448855'],
  active: ['#221155', '#332266', '#443377', '#554488'],
  disabled: ['#552211', '#663322', '#774433', '#885544'],
} as const
type State = keyof typeof palette
const rgb = (hex: string) => `rgb(${[1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16)).join(', ')})`
const overrides: Record<string, string> = {}
for (const [state, colors] of Object.entries(palette)) {
  for (const variant of ['ghost', 'input']) {
    for (const [index, part] of ['', '-foreground', '-icon', '-border'].entries()) {
      const token = `${variant}${state === 'normal' ? '' : `-${state}`}${part}`
      overrides[`global.${(registry.tokens as Record<string, { key: string }>)[token]!.key}`] = colors[index]!
    }
  }
}
overrides['global.focus'] = '#AA44CC'
overrides['global.placeholder'] = '#BB55DD'

let script: string
let css: string
test.beforeAll(async () => {
  const scopedCss: string[] = []
  const bundle = await build({
    stdin: { contents: `
      import { createApp, h, reactive } from 'vue'
      import Dropdown from './components/ui/SearchableDropdown.vue'
      import Quantity from './features/specialEquipment/components/SpecialEquipmentQuantityPicker.vue'
      import Advantages from './components/Advantages.vue'
      import { buildStorefrontTheme, serializeStorefrontThemeVariables } from './features/storefront/theme'
      import { createDefaultStorefrontAppearance } from './features/storefront/appearance'
      const appearance = createDefaultStorefrontAppearance()
      const state = reactive({ disabled: false })
      window.setDisabled = disabled => { state.disabled = disabled }
      window.applyTheme = (overrides, active = true) => {
        appearance.color_overrides = overrides
        const theme = buildStorefrontTheme(appearance)
        document.body.classList.toggle('storefront-theme', active)
        document.body.style.cssText = active ? serializeStorefrontThemeVariables(theme.variables) : ''
        document.querySelector('#theme').textContent = active ? theme.scopeCss : ''
      }
      const app = createApp({ setup: () => () => h('main', { style: 'width: 1000px; margin: 40px;' }, [
        h('div', { style: 'width: 360px; margin-bottom: 48px' }, [h(Dropdown, {
          id: 'shared-dropdown', disabled: state.disabled,
          items: [{ id: '6d161cf8-87ad-4745-8bba-227ad0b6c9ff', name: 'Локальная опция' }],
          placeholder: 'Выберите значение',
        })]),
        h(Quantity, { id: 'quantity-control', modelValue: 2, max: 10, disabled: state.disabled }),
        h(Advantages),
      ]) })
      app.mount('#app')
      window.closeFixture = () => app.unmount()
    `, resolveDir: frontend, loader: 'ts' },
    bundle: true, write: false, format: 'iife', platform: 'browser', alias: { '~': frontend, '@': frontend },
    define: { 'import.meta.client': 'true', 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
    plugins: [{ name: 'actual-components-with-scoped-css', setup(builder) {
      builder.onLoad({ filter: /\.vue$/ }, args => {
        const { descriptor } = parse(readFileSync(args.path, 'utf8'), { filename: args.path })
        const scopeId = `data-v-controls-${basename(args.path, '.vue')}`
        const compiled = compileScript(descriptor, { id: scopeId, inlineTemplate: true })
        for (const style of descriptor.styles) {
          const compiledStyle = compileStyle({ filename: args.path, source: style.content, id: scopeId, scoped: style.scoped })
          if (compiledStyle.errors.length) throw compiledStyle.errors[0]
          scopedCss.push(compiledStyle.code)
        }
        return {
          contents: `import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick, useId } from 'vue';\n${compiled.content.replace('export default', 'const component =')}\ncomponent.__scopeId = ${JSON.stringify(scopeId)}; export default component;`,
          loader: 'ts', resolveDir: dirname(args.path),
        }
      })
    } }],
  })
  script = bundle.outputFiles[0]!.text
  const config = load('./tailwind.config.js')
  const generated = await postcss([tailwindcss({ ...config, content: config.content.map((glob: string) => resolve(frontend, glob)) })])
    .process(readFileSync(resolve(frontend, 'assets/css/main.css'), 'utf8') + '\n' + scopedCss.join('\n'), { from: resolve(frontend, 'assets/css/main.css') })
  css = generated.css
})

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.setContent('<html><head><style id="theme"></style></head><body><div id="app"></div></body></html>')
  await page.addStyleTag({ content: css })
  await page.addScriptTag({ content: script })
})
test.afterEach(async ({ page }) => { await page.evaluate('window.closeFixture?.()') })

const colors = (element: Locator) => element.evaluate(node => {
  const style = getComputedStyle(node)
  const icon = node.querySelector('svg')
  return { background: style.backgroundColor, text: style.color, border: style.borderTopColor, icon: icon ? getComputedStyle(icon).color : null }
})
const setState = async (page: Page, element: Locator, state: State) => {
  await page.mouse.move(1400, 950)
  await page.evaluate('document.activeElement?.blur(); window.setDisabled(false)')
  if (state === 'hover') await element.hover()
  if (state === 'focus') {
    await page.keyboard.press('Tab')
    await element.focus()
    expect(await element.evaluate(node => node.matches(':focus-visible'))).toBe(true)
  }
  if (state === 'active') { await element.hover(); await page.mouse.down() }
  if (state === 'disabled') { await page.evaluate('window.setDisabled(true)'); await element.hover() }
}

test('actual shared button uses independent background, text, icon and visible border in every state', async ({ page }) => {
  await page.evaluate(value => (window as unknown as { applyTheme: (value: Record<string, string>) => void }).applyTheme(value), overrides)
  const button = page.locator('#shared-dropdown > button')
  for (const state of Object.keys(palette) as State[]) {
    await test.step(state, async () => {
      await setState(page, button, state)
      const [background, text, icon, border] = palette[state].map(rgb)
      await expect.poll(() => colors(button)).toEqual({ background, text, icon, border })
      expect(await button.evaluate(node => getComputedStyle(node).borderTopWidth)).toBe('1px')
      if (state === 'focus') await expect(button).toHaveCSS('outline-color', rgb('#AA44CC'))
      if (state === 'active') { await page.mouse.move(1400, 950); await page.mouse.up() }
      if (state === 'disabled') await expect(button).toHaveCSS('opacity', '1')
    })
  }
})

test('actual native quantity input applies independent state colors including disabled while hovered', async ({ page }) => {
  await page.evaluate(value => (window as unknown as { applyTheme: (value: Record<string, string>) => void }).applyTheme(value), overrides)
  const input = page.locator('#quantity-control input')
  for (const state of Object.keys(palette) as State[]) {
    await test.step(state, async () => {
      await setState(page, input, state)
      const [background, text, , border] = palette[state].map(rgb)
      await expect.poll(() => colors(input)).toEqual({ background, text, border, icon: null })
      expect(await input.evaluate(node => getComputedStyle(node).borderLeftWidth)).toBe('1px')
      if (state === 'focus') await expect(input).toHaveCSS('outline-color', rgb('#AA44CC'))
      if (state === 'active') { await page.mouse.move(1400, 950); await page.mouse.up() }
    })
  }
})

test('clearing the theme restores actual shared button and search-field workspace computed styles', async ({ page }) => {
  const button = page.locator('#shared-dropdown > button')
  await button.click()
  const input = page.getByPlaceholder('Найти...')
  await expect(input).toBeVisible()
  await page.mouse.move(1400, 950)
  await page.evaluate('document.activeElement?.blur()')
  await button.evaluate(async node => { await Promise.all(node.getAnimations().map(animation => animation.finished.catch(() => undefined))) })
  const originalButton = await colors(button)
  const originalInput = await colors(input)
  await page.evaluate(value => (window as unknown as { applyTheme: (value: Record<string, string>) => void }).applyTheme(value), overrides)
  await expect.poll(() => colors(button)).toEqual({ background: rgb('#112233'), text: rgb('#223344'), icon: rgb('#334455'), border: rgb('#445566') })
  await expect(input).toHaveCSS('background-color', rgb('#112233'))
  await expect.poll(() => input.evaluate(node => getComputedStyle(node, '::placeholder').color)).toBe(rgb('#BB55DD'))
  await page.evaluate('window.applyTheme({}, false)')
  await expect.poll(() => colors(button)).toEqual(originalButton)
  await expect.poll(() => colors(input)).toEqual(originalInput)
})

test('theme removal leaves every workspace button state unchanged, including its native disabled opacity', async ({ page }) => {
  const button = page.locator('#shared-dropdown > button')
  const capture = async () => {
    const result: Record<string, unknown> = {}
    for (const state of Object.keys(palette) as State[]) {
      await setState(page, button, state)
      await button.evaluate(async node => {
        await Promise.all(node.getAnimations().map(animation => animation.finished.catch(() => undefined)))
      })
      result[state] = await button.evaluate(node => {
        const style = getComputedStyle(node)
        return { background: style.backgroundColor, text: style.color, border: style.borderTopColor, icon: getComputedStyle(node.querySelector('svg')!).color, opacity: style.opacity, outline: style.outlineColor, outlineWidth: style.outlineWidth }
      })
      if (state === 'active') { await page.mouse.move(1400, 950); await page.mouse.up() }
    }
    return result
  }
  const before = await capture()
  await page.evaluate(value => (window as unknown as { applyTheme: (value: Record<string, string>) => void }).applyTheme(value), overrides)
  await expect(button).toHaveCSS('background-color', rgb('#552211'))
  await page.evaluate('window.applyTheme({}, false)')
  expect(await capture()).toEqual(before)
})

test('the first advantage has its own blue accent, independent from card and description', async ({ page }) => {
  const cards = page.locator('[data-storefront-block="home.advantages"] .grid > div')
  const first = cards.first()
  const accent = first.locator(':scope > div').first()
  const icon = accent.locator('span')
  await page.evaluate('window.applyTheme({})')
  await expect(accent).toHaveCSS('background-color', rgb('#DBEAFE'))
  await expect(icon).toHaveCSS('color', rgb('#2563EB'))
  await page.evaluate(`window.applyTheme({
    'home.advantages.surface_muted': '#111111',
    'home.advantages.muted_text': '#222222',
    'home.advantages.decoration.conditions.background': '#33AA11',
    'home.advantages.decoration.conditions.icon': '#4411AA',
    'home.advantages.status.success.icon': '#FA1234',
    'home.advantages.status.warning.icon': '#AB5678',
    'home.advantages.status.error.icon': '#CD9012'
  })`)
  await expect(first).toHaveCSS('background-color', rgb('#111111'))
  await expect(first.locator('p')).toHaveCSS('color', rgb('#222222'))
  await expect(accent).toHaveCSS('background-color', rgb('#33AA11'))
  await expect(icon).toHaveCSS('color', rgb('#4411AA'))
  await expect(cards.nth(1).locator('svg')).toHaveCSS('color', rgb('#FA1234'))
  await expect(cards.nth(3).locator('svg')).toHaveCSS('color', rgb('#AB5678'))
  await expect(cards.nth(4).locator('svg')).toHaveCSS('color', rgb('#CD9012'))
})

test('all six actual calculator wrapper classes use the independent focus-within border', async ({ page }) => {
  // Exercise the real wrapper classes only: no calculator state or API mocks.
  const cart = readFileSync(resolve(frontend, 'features/cart/calculator/CartLeasingCalculator.vue'), 'utf8')
  const calculator = readFileSync(resolve(frontend, 'features/calculator/components/LeasingCalculator.vue'), 'utf8')
  const wrappers = [
    ...[...cart.matchAll(/class="([^"]*focus-within:border-[^"]*)"/g)].map(match => ({ block: 'client.cart', classes: match[1]! })),
    ...[...calculator.matchAll(/@apply ([^;]*focus-within:border-[^;]*);/g)].map(match => ({ block: 'home.calculator', classes: match[1]! })),
  ]
  expect(wrappers).toHaveLength(6)
  await page.evaluate(items => {
    const host = document.createElement('div')
    host.id = 'calculator-wrappers'
    host.style.cssText = 'display:grid;gap:16px;width:600px;margin:40px'
    for (const [index, item] of items.entries()) {
      const wrapper = document.createElement('div')
      wrapper.dataset.storefrontBlock = item.block
      wrapper.className = item.classes
      wrapper.id = `calculator-wrapper-${index}`
      wrapper.append(document.createElement('input'))
      host.append(wrapper)
    }
    document.body.append(host)
  }, wrappers)
  await page.evaluate(`window.applyTheme({
    'global.border': '#112233',
    'client.cart.input.focus.border': '#AB12CD',
    'home.calculator.input.focus.border': '#34CD12'
  })`)
  try {
    for (const [index, item] of wrappers.entries()) {
      const wrapper = page.locator(`#calculator-wrapper-${index}`)
      await expect(wrapper).toHaveCSS('border-color', rgb('#112233'))
      await wrapper.locator('input').focus()
      expect(await wrapper.evaluate(node => node.matches(':focus-within'))).toBe(true)
      await expect(wrapper).toHaveCSS('border-color', rgb(item.block === 'client.cart' ? '#AB12CD' : '#34CD12'))
      await wrapper.locator('input').blur()
      await expect(wrapper).toHaveCSS('border-color', rgb('#112233'))
    }
  } finally {
    await page.locator('#calculator-wrappers').evaluate(node => node.remove())
  }
})
