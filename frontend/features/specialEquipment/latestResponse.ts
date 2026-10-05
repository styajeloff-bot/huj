export interface LatestResponse<T> {
  isLatest: boolean
  value: T
}

export const createLatestResponseGuard = () => {
  let generation = 0

  return {
    run: async <T>(request: () => Promise<T>): Promise<LatestResponse<T>> => {
      const requestGeneration = ++generation
      const value = await request()
      return { isLatest: requestGeneration === generation, value }
    },
  }
}
