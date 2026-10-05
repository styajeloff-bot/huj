export type LatestCalculationRequestResult<T> =
  | { status: 'success'; value: T }
  | { status: 'error'; error: unknown }
  | { status: 'stale' }

export const createLatestCalculationRequest = () => {
  let sequence = 0

  const run = async <T>(request: () => Promise<T>): Promise<LatestCalculationRequestResult<T>> => {
    const token = ++sequence
    try {
      const value = await request()
      return token === sequence
        ? { status: 'success', value }
        : { status: 'stale' }
    } catch (error: unknown) {
      return token === sequence
        ? { status: 'error', error }
        : { status: 'stale' }
    }
  }

  const invalidate = () => {
    sequence += 1
  }

  return {
    invalidate,
    run,
  }
}
