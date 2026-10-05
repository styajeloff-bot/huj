import { onBeforeUnmount, onMounted, onUpdated, ref, shallowRef, type Ref } from 'vue'
import { STOREFRONT_COLOR_REGISTRY, storefrontTokenVariables } from '../colorRegistry'
import { isStorefrontHexColor, normalizeStorefrontHex } from '../color'

/** Preserve actual DOM ancestry across Teleport, not a guessed registry parent.
 * The inherited layer must wrap the destination's own data-storefront-block so
 * local choices (and nested form choices) retain normal CSS cascade priority. */
export function useStorefrontTeleportContext(origin: Ref<HTMLElement | null>) {
  const inheritedColors = shallowRef<Record<string, string>>({})
  const teleportReady = ref(false)
  const observers: MutationObserver[] = []

  const refresh = () => {
    const next: Record<string, string> = {}
    const source = origin.value
    if (source?.closest('.storefront-theme')) {
      const inherited = getComputedStyle(source)
      const destination = getComputedStyle(document.body)
      for (const token of Object.keys(STOREFRONT_COLOR_REGISTRY.tokens)) {
        const value = inherited.getPropertyValue(`--storefront-${token}`).trim()
        // Only finite, validated color properties cross the boundary. Other
        // styles, markup, fonts and arbitrary CSS are never copied.
        if (!isStorefrontHexColor(value) || value === destination.getPropertyValue(`--storefront-${token}`).trim()) continue
        Object.assign(next, storefrontTokenVariables(token, normalizeStorefrontHex(value)))
      }
    }
    if (JSON.stringify(next) !== JSON.stringify(inheritedColors.value)) inheritedColors.value = next
  }

  onMounted(() => {
    refresh()
    // Before this point SSR and hydration keep the content at its real origin,
    // where native CSS inheritance is already correct and needs no snapshot.
    teleportReady.value = true
    const observe = (target: Node, options: MutationObserverInit) => {
      const observer = new MutationObserver(refresh)
      observer.observe(target, options)
      observers.push(observer)
    }
    for (let ancestor = origin.value?.parentElement; ancestor; ancestor = ancestor.parentElement) {
      observe(ancestor, { attributes: true, attributeFilter: ['class', 'style', 'data-storefront-block'] })
    }
    observe(document.head, { childList: true, characterData: true, subtree: true })
  })
  onUpdated(refresh)
  onBeforeUnmount(() => observers.forEach(observer => observer.disconnect()))
  return { inheritedColors, teleportReady }
}
