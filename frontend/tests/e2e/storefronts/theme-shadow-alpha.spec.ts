import { expect, test, type Locator } from '@playwright/test'
import { parse as parseTemplate, type ElementNode, type RootNode, type TemplateChildNode } from '@vue/compiler-dom'
import { parse } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import postcss from 'postcss'
import tailwindcss from 'tailwindcss'

// The CSS seam uses actual catalog classes, main.css, Tailwind and the theme
// resolver. No catalog requests or business actions are needed to measure a shadow.
const frontend = resolve(__dirname, '../../..')
const load = createRequire(resolve(frontend, 'package.json'))
const read = (path: string) => readFileSync(resolve(frontend, path), 'utf8')
const cardSource = read('features/cars/components/CarCard.vue')

function elements(source: string): ElementNode[] {
  const nodes: ElementNode[] = []
  const visit = (node: RootNode | TemplateChildNode) => {
    if (node.type === 1) nodes.push(node)
    if (node.type === 0 || node.type === 1) node.children.forEach(visit)
  }
  visit(parseTemplate(parse(source).descriptor.template!.content))
  return nodes
}
const classes = (node: ElementNode) => node.props.find(prop => prop.type === 6 && prop.name === 'class')
const classValue = (node: ElementNode) => {
  const attribute = classes(node)
  return attribute?.type === 6 ? attribute.value?.content ?? '' : ''
}
const required = (node: ElementNode | undefined, name: string) => {
  if (!node) throw new Error(`The actual ${name} element was not found`)
  return classValue(node)
}

const actual = {
  card: required(elements(cardSource).find(node => classValue(node).split(/\s+/).includes('card')), 'car card'),
  filter: 'p-4 md:p-6 storefront-shadow-lg',
  dropdown: 'storefront-shadow-xl',
}

// Independent pre-theme geometry and alpha, not read from the plugin/config.
const layers = {
  sm: ['0px 1px 2px 0px|0.05'],
  default: ['0px 1px 3px 0px|0.1', '0px 1px 2px -1px|0.1'],
  md: ['0px 4px 6px -1px|0.1', '0px 2px 4px -2px|0.1'],
  lg: ['0px 10px 15px -3px|0.1', '0px 4px 6px -4px|0.1'],
  xl: ['0px 20px 25px -5px|0.1', '0px 8px 10px -6px|0.1'],
  '2xl': ['0px 25px 50px -12px|0.25'],
  inner: ['0px 2px 4px 0px inset|0.05'],
  none: [],
} as const
type Size = keyof typeof layers
const sizes = Object.keys(layers) as Size[]
const utility = (size: Size) => `storefront-shadow${size === 'default' ? '' : `-${size}`}`
const states = ['hover', 'active', 'focus-visible', 'disabled', 'aria-pressed'] as const
const samples = sizes.flatMap(size => [utility(size), ...states.map(state => `${state}:${utility(size)}`)])
const consumers: { path: string, sizes: Size[] }[] = [
  { path: 'features/cars/components/CarCard.vue', sizes: ['md', 'sm', 'sm'] },
  { path: 'features/specialEquipment/components/SpecialEquipmentProductCard.vue', sizes: ['sm'] },
  { path: 'features/specialEquipment/components/SpecialEquipmentCatalogPanel.vue', sizes: ['2xl'] },
  { path: 'features/specialEquipment/components/SpecialEquipmentCartSection.vue', sizes: ['sm'] },
  { path: 'features/specialEquipment/components/SpecialEquipmentGallery.vue', sizes: ['sm', 'sm'] },
  { path: 'features/specialEquipment/components/SpecialEquipmentFacetDialog.vue', sizes: ['2xl'] },
]
const shadowLayers = (element: Locator) => element.evaluate(node =>
  // Separate layers without splitting the commas within rgb()/rgba(). Remove
  // only Tailwind's transparent placeholder/ring layers, not visible effects.
  getComputedStyle(node).boxShadow.split(/,\s*(?![^()]*\))/)
    .filter(layer => layer !== 'none' && !layer.startsWith('rgba(0, 0, 0, 0) ')),
)
const expected = (size: Size, color: string) => layers[size].map(layer => {
  const [geometry, alpha] = layer.split('|')
  return `rgba(${color}, ${alpha}) ${geometry}`
})
const expectShadow = (element: Locator, size: Size, color: string) =>
  expect.poll(() => shadowLayers(element)).toEqual(expected(size, color))

