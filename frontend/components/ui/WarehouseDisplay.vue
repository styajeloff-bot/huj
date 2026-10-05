<template>
  <div data-storefront-block="shared.form" class="space-y-6">
    <!-- Заголовок и основные действия -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
      <div>
        <h2 class="text-2xl font-bold text-[color:var(--storefront-title,#111827)]">{{ title }}</h2>
        <p class="text-[color:var(--storefront-text-muted,#4b5563)] mt-1">{{ subtitle }}</p>
      </div>
      <div class="flex items-center gap-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] p-1.5 rounded-lg">
        <slot name="header-actions">
          <button
            v-if="showImportButton"
            @click="$emit('import')"
            class="storefront-action-secondary flex items-center gap-1.5 px-3 py-1.5 text-sm text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,255_255_255)/var(--tw-bg-opacity,1))] hover:shadow-sm rounded-md transition-all"
            title="Импорт автомобилей"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
            </svg>
            <span class="inline">Импорт</span>
          </button>
          <button
            @click="$emit('add')"
            class="storefront-action-secondary flex items-center gap-1.5 px-3 py-1.5 text-sm text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,255_255_255)/var(--tw-bg-opacity,1))] hover:shadow-sm rounded-md transition-all"
            title="Добавить автомобиль"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
            </svg>
            <span class="inline">Добавить</span>
          </button>
          <button
            v-if="showExportButton"
            @click="$emit('export')"
            class="storefront-action-secondary flex items-center gap-1.5 px-3 py-1.5 text-sm text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,255_255_255)/var(--tw-bg-opacity,1))] hover:shadow-sm rounded-md transition-all"
            title="Экспорт данных"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
            <span class="inline">Экспорт</span>
          </button>
        </slot>
      </div>
    </div>

    <!-- Статистика склада -->
    <div v-if="stats" class="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div class="bg-gradient-to-r from-[var(--storefront-gradient-from,#eff6ff)] to-[var(--storefront-gradient-to,#dbeafe)] p-4 rounded-lg border border-[color:var(--storefront-border,#bfdbfe)]">
        <div class="flex items-center">
          <div class="p-2 bg-[color:rgb(var(--storefront-primary-rgb,59_130_246)/var(--tw-bg-opacity,1))] rounded-full shrink-0">
            <svg class="w-5 h-5 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-4m-5 0H3m2 0h3M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
            </svg>
          </div>
          <div class="ml-3 min-w-0">
            <div class="text-xl font-bold text-[color:var(--storefront-text-muted,#2563eb)] truncate">{{ stats.total_vehicles }}</div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#4b5563)]">Всего авто</div>
          </div>
        </div>
      </div>

      <div class="bg-gradient-to-r from-[var(--storefront-gradient-from,#f0fdf4)] to-[var(--storefront-gradient-to,#dcfce7)] p-4 rounded-lg border border-[color:var(--storefront-success-border,#bbf7d0)]">
        <div class="flex items-center">
          <div class="p-2 bg-[color:rgb(var(--storefront-success-rgb,34_197_94)/var(--tw-bg-opacity,1))] rounded-full shrink-0">
            <svg class="w-5 h-5 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
          </div>
          <div class="ml-3 min-w-0">
            <div class="text-xl font-bold text-[color:var(--storefront-success-text,#16a34a)] truncate">{{ stats.available_vehicles }}</div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#4b5563)]">В наличии</div>
          </div>
        </div>
      </div>

      <div class="bg-gradient-to-r from-[var(--storefront-gradient-from,#fefce8)] to-[var(--storefront-gradient-to,#fef9c3)] p-4 rounded-lg border border-[color:var(--storefront-warning-border,#fef08a)]">
        <div class="flex items-center">
          <div class="p-2 bg-[color:rgb(var(--storefront-warning-rgb,234_179_8)/var(--tw-bg-opacity,1))] rounded-full shrink-0">
            <svg class="w-5 h-5 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
          </div>
          <div class="ml-3 min-w-0">
            <div class="text-xl font-bold text-[color:var(--storefront-warning-text,#ca8a04)] truncate">{{ stats.reserved_vehicles }}</div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#4b5563)]">Резерв</div>
          </div>
        </div>
      </div>

      <div class="bg-gradient-to-r from-[var(--storefront-gradient-from,#faf5ff)] to-[var(--storefront-gradient-to,#f3e8ff)] p-4 rounded-lg border border-[color:var(--storefront-info-border,#e9d5ff)]">
        <div class="flex items-center">
          <div class="p-2 bg-[color:rgb(var(--storefront-info-rgb,168_85_247)/var(--tw-bg-opacity,1))] rounded-full shrink-0">
            <svg class="w-5 h-5 text-[color:var(--storefront-icon,#ffffff)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1"></path>
            </svg>
          </div>
          <div class="ml-3 min-w-0">
            <div class="text-xl font-bold text-[color:var(--storefront-info-text,#9333ea)] truncate">{{ formatPrice(stats.total_value) }}</div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#4b5563)]">Стоимость</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Фильтры и поиск -->
    <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4 rounded-lg shadow-sm border">
      <div class="flex flex-col gap-4">
        <!-- Поиск (расширенный) -->
        <div class="relative">
          <input
            :value="filters.search"
            @input="$emit('update:filters', { ...filters, search: ($event.target as HTMLInputElement).value })"
            type="text"
            :placeholder="searchPlaceholder"
            class="storefront-control w-full pl-10 pr-4 py-3 text-base border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
          >
          <svg class="absolute left-3 top-3.5 h-5 w-5 text-[color:var(--storefront-icon,#9ca3af)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
          </svg>
        </div>

        <!-- Фильтры и переключатели -->
        <div class="flex flex-wrap items-center gap-3">
          <select
            v-if="showBrandFilter && brands.length > 0"
            :value="filters.brand"
            @change="$emit('update:filters', { ...filters, brand: ($event.target as HTMLSelectElement).value })"
            class="storefront-control px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
          >
            <option value="">Все бренды</option>
            <option v-for="brand in brands" :key="brand.id" :value="brand.id">
              {{ brand.name }}
            </option>
          </select>

          <select
            :value="filters.status"
            @change="$emit('update:filters', { ...filters, status: ($event.target as HTMLSelectElement).value })"
            class="storefront-control px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
          >
            <option value="">Все статусы</option>
            <option value="available">На складе</option>
            <option value="reserved">Забронирована</option>
            <option value="sold">Продажа / оплата</option>
          </select>

          <select
            v-if="years.length > 0"
            :value="filters.year"
            @change="$emit('update:filters', { ...filters, year: ($event.target as HTMLSelectElement).value })"
            class="storefront-control px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
          >
            <option value="">Все годы</option>
            <option v-for="year in years" :key="year" :value="year">{{ year }}</option>
          </select>

          <button
            @click="$emit('reset-filters')"
            class="storefront-action-ghost px-3 py-2 text-[color:var(--storefront-secondary-foreground,#4b5563)] hover:text-[color:var(--storefront-secondary-hover-foreground,#1f2937)] border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-lg hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] transition-colors"
          >
            Сбросить
          </button>

          <div class="flex-1"></div>

          <!-- Переключение вида -->
          <div class="flex gap-1 bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] p-1 rounded-lg">
            <button class="storefront-action-secondary"
              @click="$emit('update:viewMode', 'table')"
              :class="[
                'px-3 py-1.5 rounded-md transition-colors text-sm',
                viewMode === 'table' 
                  ? 'bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-secondary-foreground,#111827)] shadow-sm'
                  : 'text-[color:var(--storefront-secondary-foreground,#4b5563)] hover:text-[color:var(--storefront-secondary-hover-foreground,#111827)]'
              ]"
            >
              Таблица
            </button>
            <button class="storefront-action-secondary"
              @click="$emit('update:viewMode', 'cards')"
              :class="[
                'px-3 py-1.5 rounded-md transition-colors text-sm',
                viewMode === 'cards' 
                  ? 'bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-secondary-foreground,#111827)] shadow-sm'
                  : 'text-[color:var(--storefront-secondary-foreground,#4b5563)] hover:text-[color:var(--storefront-secondary-hover-foreground,#111827)]'
              ]"
            >
              Карточки
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Массовые действия -->
    <div v-if="showBulkActions && selectedVehicles.length > 0" class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#bfdbfe)] rounded-lg p-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center">
          <span class="text-[color:var(--storefront-text,#1d4ed8)] font-medium">Выбрано: {{ selectedVehicles.length }} автомобилей</span>
        </div>
        <div class="flex gap-2">
          <button
            @click="$emit('bulk-edit')"
            class="storefront-action-primary px-4 py-2 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-lg transition-colors"
          >
            Массовое редактирование
          </button>
          <button
            @click="$emit('bulk-delete')"
            class="storefront-action-destructive px-4 py-2 bg-[color:rgb(var(--storefront-destructive-rgb,220_38_38)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-destructive-foreground,#ffffff)] rounded-lg transition-colors"
          >
            Удалить выбранные
          </button>
          <button
            @click="$emit('clear-selection')"
            class="storefront-action-ghost px-4 py-2 bg-[color:rgb(var(--storefront-ghost-rgb,75_85_99)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,55_65_81)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-ghost-foreground,#ffffff)] rounded-lg transition-colors"
          >
            Отменить выбор
          </button>
        </div>
      </div>
    </div>

    <!-- Загрузка -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем данные склада...</p>
    </div>

    <!-- Ошибка -->
    <div v-else-if="error" class="text-center py-12">
      <div class="text-[color:var(--storefront-error-text,#dc2626)] mb-4">{{ error }}</div>
      <button @click="$emit('retry')" class="storefront-action-primary bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] px-4 py-2 rounded-lg transition-colors">
        Попробовать снова
      </button>
    </div>

    <!-- Таблица автомобилей -->
    <div v-else-if="viewMode === 'table' && vehicles.length > 0" class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-sm border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
          <thead class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
            <tr>
              <th v-if="showBulkActions" class="px-6 py-3 text-left">
                <input
                  type="checkbox"
                  :checked="isAllSelected"
                  @change="$emit('toggle-select-all')"
                  class="storefront-control rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                >
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
                Фото
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider cursor-pointer" @click="$emit('sort', 'vin')">
                VIN
                <svg v-if="sortField === 'vin'" class="text-[color:var(--storefront-icon,inherit)] inline w-4 h-4 ml-1" :class="sortOrder === 'asc' ? 'transform rotate-180' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                </svg>
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider cursor-pointer" @click="$emit('sort', 'brand')">
                Марка/Модель
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider cursor-pointer" @click="$emit('sort', 'year')">
                Год
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider cursor-pointer" @click="$emit('sort', 'base_price')">
                Цена
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
                Статус
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
                Действия
              </th>
            </tr>
          </thead>
          <tbody class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
            <tr v-for="vehicle in vehicles" :key="vehicle.id" class="hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
              <td v-if="showBulkActions" class="px-6 py-4">
                <input
                  type="checkbox"
                  :value="vehicle.id"
                  :checked="selectedVehicles.includes(vehicle.id)"
                  @change="$emit('toggle-select', vehicle.id)"
                  class="storefront-control rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                >
              </td>
              <td class="px-6 py-4">
                <div class="w-16 h-12 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded overflow-hidden">
                  <img
                    v-if="getVehicleImage(vehicle)"
                    :src="getVehicleImage(vehicle)"
                    :alt="getVehicleName(vehicle)"
                    class="w-full h-full object-cover"
                  >
                  <div v-else class="w-full h-full flex items-center justify-center">
                    <svg class="w-6 h-6 text-[color:var(--storefront-icon,#9ca3af)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
                    </svg>
                  </div>
                </div>
              </td>
              <td class="px-6 py-4 text-sm font-mono text-[color:var(--storefront-text,#111827)]">
                {{ vehicle.vin || 'Не указан' }}
              </td>
              <td class="px-6 py-4 text-sm text-[color:var(--storefront-text,#111827)]">
                <div class="font-medium">{{ getVehicleBrand(vehicle) }}</div>
                <div class="text-[color:var(--storefront-text-muted,#6b7280)]">{{ getVehicleModel(vehicle) }}</div>
              </td>
              <td class="px-6 py-4 text-sm text-[color:var(--storefront-text,#111827)]">
                {{ vehicle.year }}
              </td>
              <td class="px-6 py-4 text-sm text-[color:var(--storefront-text,#111827)]">
                <div class="font-medium">{{ formatPrice(getVehiclePrice(vehicle)) }}</div>
                <div v-if="vehicle.discount_price && vehicle.discount_price < getVehiclePrice(vehicle)" class="text-[color:var(--storefront-success-text,#16a34a)] text-xs">
                  Компенсация ПВ: {{ formatPrice(getVehiclePrice(vehicle) - vehicle.discount_price) }}
                </div>
              </td>
              <td class="px-6 py-4">
                <span :class="getStatusClass(vehicle.status)" class="px-2 py-1 text-xs font-medium rounded-full">
                  {{ vehicleStockStatusLabel(vehicle) }}
                </span>
                <p v-if="vehicle.reserved_until" class="mt-1 text-xs">Бронь до {{ new Date(vehicle.reserved_until).toLocaleDateString('ru-RU') }}</p>
              </td>
              <td class="px-6 py-4 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                <div class="flex space-x-2">
                  <button
                    @click="$emit('view', vehicle)"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e3a8a)] transition-colors"
                    title="Просмотр"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                    </svg>
                  </button>
                  <button
                    @click="$emit('edit', vehicle)"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#ca8a04)] hover:text-[color:var(--storefront-ghost-hover-foreground,#713f12)] transition-colors"
                    title="Редактировать"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                    </svg>
                  </button>
                  <button
                    v-if="showDuplicateButton"
                    @click="$emit('duplicate', vehicle)"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#16a34a)] hover:text-[color:var(--storefront-ghost-hover-foreground,#14532d)] transition-colors"
                    title="Дублировать"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                    </svg>
                  </button>
                  <button
                    @click="$emit('delete', vehicle)"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#7f1d1d)] transition-colors"
                    title="Удалить"
                    :disabled="vehicle.status === 'sold' || vehicle.status === 'reserved'"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Карточки автомобилей -->
    <div v-else-if="viewMode === 'cards' && vehicles.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      <div
        v-for="vehicle in vehicles"
        :key="vehicle.id"
        class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-sm border hover:shadow-md transition-shadow relative"
      >
        <!-- Чекбокс для выбора -->
        <div v-if="showBulkActions" class="absolute top-3 left-3 z-10">
          <input
            type="checkbox"
            :value="vehicle.id"
            :checked="selectedVehicles.includes(vehicle.id)"
            @change="$emit('toggle-select', vehicle.id)"
            class="storefront-control rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-sm"
          >
        </div>

        <!-- Изображение -->
        <div class="relative h-48 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-t-lg overflow-hidden cursor-pointer" @click="$emit('view', vehicle)">
          <img
            v-if="getVehicleImage(vehicle)"
            :src="getVehicleImage(vehicle)"
            :alt="getVehicleName(vehicle)"
            class="w-full h-full object-cover"
          >
          <div v-else class="w-full h-full flex items-center justify-center">
            <svg class="w-12 h-12 text-[color:var(--storefront-icon,#9ca3af)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
            </svg>
          </div>

          <!-- Статус -->
          <div class="absolute top-3 right-3">
            <span :class="getStatusClass(vehicle.status)" class="px-2 py-1 text-xs font-medium rounded-full">
              {{ vehicleStockStatusLabel(vehicle) }}
            </span>
          </div>
        </div>

        <!-- Информация -->
        <div class="p-4">
          <div class="mb-2">
            <h3 class="font-semibold text-[color:var(--storefront-title,#111827)]">
              {{ getVehicleBrand(vehicle) }} {{ getVehicleModel(vehicle) }}
            </h3>
            <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ vehicle.year }} год</p>
          </div>

          <div class="mb-3">
            <div class="font-mono text-sm text-[color:var(--storefront-text-muted,#4b5563)]">VIN: {{ vehicle.vin || 'Не указан' }}</div>
            <div v-if="vehicle.color" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Цвет: {{ vehicle.color }}</div>
          </div>

          <div class="mb-4">
            <div class="text-lg font-bold text-[color:var(--storefront-text,#111827)]">
              {{ formatPrice(getVehiclePrice(vehicle)) }}
            </div>
            <div v-if="vehicle.discount_price && vehicle.discount_price < getVehiclePrice(vehicle)" class="text-sm text-[color:var(--storefront-success-text,#16a34a)]">
              Компенсация ПВ: {{ formatPrice(getVehiclePrice(vehicle) - vehicle.discount_price) }}
            </div>
          </div>

          <!-- Действия -->
          <div class="flex justify-between items-center pt-3 border-t">
            <div class="flex space-x-2">
              <button
                @click="$emit('view', vehicle)"
                class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e3a8a)] transition-colors"
                title="Просмотр"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                </svg>
              </button>
              <button
                @click="$emit('edit', vehicle)"
                class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#ca8a04)] hover:text-[color:var(--storefront-ghost-hover-foreground,#713f12)] transition-colors"
                title="Редактировать"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                </svg>
              </button>
              <button
                v-if="showDuplicateButton"
                @click="$emit('duplicate', vehicle)"
                class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#16a34a)] hover:text-[color:var(--storefront-ghost-hover-foreground,#14532d)] transition-colors"
                title="Дублировать"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                </svg>
              </button>
            </div>
            <button
              @click="$emit('delete', vehicle)"
              class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#7f1d1d)] transition-colors"
              title="Удалить"
              :disabled="vehicle.status === 'sold' || vehicle.status === 'reserved'"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Пустое состояние -->
    <div v-else-if="!loading && vehicles.length === 0" class="text-center py-12">
      <svg class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)] mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-4m-5 0H3m2 0h3M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
      </svg>
      <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)] mb-2">{{ emptyTitle }}</h3>
      <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-4">{{ emptySubtitle }}</p>
      <button
        @click="$emit('add')"
        class="storefront-action-primary bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] px-4 py-2 rounded-lg transition-colors"
      >
        Добавить автомобиль
      </button>
    </div>

    <!-- Пагинация -->
    <div v-if="pagination && pagination.pages > 1" class="flex justify-between items-center">
      <div class="text-sm text-[color:var(--storefront-text,#374151)]">
        Показано {{ (pagination.page - 1) * pagination.limit + 1 }} - 
        {{ Math.min(pagination.page * pagination.limit, pagination.total) }} 
        из {{ pagination.total }} автомобилей
      </div>
      <div class="flex space-x-1">
        <button
          v-for="page in visiblePages"
          :key="page"
          @click="$emit('change-page', page)"
          :class="{
            'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)]': page === pagination.page,
            'bg-[color:rgb(var(--storefront-primary-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,209_213_219)/var(--tw-bg-opacity,1))]': page !== pagination.page
          }"
          class="storefront-action-primary px-3 py-1 rounded transition-colors"
          :disabled="page === pagination.page"
        >
          {{ page }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { vehicleStockStatusLabel } from '~/utils/vehicleStockStatus'
import { computed } from 'vue'
import { useFormatPrice } from '@/composables/useFormatPrice'
import type { PropType } from 'vue'
import type { Vehicle, Brand, WarehouseStats, WarehouseFilters, WarehousePagination } from '@/types'
import type { UUID } from '~/types/ids'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'

const { formatPrice } = useFormatPrice()

const props = defineProps({
  // Заголовки
  title: {
    type: String,
    default: 'Управление складом'
  },
  subtitle: {
    type: String,
    default: 'Полное управление автомобильным складом'
  },
  searchPlaceholder: {
    type: String,
    default: 'Поиск по VIN, марке, модели, цвету...'
  },
  emptyTitle: {
    type: String,
    default: 'Склад пуст'
  },
  emptySubtitle: {
    type: String,
    default: 'Добавьте первый автомобиль в ваш склад'
  },

  // Данные
  vehicles: {
    type: Array as PropType<Vehicle[]>,
    default: () => []
  },
  stats: {
    type: Object as PropType<WarehouseStats | null>,
    default: null
  },
  brands: {
    type: Array as PropType<Brand[]>,
    default: () => []
  },
  years: {
    type: Array as PropType<number[]>,
    default: () => []
  },
  pagination: {
    type: Object as PropType<WarehousePagination | null>,
    default: null
  },

  // Состояния
  loading: {
    type: Boolean,
    default: false
  },
  error: {
    type: String,
    default: ''
  },

  // Фильтры
  filters: {
    type: Object as PropType<WarehouseFilters>,
    default: () => ({
      search: '',
      brand: '',
      status: '',
      year: ''
    })
  },
  viewMode: {
    type: String as PropType<'table' | 'cards'>,
    default: 'table'
  },

  // Сортировка
  sortField: {
    type: String,
    default: 'created_at'
  },
  sortOrder: {
    type: String as PropType<'asc' | 'desc'>,
    default: 'desc'
  },

  // Выбранные элементы (для массовых действий)
  selectedVehicles: {
    type: Array as PropType<UUID[]>,
    default: () => []
  },

  // Конфигурация отображения
  showImportButton: {
    type: Boolean,
    default: false
  },
  showExportButton: {
    type: Boolean,
    default: false
  },
  showBulkActions: {
    type: Boolean,
    default: false
  },
  showDuplicateButton: {
    type: Boolean,
    default: false
  },
  showBrandFilter: {
    type: Boolean,
    default: true
  }
})

defineEmits<{
  add: []
  import: []
  export: []
  view: [vehicle: Vehicle]
  edit: [vehicle: Vehicle]
  delete: [vehicle: Vehicle]
  duplicate: [vehicle: Vehicle]
  retry: []
  'change-page': [page: number]
  sort: [field: string]
  'reset-filters': []
  'update:filters': [filters: WarehouseFilters]
  'update:viewMode': [viewMode: 'table' | 'cards']
  'toggle-select': [vehicleId: UUID]
  'toggle-select-all': []
  'clear-selection': []
  'bulk-edit': []
  'bulk-delete': []
}>()

// Вычисляемые свойства
const visiblePages = computed(() => {
  if (!props.pagination || props.pagination.pages <= 1) return []
  
  const current = props.pagination.page
  const total = props.pagination.pages
  const pages = []
  
  let start = Math.max(1, current - 2)
  let end = Math.min(total, start + 4)
  
  if (end - start < 4) {
    start = Math.max(1, end - 4)
  }
  
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  
  return pages
})

const isAllSelected = computed(() => {
  return props.vehicles.length > 0 && props.selectedVehicles.length === props.vehicles.length
})

// Методы для получения данных автомобиля (поддержка разных структур данных)
const getVehicleImage = (vehicle: Vehicle): string | undefined => {
  // Поддержка разных форматов изображений
  if (vehicle.images && vehicle.images.length > 0) {
    return vehicleImageUrl(vehicle.images[0])
  }
  if (vehicle.main_image) {
    if (vehicle.main_image.startsWith('http')) {
      return vehicle.main_image
    }
    return vehicleImageUrl(vehicle.main_image)
  }
  return undefined
}

const getVehicleName = (vehicle: Vehicle): string => {
  const brand = getVehicleBrand(vehicle)
  const model = getVehicleModel(vehicle)
  return `${brand} ${model}`
}

const getVehicleBrand = (vehicle: Vehicle): string => {
  return vehicle.mark_name || vehicle.brand_name || vehicle.mark_id as string || ''
}

const getVehicleModel = (vehicle: Vehicle): string => {
  return vehicle.model_name || vehicle.model_id as string || ''
}

const getVehiclePrice = (vehicle: Vehicle): number => {
  return vehicle.base_price || vehicle.price || 0
}

// Вспомогательные функции для статусов
const getStatusClass = (status: string | undefined): string => {
  const classes: Record<string, string> = {
    available: 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]',
    reserved: 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#854d0e)]',
    sold: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]',
    maintenance: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]'
  }
  return (status && classes[status]) || 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
}


</script>
