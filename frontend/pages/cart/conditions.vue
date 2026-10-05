<template>
  <div data-storefront-block="client.cart" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-4 sm:py-6 md:py-8">
    <div class="max-w-5xl mx-auto px-3 sm:px-6 lg:px-8">
      <nav class="flex mb-4 sm:mb-8 overflow-x-auto" aria-label="Breadcrumb">
        <ol class="flex items-center space-x-2 sm:space-x-4 text-xs sm:text-sm whitespace-nowrap">
          <li>
            <NuxtLink :to="publicRoute('/')" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#6b7280)]">{{ pageTitle('home') }}</NuxtLink>
          </li>
          <li class="text-[color:var(--storefront-text,#d1d5db)]">/</li>
          <li><NuxtLink :to="backLocation" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#6b7280)]">{{ backLabel }}</NuxtLink></li>
          <li class="text-[color:var(--storefront-text,#d1d5db)]">/</li>
          <li class="text-[color:var(--storefront-text-muted,#6b7280)]">Оформление заявки</li>
        </ol>
      </nav>

      <div class="mb-6 md:mb-8">
        <h1 class="text-xl sm:text-2xl md:text-3xl font-bold text-[color:var(--storefront-title,#111827)]">
          Оформление заявки на лизинг
        </h1>
        <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Проверьте условия и выберите компанию для создания заявки
        </p>
      </div>

      <div v-if="bootLoading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-10 w-10 border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
      </div>

      <div v-else class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-sm p-4 sm:p-6 md:p-8">
        <div v-if="error" class="mb-6 p-4 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#f87171)] text-[color:var(--storefront-error-text,#b91c1c)] rounded">
          {{ error }}
        </div>

        <CheckoutConditions
          ref="conditionsRef"
          :vehicles="checkoutStore.vehicles"
          :commerce-items="checkoutStore.commerceItems"
          :show-item-details="false"
          :show-leasing-conditions="true"
          :leasing-conditions="leasingConditions"
          :show-company-error="showCompanyError"
          @company-selected="handleCompanySelected"
        />

        <fieldset v-if="needsManualCommerceConditions" class="mt-6 rounded-lg bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4">
          <legend class="text-sm font-semibold text-[color:var(--storefront-text,#172554)]">Запрашиваемые условия</legend>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <label>
              <span class="block text-sm font-medium text-[color:var(--storefront-text,#172554)]">Первоначальный взнос, %</span>
              <input
                v-model.trim="commerceDownPaymentPercent"
                type="text"
                inputmode="decimal"
                autocomplete="off"
                class="storefront-control mt-2 min-h-11 w-full rounded-md border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
                :aria-invalid="commercePercentError ? 'true' : undefined"
              >
              <span v-if="commercePercentError" class="mt-1 block text-sm text-[color:var(--storefront-error-text,#b91c1c)]">{{ commercePercentError }}</span>
            </label>
            <label>
              <span class="block text-sm font-medium text-[color:var(--storefront-text,#172554)]">Срок, месяцев</span>
              <input
                v-model.number="commerceLeaseTermMonths"
                type="number"
                inputmode="numeric"
                min="12"
                max="84"
                step="6"
                class="storefront-control mt-2 min-h-11 w-full rounded-md border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
              >
            </label>
          </div>
        </fieldset>

        <CheckoutCompanyData
          v-if="checkoutStore.selectedCompanyId"
          :key="checkoutStore.selectedCompanyId"
          class="mt-6"
          :company-id="checkoutStore.selectedCompanyId"
        />

        <div class="mt-6 sm:mt-8 flex flex-col-reverse sm:flex-row justify-between gap-3">
          <NuxtLink
            :to="backLocation"
            class="btn-secondary text-center sm:text-left"
          >
            Назад
          </NuxtLink>

          <button
            type="button"
            :disabled="saving"
            class="btn-primary w-full sm:w-auto justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            @click="onCreateApplication"
          >
            <span v-if="saving" class="flex items-center justify-center gap-2">
              <span class="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-primary-border,#ffffff)]" />
              <span>Сохранение…</span>
            </span>
            <span v-else>Далее</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import CheckoutCompanyData from '~/features/checkout/components/CheckoutCompanyData.vue'
