<template>
  <div data-storefront-block="client.application" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-8">
    <div class="mx-auto max-w-6xl px-6 lg:px-8">
      <nav class="mb-8 flex items-center gap-3 text-sm" aria-label="Breadcrumb">
        <NuxtLink :to="publicRoute('/')" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#4b5563)]">Главная</NuxtLink>
        <span class="text-[color:var(--storefront-text,#d1d5db)]">/</span>
        <NuxtLink :to="publicRoute('/cart')" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#4b5563)]">Корзина</NuxtLink>
        <span class="text-[color:var(--storefront-text,#d1d5db)]">/</span>
        <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Оформление заявки</span>
      </nav>

      <header class="mb-8">
        <h1 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)]">Оформление заявки на лизинг</h1>
        <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Проверьте условия и выберите компанию для создания заявки
        </p>
      </header>

      <div v-if="bootLoading" class="flex justify-center py-16">
        <div class="h-10 w-10 animate-spin rounded-full border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
      </div>

      <template v-else>
        <div v-if="pageError" class="mb-6 rounded-lg border border-[color:var(--storefront-error-border,#fca5a5)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-4 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
          {{ pageError }}
        </div>

        <section class="rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-6 shadow-sm">
          <label class="mb-2 block text-sm font-semibold text-[color:var(--storefront-label,#111827)]">
            Выберите компанию
          </label>
          <select
            :value="selectedCompanyId ?? ''"
            :disabled="companiesLoading || selectingCompany"
            class="storefront-control w-full rounded-lg border border-[color:var(--storefront-border,#d1d5db)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-3 text-sm text-[color:var(--storefront-text,#111827)] shadow-sm focus:border-[color:var(--storefront-border,#3b82f6)] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] disabled:cursor-wait disabled:bg-[color:rgb(var(--storefront-disabled-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
            @change="onCompanySelect"
          >
            <option value="">Выберите компанию</option>
            <option v-for="company in companies" :key="company.id" :value="company.id">
              {{ company.name }}{{ company.inn ? ` (ИНН: ${company.inn})` : '' }}
            </option>
          </select>
          <button
            type="button"
            class="storefront-action-ghost mt-3 text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
            @click="openAddCompanyModal"
          >
            + Добавить ещё компанию
          </button>
        </section>

        <section v-if="calculation" class="mt-6 rounded-xl border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-6">
          <h2 class="text-base font-semibold text-[color:var(--storefront-title,#172554)]">Запрашиваемые условия</h2>
          <dl class="mt-4 grid grid-cols-2 gap-x-8 gap-y-4 lg:grid-cols-4">
            <div>
              <dt class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">Ежемесячный платёж</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#172554)]">{{ formatPrice(monthlyPayment) }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">Ставка удорожания</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#172554)]">{{ rateLabel }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">Первоначальный взнос</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#172554)]">{{ downPaymentLabel }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">Срок</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#172554)]">{{ leaseTermLabel }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">Общая сумма выплат</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#172554)]">{{ formatPrice(totalCost) }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">Проценты</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#172554)]">{{ formatPrice(totalInterest) }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">Стоимость имущества</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#172554)]">{{ formatPrice(totalAmount) }}</dd>
            </div>
            <div>
              <dt class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">Выкупная стоимость</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#172554)]">{{ formatPrice(buyoutAmount) }}</dd>
            </div>
          </dl>
        </section>

        <section v-if="selectedCompanyId" class="mt-6 rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-6 shadow-sm">
          <h2 class="mb-5 text-xl font-semibold text-[color:var(--storefront-title,#111827)]">О компании</h2>
          <CheckoutCompanyData :key="selectedCompanyId" :company-id="selectedCompanyId" />
        </section>

        <div class="mt-8 flex items-center justify-between gap-4">
          <NuxtLink :to="publicRoute('/cart')" class="btn-secondary">Назад</NuxtLink>
          <button
            type="button"
            :disabled="!selectedCompanyId || addingCompany || selectingCompany || saving"
            class="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
            @click="createApplication"
          >
            {{ saving ? 'Оформление…' : 'Далее' }}
          </button>
        </div>

        <Modal
          :show="showAddCompanyModal"
          title="Добавить компанию"
          size="lg"
          :show-footer="false"
          @close="closeAddCompanyModal"
        >
          <div class="space-y-4">
            <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Введите название компании или ИНН.</p>
            <div>
              <label class="mb-1 block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Компания</label>
              <CompanyAutocomplete
                v-model="newCompanyValue"
                placeholder="Введите название компании или ИНН"
                required
                @validation="onNewCompanyValidation"
                @select="onNewCompanySelect"
              />
            </div>
            <p v-if="addCompanyError" class="rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
              {{ addCompanyError }}
            </p>
            <div class="flex justify-end gap-3 pt-2">
              <button type="button" class="btn-secondary" :disabled="addingCompany" @click="closeAddCompanyModal">
                Отмена
              </button>
              <button
                type="button"
                :disabled="addingCompany || !newCompanyValid || !newCompany"
                class="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
                @click="submitNewCompany"
              >
                {{ addingCompany ? 'Сохранение...' : 'Сохранить' }}
              </button>
            </div>
          </div>
        </Modal>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { useCompanySelectHistory } from '~/features/auth/composables/useCompanySelectHistory'
import CompanyAutocomplete from '~/components/ui/CompanyAutocomplete.vue'
import { createCompanyApi } from '~/features/company/api/companyApi'
import { buildApplicationCalculationPayload } from '~/features/checkout/utils/applicationCalculation'
import CheckoutCompanyData from '~/features/checkout/components/CheckoutCompanyData.vue'
import { useDraftApplication } from '~/features/checkout/composables/useDraftApplication'
import { commerceLeasingApplicationItems } from '~/features/commerce/leasingProjection'
import { createCommerceApi } from '~/features/commerce/api/commerceApi'
import { commerceFailureMessage } from '~/features/commerce/composables/commerceErrors'
import { createSpecialEquipmentCartApi } from '~/features/specialEquipment/api/specialEquipmentCartApi'
import { useSpecialEquipmentCommerceShellStore } from '~/features/specialEquipment/store/commerceShell'
import { useStorefront } from '~/features/storefront'
import type { UUID } from '~/types/ids'
import type { CompanyInfo } from '~/types'

definePageMeta({ middleware: ['auth'] })

const router = useRouter()
const config = useRuntimeConfig()
const toast = useToast()
const authStore = useAuthStore()
const cartStore = useCartStore()
const checkoutStore = useCheckoutStore()
const specialEquipmentCartStore = useSpecialEquipmentCommerceShellStore()
const { publicRoute, apiPath, slug } = useStorefront()
const companySelect = useCompanySelectHistory()
const companyApi = createCompanyApi(config)
const commerceApi = createCommerceApi(config, apiPath)
const specialEquipmentCartApi = createSpecialEquipmentCartApi(config, apiPath)
const draftApi = useDraftApplication()

const bootLoading = ref(true)
const saving = ref(false)
const addingCompany = ref(false)
const selectingCompany = ref(false)
const pageError = ref('')
const showAddCompanyModal = ref(false)
const newCompanyValue = ref('')
const newCompanyValid = ref(false)
const newCompany = ref<CompanyInfo | null>(null)
const addCompanyError = ref('')
const companies = computed(() => companySelect.companies.value)
const companiesLoading = computed(() => companySelect.loadingCompanies.value || companySelect.loadingSelected.value)
const selectedCompanyId = computed(() => checkoutStore.selectedCompanyId)
const calculation = computed(() => checkoutStore.calculation)

const totalAmount = computed(() => calculation.value?.total_amount ?? 0)
const monthlyPayment = computed(() => calculation.value?.calculation?.monthlyPayment ?? 0)
const totalCost = computed(() => calculation.value?.calculation?.totalCost ?? 0)
const totalInterest = computed(() => calculation.value?.calculation?.totalInterest ?? 0)
const buyoutAmount = computed(() => calculation.value?.buyout_amount ?? calculation.value?.calculation?.buyoutAmount ?? 0)
const rateLabel = computed(() => calculation.value?.calculation?.rate == null ? '—' : `${calculation.value.calculation.rate}%`)
const downPaymentLabel = computed(() => calculation.value?.down_payment_percent == null ? '—' : `${calculation.value.down_payment_percent}%`)
const leaseTermLabel = computed(() => calculation.value?.lease_term_months == null ? '—' : `${calculation.value.lease_term_months} мес.`)

const formatPrice = (value: number) => value > 0
  ? `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`
  : '—'

const hasCheckoutItems = () => checkoutStore.commerceItems.length > 0 || checkoutStore.vehicles.length > 0

const onCompanySelect = async (event: Event) => {
  const companyId = (event.target as HTMLSelectElement).value as UUID
  if (!companyId) {
    checkoutStore.setSelectedCompanyId(null)
    return
  }

  selectingCompany.value = true
  pageError.value = ''
  try {
    await companySelect.selectCompany(companyId)
  } catch (error: unknown) {
    pageError.value = commerceFailureMessage(error, 'Не удалось выбрать организацию')
    toast.error(pageError.value)
  } finally {
    selectingCompany.value = false
  }
}

const openAddCompanyModal = () => {
  newCompanyValue.value = ''
  newCompanyValid.value = false
  newCompany.value = null
  addCompanyError.value = ''
  showAddCompanyModal.value = true
}

const closeAddCompanyModal = () => {
  if (addingCompany.value) return
  showAddCompanyModal.value = false
  newCompanyValue.value = ''
  newCompanyValid.value = false
  newCompany.value = null
  addCompanyError.value = ''
}

const onNewCompanyValidation = (valid: boolean) => {
  newCompanyValid.value = valid
  if (!valid) newCompany.value = null
}

const onNewCompanySelect = (company: CompanyInfo | null) => {
  newCompany.value = company
}

const submitNewCompany = async () => {
  if (addingCompany.value || !newCompanyValid.value || !newCompany.value?.inn) return

  addingCompany.value = true
  addCompanyError.value = ''
  try {
    const response = await companyApi.addMyCompany(newCompany.value)
    await companySelect.loadCompanies()
    await authStore.checkAuth(true)
    await companySelect.selectCompany(response.company_id)
    showAddCompanyModal.value = false
    toast.success('Компания успешно добавлена')
  } catch (error: unknown) {
    addCompanyError.value = commerceFailureMessage(error, 'Не удалось добавить компанию')
  } finally {
    addingCompany.value = false
  }
}

const finishCreation = async (applicationId: UUID) => {
  checkoutStore.setApplicationId(applicationId)
  checkoutStore.resetQuestionnaireData()
  await router.push(publicRoute(`/application/${applicationId}?step=items`))
}

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

const createCommerceApplication = async (idempotencyKey: string): Promise<UUID> => {
  const lines = checkoutStore.commerceItems
  const companyId = checkoutStore.selectedCompanyId
  if (!companyId || lines.length === 0) throw new Error('Не удалось определить технику или компанию для заявки.')

  const specialEquipmentLines = lines.filter(line => line.item.ref.type === 'special_equipment')
  if (specialEquipmentLines.length === lines.length) {
    const cartItemIds = [...new Set(specialEquipmentLines.flatMap(line => line.cart_item_ids ?? []))]
    if (cartItemIds.length !== specialEquipmentLines.length) {
      throw new Error('Корзина изменилась. Вернитесь в корзину и повторите оформление.')
    }
    const result = await specialEquipmentCartApi.createLeasingApplication({
      source_type: slug.value ? 'dealer_site' : 'platform',
      company_id: companyId,
      cart_item_ids: cartItemIds,
      leasing_purpose: null,
      down_payment_percent: String(calculation.value?.down_payment_percent ?? 10),
      lease_term_months: calculation.value?.lease_term_months ?? 36,
    }, idempotencyKey)
    await synchronizeCartStateAfterDraftCreation()
    return result.application_id
  }

  const result = await commerceApi.createLeasingApplication({
    source_type: slug.value ? 'dealer_site' : 'platform',
    items: commerceLeasingApplicationItems(lines),
    company_id: companyId,
    name: authStore.user?.name || undefined,
    email: authStore.user?.email || undefined,
    down_payment_percent: String(calculation.value?.down_payment_percent ?? 10),
    lease_term_months: calculation.value?.lease_term_months ?? 36,
    calculation: buildApplicationCalculationPayload(calculation.value) ?? undefined,
  }, idempotencyKey)
  await synchronizeCartStateAfterDraftCreation()
  return result.application_id
}

const createLegacyApplication = async (idempotencyKey: string): Promise<UUID> => {
  const draft = await draftApi.createApplication(idempotencyKey)
  await synchronizeCartStateAfterDraftCreation()
  await draftApi.updateVehicles(draft.application_id)
  await draftApi.updateConditions(draft.application_id)
  return draft.application_id
}

const createApplication = async () => {
  if (!checkoutStore.selectedCompanyId || saving.value) return

  saving.value = true
  pageError.value = ''
  try {
    const idempotencyKey = checkoutStore.getApplicationCreateIdempotencyKey()
    const applicationId = checkoutStore.commerceItems.length > 0
      ? await createCommerceApplication(idempotencyKey)
      : await createLegacyApplication(idempotencyKey)
    await finishCreation(applicationId)
  } catch (error: unknown) {
    pageError.value = commerceFailureMessage(error, 'Не удалось оформить заявку')
    toast.error(pageError.value)
    try {
      await companySelect.loadCompanies()
      await companySelect.loadSelectedCompany()
    } catch {
      // The original create error remains visible.
    }
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
    if (!authStore.isClient) {
      await router.replace(publicRoute('/cart/conditions'))
      return
    }
    if (!hasCheckoutItems()) {
      await router.replace(publicRoute('/cart/conditions'))
      return
    }
    await companySelect.loadCompanies()
    await companySelect.loadSelectedCompany()
  } catch {
    pageError.value = 'Не удалось загрузить список компаний'
  } finally {
    bootLoading.value = false
  }
})

useSeoMeta({
  title: 'Оформление заявки — CarCraft Multileasing',
  description: 'Выбор компании и проверка условий перед созданием заявки',
})
</script>

<style scoped>
.btn-primary {
  @apply rounded-md bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 py-3 font-medium text-[color:var(--storefront-text,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2;
}

.btn-secondary {
  @apply rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-5 py-3 font-medium text-[color:var(--storefront-text,#374151)] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2;
}
</style>
