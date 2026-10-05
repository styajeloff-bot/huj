type AnyFunction = (...args: any[]) => any
type DebouncedFunction<T extends AnyFunction> = ((...args: Parameters<T>) => void) & {
  cancel: () => void
}

export const useLodash = () => {
  const debounce = <T extends AnyFunction>(func: T, wait: number, immediate = false) => {
    let timeout: ReturnType<typeof setTimeout> | null = null
    const debounced = function (this: any, ...args: Parameters<T>) {
      const later = () => {
        timeout = null
        if (!immediate) func.apply(this, args)
      }
      const callNow = immediate && !timeout
      if (timeout) clearTimeout(timeout)
      timeout = setTimeout(later, wait)
      if (callNow) func.apply(this, args)
    } as DebouncedFunction<T>
    debounced.cancel = () => {
      if (timeout) clearTimeout(timeout)
      timeout = null
    }
    return debounced
  }

  const throttle = <T extends AnyFunction>(func: T, wait: number) => {
    let inThrottle = false
    return function (this: any, ...args: Parameters<T>) {
      if (!inThrottle) {
        func.apply(this, args)
        inThrottle = true
        setTimeout(() => (inThrottle = false), wait)
      }
    }
  }

  const cloneDeep = <T>(obj: T): T => {
    if (obj === null || typeof obj !== 'object') return obj
    if (obj instanceof Date) return new Date(obj.getTime()) as T
    if (Array.isArray(obj)) return obj.map((item) => cloneDeep(item)) as T
    const clonedObj: Record<string, unknown> = {}
    for (const key in obj) {
      if (Object.prototype.hasOwnProperty.call(obj, key)) {
        clonedObj[key] = cloneDeep((obj as Record<string, unknown>)[key])
      }
    }
    return clonedObj as T
  }

  const isEmpty = (value: unknown): boolean => {
    if (value == null) return true
    if (Array.isArray(value) || typeof value === 'string') return value.length === 0
    if (typeof value === 'object') return Object.keys(value).length === 0
    return false
  }

  const isEqual = (a: unknown, b: unknown): boolean => {
    if (a === b) return true
    if (a == null || b == null) return false
    if (typeof a !== typeof b) return false
    if (typeof a === 'object' && typeof b === 'object') {
      const keysA = Object.keys(a as object)
      const keysB = Object.keys(b as object)
      if (keysA.length !== keysB.length) return false
      for (const key of keysA) {
        if (
          !keysB.includes(key) ||
          !isEqual((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key])
        )
          return false
      }
      return true
    }
    return false
  }

  return { debounce, throttle, cloneDeep, isEmpty, isEqual }
}
