import { test, expect } from '@playwright/test'
import { build } from 'esbuild'
import { compileScript, compileStyle, parse } from '@vue/compiler-sfc'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createRequire } from 'node:module'
import postcss from 'postcss'
import tailwindcss from 'tailwindcss'

const frontend = resolve(__dirname, '../../..')
const load = createRequire(resolve(frontend, 'package.json'))

let script: string
let css: string

test.beforeAll(async () => {
  const scopedCss: string[] = []
  const bundle = await build({
    stdin: {
      contents: `
        globalThis.useRuntimeConfig = () => ({ public: { apiBase: '' } })
        globalThis.useToast = () => ({ showToast: () => {} })
        globalThis.useLogger = () => ({ info: () => {}, error: () => {}, warn: () => {} })
        globalThis.useFormatPrice = () => ({ formatPrice: v => String(v) + ' ₽' })
        globalThis.useFormatDate = () => ({ formatDate: v => String(v) })

        import { createApp, h, reactive } from 'vue'
        import ClientCalculatorPanel from './features/calculator/components/ClientCalculatorPanel.vue'

        const app = createApp({
          setup: () => () => h('main', { style: 'width: 1000px; padding: 24px;' }, [
            h('div', { id: 'calc-container' }, [h(ClientCalculatorPanel)]),
            h('div', { id: 'test-controls', class: 'space-y-4 mt-8' }, [
              h('input', {
                id: 'theme-range',
                type: 'range',
                min: 12,
                max: 84,
                step: 12,
                class: 'storefront-control w-full h-2 rounded-lg appearance-none cursor-pointer',
              }),
              h('select', {
                id: 'workspace-select',
                class: 'select-field',
              }, [
                h('option', { value: '1' }, 'Опция 1'),
                h('option', { value: '2' }, 'Опция 2'),
              ]),
            ]),
          ]),
        })
        app.mount('#app')
      `,
      resolveDir: frontend,
      loader: 'ts',
    },
    bundle: true,
    write: false,
    format: 'iife',
    platform: 'browser',
    plugins: [
      {
        name: 'vue-sfc',
        setup(buildPlugin) {
          buildPlugin.onResolve({ filter: /\.vue$/ }, args => ({
            path: resolve(args.resolveDir, args.path),
          }))
          buildPlugin.onLoad({ filter: /\.vue$/ }, args => {
            const raw = readFileSync(args.path, 'utf8')
            const parsed = parse(raw, { filename: args.path })
            const descriptor = parsed.descriptor
            const id = 'v-' + Math.random().toString(36).slice(2, 8)
            const scriptBlock = descriptor.script || descriptor.scriptSetup
              ? compileScript(descriptor, { id, inlineTemplate: true, templateOptions: { scoped: true } })
              : null
            for (const style of descriptor.styles) {
              const compiled = compileStyle({ source: style.content, filename: args.path, id: `data-${id}`, scoped: style.scoped })
              scopedCss.push(compiled.code)
            }
            return {
              contents: scriptBlock ? scriptBlock.content : 'export default {}',
              loader: 'ts',
              resolveDir: resolve(args.path, '..'),
            }
          })
        },
      },
    ],
  })

  script = bundle.outputFiles[0]!.text
  const mainCss = readFileSync(resolve(frontend, 'assets/css/main.css'), 'utf8')
  const processor = postcss([tailwindcss(load('./tailwind.config.js'))])
  const result = await processor.process(mainCss, { from: resolve(frontend, 'assets/css/main.css') })
  css = `${result.css}\n${scopedCss.join('\n')}`
})

test.describe('Проверка калькулятора клиента, ползунков и селектов', () => {
  test.beforeEach(async ({ page }) => {
    page.on('pageerror', err => console.error('Browser pageerror:', err))
    await page.setContent(`<!DOCTYPE html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=1280">
    <style id="base-css">${css}</style>
  </head>
  <body class="storefront-theme" style="--storefront-primary: #3b82f6; --storefront-primary-hover: #2563eb; --storefront-surface-muted: #e5e7eb; --storefront-surface: #ffffff; --storefront-input: #ffffff; --storefront-focus: #3b82f6;">
    <div id="app"></div>
    <script>${script}</script>
  </body>
</html>`)
  })

  test('В ClientCalculatorPanel отсутствуют блоки "График платежей" и "Сравнение вариантов"', async ({ page }) => {
    const calcContainer = page.locator('#calc-container')
    await expect(calcContainer).toBeVisible()

    // Проверяем, что заголовки и блоки графиков и сравнения удалены
    await expect(page.getByText('График платежей')).toHaveCount(0)
    await expect(page.getByText('Сравнение вариантов')).toHaveCount(0)
    await expect(page.getByText('Покупка за наличные')).toHaveCount(0)

    // Проверяем, что основные параметры калькулятора остались на месте
    await expect(page.getByText('Стоимость автомобиля', { exact: true })).toBeVisible()
    await expect(page.getByText('Срок лизинга', { exact: false }).first()).toBeVisible()
    await expect(page.getByText('Первоначальный взнос', { exact: false }).first()).toBeVisible()
    await expect(page.getByText('Ежемесячный платеж', { exact: false }).first()).toBeVisible()
  })

  test('Ползунки input[type="range"] имеют видимый бегунок и дорожку с фоном surface-muted', async ({ page }) => {
    const rangeInput = page.locator('#theme-range')
    await expect(rangeInput).toBeVisible()

    // Проверяем вычисленный цвет фона дорожки ползунка: он НЕ должен быть белым (--storefront-input = #ffffff)
    const bgColor = await rangeInput.evaluate(el => window.getComputedStyle(el).backgroundColor)
    expect(bgColor).toBe('rgb(229, 231, 235)')

    // Проверяем cursor и appearance
    const cursor = await rangeInput.evaluate(el => window.getComputedStyle(el).cursor)
    expect(cursor).toBe('pointer')
    const appearance = await rangeInput.evaluate(el => window.getComputedStyle(el).appearance)
    expect(appearance).toBe('none')

    // Проверяем наличие стилей псевдоэлемента ::-webkit-slider-thumb в document.styleSheets
    const hasThumbRules = await page.evaluate(() => {
      let found = false
      for (const sheet of document.styleSheets) {
        try {
          for (const rule of sheet.cssRules) {
            if (rule.cssText.includes('-slider-thumb') && rule.cssText.includes('var(--storefront-primary')) {
              found = true
              break
            }
          }
        } catch {}
      }
      return found
    })
    expect(hasThumbRules).toBe(true)
  })

  test('Селект с классом select-field имеет кастомную стрелку, padding-right и appearance none', async ({ page }) => {
    // В workspace селект рендерится без body.storefront-theme
    await page.evaluate(() => document.body.classList.remove('storefront-theme'))
    const select = page.locator('#workspace-select')
    await expect(select).toBeVisible()

    const selectStyles = await select.evaluate(el => {
      const computed = window.getComputedStyle(el)
      return {
        appearance: computed.appearance,
        backgroundImage: computed.backgroundImage,
        paddingRight: computed.paddingRight,
        cursor: computed.cursor,
      }
    })

    expect(selectStyles.appearance).toBe('none')
    expect(selectStyles.backgroundImage).toContain('data:image/svg+xml')
    expect(selectStyles.paddingRight).toBe('40px') // 2.5rem = 40px
    expect(selectStyles.cursor).toBe('pointer')
  })
})
