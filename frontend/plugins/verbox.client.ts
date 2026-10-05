const VERBOX_METHOD = 'Verbox'
const VERBOX_SCRIPT_ID = 'supportScript'
const VERBOX_WIDGET_ID = '060914ac3490e8d4fee8e2620cfa7b52'

declare global {
  interface Window {
    supportAPIMethod?: string
    Verbox?: ((...args: unknown[]) => void) & { q?: unknown[][] }
  }
}

const injectVerboxScript = (useFallback = false) => {
  if (document.getElementById(VERBOX_SCRIPT_ID)) {
    return
  }

  window.supportAPIMethod = VERBOX_METHOD
  window.Verbox = window.Verbox || ((...args: unknown[]) => {
    window.Verbox!.q = window.Verbox!.q || []
    window.Verbox!.q.push(args)
  })

  const script = document.createElement('script')
  script.id = VERBOX_SCRIPT_ID
  script.async = true
  script.src = `${useFallback
    ? 'https://static.site-chat.me/support/support.int.js'
    : 'https://admin.verbox.ru/support/support.js'}?h=${VERBOX_WIDGET_ID}`

  if (!useFallback) {
    script.onerror = () => {
      script.remove()
      injectVerboxScript(true)
    }
  }

  ;(document.head || document.body).appendChild(script)
}

export default defineNuxtPlugin(() => {
  const config = useRuntimeConfig()
  const verboxEnabled = config.public.verboxEnabled

  if (verboxEnabled === false || String(verboxEnabled) === 'false') {
    return
  }

  injectVerboxScript()
})
