let bodyScrollLockCount = 0
let bodyOverflowBeforeFirstLock = ''

interface BackgroundState {
  inert: boolean
  ariaHidden: string | null
}

const modalRoots: HTMLElement[] = []
const backgroundStates = new Map<HTMLElement, BackgroundState>()

const rememberBackgroundState = (element: HTMLElement) => {
  if (!backgroundStates.has(element)) {
    backgroundStates.set(element, {
      inert: element.hasAttribute('inert'),
      ariaHidden: element.getAttribute('aria-hidden')
    })
  }
}

const restoreElement = (element: HTMLElement, state: BackgroundState) => {
  if (state.inert) element.setAttribute('inert', '')
  else element.removeAttribute('inert')
  if (state.ariaHidden === null) element.removeAttribute('aria-hidden')
  else element.setAttribute('aria-hidden', state.ariaHidden)
}

const applyModalIsolation = () => {
  const topModalRoot = modalRoots.at(-1)
  for (const child of document.body.children) {
    if (!(child instanceof HTMLElement)) continue
    rememberBackgroundState(child)
    if (child === topModalRoot) restoreElement(child, backgroundStates.get(child)!)
    else {
      child.setAttribute('inert', '')
      child.setAttribute('aria-hidden', 'true')
    }
  }
}

/** Keeps the foremost nested modal interactive and restores each layer safely. */
export const registerModalRoot = (root: HTMLElement): (() => void) => {
  if (!import.meta.client) return () => undefined
  modalRoots.push(root)
  applyModalIsolation()

  let released = false
  return () => {
    if (released) return
    released = true
    const index = modalRoots.lastIndexOf(root)
    if (index !== -1) modalRoots.splice(index, 1)
    if (modalRoots.length > 0) {
      applyModalIsolation()
      return
    }
    for (const [element, state] of backgroundStates) {
      if (element.isConnected) restoreElement(element, state)
    }
    backgroundStates.clear()
  }
}

export const acquireBodyScrollLock = (): (() => void) => {
  if (!import.meta.client) return () => undefined

  if (bodyScrollLockCount === 0) {
    bodyOverflowBeforeFirstLock = document.body.style.overflow
  }
  bodyScrollLockCount += 1
  document.body.style.overflow = 'hidden'

  let released = false
  return () => {
    if (released) return
    released = true
    bodyScrollLockCount = Math.max(0, bodyScrollLockCount - 1)
    if (bodyScrollLockCount === 0) {
      document.body.style.overflow = bodyOverflowBeforeFirstLock
      bodyOverflowBeforeFirstLock = ''
    }
  }
}