let css: string
let script: string
test.beforeAll(async () => {
  const config = load('./tailwind.config.js')
  css = (await postcss([tailwindcss({
    ...config,
    content: [{
      raw: consumers.map(consumer => read(consumer.path)).join('\n') + '\n' +
        samples.join(' ') + '\nshadow-sm shadow shadow-md shadow-lg shadow-xl shadow-2xl shadow-inner shadow-none ring-2 ring-offset-2',
      extension: 'vue',
    }],
  })]).process(read('assets/css/main.css'), { from: resolve(frontend, 'assets/css/main.css') })).css
  script = (await build({
    stdin: { contents: `
      import { buildStorefrontTheme, serializeStorefrontThemeVariables } from './features/storefront/theme'
      import { createDefaultStorefrontAppearance } from './features/storefront/appearance'
      const appearance = createDefaultStorefrontAppearance()
      window.setShadowTheme = (overrides, active = true) => {
        appearance.color_overrides = overrides
        const theme = buildStorefrontTheme(appearance)
        document.body.classList.toggle('storefront-theme', active)
        document.body.style.cssText = active ? serializeStorefrontThemeVariables(theme.variables) : ''
        document.querySelector('#theme').textContent = active ? theme.scopeCss : ''
      }
    `, resolveDir: frontend, loader: 'ts' },
    bundle: true, write: false, format: 'iife', platform: 'browser', alias: { '~': frontend },
  })).outputFiles[0]!.text
})

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.setContent('<html><head><style id="theme"></style></head><body><main></main></body></html>')
  await page.addStyleTag({ content: css })
  await page.addScriptTag({ content: script })
  await page.evaluate(items => {
    const host = document.querySelector('main')!
    host.setAttribute('style', 'display:flex;gap:80px;padding:80px;align-items:flex-start')
    for (const [name, value] of Object.entries(items)) {
      const element = document.createElement('div')
      element.id = name
      element.className = value
      element.dataset.storefrontBlock = name === 'card' ? 'cars.card' : 'cars.filters'
      // Only positioning/sizing is isolated: all actual color/shadow classes stay.
      element.style.cssText = 'position:relative;width:220px;height:140px;top:auto;left:auto'
      element.textContent = name
      host.append(element)
    }
  }, actual)
})

test('actual card, catalog filter and dropdown preserve each shadow layer while changing only RGB', async ({ page }) => {
  await page.evaluate(`window.setShadowTheme({
    'cars.card.shadow': '#A12B45', 'cars.filters.shadow': '#176FA3'
  })`)
  await expectShadow(page.locator('#card'), 'md', '161, 43, 69')
  await expectShadow(page.locator('#filter'), 'lg', '23, 111, 163')
  await expectShadow(page.locator('#dropdown'), 'xl', '23, 111, 163')
  await page.locator('#card').hover()
  await expectShadow(page.locator('#card'), 'lg', '161, 43, 69')
  await page.mouse.move(1400, 950)
  await page.evaluate('window.setShadowTheme({}, false)')
  await expectShadow(page.locator('#card'), 'md', '0, 0, 0')
  await expectShadow(page.locator('#filter'), 'lg', '0, 0, 0')
  await expectShadow(page.locator('#dropdown'), 'xl', '0, 0, 0')
})

