export const appUrl = (path: string): string => new URL(
  path,
  process.env.E2E_APP_BASE_URL ?? process.env.E2E_BASE_URL ?? 'http://127.0.0.1',
).toString()
