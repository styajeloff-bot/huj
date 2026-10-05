import { createPublicStorefrontApi } from '~/features/storefront/api/storefrontApi'
import { replaceStorefrontSlug } from '~/features/storefront/publicRoute'
import { isReservedRouteSlug, resolveStorefrontRootRedirect } from '~/features/storefront/routeManifest'
import { resolveConfiguredHomeRedirect } from '~/features/storefront/publicUi'
import { useStorefrontStore } from '~/features/storefront/store/storefront'

function storefrontNotFound(): ReturnType<typeof createError> {
  return createError({
    statusCode: 404,
    statusMessage: 'Витрина не найдена',
  })
}

function routeSlug(value: unknown): string | null {
  const rawValue = Array.isArray(value) ? value[0] : value
  return rawValue === undefined || rawValue === null || rawValue === ''
    ? null
    : String(rawValue)
}

export default defineNuxtRouteMiddleware(async (to, from) => {
  const storefront = useStorefrontStore()
  const rawSlug = to.params.storefrontSlug

  if (rawSlug === undefined) {
    const sourceSlug = routeSlug(from.params.storefrontSlug) ?? (
      storefront.is_resolved && !storefront.is_default ? storefront.slug : null
    )
    const redirectTarget = resolveStorefrontRootRedirect(
      sourceSlug,
      to.path,
      to.fullPath,
    )
    if (redirectTarget) return navigateTo(redirectTarget, { replace: true })
  }

  const api = createPublicStorefrontApi(useRuntimeConfig())

  const configuredHomeRedirect = () => resolveConfiguredHomeRedirect(
    storefront.slug,
    storefront.public_ui.home_page_key,
    to.path,
    to.fullPath,
  )

  if (rawSlug === undefined) {
    if (storefront.is_default && storefront.is_resolved && storefront.id) {
      const redirectTarget = configuredHomeRedirect()
      return redirectTarget ? navigateTo(redirectTarget, { replace: true }) : undefined
    }
    try {
      const resolved = await api.resolve(null)
      if (!resolved.is_default || resolved.slug !== null || !resolved.is_active) {
        throw new Error('Invalid default storefront context')
      }
      storefront.resolve(resolved)
      const redirectTarget = configuredHomeRedirect()
      return redirectTarget ? navigateTo(redirectTarget, { replace: true }) : undefined
    } catch {
      throw createError({
        statusCode: 503,
        statusMessage: 'Сайт временно недоступен',
      })
    }
  }

  const requestedSlug = Array.isArray(rawSlug) ? rawSlug[0] : String(rawSlug)
  if (!requestedSlug) throw storefrontNotFound()
  if (storefront.slug === requestedSlug && storefront.is_resolved && storefront.is_active) {
    const redirectTarget = configuredHomeRedirect()
    return redirectTarget ? navigateTo(redirectTarget, { replace: true }) : undefined
  }

  try {
    const resolved = await api.resolve(requestedSlug)
    if (!resolved.is_active || resolved.is_default || !resolved.slug) {
      throw storefrontNotFound()
    }
    if (resolved.slug !== requestedSlug) {
      return navigateTo(replaceStorefrontSlug(to.fullPath, resolved.slug), {
        redirectCode: 301,
      })
    }
    storefront.resolve(resolved)
    const redirectTarget = configuredHomeRedirect()
    if (redirectTarget) return navigateTo(redirectTarget, { replace: true })
  } catch (error: unknown) {
    const status = (error as { status?: number; statusCode?: number }).status
      ?? (error as { status?: number; statusCode?: number }).statusCode
    if (status === 404) {
      if (to.name === 'index-storefront' && requestedSlug && !isReservedRouteSlug(requestedSlug)) {
        try {
          const resolved = await api.resolve(null)
          if (resolved.is_default && resolved.slug === null && resolved.is_active) {
            storefront.resolve(resolved)
            return navigateTo(
              {
                name: 'default-custom-page',
                params: { pageSlug: requestedSlug },
              },
              { replace: true },
            )
          }
        } catch {
          // fall through to storefrontNotFound()
        }
      }
      throw storefrontNotFound()
    }
    throw createError({
      statusCode: 503,
      statusMessage: 'Витрина временно недоступна',
    })
  }
})
