<template>
  <div>
    <div v-if="!selectedApplication">
      <div class="flex items-center justify-between mb-6">
        <div>
          <h2 class="text-xl font-semibold text-gray-900">Управление заявками</h2>
          <p class="text-sm text-gray-600 mt-1">Выберите заявку для управления автомобилями</p>
        </div>
        <div class="flex items-center space-x-4">
          <div v-if="stats" class="flex space-x-4 text-sm">
            <div class="flex items-center">
              <span class="w-3 h-3 rounded-full bg-orange-400 mr-2"></span>
              <span class="text-gray-600">Ожидают VIN: <strong class="text-orange-600">{{ stats.pending_orders || 0 }}</strong></span>
            </div>
            <div class="flex items-center">
              <span class="w-3 h-3 rounded-full bg-green-400 mr-2"></span>
              <span class="text-gray-600">Назначено: <strong class="text-green-600">{{ stats.assigned_orders || 0 }}</strong></span>
            </div>
          </div>
          <button @click="fetchApplications" class="btn-secondary">
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Обновить
          </button>
        </div>
      </div>

      <div v-if="loading" class="text-center py-8">
        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <p class="mt-2 text-gray-600">Загружаем заявки...</p>
      </div>

      <div v-else-if="error" class="text-center py-8">
        <p class="text-red-600 mb-4">{{ error }}</p>
        <button @click="fetchApplications" class="btn-primary">Попробовать снова</button>
      </div>

      <div v-else-if="applications.length === 0" class="text-center py-12">
        <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
        </svg>
        <h3 class="text-lg font-medium text-gray-900 mb-2">Нет заявок</h3>
        <p class="text-gray-600">Пока нет заявок с автомобилями вашего дистрибьютора</p>
      </div>

      <div v-else class="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Заявка</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Заявитель</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Статус</th>
              <th class="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Авто</th>
              <th class="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">VIN</th>
              <th class="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Поддержка</th>
              <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Сумма</th>
              <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Дата</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr 
              v-for="app in applications" 
              :key="app.id" 
              @click="openApplication(app)"
              class="hover:bg-blue-50 cursor-pointer transition-colors"
            >
              <td class="px-6 py-4 whitespace-nowrap">
                <span class="text-blue-600 font-semibold hover:text-blue-800">
                  {{ formatApplicationNumber(app as any) }}
                </span>
              </td>
              <td class="px-6 py-4">
                <div class="text-sm font-medium text-gray-900">{{ app.applicant_name }}</div>
                <div class="text-sm text-gray-500">{{ app.company }}</div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="getStatusClass(app.status)" class="inline-flex px-2 py-1 text-xs font-semibold rounded-full">
                  {{ getStatusLabel(app.status) }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-center">
                <span class="text-sm font-medium text-gray-900">{{ app.vehicles_count }}</span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-center">
                <div class="flex items-center justify-center space-x-2">
                  <span v-if="app.pending_count > 0" class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800">
                    {{ app.pending_count }} ожид.
                  </span>
                  <span v-if="app.assigned_count > 0" class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                    {{ app.assigned_count }} назн.
                  </span>
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-center">
                <span v-if="app.support" class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800" title="Применена поддержка">
                  <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"/>
                  </svg>
                  Есть
                </span>
                <span v-else class="text-gray-300 text-xs">—</span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium text-gray-900">
                {{ formatMoney(app.total_amount) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm text-gray-500">
                {{ formatDate(app.created_at) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="pagination.pages > 1" class="mt-6 flex justify-center">
        <div class="flex space-x-2">
          <button
            @click="changePage(pagination.page - 1)"
            :disabled="pagination.page <= 1"
            class="btn-secondary disabled:opacity-50"
          >
            Предыдущая
          </button>
          <span class="flex items-center px-3 py-2 text-sm text-gray-700">
            Страница {{ pagination.page }} из {{ pagination.pages }}
          </span>
          <button
            @click="changePage(pagination.page + 1)"
            :disabled="pagination.page >= pagination.pages"
            class="btn-secondary disabled:opacity-50"
          >
            Следующая
          </button>
        </div>
      </div>
    </div>

    <div v-else>
      <div class="mb-6">
        <button @click="closeApplication" class="flex items-center text-gray-600 hover:text-gray-900 mb-4">
          <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Назад к списку заявок
        </button>
        
        <div class="bg-white border border-gray-200 rounded-lg p-6">
          <div class="flex items-center justify-between">
            <div>
              <h2 class="text-xl font-semibold text-gray-900">
                Заявка {{ formatApplicationNumber(selectedApplication as any) }}
              </h2>
              <p class="text-sm text-gray-600 mt-1">
                {{ selectedApplication.applicant_name }} • {{ selectedApplication.company }}
              </p>
            </div>
            <div class="flex items-center space-x-4">
              <span :class="getStatusClass(selectedApplication.status)" class="inline-flex px-3 py-1 text-sm font-semibold rounded-full">
                {{ getStatusLabel(selectedApplication.status) }}
              </span>
              <div class="text-right">
                <p class="text-lg font-semibold text-gray-900">{{ formatMoney(selectedApplication.total_amount) }}</p>
                <p class="text-sm text-gray-500">{{ formatDate(selectedApplication.created_at) }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Support Info Block -->
      <div v-if="selectedApplication.support" class="bg-yellow-50 border border-yellow-200 rounded-lg p-5 mb-6">
        <h3 class="text-base font-semibold text-gray-900 mb-3 flex items-center gap-2">
          <svg class="w-4 h-4 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"/>
          </svg>
          Поддержка применена
        </h3>
        <div class="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
          <div v-if="selectedApplication.support.base_total != null" class="flex justify-between">
            <span class="text-gray-600">Базовая сумма:</span>
            <span class="font-medium">{{ formatMoney(selectedApplication.support.base_total) }}</span>
          </div>
          <div v-if="(selectedApplication.support.vehicle_discount_support || 0) > 0" class="flex justify-between">
            <span class="text-gray-600">Поддержка на ТС:</span>
            <span class="font-medium text-green-700">−{{ formatMoney(selectedApplication.support.vehicle_discount_support || 0) }}</span>
          </div>
          <div v-if="(selectedApplication.support.dealer_commission_support || 0) > 0" class="flex justify-between">
            <span class="text-gray-600">Комиссия дилеру:</span>
            <span class="font-medium text-green-700">−{{ formatMoney(selectedApplication.support.dealer_commission_support || 0) }}</span>
          </div>
          <div v-if="(selectedApplication.support.down_payment_support || 0) > 0" class="flex justify-between">
            <span class="text-gray-600">Поддержка на аванс:</span>
            <span class="font-medium text-green-700">−{{ formatMoney(selectedApplication.support.down_payment_support || 0) }}</span>
          </div>
          <div v-if="(selectedApplication.support.interest_support || 0) > 0" class="flex justify-between">
            <span class="text-gray-600">Поддержка на проценты:</span>
            <span class="font-medium text-green-700">−{{ formatMoney(selectedApplication.support.interest_support || 0) }}</span>
          </div>
          <div v-if="selectedApplication.support.effective_total != null" class="flex justify-between col-span-2 border-t border-yellow-200 pt-2 mt-1">
            <span class="text-gray-800 font-medium">Итого с поддержкой:</span>
            <span class="font-bold text-yellow-700">{{ formatMoney(selectedApplication.support.effective_total) }}</span>
          </div>
          <div v-if="selectedApplication.support.effective_down_payment != null" class="flex justify-between">
            <span class="text-gray-800 font-medium">Аванс с поддержкой:</span>
            <span class="font-bold text-yellow-700">{{ formatMoney(selectedApplication.support.effective_down_payment) }}</span>
          </div>
        </div>
      </div>

      <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 class="text-lg font-medium text-gray-900">
            Автомобили в заявке
            <span class="text-sm font-normal text-gray-500 ml-2">
              ({{ vehiclesPagination.total }} шт.)
            </span>
          </h3>
          <button @click="openAddVehicleModal" class="btn-primary-sm">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            Добавить автомобиль
          </button>
        </div>

        <div v-if="vehiclesLoading" class="text-center py-8">
          <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          <p class="mt-2 text-sm text-gray-600">Загружаем автомобили...</p>
        </div>

        <div v-else-if="vehicles.length === 0" class="text-center py-8 text-gray-500">
          Нет автомобилей в заявке
        </div>

        <div v-else>
          <div class="mb-5 space-y-4">
            <VehicleFulfillmentPanel v-for="vehicle in vehicles" :key="`fulfillment-${vehicle.id}`" :title="`${vehicle.mark_name} ${vehicle.model_name}: количество и подбор`" :application-vehicle-id="vehicle.id" @updated="refreshFulfillment" />
          </div>
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Автомобиль</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Цель / регион</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">VIN</th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Цена</th>
                <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Действия</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="vehicle in vehicles" :key="vehicle.id" class="hover:bg-gray-50">
                <td class="px-6 py-4">
                  <NuxtLink 
                    :to="vehicle.catalog_url" 
                    class="text-blue-600 hover:text-blue-800 font-medium"
                    target="_blank"
                  >
                    {{ vehicle.mark_name }} {{ vehicle.model_name }}
                  </NuxtLink>
                  <p class="text-sm text-gray-500">
                    {{ vehicle.generation_name }} • {{ vehicle.configuration_name }}
                    <span v-if="vehicle.color"> • {{ vehicle.color }}</span>
                    <span v-if="vehicle.year"> • {{ vehicle.year }}</span>
                  </p>
                  <span 
                    v-if="vehicle.is_model_order && !vehicle.vin" 
                    class="inline-flex mt-1 px-2 py-0.5 text-xs font-medium rounded bg-orange-100 text-orange-800"
                  >
                    Заказ по модели
                  </span>
                </td>
                <td class="px-6 py-4 text-sm text-gray-700">
                  <div>
                    <span class="text-gray-500">Цель:</span> {{ formatLeasingPurpose(vehicle) }}
                  </div>
                  <div class="mt-1">
                    <span class="text-gray-500">Регион:</span>
                    <VehicleRegionsDisplay :vehicle="vehicle" />
                  </div>
                </td>
                <td class="px-6 py-4">
                  <div v-if="vehicle.fulfillment_version" class="font-mono text-sm">{{ vehicle.allocated_vins?.filter(Boolean).join(', ') || 'Не подобраны' }}</div>
                  <div v-else-if="vehicle.vin" class="flex items-center">
                    <span class="font-mono text-sm text-green-700 bg-green-50 px-2 py-1 rounded">
                      {{ vehicle.vin }}
                    </span>
                    <svg class="w-4 h-4 ml-2 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <div v-else class="flex items-center space-x-2">
                    <input
                      v-model="vinInputs[vehicle.id]"
                      type="text"
                      placeholder="Введите VIN"
                      class="input-field-sm uppercase font-mono w-48"
                      maxlength="17"
                    />
                    <button
                      @click="assignVin(vehicle)"
                      :disabled="!vinInputs[vehicle.id] || vinInputs[vehicle.id].length !== 17 || processingId === vehicle.id"
                      class="btn-success-sm disabled:opacity-50"
                    >
                      <svg v-if="processingId === vehicle.id" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      <span v-else>OK</span>
                    </button>
                  </div>
                </td>
                <td class="px-6 py-4">
                  <span class="text-gray-900 font-medium">{{ formatMoney(vehicle.unit_price) }}</span>
                </td>
                <td class="px-6 py-4 text-right">
                  <div class="flex items-center justify-end space-x-2">
                    <button
                      @click="openReplaceModal(vehicle)"
                      :disabled="processingId === vehicle.id"
                      class="btn-secondary-sm"
                      title="Заменить автомобиль"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                      </svg>
                    </button>
                    <button
                      @click="confirmDelete(vehicle)"
                      :disabled="processingId === vehicle.id"
                      class="btn-danger-sm"
                      title="Удалить из заявки"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <div v-if="vehiclesPagination.pages > 1" class="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
            <p class="text-sm text-gray-700">
              Показано {{ (vehiclesPagination.page - 1) * vehiclesPagination.limit + 1 }} - 
              {{ Math.min(vehiclesPagination.page * vehiclesPagination.limit, vehiclesPagination.total) }} 
              из {{ vehiclesPagination.total }}
            </p>
            <div class="flex space-x-2">
              <button
                @click="changeVehiclesPage(vehiclesPagination.page - 1)"
                :disabled="vehiclesPagination.page <= 1"
                class="btn-secondary-sm disabled:opacity-50"
              >
                Пред.
              </button>
              <span class="flex items-center px-2 text-sm text-gray-700">
                {{ vehiclesPagination.page }} / {{ vehiclesPagination.pages }}
              </span>
              <button
                @click="changeVehiclesPage(vehiclesPagination.page + 1)"
                :disabled="vehiclesPagination.page >= vehiclesPagination.pages"
                class="btn-secondary-sm disabled:opacity-50"
              >
                След.
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showVehicleModal" class="fixed inset-0 z-50 overflow-y-auto">
      <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
        <div class="fixed inset-0 transition-opacity" @click="closeModal">
          <div class="absolute inset-0 bg-gray-900 opacity-75"></div>
        </div>

        <div class="relative bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:max-w-2xl sm:w-full">
          <div class="bg-white px-6 py-4 border-b border-gray-200">
            <div class="flex items-center justify-between">
              <h3 class="text-lg font-semibold text-gray-900">
                {{ modalMode === 'add' ? 'Добавить автомобиль в заявку' : 'Заменить автомобиль' }}
              </h3>
              <button @click="closeModal" class="text-gray-400 hover:text-gray-500">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <div class="px-6 py-4">
            <div class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-2">Поиск автомобиля</label>
              <div class="flex space-x-2">
                <input
                  v-model="vehicleSearch"
                  type="text"
                  placeholder="Поиск по VIN, марке или модели..."
                  class="input-field flex-1"
                  @input="searchVehicles"
                />
                <div class="flex items-center space-x-4">
                  <label class="inline-flex items-center">
                    <input type="radio" v-model="vinFilter" value="all" class="form-radio" @change="searchVehicles">
                    <span class="ml-2 text-sm text-gray-700">Все</span>
                  </label>
                  <label class="inline-flex items-center">
                    <input type="radio" v-model="vinFilter" value="with" class="form-radio" @change="searchVehicles">
                    <span class="ml-2 text-sm text-gray-700">С VIN</span>
                  </label>
                  <label class="inline-flex items-center">
                    <input type="radio" v-model="vinFilter" value="without" class="form-radio" @change="searchVehicles">
                    <span class="ml-2 text-sm text-gray-700">Без VIN</span>
                  </label>
                </div>
              </div>
            </div>

            <div v-if="searchingVehicles" class="text-center py-8">
              <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
            </div>

            <div v-else-if="availableVehicles.length === 0" class="text-center py-8 text-gray-500">
              {{ vehicleSearch ? 'Автомобили не найдены' : 'Введите запрос для поиска' }}
            </div>

            <div v-else class="max-h-96 overflow-y-auto">
              <div class="space-y-2">
                <button
                  v-for="v in availableVehicles"
                  :key="v.id"
                  @click="selectVehicle(v)"
                  :disabled="modalProcessing"
                  class="w-full text-left p-4 border rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-colors disabled:opacity-50"
                  :class="selectedVehicle?.id === v.id ? 'bg-blue-50 border-blue-500' : 'border-gray-200'"
                >
                  <div class="flex items-center justify-between">
                    <div>
                      <p class="font-medium text-gray-900">
                        {{ v.mark_name }} {{ v.model_name }}
                      </p>
                      <p class="text-sm text-gray-500">
                        {{ v.generation_name }} • {{ v.configuration_name }}
                        <span v-if="v.color"> • {{ v.color }}</span>
                        <span v-if="v.year"> • {{ v.year }} г.</span>
                      </p>
                      <p v-if="v.vin" class="text-sm font-mono text-green-600 mt-1">
                        VIN: {{ v.vin }}
                      </p>
                      <p v-else class="text-sm text-orange-600 mt-1">
                        Без VIN (заказ по модели)
                      </p>
                    </div>
                    <div class="text-right">
                      <p class="text-lg font-semibold text-gray-900">
                        {{ formatMoney(v.discount_price || v.base_price || 0) }}
                      </p>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          </div>

          <div class="bg-gray-50 px-6 py-4 flex justify-end space-x-3">
            <button @click="closeModal" class="btn-secondary">
              Отмена
            </button>
            <button
              @click="confirmVehicleSelection"
              :disabled="!selectedVehicle || modalProcessing"
              class="btn-primary disabled:opacity-50"
            >
              <svg v-if="modalProcessing" class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              {{ modalMode === 'add' ? 'Добавить' : 'Заменить' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showDeleteConfirm" class="fixed inset-0 z-50 overflow-y-auto">
      <div class="flex items-center justify-center min-h-screen px-4">
        <div class="fixed inset-0 transition-opacity" @click="showDeleteConfirm = false">
          <div class="absolute inset-0 bg-gray-900 opacity-75"></div>
        </div>

        <div class="relative bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:max-w-lg sm:w-full">
          <div class="bg-white px-6 py-4">
            <div class="flex items-start">
              <div class="mx-auto flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-red-100">
                <svg class="h-6 w-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
            </div>
            <div class="mt-3 text-center">
              <h3 class="text-lg font-medium text-gray-900">Удалить автомобиль из заявки?</h3>
              <p class="mt-2 text-sm text-gray-500">
                {{ deleteTarget?.mark_name }} {{ deleteTarget?.model_name }} будет удален из заявки. Это действие нельзя отменить.
              </p>
            </div>
          </div>
          <div class="bg-gray-50 px-6 py-4 flex justify-end space-x-3">
            <button @click="showDeleteConfirm = false" class="btn-secondary">
              Отмена
            </button>
            <button
              @click="deleteVehicle"
              :disabled="!!processingId"
              class="btn-danger disabled:opacity-50"
            >
              <svg v-if="processingId" class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Удалить
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Application, ApplicationVehicle, ModelOrderStats, Pagination, OrderStatus } from '~/features/distributor/types'
import VehicleFulfillmentPanel from '~/features/applications/components/VehicleFulfillmentPanel.vue'
import VehicleRegionsDisplay from '~/features/applications/components/VehicleRegionsDisplay.vue'
import { formatLeasingPurpose } from '~/features/applications/utils/applicationVehicleDisplay'
import { formatApplicationNumber } from '~/utils'
import type { UUID } from '~/types/ids'

const config = useRuntimeConfig()
const { showToast } = useToast()

const applications = ref<Application[]>([])
const stats = ref<ModelOrderStats | null>(null)
const loading = ref(true)
const error = ref('')
const processingId = ref<UUID | null>(null)
const modalProcessing = ref(false)

const pagination = ref<Pagination>({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

const selectedApplication = ref<Application | null>(null)
const vehicles = ref<ApplicationVehicle[]>([])
const vehiclesLoading = ref(false)
const vinInputs = ref<Record<UUID, string>>({})

const vehiclesPagination = ref<Pagination>({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

const showVehicleModal = ref(false)
const modalMode = ref<'add' | 'replace'>('add')
const replaceVehicleItem = ref<ApplicationVehicle | null>(null)
const vehicleSearch = ref('')
const vinFilter = ref('all')
const availableVehicles = ref<ApplicationVehicle[]>([])
const selectedVehicle = ref<ApplicationVehicle | null>(null)
const searchingVehicles = ref(false)
let searchTimeout: ReturnType<typeof setTimeout> | null = null

const showDeleteConfirm = ref(false)
const deleteTarget = ref<ApplicationVehicle | null>(null)

const applicationTimestamp = (application: Application): number => {
  const value = String(application.updated_at || application.created_at || '')
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const flattenGroupedApplications = (grouped: Record<string, Application[]> | Application[] | null | undefined): Application[] => {
  if (Array.isArray(grouped)) return grouped
  return Object.values(grouped || {})
    .flat()
    .sort((a, b) => applicationTimestamp(b) - applicationTimestamp(a))
}

const fetchApplications = async () => {
  loading.value = true
  error.value = ''

  try {
    const params = new URLSearchParams({
      page: pagination.value.page.toString(),
      limit: pagination.value.limit.toString()
    })

    const [appsResponse, statsResponse] = await Promise.all([
      $fetch<{ applications: Record<string, Application[]> | Application[]; pagination: Pagination }>(`/api/v1/distributor/applications-grouped?${params.toString()}`, {
        baseURL: config.public.apiBase,
        credentials: 'include'
      }),
      $fetch<{ stats: ModelOrderStats | null }>('/api/v1/distributor/model-orders/stats', {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
    ])

    applications.value = flattenGroupedApplications(appsResponse.applications)
    pagination.value = appsResponse.pagination || { page: 1, limit: 20, total: 0, pages: 1 }
    stats.value = statsResponse.stats || null
  } catch (err: unknown) {
    console.error('Error fetching applications:', err)
    const fetchErr = err as { data?: { error?: string } }
    error.value = fetchErr.data?.error || 'Ошибка при загрузке заявок'
  } finally {
    loading.value = false
  }
}

const openApplication = (app: Application) => {
  selectedApplication.value = app
  vehiclesPagination.value.page = 1
  fetchVehicles()
}

const refreshFulfillment = async () => {
  await Promise.all([fetchVehicles(), fetchApplications()])
  const updated = applications.value.find(item => item.id === selectedApplication.value?.id)
  if (updated) selectedApplication.value = updated
}

const closeApplication = () => {
  selectedApplication.value = null
  vehicles.value = []
  vinInputs.value = {}
}

const fetchVehicles = async () => {
  if (!selectedApplication.value) return

  vehiclesLoading.value = true

  try {
    const params = new URLSearchParams({
      page: vehiclesPagination.value.page.toString(),
      limit: vehiclesPagination.value.limit.toString()
    })

    const response = await $fetch<{ vehicles: ApplicationVehicle[]; pagination?: Pagination }>(
      `/api/v1/distributor/applications/${selectedApplication.value.id}/vehicles?${params.toString()}`,
      {
        baseURL: config.public.apiBase,
        credentials: 'include'
      }
    )

    vehicles.value = response.vehicles || []
    if (response.pagination) {
      vehiclesPagination.value = response.pagination
    } else {
      vehiclesPagination.value = {
        page: 1,
        limit: 20,
        total: vehicles.value.length,
        pages: 1
      }
    }
  } catch (err) {
    console.error('Error fetching vehicles:', err)
    showToast.error('Ошибка при загрузке автомобилей')
  } finally {
    vehiclesLoading.value = false
  }
}

const assignVin = async (vehicle: ApplicationVehicle) => {
  const vin = vinInputs.value[vehicle.id]?.trim().toUpperCase()
  
  if (!vin || vin.length !== 17) {
    showToast.error('VIN должен содержать 17 символов')
    return
  }

  processingId.value = vehicle.id

  try {
    await $fetch(`/api/v1/application-vehicles/${vehicle.id}`, {
      baseURL: config.public.apiBase,
      method: 'PATCH',
      credentials: 'include',
      body: { vin }
    })

    showToast.success(`VIN ${vin} успешно назначен`)
    vinInputs.value[vehicle.id] = ''
    await fetchVehicles()
    await fetchApplications()
  } catch (err: unknown) {
    console.error('Error assigning VIN:', err)
    const fetchErr = err as { data?: { error?: string } }
    showToast.error(fetchErr.data?.error || 'Ошибка при назначении VIN')
  } finally {
    processingId.value = null
  }
}

const openAddVehicleModal = () => {
  modalMode.value = 'add'
  replaceVehicleItem.value = null
  vehicleSearch.value = ''
  availableVehicles.value = []
  selectedVehicle.value = null
  showVehicleModal.value = true
}

const openReplaceModal = (vehicle: ApplicationVehicle) => {
  modalMode.value = 'replace'
  replaceVehicleItem.value = vehicle
  vehicleSearch.value = ''
  availableVehicles.value = []
  selectedVehicle.value = null
  showVehicleModal.value = true
}

const closeModal = () => {
  showVehicleModal.value = false
  replaceVehicleItem.value = null
  selectedVehicle.value = null
}

const searchVehicles = () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  
  searchTimeout = setTimeout(async () => {
    if (!vehicleSearch.value && vinFilter.value === 'all') {
      availableVehicles.value = []
      return
    }

    searchingVehicles.value = true

    try {
      const params = new URLSearchParams()
      if (vehicleSearch.value) params.append('search', vehicleSearch.value)
      if (vinFilter.value === 'with') params.append('has_vin', 'true')
      if (vinFilter.value === 'without') params.append('has_vin', 'false')

      const response = await $fetch<{ vehicles: ApplicationVehicle[] }>(`/api/v1/distributor/available-vehicles-for-app?${params.toString()}`, {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })

      availableVehicles.value = response.vehicles || []
    } catch (err) {
      console.error('Error searching vehicles:', err)
      showToast.error('Ошибка при поиске автомобилей')
    } finally {
      searchingVehicles.value = false
    }
  }, 300)
}

const selectVehicle = (vehicle: ApplicationVehicle) => {
  selectedVehicle.value = vehicle
}

const confirmVehicleSelection = async () => {
  if (!selectedVehicle.value || !selectedApplication.value) return

  modalProcessing.value = true

  try {
    if (modalMode.value === 'add') {
      await $fetch(`/api/v1/distributor/applications/${selectedApplication.value.id}/vehicles`, {
        baseURL: config.public.apiBase,
        method: 'POST',
        credentials: 'include',
        body: {
          vehicle_id: selectedVehicle.value.id,
          is_model_order: !selectedVehicle.value.vin
        }
      })
      showToast.success('Автомобиль добавлен в заявку')
    } else if (replaceVehicleItem.value) {
      await $fetch(`/api/v1/distributor/application-vehicles/${replaceVehicleItem.value.id}/replace`, {
        baseURL: config.public.apiBase,
        method: 'PUT',
        credentials: 'include',
        body: {
          vehicle_id: selectedVehicle.value.id,
          is_model_order: !selectedVehicle.value.vin
        }
      })
      showToast.success('Автомобиль заменен')
    }

    closeModal()
    await fetchVehicles()
    await fetchApplications()
  } catch (err: unknown) {
    console.error('Error updating vehicle:', err)
    const fetchErr = err as { data?: { error?: string } }
    showToast.error(fetchErr.data?.error || 'Ошибка при обновлении')
  } finally {
    modalProcessing.value = false
  }
}

const confirmDelete = (vehicle: ApplicationVehicle) => {
  deleteTarget.value = vehicle
  showDeleteConfirm.value = true
}

const deleteVehicle = async () => {
  if (!deleteTarget.value) return

  processingId.value = deleteTarget.value.id

  try {
    await $fetch(`/api/v1/distributor/application-vehicles/${deleteTarget.value.id}`, {
      baseURL: config.public.apiBase,
      method: 'DELETE',
      credentials: 'include'
    })

    showToast.success('Автомобиль удален из заявки')
    showDeleteConfirm.value = false
    deleteTarget.value = null
    await fetchVehicles()
    await fetchApplications()
  } catch (err: unknown) {
    console.error('Error deleting vehicle:', err)
    const fetchErr = err as { data?: { error?: string } }
    showToast.error(fetchErr.data?.error || 'Ошибка при удалении')
  } finally {
    processingId.value = null
  }
}

const changePage = (page: number) => {
  pagination.value.page = page
  fetchApplications()
}

const changeVehiclesPage = (page: number) => {
  vehiclesPagination.value.page = page
  fetchVehicles()
}

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

const formatDate = (dateString: string) => {
  if (!dateString) return ''
  return formatSharedDate(dateString)
}

const formatMoney = (amount: number) => {
  if (!amount) return '0 ₽'
  return formatSharedPrice(amount)
}

const getStatusClass = (status: string) => {
  const classes: Record<string, string> = {
    'active': 'bg-blue-100 text-blue-800',
    'rejected': 'bg-red-100 text-red-800',
    'issued': 'bg-green-100 text-green-800'
  }
  return classes[status] || 'bg-gray-100 text-gray-800'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    'active': 'Активная',
    'rejected': 'Отклонена',
    'issued': 'Выдана'
  }
  return labels[status] || status
}

onMounted(() => {
  fetchApplications()
})
</script>

<style scoped>
.btn-primary {
  @apply inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors;
}

.btn-primary-sm {
  @apply inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors;
}

.btn-secondary {
  @apply inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors;
}

.btn-secondary-sm {
  @apply inline-flex items-center px-2.5 py-1.5 border border-gray-300 text-xs font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors;
}

.btn-success-sm {
  @apply inline-flex items-center px-2.5 py-1.5 border border-transparent text-xs font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition-colors;
}

.btn-danger {
  @apply inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-colors;
}

.btn-danger-sm {
  @apply inline-flex items-center px-2.5 py-1.5 border border-transparent text-xs font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-colors;
}

.input-field {
  @apply block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm;
}

.input-field-sm {
  @apply block rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-xs px-2 py-1.5;
}

.form-radio {
  @apply h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300;
}
</style>
