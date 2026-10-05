import { expect, test } from '@playwright/test'
import type { App } from 'vue'
import type { useToastStore } from '../../../stores/toast'

type NuxtRoot = Element & { __vue_app__?: App }
type ToastState = ReturnType<typeof useToastStore>['$state']

for (const width of [768, 1440]) {
  test(`new application toast stays above the header at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await page.route(/https:\/\/(?:mc\.yandex\.ru|static\.me-talk\.ru)\//, route => route.abort())
    await page.goto('/about')
    await page.waitForFunction(() => {
      const root = document.querySelector('#__nuxt') as NuxtRoot | null
      return Boolean(root?.__vue_app__?.config.globalProperties.$pinia?.state.value.toast)
    })

    const header = page.getByRole('banner')
    const initialHeader = await header.boundingBox()
    expect(initialHeader).not.toBeNull()

    for (const scrollY of [0, 300]) {
      await page.evaluate(y => window.scrollTo(0, y), scrollY)
      await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(scrollY)
      await page.evaluate(() => {
        const root = document.querySelector('#__nuxt') as NuxtRoot
        const state = root.__vue_app__!.config.globalProperties.$pinia.state.value.toast as ToastState
        state.toasts.push({
          id: state.nextId++,
          type: 'info',
          title: 'Новая заявка',
          message: 'Поступила новая заявка на лизинг',
          duration: 5000,
          persistent: true,
          remainingTime: 5000,
          actionText: 'Перейти',
          actionCallback: () => {},
        })
      })

      const title = page.getByRole('heading', { name: 'Новая заявка', exact: true })
      const close = title.locator('../..').getByRole('button').last()
      await expect(title).toBeVisible()
      await expect.poll(async () => close.evaluate(button => {
        const bounds = button.getBoundingClientRect()
        const headerBounds = document.querySelector('header')!.getBoundingClientRect()
        const x = bounds.x + bounds.width / 2
        const y = bounds.y + bounds.height / 2
        return {
          overlapsHeader: x >= headerBounds.left && x <= headerBounds.right
            && y >= headerBounds.top && y <= headerBounds.bottom,
          receivesPointer: button.contains(document.elementFromPoint(x, y)),
        }
      })).toEqual({ overlapsHeader: true, receivesPointer: true })
      expect(await header.boundingBox()).toEqual(initialHeader)
      await page.screenshot({ path: testInfo.outputPath(`toast-${width}-scroll-${scrollY}.png`) })

      await close.click()
      await expect(title).toHaveCount(0)
      expect(await header.boundingBox()).toEqual(initialHeader)
    }
  })
}
