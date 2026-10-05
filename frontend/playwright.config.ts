import fs from 'node:fs'
import { defineConfig, devices } from '@playwright/test'

const isCi = Boolean(process.env.CI)
const isDocker = fs.existsSync('/.dockerenv')
const defaultBaseUrl = isDocker ? 'http://nginx' : 'http://127.0.0.1'

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: './test-results/playwright',
  fullyParallel: false,
  forbidOnly: isCi,
  retries: 0,
  maxFailures: isCi ? 1 : undefined,
  workers: isCi ? 1 : undefined,
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  reporter: [
    ['line'],
    ['junit', { outputFile: process.env.PLAYWRIGHT_JUNIT_OUTPUT_NAME ?? './test-results/playwright/junit.xml' }],
    ['html', { outputFolder: './playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? defaultBaseUrl,
    channel: process.env.E2E_BROWSER_CHANNEL === 'chrome' ? 'chrome' : undefined,
    actionTimeout: 5_000,
    navigationTimeout: 15_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    timezoneId: 'Europe/Minsk',
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
})
