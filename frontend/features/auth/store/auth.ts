export interface AvailableCompany {
  id: string
  name: string
  inn?: string | null
  role: string
  position_id?: string | null
  positionId?: string | null
  position_name?: string | null
  positionName?: string | null
  is_active?: boolean
  isActive?: boolean
}

export interface AuthUser {
  id?: string
  role?: string
  company_id?: string | null
  company_name?: string
  name?: string
  email?: string
  scopes?: string[]
  mfa_enabled?: boolean
  sub_role?: string | null
  can_view_applications?: boolean
  can_create_applications?: boolean
  can_create_employees?: boolean
  canViewApplications?: boolean
  canCreateApplications?: boolean
  canCreateEmployees?: boolean
  active_role?: string | null
  activeRole?: string | null
  active_company_id?: string | null
  activeCompanyId?: string | null
  active_company_name?: string | null
  activeCompanyName?: string | null
  position_id?: string | null
  positionId?: string | null
  position_name?: string | null
  positionName?: string | null
  available_companies?: AvailableCompany[]
  availableCompanies?: AvailableCompany[]
  section_access?: Record<string, boolean> | null
  sectionAccess?: Record<string, boolean> | null
  [key: string]: unknown
}

/**
 * MFA / setup pending context.
 *
 * When the backend rejects primary auth with `mfaRequired` or `mfaSetupRequired`,
 * we stash the short-lived token here so the dedicated pages can pick it up
 * without stuffing it into URL query strings (safer — never hits the browser
 * history or server logs).
 */
interface MfaPending {
  mfaToken?: string
  setupToken?: string
  phone?: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const mfaPending = ref<MfaPending>({})
  const isAuthenticated = computed(() => !!user.value)
  const effectiveRole = computed(() => {
    if (user.value?.role === 'carcraft_employee') return 'carcraft_employee'
    return user.value?.active_role || user.value?.activeRole || user.value?.role || null
  })
  const userRole = computed(() => effectiveRole.value)
  const activeRole = computed(() => user.value?.active_role || user.value?.activeRole || null)
  const userCompany = computed(
    () => user.value?.active_company_name || user.value?.activeCompanyName || user.value?.company_name || null,
  )
  const activeCompanyId = computed(
    () => user.value?.active_company_id || user.value?.activeCompanyId || user.value?.company_id || null,
  )
  const userScopes = computed<string[]>(() => user.value?.scopes || [])
  const config = useRuntimeConfig()

  // Role-based permissions
  const isCarCraftEmployee = computed(() => user.value?.role === 'carcraft_employee')
  const isDealer = computed(() => effectiveRole.value === 'dealer')
  const isClient = computed(() => effectiveRole.value === 'client')
  const isLeasingCompany = computed(() => effectiveRole.value === 'leasing_company')
  const isDistributor = computed(() => effectiveRole.value === 'distributor')

  // Business roles get the fullscreen /workspace admin area; clients use /cabinet.
  const isBusinessRole = computed(() =>
    isDealer.value || isLeasingCompany.value || isDistributor.value || isCarCraftEmployee.value
  )
  /** Where a logged-in user's "home" / personal-area link should point. */
  const homeRoute = computed(() => (isBusinessRole.value ? '/workspace' : '/cabinet'))

