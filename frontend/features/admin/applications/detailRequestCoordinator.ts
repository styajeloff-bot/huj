export interface LatestRequestHandlers<T> {
  onSuccess: (value: T) => void
  onError: (error: unknown) => void
  onSettled: () => void
}

export const createDetailRequestCoordinator = () => {
  let sequence = 0
  const activeTokens = new Map<string, number>()

  // nosemgrep: eslint.detect-possible-timing-attacks, nodejs_scan.javascript-crypto-rule-node_timing_attack -- Internal request sequence token, not a secret.
  const isCurrent = (key: string, token: number) => activeTokens.get(key) === token

  const run = async <T>(
    key: string,
    request: () => Promise<T>,
    handlers: LatestRequestHandlers<T>,
  ): Promise<void> => {
    const token = ++sequence
    activeTokens.set(key, token)

    let value: T
    try {
      value = await request()
    } catch (error: unknown) {
      if (isCurrent(key, token)) handlers.onError(error)
      if (isCurrent(key, token)) handlers.onSettled()
      return
    }

    if (isCurrent(key, token)) handlers.onSuccess(value)
    if (isCurrent(key, token)) handlers.onSettled()
  }

  const invalidate = (key: string) => {
    activeTokens.set(key, ++sequence)
  }

  return {
    invalidate,
    run,
  }
}
