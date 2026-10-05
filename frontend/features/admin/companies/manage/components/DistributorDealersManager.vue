<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 overflow-y-auto" aria-labelledby="modal-title" role="dialog" aria-modal="true">
      <div class="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
        <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" @click="$emit('close')" />

        <span class="inline-block h-screen align-middle" aria-hidden="true">&#8203;</span>

        <div class="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full">
          <div class="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
            <div class="flex justify-between items-center mb-4">
              <h3 class="text-lg leading-6 font-medium text-gray-900" id="modal-title">
                Дилеры дистрибьютора: {{ distributor.name }}
              </h3>
              <button @click="$emit('close')" class="text-gray-400 hover:text-gray-500">
                <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Add dealer form -->
            <div class="mb-6 p-4 bg-gray-50 rounded-lg">
              <div class="flex items-center gap-3">
                <select
                  v-model="selectedDealerId"
                  class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                  :disabled="loadingDealers || availableDealers.length === 0"
                >
                  <option value="">Выберите дилера</option>
                  <option v-for="dealer in availableDealers" :key="dealer.id" :value="dealer.id">
                    {{ dealer.name }} {{ dealer.inn ? `(ИНН: ${dealer.inn})` : '' }}
                  </option>
                </select>
                <button
                  @click="linkDealer"
                  :disabled="!selectedDealerId || linking"
                  class="btn-primary"
                >
                  <span v-if="linking">Добавление...</span>
                  <span v-else>Добавить</span>
                </button>
              </div>
              <p v-if="availableDealers.length === 0 && !loadingDealers" class="text-sm text-gray-500 mt-2">
                Нет доступных дилеров для добавления
              </p>
            </div>

            <!-- Linked dealers table -->
            <div v-if="linkedDealers.length > 0">
              <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Компания</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ИНН</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Статус</th>
                    <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Действия</th>
                  </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                  <tr v-for="dealer in linkedDealers" :key="dealer.id">
                    <td class="px-6 py-4 whitespace-nowrap">
                      <div class="text-sm font-medium text-gray-900">{{ dealer.name }}</div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                      <div class="text-sm text-gray-500">{{ dealer.inn || '-' }}</div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                      <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
                            :class="dealer.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'">
                        {{ dealer.is_active ? 'Активен' : 'Неактивен' }}
                      </span>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button
                        @click="unlinkDealer(dealer.id)"
                        :disabled="unlinkingId === dealer.id"
                        class="text-red-600 hover:text-red-900"
                      >
                        <span v-if="unlinkingId === dealer.id">Удаление...</span>
                        <span v-else>Удалить</span>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
              Нет связанных дилеров
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { createCompaniesAdminApi } from '../api/companiesAdminApi'
import type { Company } from '~/types/features'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  distributor: Company
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated'): void
}>()

const config = useRuntimeConfig()
const api = createCompaniesAdminApi(config)
const toast = useToast()

const linkedDealers = ref<Company[]>([])
const availableDealers = ref<Company[]>([])
const allDealers = ref<Company[]>([])
const selectedDealerId = ref<UUID>('')
const linking = ref(false)
const unlinkingId = ref<UUID | null>(null)
const loadingDealers = ref(false)

const linkedDealerIds = computed(() => new Set(linkedDealers.value.map(d => d.id)))

const fetchLinkedDealers = async () => {
  try {
    const response = await api.getDistributorDealers(props.distributor.id)
    linkedDealers.value = response.dealers || []
  } catch (err) {
    console.error('Error fetching linked dealers:', err)
    toast.error('Ошибка при загрузке связанных дилеров')
  }
}

const fetchAllDealers = async () => {
  loadingDealers.value = true
  try {
    // Fetch all dealers to show in dropdown (limit=200 should be enough for admin)
    const response = await api.getCompanies({ company_type: 'dealer', limit: '200' })
    allDealers.value = response.companies || []
  } catch (err) {
    console.error('Error fetching dealers:', err)
  } finally {
    loadingDealers.value = false
  }
}

const computeAvailableDealers = () => {
  availableDealers.value = allDealers.value.filter(
    d => !linkedDealerIds.value.has(d.id)
  )
}

const linkDealer = async () => {
  if (!selectedDealerId.value) return
  linking.value = true
  try {
    await api.linkDistributorDealer(props.distributor.id, selectedDealerId.value)
    toast.success('Дилер успешно добавлен')
    selectedDealerId.value = ''
    await fetchLinkedDealers()
    computeAvailableDealers()
    emit('updated')
  } catch (err: any) {
    console.error('Error linking dealer:', err)
    const msg = err?.data?.detail || 'Ошибка при добавлении дилера'
    toast.error(msg)
  } finally {
    linking.value = false
  }
}

const unlinkDealer = async (dealerId: UUID) => {
  unlinkingId.value = dealerId
  try {
    await api.unlinkDistributorDealer(props.distributor.id, dealerId)
    toast.success('Связь удалена')
    await fetchLinkedDealers()
    computeAvailableDealers()
    emit('updated')
  } catch (err: any) {
    console.error('Error unlinking dealer:', err)
    const msg = err?.data?.detail || 'Ошибка при удалении связи'
    toast.error(msg)
  } finally {
    unlinkingId.value = null
  }
}

onMounted(async () => {
  await fetchLinkedDealers()
  await fetchAllDealers()
  computeAvailableDealers()
})

watch(() => linkedDealers.value, computeAvailableDealers)
</script>