test('all actual shadow consumers keep their pre-theme geometry and opacity', async ({ page }) => {
  const items = consumers.flatMap(consumer => {
    const nodes = elements(read(consumer.path)).filter(node =>
      /(?:^|\s)(?:[\w-]+:)*storefront-shadow(?:-[\w]+)?(?:\s|$)/.test(classValue(node)),
    )
    expect(nodes, consumer.path).toHaveLength(consumer.sizes.length)
    return nodes.map((node, index) => ({ classes: classValue(node), size: consumer.sizes[index]! }))
  })
  expect(items).toHaveLength(consumers.reduce((acc, c) => acc + c.sizes.length, 0))
  await page.evaluate(entries => {
    const host = document.querySelector('main')!
    host.replaceChildren()
    host.setAttribute('style', 'display:grid;grid-template-columns:repeat(5,180px);gap:60px;padding:60px')
    for (const [index, entry] of entries.entries()) {
      const node = document.createElement('div')
      node.id = `consumer-${index}`
      node.className = entry.classes
      node.style.cssText = 'position:relative;inset:auto;transform:none;width:180px;height:80px'
      host.append(node)
    }
  }, items)
  await page.evaluate(`window.setShadowTheme({ 'global.shadow': '#406080' })`)
  for (const [index, item] of items.entries()) {
    await expectShadow(page.locator(`#consumer-${index}`), item.size, '64, 96, 128')
  }
})

for (const size of sizes) {
  test(`${size} shadow preserves layers, color and workspace fallback in every utility state`, async ({ page }) => {
    await page.evaluate(() => {
      const host = document.querySelector('main')!
      host.innerHTML = '<button id="sample" style="width:180px;height:80px">Shadow sample</button>' +
        '<div id="ordinary" style="width:180px;height:80px">Ordinary workspace shadow</div>'
    })
    const sample = page.locator('#sample')
    const ordinary = page.locator('#ordinary')
    await sample.evaluate((node, value) => node.setAttribute('class', value), utility(size))
    await ordinary.evaluate((node, value) => node.setAttribute('class', value), `shadow${size === 'default' ? '' : `-${size}`}`)
    await expectShadow(sample, size, '0, 0, 0')
    await expectShadow(ordinary, size, '0, 0, 0')
    await page.evaluate(`window.setShadowTheme({ 'global.shadow': '#BA4C26' })`)
    await expectShadow(sample, size, '186, 76, 38')
    // The new utilities never recolor ordinary Tailwind shadows, even inside a theme.
    await expectShadow(ordinary, size, '0, 0, 0')
    for (const state of states) {
      await test.step(state, async () => {
        await page.mouse.move(1400, 950)
        await sample.evaluate((node, value) => {
          node.blur()
          node.removeAttribute('disabled')
          node.removeAttribute('aria-pressed')
          node.setAttribute('class', `storefront-shadow-none ${value}`)
        }, `${state}:${utility(size)}`)
        if (state === 'hover') await sample.hover()
        if (state === 'active') { await sample.hover(); await page.mouse.down() }
        if (state === 'focus-visible') {
          await page.keyboard.press('Tab')
          await sample.focus()
          expect(await sample.evaluate(node => node.matches(':focus-visible'))).toBe(true)
        }
        if (state === 'disabled') await sample.evaluate(node => node.setAttribute('disabled', ''))
        if (state === 'aria-pressed') await sample.evaluate(node => node.setAttribute('aria-pressed', 'true'))
        await expectShadow(sample, size, '186, 76, 38')
        await page.evaluate(`window.setShadowTheme({ 'global.shadow': '#2864C8' })`)
        await expectShadow(sample, size, '40, 100, 200')
        await page.evaluate('window.setShadowTheme({}, false)')
        await expectShadow(sample, size, '0, 0, 0')
        if (state === 'active') await page.mouse.up()
        await page.evaluate(`window.setShadowTheme({ 'global.shadow': '#BA4C26' })`)
      })
    }
  })
}

test('a colored shadow and a focus ring retain their independent layers', async ({ page }) => {
  await page.evaluate(() => {
    const host = document.querySelector('main')!
    host.innerHTML = '<button id="ring" class="storefront-shadow-md ring-2 ring-offset-2" ' +
      'style="width:180px;height:80px;--tw-ring-color:rgb(23 111 163);--tw-ring-offset-color:rgb(240 230 220)">Ring and shadow</button>'
  })
  await page.evaluate(`window.setShadowTheme({ 'global.shadow': '#A12B45' })`)
  await expect.poll(() => shadowLayers(page.locator('#ring'))).toEqual([
    'rgb(240, 230, 220) 0px 0px 0px 2px',
    'rgb(23, 111, 163) 0px 0px 0px 4px',
    ...expected('md', '161, 43, 69'),
  ])
})