import CheckoutConditions from '~/features/checkout/components/CheckoutConditions.vue'
import { useDraftApplication } from '~/features/checkout/composables/useDraftApplication'
import { useAuthStore } from '~/features/auth/store/auth'
import { buildApplicationCalculationPayload } from '~/features/checkout/utils/applicationCalculation'
import { commerceAdapterFor, isCommerceItemType } from '~/features/commerce/adapters/commerceAdapters'
import { createCommerceApi } from '~/features/commerce/api/commerceApi'
import { commerceLeasingApplicationItems } from '~/features/commerce/leasingProjection'
import { commerceFailureMessage } from '~/features/commerce/composables/commerceErrors'
import { normalizeMoney } from '~/features/commerce/money'
import type { CommerceCheckoutLine, CommerceItemRef, CommerceItemType } from '~/features/commerce/types'
import { createPurchasesApi } from '~/features/purchases/api/purchasesApi'
import { createCarsApi } from '~/features/cars/api/carsApi'
import { createSpecialEquipmentCartApi } from '~/features/specialEquipment/api/specialEquipmentCartApi'
import { useSpecialEquipmentCommerceShellStore } from '~/features/specialEquipment/store/commerceShell'
import { isUuid, type UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'

definePageMeta({ middleware: ['auth'] })

const route = useRoute()
const router = useRouter()
const config = useRuntimeConfig()
const { apiPath, pageTitle, publicRoute, slug } = useStorefront()
const purchasesApi = createPurchasesApi(config)
const carsApi = createCarsApi(config, apiPath)
const commerceApi = createCommerceApi(config, apiPath)
const specialEquipmentCartApi = createSpecialEquipmentCartApi(config, apiPath)
const toast = useToast()
const authStore = useAuthStore()
const cartStore = useCartStore()
const checkoutStore = useCheckoutStore()
const specialEquipmentCartStore = useSpecialEquipmentCommerceShellStore()
const { createApplication, loadApplication, updateConditions, updateCompany, updateVehicles } = useDraftApplication()

const bootLoading = ref(true)
const saving = ref(false)
const error = ref('')
const showCompanyError = ref(false)
const conditionsRef = ref<InstanceType<typeof CheckoutConditions> | null>(null)
const commerceDownPaymentPercent = ref('10')
const commerceLeaseTermMonths = ref(36)

const routeItemType = computed<CommerceItemType | null>(() => {
  const value = Array.isArray(route.query.item_type) ? route.query.item_type[0] : route.query.item_type
  return isCommerceItemType(value) ? value : null
})
const routeItemId = computed<UUID | null>(() => {
  const value = Array.isArray(route.query.item_id) ? route.query.item_id[0] : route.query.item_id
  return typeof value === 'string' && isUuid(value) ? value : null
})
const routeItemRef = computed<CommerceItemRef | null>(() => routeItemType.value && routeItemId.value
  ? { type: routeItemType.value, id: routeItemId.value }
  : null)
const isDirectCommerceFlow = computed(() => routeItemRef.value !== null)
const isCommerceFlow = computed(() => isDirectCommerceFlow.value || checkoutStore.commerceItems.length > 0)
const needsManualCommerceConditions = computed(() => isCommerceFlow.value && !checkoutStore.calculation)
const isSingleCarMode = computed(() => isDirectCommerceFlow.value || checkoutStore.isSingleCarMode)
const normalizedCommerceDownPaymentPercent = computed(() => normalizeMoney(commerceDownPaymentPercent.value))
const commercePercentError = computed(() => {
  const normalized = normalizedCommerceDownPaymentPercent.value
  const percent = normalized === null ? Number.NaN : Number(normalized)
  return Number.isFinite(percent) && percent >= 0 && percent <= 49
    ? ''
    : 'Введите значение от 0 до 49.'
})
const backLocation = computed(() => {
  const item = checkoutStore.commerceItems[0]?.item
  if (isDirectCommerceFlow.value && item) {
    const location = commerceAdapterFor(item.ref.type).detailLocation(item)
    if (typeof location === 'string') return publicRoute(location)
    return location ?? publicRoute('/cart')
  }
  return publicRoute(isSingleCarMode.value ? '/special-equipment' : '/cart')
})
const backLabel = computed(() => isDirectCommerceFlow.value
  ? commerceAdapterFor(routeItemType.value as CommerceItemType).catalogLabel
  : (isCommerceFlow.value ? 'Корзина' : (isSingleCarMode.value ? pageTitle('special_equipment_catalog') : 'Корзина')))

const leasingConditions = computed(() => {
  if (!checkoutStore.calculation) return null
  return {
    monthlyPayment: checkoutStore.calculation.calculation?.monthlyPayment,
    rate: checkoutStore.calculation.calculation?.rate,
    leaseTermMonths: checkoutStore.calculation.lease_term_months,
    downPaymentPercent: checkoutStore.calculation.down_payment_percent,
    downPayment: checkoutStore.calculation.down_payment,
    totalAmount: checkoutStore.calculation.total_amount,
    totalCost: checkoutStore.calculation.calculation?.totalCost,
    totalInterest: checkoutStore.calculation.calculation?.totalInterest,
    buyoutAmount:
      checkoutStore.calculation.buyout_amount ||
      checkoutStore.calculation.calculation?.buyoutAmount,
  }
})

const handleCompanySelected = (companyId: UUID | null) => {
  checkoutStore.setSelectedCompanyId(companyId)
  showCompanyError.value = false
}

const createBlockedMessage = 'Создание заявок ограничено администратором компании. Если вас не устраивает такое положение, напишите в поддержку.'
const canCreateCurrentApplication = computed(() =>
  authStore.user?.role === 'dealer' || authStore.canCreateApplications,
)

const synchronizeCartStateAfterDraftCreation = async (): Promise<void> => {
  const [vehicleCart, specialEquipmentCart] = await Promise.allSettled([
    cartStore.fetchCart(),
    specialEquipmentCartStore.loadCart({ force: true, resolveGuestProducts: true }),
  ])
  const vehicleCartLoaded = vehicleCart.status === 'fulfilled' && vehicleCart.value.success
  const specialEquipmentCartLoaded = specialEquipmentCart.status === 'fulfilled' && specialEquipmentCart.value
  if (!vehicleCartLoaded || !specialEquipmentCartLoaded) {
    console.warn('Не удалось обновить корзину после создания заявки', {
      vehicleCart,
      specialEquipmentCart,
    })
    toast.warning('Корзина не обновилась. Обновите страницу.', {
      persistent: true,
      actionText: 'Обновить страницу',
      actionCallback: () => window.location.reload(),
    })
  }
}

const onCreateApplication = async () => {
  error.value = ''

  if (!checkoutStore.selectedCompanyId && !checkoutStore.selectedApplicationCompany) {
    showCompanyError.value = true
    error.value = authStore.user?.role === 'dealer'
      ? 'Выберите компанию клиента из списка'
      : 'Выберите компанию'
    return
  }
  if (!canCreateCurrentApplication.value) {
    error.value = createBlockedMessage
    toast.error(error.value)
    return
  }
  const vehicleCheck = conditionsRef.value?.validateVehicleLeasingFields?.() ?? { canProceed: true, messages: [] }
  if (!vehicleCheck.canProceed) {
    error.value = vehicleCheck.messages.join(', ')
    toast.error(error.value)
    return
  }
  if (needsManualCommerceConditions.value && commercePercentError.value) {
    error.value = commercePercentError.value
    return
  }
  if (needsManualCommerceConditions.value && (commerceLeaseTermMonths.value < 12 || commerceLeaseTermMonths.value > 84)) {
    error.value = 'Срок лизинга должен быть от 12 до 84 месяцев.'
    return
  }

  saving.value = true
  try {
    if (isCommerceFlow.value) {
      const lines = checkoutStore.commerceItems
      const companyId = checkoutStore.selectedCompanyId
      const company = checkoutStore.selectedApplicationCompany
      if (lines.length === 0 || (!companyId && !company)) {
        throw new Error('Не удалось определить технику или компанию для заявки.')
      }
      const downPaymentPercent = checkoutStore.calculation
        ? String(checkoutStore.calculation.down_payment_percent)
        : normalizedCommerceDownPaymentPercent.value
      if (!downPaymentPercent) {
        throw new Error('Введите корректный размер первоначального взноса.')
      }
      const leaseTermMonths = checkoutStore.calculation?.lease_term_months
        ?? commerceLeaseTermMonths.value
      const calculationPayload = buildApplicationCalculationPayload(
        checkoutStore.calculation,
      )
      const specialEquipmentLines = lines.filter(
        line => line.item.ref.type === 'special_equipment',
      )
      if (specialEquipmentLines.length === lines.length) {
        if (!companyId) {
          throw new Error('Для оформления спецтехники выберите сохранённую компанию.')
        }
        const cartItemIds = [...new Set(specialEquipmentLines.flatMap(
          line => line.cart_item_ids ?? [],
        ))]
        if (cartItemIds.length !== specialEquipmentLines.length) {
          throw new Error('Корзина изменилась. Вернитесь в корзину и повторите оформление.')
        }
        const result = await specialEquipmentCartApi.createLeasingApplication({
          source_type: slug.value ? 'dealer_site' : 'platform',
          company_id: companyId,
          cart_item_ids: cartItemIds,
          leasing_purpose: null,
          down_payment_percent: downPaymentPercent,
          lease_term_months: leaseTermMonths,
        })
        await synchronizeCartStateAfterDraftCreation()
        checkoutStore.setApplicationId(result.application_id)
        checkoutStore.resetQuestionnaireData()
        checkoutStore.setCommerceItems([])
        checkoutStore.setCalculation(null)
        await router.push(publicRoute(`/application/${result.application_id}?step=items`))
        return
      }
      const result = await commerceApi.createLeasingApplication({
        source_type: slug.value ? 'dealer_site' : 'platform',
        items: commerceLeasingApplicationItems(lines),
        ...(companyId ? { company_id: companyId } : {}),
        ...(company ? { company } : {}),
        name: authStore.user?.name || undefined,
        email: authStore.user?.email || undefined,
        down_payment_percent: downPaymentPercent,
        lease_term_months: leaseTermMonths,
        ...(calculationPayload ? { calculation: calculationPayload } : {}),
      })
      await synchronizeCartStateAfterDraftCreation()
      checkoutStore.setApplicationId(result.application_id)
      checkoutStore.resetQuestionnaireData()
      checkoutStore.setCommerceItems([])
      checkoutStore.setCalculation(null)
      await router.push(publicRoute(`/application/${result.application_id}?step=items`))
      return
    }

    const selectedCompanyIdBeforeCreate = checkoutStore.selectedCompanyId
    const selectedApplicationCompanyBeforeCreate = checkoutStore.selectedApplicationCompany
    const draft = await createApplication()
    const appId = draft.application_id
    await synchronizeCartStateAfterDraftCreation()
    checkoutStore.setApplicationId(appId)

    const isDealerFlow = authStore.user?.role === 'dealer'
    if (!isDealerFlow && selectedCompanyIdBeforeCreate) {
      await updateCompany(appId, selectedCompanyIdBeforeCreate)
    }
    const createdApplication = await loadApplication(appId)
    const clientCompanyId = createdApplication.company_id as UUID | undefined | null

    if (!selectedCompanyIdBeforeCreate && clientCompanyId) {
      checkoutStore.setSelectedCompanyId(clientCompanyId)
    }
    if (selectedApplicationCompanyBeforeCreate) {
      checkoutStore.setSelectedApplicationCompany(selectedApplicationCompanyBeforeCreate)
    } else if (!selectedCompanyIdBeforeCreate && createdApplication.company && typeof createdApplication.company === 'object') {
      checkoutStore.setSelectedApplicationCompany(createdApplication.company as any)
    }
    checkoutStore.resetQuestionnaireData()

    await updateVehicles(appId)
    await updateConditions(appId)
    router.push(publicRoute(`/application/${appId}?step=items`))
  } catch (err: unknown) {
    error.value = commerceFailureMessage(err, 'Не удалось создать заявку')
    toast.error(error.value)
  } finally {
    saving.value = false
  }
}

// Pinia applies the SSR state after the store's initial storage read.
// Restore before entry checks or company selection can persist that empty state.
onBeforeMount(() => {
  checkoutStore.loadState()
})

onMounted(async () => {
  try {
    const vehicleId = route.query.vehicleId
    const fromPurchaseId = Array.isArray(route.query.fromPurchase)
      ? route.query.fromPurchase[0]
      : route.query.fromPurchase
    const applicationIdQuery = route.query.applicationId

    // Resume flow: already created application — go to checkout
    if (applicationIdQuery) {
      router.push(publicRoute(`/application/${applicationIdQuery}`))
      return
    }

    if (route.query.item_type !== undefined || route.query.item_id !== undefined) {
      const itemRef = routeItemRef.value
      checkoutStore.setCommerceItems([])
      checkoutStore.setCalculation(null)
      if (!itemRef) {
        error.value = 'Ссылка оформления содержит некорректный тип или идентификатор техники.'
        return
      }
      try {
        const response = await commerceApi.getItem(itemRef)
        const line: CommerceCheckoutLine = {
          item: response.item,
          quantity: 1,
          custom_price: null,
          comment: '',
          equipments: [],
          services: [],
          leasing_purpose: null,
          leasing_purpose_comment: null,
          regions: [],
        }
        checkoutStore.setVehicles([])
        checkoutStore.setCommerceItems([line])
      } catch (requestError: unknown) {
        error.value = commerceFailureMessage(requestError, 'Не удалось загрузить выбранную технику.')
      }
      return
    }

    if (fromPurchaseId) {
      checkoutStore.setCommerceItems([])
      checkoutStore.setCalculation(null)
      const purchaseOrderId: UUID = fromPurchaseId
      const response = await purchasesApi.getOrderDetails(purchaseOrderId)
      const order = response.order
      checkoutStore.sourcePurchaseOrderId = purchaseOrderId
      checkoutStore.setVehicles([
        {
          vehicle_id: order.vehicle_id,
          mark_name: (order.mark_name as string) || '',
          model_name: (order.model_name as string) || '',
          base_price: parseFloat(String(order.total_price)),
          vin: order.vin as string | undefined,
          color: order.color as string | undefined,
          year: order.vehicle_year as number | undefined,
          images: order.images as string[] | undefined,
          quantity: 1,
        },
      ])
    } else if (vehicleId) {
      checkoutStore.setCommerceItems([])
      checkoutStore.setCalculation(null)
      const response = await carsApi.getCarById(String(vehicleId))
      checkoutStore.setVehicles([response as any])
    } else if (checkoutStore.commerceItems.length > 0) {
      checkoutStore.setVehicles([])
      return
    } else {
      checkoutStore.setCommerceItems([])
      if (cartStore.selectedItems.length === 0 && checkoutStore.vehicles.length === 0) {
        toast.error('Нет выбранных транспортных средств для оформления заявки')
        router.push(publicRoute('/cart'))
        return
      }
      if (cartStore.selectedItems.length > 0) {
        checkoutStore.setVehicles(
          cartStore.selectedItems as unknown as Array<{
            mark_name: string
            model_name: string
            [k: string]: unknown
          }>,
        )
      }
    }
  } finally {
    bootLoading.value = false
  }
})

useSeoMeta({
  title: 'Оформление заявки — CarCraft Multileasing',
  description: 'Оформление единой заявки на лизинг транспортных средств',
})
</script>

<style scoped>
.btn-primary {
  @apply bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)] px-4 py-2 rounded-md hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2;
}

.btn-secondary {
  @apply bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)] px-4 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2;
}
</style>