  // Sub-role awareness
  const subRole = computed(() => user.value?.sub_role || null)
  const isCompanyAdmin = computed(() => subRole.value === 'administrator')
  const isCompanyManager = computed(() => subRole.value === 'manager')
  const isCompanyEmployee = computed(() => subRole.value === 'employee')
  const activeCanViewApplications = computed(() =>
    user.value?.can_view_applications ?? user.value?.canViewApplications,
  )
  const activeCanCreateApplications = computed(() =>
    user.value?.can_create_applications ?? user.value?.canCreateApplications,
  )
  const sectionAccess = computed<Record<string, boolean> | null>(() => {
    const raw = user.value?.section_access ?? user.value?.sectionAccess
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      return raw as Record<string, boolean>
    }
    return null
  })
  const canViewApplications = computed(() => {
    if (!isCarCraftEmployee.value && sectionAccess.value && sectionAccess.value.applications === false) return false
    if (isCarCraftEmployee.value || isDistributor.value) return true
    if (isCompanyAdmin.value || isCompanyManager.value) return true
    if (isCompanyEmployee.value) return activeCanViewApplications.value === true
    return activeCanViewApplications.value ?? true
  })
  const canCreateApplications = computed(() => {
    if (isCarCraftEmployee.value || isDistributor.value || isLeasingCompany.value || isDealer.value) return true
    if (isCompanyAdmin.value || isCompanyManager.value) return true
    if (isCompanyEmployee.value) return activeCanCreateApplications.value === true
    if (isClient.value) {
      return activeCanCreateApplications.value ?? true
    }
    return false
  })

  const canCreateEmployees = computed(() => {
    if (isCarCraftEmployee.value) return true
    if (user.value?.sub_role === 'administrator') return true
    return Boolean(user.value?.can_create_employees ?? user.value?.canCreateEmployees ?? false)
  })

  const canManageUsers = computed(() => isCarCraftEmployee.value)
  const canManageStock = computed(() => isCarCraftEmployee.value)
  const canManageVehicles = computed(() => isCarCraftEmployee.value)
  const canReviewApplications = computed(() =>
    isLeasingCompany.value || isCarCraftEmployee.value
  )

  /** True when the user JWT carries an auth:admin scope (or is a carcraft_employee as fallback). */
  const hasAdminScope = computed(() => {
    const scopes = userScopes.value
    if (scopes.includes('auth:admin')) return true
    // Fallback for backends not yet emitting scopes — keep the role gate working.
    return isCarCraftEmployee.value
  })

  const hasScope = (scope: string): boolean => userScopes.value.includes(scope)

  const setMfaPending = (payload: MfaPending) => {
    mfaPending.value = { ...mfaPending.value, ...payload }
  }

  const consumeMfaToken = (): string | null => {
    const token = mfaPending.value.mfaToken ?? null
    mfaPending.value = { ...mfaPending.value, mfaToken: undefined }
    return token
  }

  const consumeSetupToken = (): string | null => {
    const token = mfaPending.value.setupToken ?? null
    mfaPending.value = { ...mfaPending.value, setupToken: undefined }
    return token
  }

  const clearMfaPending = () => {
    mfaPending.value = {}
  }

  const login = async (credentials: { phone: string }, options: { redirectAfterLogin?: boolean } = {}) => {
    try {
      const data: any = await $fetch('/api/v1/auth/login', {
        method: 'POST',
        body: credentials,
        baseURL: config.public.apiBase,
        credentials: 'include'
      })

      if (data.mfaRequired && data.mfaToken) {
        setMfaPending({ mfaToken: data.mfaToken, phone: data.phone })
        return {
          success: false,
          mfaRequired: true,
          mfaToken: data.mfaToken,
          phone: data.phone
        }
      }

      if (data.mfaSetupRequired && data.setupToken) {
        setMfaPending({ setupToken: data.setupToken, phone: data.phone })
        return {
          success: false,
          mfaSetupRequired: true,
          setupToken: data.setupToken,
          phone: data.phone
        }
      }

      if (data.requiresVerification) {
        return {
          success: false,
          requiresVerification: true,
          phone: data.phone,
          message: data.message,
          codeAlreadySent: data.codeAlreadySent
        }
      }

      if (data.user) {
        user.value = data.user
      }

      if (process.client && options.redirectAfterLogin !== false) {
        const redirectUrl = sessionStorage.getItem('redirectAfterLogin')
        if (redirectUrl) {
          sessionStorage.removeItem('redirectAfterLogin')
          setTimeout(() => {
            navigateTo(redirectUrl)
          }, 100)
        }
      }

      return { success: true }
    } catch (error: any) {
      if (error.data?.requiresVerification) {
        return {
          success: false,
          error: error.data.error,
          requiresVerification: true,
          phone: error.data.phone,
          message: error.data.message,
          codeAlreadySent: error.data.codeAlreadySent
        }
      }
      if (error.data?.requiresRegistration) {
        return {
          success: false,
          error: error.data.error,
          requiresRegistration: true,
          phone: error.data.phone,
          message: error.data.message,
          codeAlreadySent: error.data.codeAlreadySent
        }
      }
      return {
        success: false,
        error: error.data?.error || 'Ошибка авторизации'
      }
    }
  }

  const register = async (userData: {
    phone: string
    email?: string
    name?: string
    companies?: Array<{
      name: string
      inn: string
      kpp?: string | null
      ogrn?: string | null
      legal_address?: string | null
      actual_address?: string | null
      phone?: string | null
      email?: string | null
      manager_name?: string | null
      entity_type?: string | null
    }>
    code?: string
  }) => {
    try {
      const data: any = await $fetch('/api/v1/auth/register', {
        method: 'POST',
        body: userData,
        baseURL: config.public.apiBase,
        credentials: 'include'
      })

      if (data.requiresVerification) {
        return {
          success: false,
          requiresVerification: true,
          phone: data.phone,
          message: data.message
        }
      }

      user.value = data.user
      return { success: true }
    } catch (error: any) {
      const logger = useLogger()
      logger.error('Registration error', error)
      const detail = error.data?.detail || error.data?.error || ''
      const isAlreadyRegistered =
        error.statusCode === 409 ||
        error.status === 409 ||
        error.data?.code === 'USER_ALREADY_EXISTS_ERROR' ||
        (typeof detail === 'string' && (detail.includes('уже зарегистрирован') || detail.includes('уже существует')))
      return {
        success: false,
        isAlreadyRegistered: Boolean(isAlreadyRegistered),
        error: detail || 'Ошибка регистрации'
      }
    }
  }

  const verifyPhone = async (phone: string, code: string) => {
    try {
      const data: any = await $fetch('/api/v1/auth/verify-phone', {
        method: 'POST',
        body: { phone, code },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })

      if (data.mfaRequired && data.mfaToken) {
        setMfaPending({ mfaToken: data.mfaToken, phone })
        return {
          success: false,
          mfaRequired: true,
          mfaToken: data.mfaToken
        }
      }

      if (data.mfaSetupRequired && data.setupToken) {
        setMfaPending({ setupToken: data.setupToken, phone })
        return {
          success: false,
          mfaSetupRequired: true,
          setupToken: data.setupToken
        }
      }

      user.value = data.user
      return { success: true }
    } catch (error: any) {
      return {
        success: false,
        error: error.data?.error || 'Ошибка подтверждения телефона'
      }
    }
  }

  const resendCode = async (phone: string) => {
    try {
      await $fetch('/api/v1/auth/resend-code', {
        method: 'POST',
        body: { phone },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      return { success: true }
    } catch (error: any) {
      return {
        success: false,
        error: error.data?.error || 'Ошибка повторной отправки кода'
      }
    }
  }

  /**
   * Broadcasts a logout to sibling tabs. The plugin `plugins/logout-broadcast.client.ts`
   * wires a listener on the same channel that clears state and redirects.
   * Exposed separately from `logout()` so it can be called without triggering
   * the server round-trip (handy in the listener itself).
   */
  const broadcastLogout = () => {
    if (!process.client) return
    try {
      if (typeof BroadcastChannel !== 'undefined') {
        const channel = new BroadcastChannel('carcraft-auth')
        channel.postMessage({ type: 'logout', ts: Date.now() })
        channel.close()
      }
      // Safari fallback — `storage` event fires in OTHER tabs when a key changes.
      // Writing+removing flushes the event to siblings without polluting storage.
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem('carcraft-auth-logout', String(Date.now()))
        window.localStorage.removeItem('carcraft-auth-logout')
      }
    } catch {
      // Channel/storage unavailable — degrade silently.
    }
  }

  const logout = async () => {
    try {
      await $fetch('/api/v1/auth/logout', {
        method: 'POST',
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
    } catch (error) {
      const logger = useLogger()
      logger.error('Logout error', error)
    } finally {
      user.value = null
      clearMfaPending()
      if (process.client) {
        sessionStorage.removeItem('redirectAfterLogin')
      }
      broadcastLogout()
    }
  }

  /**
   * Local-only logout — used by the broadcast listener when a sibling tab
   * already performed the server-side logout. Skips the network call to
   * avoid redundant requests and potential 401 noise.
   */
  const logoutLocal = () => {
    user.value = null
    clearMfaPending()
    if (process.client) {
      sessionStorage.removeItem('redirectAfterLogin')
    }
  }

  const refreshToken = async () => {
    try {
      await $fetch('/api/v1/auth/refresh', {
        method: 'POST',
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      return true
    } catch (error) {
      user.value = null
      return false
    }
  }

  // Deduplicates concurrent checkAuth calls — only one in-flight request at a time
  let _checkAuthPromise: Promise<boolean> | null = null

  const checkAuth = async (forceRefresh = false) => {
    // Fast-path: user already loaded in this session — skip the network call
    if (!forceRefresh && user.value) return true

    // Deduplicate: if a check is already in flight, piggyback on it
    if (_checkAuthPromise) return _checkAuthPromise

    _checkAuthPromise = _doCheckAuth()
    try {
      return await _checkAuthPromise
    } finally {
      _checkAuthPromise = null
    }
  }

  const _doCheckAuth = async (): Promise<boolean> => {
    try {
      const response = await $fetch<{ user: AuthUser }>('/api/v1/auth/me', {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      user.value = response.user
      return true
    } catch (error: any) {
      if (error.status === 401) {
        const refreshed = await refreshToken()
        if (refreshed) {
          return await _doCheckAuth()
        }
      }
      user.value = null
      return false
    }
  }

  /** Called after successful MFA verify/complete-setup to hydrate the user. */
  const setUser = (next: AuthUser | null) => {
    user.value = next
  }

  // Computed projections stay readonly for consumers and, unlike readonly refs,
  // are not registered as setup-store state by Pinia. This keeps client-only
  // credentials out of the SSR payload and prevents hydration from assigning
  // serialized values back into readonly RefImpl instances.
  const exposedUser = computed(() => user.value)
  const exposedMfaPending = computed(() => mfaPending.value)

  return {
    user: exposedUser,
    mfaPending: exposedMfaPending,
    isAuthenticated,
    effectiveRole,
    activeRole,
    activeCompanyId,
    userRole,
    userCompany,
    userScopes,
    isCarCraftEmployee,
    isDealer,
    isClient,
    isLeasingCompany,
    isDistributor,
    isBusinessRole,
    homeRoute,
    subRole,
    isCompanyAdmin,
    isCompanyManager,
    isCompanyEmployee,
    canViewApplications,
    canCreateApplications,
    canCreateEmployees,
    sectionAccess,
    canManageUsers,
    canManageStock,
    canManageVehicles,
    canReviewApplications,
    hasAdminScope,
    hasScope,
    login,
    register,
    verifyPhone,
    resendCode,
    logout,
    logoutLocal,
    broadcastLogout,
    refreshToken,
    checkAuth,
    setUser,
    setMfaPending,
    consumeMfaToken,
    consumeSetupToken,
    clearMfaPending
  }
})
