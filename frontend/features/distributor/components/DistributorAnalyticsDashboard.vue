<template>
  <div class="analytics-dashboard">
    <!-- Page header -->
    <header class="dash-header">
      <div class="dash-header-text">
        <h1 class="dash-title">{{ pageTitle }}</h1>
        <p class="dash-subtitle">{{ activeTabLabel }}</p>
      </div>
      <button class="dash-refresh" :disabled="isLoading" @click="refresh">
        <svg class="dash-refresh-icon" :class="{ spinning: isLoading }" width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Обновить
      </button>
    </header>

    <!-- Tabs -->
    <div class="tabs-bar">
      <nav class="tabs-nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-button"
          :class="{ active: activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </nav>
    </div>

    <ApplicationStatusFunnel
      v-if="activeTab === 'applications'"
      ref="applicationStatusFunnelRef"
    />

    <!-- Filter Bar -->
    <div v-if="activeTab !== 'team'" class="filter-bar">
      <div class="filter-bar-inner">
        <!-- Date range -->
        <div class="filter-group filter-group--date">
          <label class="filter-label">Дата заявки*</label>
          <div class="filter-date-range">
            <input
              v-model="filters.period_from"
              type="date"
              class="filter-date-input"
            />
            <span class="filter-date-sep">—</span>
            <input
              v-model="filters.period_to"
              type="date"
              class="filter-date-input"
            />
          </div>
        </div>

        <!-- Month selector for Sales DC tabs -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Месяц</label>
          <select v-model="filters.month" class="filter-select">
            <option value="">Все</option>
            <option v-for="m in MONTH_OPTIONS" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
        </div>

        <!-- Period selector for other local-filter tabs -->
        <div v-if="false" class="filter-group filter-group--date">
          <label class="filter-label">Период</label>
          <div class="filter-date-range">
            <input v-model="filters.period_from" type="date" class="filter-date-input" />
            <span class="filter-date-sep">—</span>
            <input v-model="filters.period_to" type="date" class="filter-date-input" />
          </div>
        </div>

        <!-- Previous period for applications -->
        <div v-if="false" class="filter-group filter-group--date">
          <label class="filter-label">Предыдущий период</label>
          <div class="filter-date-range">
            <input v-model="filters.prev_period_from" type="date" class="filter-date-input" />
            <span class="filter-date-sep">—</span>
            <input v-model="filters.prev_period_to" type="date" class="filter-date-input" />
          </div>
        </div>

        <!-- City -->
        <div v-if="activeTab !== 'exchange'" class="filter-group">
          <label class="filter-label">Город</label>
          <select v-model="filters.cities" class="filter-select">
            <option value="">Все</option>
            <option v-for="c in CITY_OPTIONS" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </div>

        <!-- Mark -->
        <div v-if="showVehicleFilters" class="filter-group">
          <label class="filter-label">Марка</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="markDropdownOpen = !markDropdownOpen">
              <span class="truncate">{{ filters.marks.length ? `${filters.marks.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="markDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in MARK_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.marks, opt.value)">
                <input type="checkbox" :checked="filters.marks.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Model (dependent on mark) -->
        <div v-if="showVehicleFilters" class="filter-group">
          <label class="filter-label">Модель</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="modelDropdownOpen = !modelDropdownOpen">
              <span class="truncate">{{ filters.models.length ? `${filters.models.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="modelDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in availableModels" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.models, opt.value)">
                <input type="checkbox" :checked="filters.models.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Statuses (context-aware: applications buckets / warehouse codes) -->
        <div v-if="['applications', 'warehouse'].includes(activeTab)" class="filter-group">
          <label class="filter-label">{{ statusLabelTitle }}</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="statusDropdownOpen = !statusDropdownOpen">
              <span class="truncate">{{ currentStatusArray.length ? `${currentStatusArray.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="statusDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in currentStatusOptions" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(currentStatusArray, opt.value)">
                <input type="checkbox" :checked="currentStatusArray.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== TAB-SPECIFIC FILTERS ===== -->

        <!-- Applications: Dealer Group -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Группа дилеров</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="dealerGroupDropdownOpen = !dealerGroupDropdownOpen">
              <span class="truncate">{{ filters.dealer_groups.length ? `${filters.dealer_groups.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="dealerGroupDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in DEALER_GROUP_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.dealer_groups, opt.value)">
                <input type="checkbox" :checked="filters.dealer_groups.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Applications / Sales-DC: Dealer -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Дилер</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="dealerDropdownOpen = !dealerDropdownOpen">
              <span class="truncate">{{ filters.dealers.length ? `${filters.dealers.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="dealerDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in DEALER_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.dealers, opt.value)">
                <input type="checkbox" :checked="filters.dealers.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Applications / Sales-DC: Leasing -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Лизинговая</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="leasingDropdownOpen = !leasingDropdownOpen">
              <span class="truncate">{{ filters.leasing_companies.length ? `${filters.leasing_companies.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="leasingDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in LEASING_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.leasing_companies, opt.value)">
                <input type="checkbox" :checked="filters.leasing_companies.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Applications: Show Deals -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Сделки</label>
          <label class="inline-flex items-center gap-2 text-sm cursor-pointer">
            <input v-model="filters.show_deals" type="checkbox" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500" />
            Отображать на графике
          </label>
        </div>

        <!-- Financials: Statuses (different from applications) -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Статусы сделок</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="finStatusDropdownOpen = !finStatusDropdownOpen">
              <span class="truncate">{{ filters.fin_statuses.length ? `${filters.fin_statuses.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="finStatusDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in FINANCIAL_STATUS_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.fin_statuses, opt.value)">
                <input type="checkbox" :checked="filters.fin_statuses.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Financials: Dealer -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Дилер</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="finDealerDropdownOpen = !finDealerDropdownOpen">
              <span class="truncate">{{ filters.fin_dealers.length ? `${filters.fin_dealers.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="finDealerDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in DEALER_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.fin_dealers, opt.value)">
                <input type="checkbox" :checked="filters.fin_dealers.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Financials: Leasing -->
        <div v-if="activeTab === 'financials'" class="filter-group">
          <label class="filter-label">Лизинговая</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="finLeasingDropdownOpen = !finLeasingDropdownOpen">
              <span class="truncate">{{ filters.fin_leasing.length ? `${filters.fin_leasing.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="finLeasingDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in LEASING_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.fin_leasing, opt.value)">
                <input type="checkbox" :checked="filters.fin_leasing.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Exchange: Status -->
        <div v-if="activeTab === 'exchange'" class="filter-group">
          <label class="filter-label">Статус биржи</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="excStatusDropdownOpen = !excStatusDropdownOpen">
              <span class="truncate">{{ filters.exc_statuses.length ? `${filters.exc_statuses.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="excStatusDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in EXCHANGE_STATUS_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.exc_statuses, opt.value)">
                <input type="checkbox" :checked="filters.exc_statuses.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Sales DC: Dealer Group -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Группа дилеров</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="salesDealerGroupDropdownOpen = !salesDealerGroupDropdownOpen">
              <span class="truncate">{{ filters.sales_dealer_groups.length ? `${filters.sales_dealer_groups.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="salesDealerGroupDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in DEALER_GROUP_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.sales_dealer_groups, opt.value)">
                <input type="checkbox" :checked="filters.sales_dealer_groups.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Sales DC: Dealer -->
        <div v-if="false" class="filter-group">
          <label class="filter-label">Дилер</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="salesDealerDropdownOpen = !salesDealerDropdownOpen">
              <span class="truncate">{{ filters.sales_dealers.length ? `${filters.sales_dealers.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="salesDealerDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in DEALER_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.sales_dealers, opt.value)">
                <input type="checkbox" :checked="filters.sales_dealers.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Sales DC Regions: Mark -->
        <div v-if="showVehicleFilters && activeTab === 'sales-dc-regions'" class="filter-group">
          <label class="filter-label">Марка</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="sdrMarkDropdownOpen = !sdrMarkDropdownOpen">
              <span class="truncate">{{ filters.sdr_marks.length ? `${filters.sdr_marks.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="sdrMarkDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in MARK_OPTIONS" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.sdr_marks, opt.value)">
                <input type="checkbox" :checked="filters.sdr_marks.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Sales DC Regions: Model -->
        <div v-if="showVehicleFilters && activeTab === 'sales-dc-regions'" class="filter-group">
          <label class="filter-label">Модель</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="sdrModelDropdownOpen = !sdrModelDropdownOpen">
              <span class="truncate">{{ filters.sdr_models.length ? `${filters.sdr_models.length} выбрано` : 'Все' }}</span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
            </button>
            <div v-if="sdrModelDropdownOpen" class="filter-dropdown absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto">
              <div v-for="opt in availableModels" :key="opt.value" class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer" @click.stop="toggleArrayValue(filters.sdr_models, opt.value)">
                <input type="checkbox" :checked="filters.sdr_models.includes(opt.value)" class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 pointer-events-none" />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Reset button only -->
        <div class="filter-actions">
          <button class="filter-btn filter-btn_reset" @click="resetFilters">
            Сбросить
          </button>
        </div>
      </div>
    </div>

    <!-- Loading Skeleton -->
    <div v-if="isLoading" class="dash-grid">
      <!-- Applications now contains four full-width widgets and no KPI row. -->
      <template v-if="activeTab === 'applications'">
        <div v-for="i in 4" :key="`applications-widget-${i}`" class="chart-wide">
          <div
            class="bg-white rounded p-4 animate-pulse"
            :class="i <= 2 ? 'h-80' : 'h-72'"
          />
        </div>
      </template>
      <template v-else>
        <div v-for="i in 4" :key="i" class="kpi-span-3">
          <div class="bg-white rounded p-4 animate-pulse h-24" />
        </div>
        <div class="chart-wide">
          <div class="bg-white rounded p-4 animate-pulse h-80" />
        </div>
        <div class="chart-half">
          <div class="bg-white rounded p-4 animate-pulse h-72" />
        </div>
        <div class="chart-half">
          <div class="bg-white rounded p-4 animate-pulse h-72" />
        </div>
      </template>
    </div>

    <!-- Error State -->
    <div
      v-else-if="error"
      class="bg-white rounded p-8 flex flex-col items-center justify-center text-center"
    >
      <svg class="w-10 h-10 mb-3 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <p class="text-sm font-medium text-gray-900 mb-1">Не удалось загрузить данные</p>
      <p class="text-sm text-gray-500 mb-4">{{ error }}</p>
      <button
        class="px-4 py-2 rounded text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
        @click="refresh"
      >
        Повторить
      </button>
    </div>

    <!-- Tab Content -->
    <div v-else>
      <WarehouseTab
        v-if="activeTab === 'warehouse'"
        :data="displayData as any"
        :loading="isLoading"
        @page-change="onPageChange"
      />
      <ApplicationsTab
        v-else-if="activeTab === 'applications'"
        :data="displayData as any"
        :loading="isLoading"
        @page-change="onPageChange"
      />
      <ExchangeTab
        v-else-if="activeTab === 'exchange'"
        :data="displayData as any"
        :loading="isLoading"
        @page-change="onPageChange"
      />
      <FinancialsTab
        v-else-if="activeTab === 'financials'"
        :data="displayData as any"
        :loading="isLoading"
        @page-change="onPageChange"
      />
      <SalesDcTab
        v-else-if="activeTab === 'sales-dc'"
        :data="displayData as any"
        :loading="isLoading"
        @page-change="onPageChange"
      />
      <SalesDcRegionsTab
        v-else-if="activeTab === 'sales-dc-regions'"
        :data="displayData as any"
        :loading="isLoading"
        @page-change="onPageChange"
      />
      <TeamTab
        v-else-if="activeTab === 'team'"
        :data="displayData as any"
        :loading="isLoading"
        @page-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import WarehouseTab from './tabs/WarehouseTab.vue'
import ApplicationsTab from './tabs/ApplicationsTab.vue'
import FinancialsTab from './tabs/FinancialsTab.vue'
import SalesDcTab from './tabs/SalesDcTab.vue'
import SalesDcRegionsTab from './tabs/SalesDcRegionsTab.vue'
import ExchangeTab from './tabs/ExchangeTab.vue'
import TeamTab from './tabs/TeamTab.vue'
import ApplicationStatusFunnel from './ApplicationStatusFunnel.vue'
import { fetchDistributorAnalytics, getDistributorAnalyticsErrorMessage } from '../api/analytics'
import type { DistributorDashboardTab, DistributorDashboardResponse, DistributorDashboardFilters } from '../api/analytics'
import type { UUID } from '~/types/ids'
import { useAuthStore } from '~/features/auth/store/auth'

const authStore = useAuthStore()

// ============================================================================
// Constants / Options
// ============================================================================

const MONTH_OPTIONS = [
  { value: '2024-01', label: 'Январь 2024' },
  { value: '2024-02', label: 'Февраль 2024' },
  { value: '2024-03', label: 'Март 2024' },
  { value: '2024-04', label: 'Апрель 2024' },
  { value: '2024-05', label: 'Май 2024' },
  { value: '2024-06', label: 'Июнь 2024' },
  { value: '2024-07', label: 'Июль 2024' },
  { value: '2024-08', label: 'Август 2024' },
  { value: '2024-09', label: 'Сентябрь 2024' },
  { value: '2024-10', label: 'Октябрь 2024' },
  { value: '2024-11', label: 'Ноябрь 2024' },
  { value: '2024-12', label: 'Декабрь 2024' },
]

const CITY_OPTIONS = [
  { value: 'Москва', label: 'Москва' },
  { value: 'Санкт-Петербург', label: 'Санкт-Петербург' },
  { value: 'Казань', label: 'Казань' },
  { value: 'Екатеринбург', label: 'Екатеринбург' },
  { value: 'Новосибирск', label: 'Новосибирск' },
  { value: 'Ростов-на-Дону', label: 'Ростов-на-Дону' },
  { value: 'Калининград', label: 'Калининград' },
  { value: 'Петрозаводск', label: 'Петрозаводск' },
  { value: 'Зеленоград', label: 'Зеленоград' },
  { value: 'Подольск', label: 'Подольск' },
]

// Marks / models mirror the seeded vehicle catalog (vehicles store the mark/model
// NAME in mark_id/model_id), so these filter values match dwh_vehicles directly.
const MODEL_MAP: Record<string, string[]> = {
  Lada: ['Vesta', 'Granta', 'Largus', 'Niva'],
  Kia: ['Rio', 'Sportage', 'Seltos', 'Sorento'],
  Hyundai: ['Solaris', 'Creta', 'Tucson', 'Santa Fe'],
  Toyota: ['Camry', 'RAV4', 'Corolla', 'Land Cruiser'],
  Haval: ['Jolion', 'F7', 'Dargo', 'H9'],
  Chery: ['Tiggo 4', 'Tiggo 7', 'Tiggo 8', 'Arrizo 8'],
  Geely: ['Coolray', 'Atlas', 'Tugella', 'Monjaro'],
  Omoda: ['C5', 'S5', 'C5 GT', 'S5 GT'],
}

const MARK_OPTIONS = Object.keys(MODEL_MAP).map((m) => ({ value: m, label: m }))

const ALL_MODELS = Object.entries(MODEL_MAP).flatMap(([mark, models]) =>
  models.map((model) => ({ value: model, label: `${mark} ${model}` })),
)

// Warehouse statuses: values are the raw english codes the backend filters on
// (`v.status IN [...]`), labels are russian (contract §2).
const STATUS_OPTIONS = [
  { value: 'available', label: 'В наличии' },
  { value: 'reserved', label: 'В резерве' },
  { value: 'sold', label: 'Продано' },
  { value: 'in_transit', label: 'В пути' },
  { value: 'unknown', label: 'Неизвестно' },
]

// Application/financial statuses are sent as BUCKETS (active|rejected|issued);
// the backend expands them via status_buckets_to_conditions on la.status.
const APPLICATION_STATUS_OPTIONS = [
  { value: 'active', label: 'Активные' },
  { value: 'rejected', label: 'Отклонённые' },
  { value: 'issued', label: 'Выданные' },
]

const FINANCIAL_STATUS_OPTIONS = [
  { value: 'active', label: 'Активные' },
  { value: 'rejected', label: 'Отклонённые' },
  { value: 'issued', label: 'Выданные' },
]

// Exchange request statuses (raw er.status values).
const EXCHANGE_STATUS_OPTIONS = [
  { value: 'active', label: 'Активен' },
  { value: 'closed', label: 'Закрыт' },
  { value: 'cancelled', label: 'Отменён' },
]

const DEALER_GROUP_OPTIONS = [
  { value: 'group1', label: 'Группа 1' },
  { value: 'group2', label: 'Группа 2' },
]

const DEALER_OPTIONS = [
  { value: 'АвтоГрад Москва', label: 'АвтоГрад Москва' },
  { value: 'МоторПлюс СПб', label: 'МоторПлюс СПб' },
  { value: 'Дилер Центр Казань', label: 'Дилер Центр Казань' },
  { value: 'АвтоМир Екатеринбург', label: 'АвтоМир Екатеринбург' },
  { value: 'ТопАвто Новосибирск', label: 'ТопАвто Новосибирск' },
  { value: 'Премиум Моторс', label: 'Премиум Моторс' },
  { value: 'Сити Авто Ростов', label: 'Сити Авто Ростов' },
  { value: 'Гранд Мотор', label: 'Гранд Мотор' },
  { value: 'АвтоЛюкс Казань', label: 'АвтоЛюкс Казань' },
  { value: 'ДВ-Авто Владивосток', label: 'ДВ-Авто Владивосток' },
  { value: 'Автомир Нижний Новгород', label: 'Автомир Нижний Новгород' },
  { value: 'УралАвто Челябинск', label: 'УралАвто Челябинск' },
  { value: 'ЮгАвто Краснодар', label: 'ЮгАвто Краснодар' },
  { value: 'ВолгаАвто Самарa', label: 'ВолгаАвто Самара' },
  { value: 'СибАвто Омск', label: 'СибАвто Омск' },
  { value: 'Дилер-Плюс Воронеж', label: 'Дилер-Плюс Воронеж' },
  { value: 'АвтоСити Пермь', label: 'АвтоСити Пермь' },
  { value: 'Мотор-Хаус Тюмень', label: 'Мотор-Хаус Тюмень' },
]

const LEASING_OPTIONS = [
  { value: 'Европлан', label: 'Европлан' },
  { value: 'ВТБ Лизинг', label: 'ВТБ Лизинг' },
  { value: 'СберЛизинг', label: 'СберЛизинг' },
  { value: 'Росбанк Лизинг', label: 'Росбанк Лизинг' },
  { value: 'Уралсиб Лизинг', label: 'Уралсиб Лизинг' },
]

// ============================================================================
// Tabs
// ============================================================================

type TabKey = DistributorDashboardTab

const ALL_TABS: ReadonlyArray<{ key: TabKey; label: string }> = [
  { key: 'warehouse', label: 'Склад' },
  { key: 'applications', label: 'Лизинговые сделки' },
  { key: 'exchange', label: 'Биржа ТС' },
  { key: 'financials', label: 'Финансы' },
  { key: 'sales-dc', label: 'Продажи ДЦ' },
  { key: 'sales-dc-regions', label: 'Продажи ДЦ по регионам/маркам' },
  { key: 'team', label: 'Анализ по сотрудникам' },
] as const

const tabs = computed(() => (
  authStore.isDealer
    ? ALL_TABS.filter((tab) => tab.key === 'applications')
    : ALL_TABS
))

// ============================================================================
// State
// ============================================================================

const activeTab = ref<TabKey>(authStore.isDealer ? 'applications' : 'warehouse')
const applicationStatusFunnelRef = ref<{ refresh: () => void } | null>(null)
const isLoading = ref(false)
const error = ref('')
const displayData = ref<DistributorDashboardResponse | null>(null)
const paginationByTab = ref<Record<DistributorDashboardTab, { page: number; limit: number }>>({
  warehouse: { page: 1, limit: 20 },
  applications: { page: 1, limit: 20 },
  exchange: { page: 1, limit: 20 },
  financials: { page: 1, limit: 20 },
  'sales-dc': { page: 1, limit: 20 },
  'sales-dc-regions': { page: 1, limit: 20 },
  team: { page: 1, limit: 20 },
})

// Abort controller for debounced reload
let currentAbort: AbortController | null = null
let hasMounted = false

const filters = ref({
  period_from: '',
  period_to: '',
  prev_period_from: '',
  prev_period_to: '',
  month: '',
  statuses: [] as string[],
  marks: [] as string[],
  models: [] as string[],
  cities: '' as string,
  dealers: [] as UUID[],
  dealer_groups: [] as string[],
  leasing_companies: [] as string[],
  // Applications-specific
  app_statuses: [] as string[],
  show_deals: false,
  // Financials-specific
  fin_statuses: [] as string[],
  fin_dealers: [] as UUID[],
  fin_leasing: [] as string[],
  // Exchange-specific
  exc_statuses: [] as string[],
  // Sales DC-specific
  sales_dealer_groups: [] as string[],
  sales_dealers: [] as UUID[],
  // Sales DC Regions-specific
  sdr_marks: [] as string[],
  sdr_models: [] as string[],
})

// ============================================================================
// Dropdown states
// ============================================================================

const statusDropdownOpen = ref(false)
const markDropdownOpen = ref(false)
const modelDropdownOpen = ref(false)
const appStatusDropdownOpen = ref(false)
const finStatusDropdownOpen = ref(false)
const excStatusDropdownOpen = ref(false)
const dealerGroupDropdownOpen = ref(false)
const salesDealerGroupDropdownOpen = ref(false)
const salesDealerDropdownOpen = ref(false)
const dealerDropdownOpen = ref(false)
const finDealerDropdownOpen = ref(false)
const leasingDropdownOpen = ref(false)
const finLeasingDropdownOpen = ref(false)
const sdrMarkDropdownOpen = ref(false)
const sdrModelDropdownOpen = ref(false)

// ============================================================================
// Computed
// ============================================================================

const activeTabLabel = computed(() => {
  return tabs.value.find((t) => t.key === activeTab.value)?.label ?? ''
})

const pageTitle = computed(() => {
  if (authStore.isDealer) return 'Аналитика дилера'
  if (authStore.isDistributor) return 'Аналитика дистрибьютора'
  return 'Аналитика'
})

const isLocalFilterTab = computed(() => {
  return ['applications', 'sales-dc', 'sales-dc-regions'].includes(activeTab.value)
})

const showVehicleFilters = computed(() => false)

const statusLabelTitle = computed(() => {
  if (activeTab.value === 'applications') return 'Статусы заявок'
  if (activeTab.value === 'exchange') return 'Статус биржи'
  return 'Статусы'
})

// The shared status dropdown is only shown on applications + warehouse (other
// tabs have their own dedicated status dropdowns or none).
const currentStatusOptions = computed(() =>
  activeTab.value === 'applications' ? APPLICATION_STATUS_OPTIONS : STATUS_OPTIONS,
)

// Bind the shared dropdown to a per-tab array so applications (buckets) and
// warehouse (raw codes) never write into the same selection.
const currentStatusArray = computed(() =>
  activeTab.value === 'applications' ? filters.value.app_statuses : filters.value.statuses,
)

const availableModels = computed(() => {
  if (!filters.value.marks.length) return ALL_MODELS
  const allowed = new Set<string>()
  for (const mark of filters.value.marks) {
    const models = MODEL_MAP[mark] || []
    models.forEach((m) => allowed.add(m))
  }
  return ALL_MODELS.filter((opt) => allowed.has(opt.value))
})

// ============================================================================
// Helpers
// ============================================================================

function toggleArrayValue(arr: string[], value: string) {
  const idx = arr.indexOf(value)
  if (idx > -1) {
    arr.splice(idx, 1)
  } else {
    arr.push(value)
  }
}

// ============================================================================
// Data loading with debounce
// ============================================================================

function scheduleLoad() {
  // Cancel any pending load
  if (currentAbort) {
    currentAbort.abort()
  }

  const controller = new AbortController()
  currentAbort = controller

  setTimeout(() => {
    if (controller.signal.aborted) return
    loadTabData()
  }, 250)
}

function loadTabData() {
  isLoading.value = true
  error.value = ''

  const tab = activeTab.value as DistributorDashboardTab
  const payload = buildFilterPayload(tab)

  // Fetch real data. An HTTP 200 with empty widgets is a valid success — each
  // per-tab component renders its own natural empty state. Any failure surfaces
  // the error state with a retry button.
  fetchDistributorAnalytics(tab, payload)
    .then((result) => {
      // Ignore stale responses if the tab changed while the request was in flight.
      if (activeTab.value !== tab) return
      displayData.value = result
      isLoading.value = false
    })
    .catch((err: unknown) => {
      if (activeTab.value !== tab) return
      error.value = getDistributorAnalyticsErrorMessage(err)
      displayData.value = null
      isLoading.value = false
    })
}

// ============================================================================
// Tab switching
// ============================================================================

function switchTab(tab: TabKey) {
  activeTab.value = tab
  // Reset dropdowns
  closeAllDropdowns()
  if (tab === 'team') {
    displayData.value = null
    error.value = ''
    isLoading.value = false
    return
  }
  loadTabData()
}

function refresh() {
  scheduleLoad()
  if (activeTab.value === 'applications') {
    applicationStatusFunnelRef.value?.refresh()
  }
}

// ============================================================================
// Filter reset
// ============================================================================

function resetFilters() {
  filters.value = {
    period_from: '',
    period_to: '',
    prev_period_from: '',
    prev_period_to: '',
    month: '',
    statuses: [],
    marks: [],
    models: [],
    cities: '',
    dealers: [],
    dealer_groups: [],
    leasing_companies: [],
    app_statuses: [],
    show_deals: false,
    fin_statuses: [],
    fin_dealers: [],
    fin_leasing: [],
    exc_statuses: [],
    sales_dealer_groups: [],
    sales_dealers: [],
    sdr_marks: [],
    sdr_models: [],
  }
  closeAllDropdowns()
  scheduleLoad()
}

// ============================================================================
// Dropdown management
// ============================================================================

function closeAllDropdowns() {
  statusDropdownOpen.value = false
  markDropdownOpen.value = false
  modelDropdownOpen.value = false
  appStatusDropdownOpen.value = false
  finStatusDropdownOpen.value = false
  excStatusDropdownOpen.value = false
  dealerGroupDropdownOpen.value = false
  salesDealerGroupDropdownOpen.value = false
  salesDealerDropdownOpen.value = false
  dealerDropdownOpen.value = false
  finDealerDropdownOpen.value = false
  leasingDropdownOpen.value = false
  finLeasingDropdownOpen.value = false
  sdrMarkDropdownOpen.value = false
  sdrModelDropdownOpen.value = false
}

function buildFilterPayload(tab: DistributorDashboardTab): DistributorDashboardFilters {
  const f = filters.value
  const pagination = paginationByTab.value[tab]
  const periodFrom = f.month ? `${f.month}-01` : f.period_from || undefined
  const periodTo = f.month ? lastDayOfMonth(f.month) : f.period_to || undefined

  // Shared filters every route accepts. Query-param names map 1:1 to the
  // backend (period_from, period_to, cities[], marks[], models[], dealers[],
  // leasing_companies[], statuses[]).
  const payload: DistributorDashboardFilters = {
    period_from: periodFrom,
    period_to: periodTo,
    page: pagination.page,
    limit: pagination.limit,
    cities: f.cities ? [f.cities] : [],
    marks: [],
    models: [],
    dealers: [],
    dealer_groups: [],
    leasing_companies: [],
    statuses: [],
  }

  // Per-tab scoping: send only the status array and the dealer/leasing/mark
  // selections that belong to the active tab — never merge every tab's filters
  // into a single request.
  switch (tab) {
    case 'applications':
      payload.statuses = f.app_statuses
      break
    case 'exchange':
      payload.statuses = f.exc_statuses
      break
    case 'financials':
      payload.statuses = f.fin_statuses
      break
    case 'warehouse':
      payload.statuses = f.statuses
      break
    case 'sales-dc':
      break
    case 'sales-dc-regions':
      break
  }

  return payload
}

function onClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  // Close dropdowns only when clicking outside any filter group (button + dropdown)
  if (!target.closest('.filter-group')) {
    closeAllDropdowns()
  }
}

// ============================================================================
// Pagination
// ============================================================================

function onPageChange(offset: number) {
  const tab = activeTab.value as DistributorDashboardTab
  const current = paginationByTab.value[tab]
  paginationByTab.value[tab] = {
    ...current,
    page: Math.floor(offset / current.limit) + 1,
  }
  loadTabData()
}

// ============================================================================
// Reactive watchers — filters auto-apply on change
// ============================================================================

watch(
  () => ({ ...filters.value }),
  () => {
    paginationByTab.value[activeTab.value as DistributorDashboardTab].page = 1
    scheduleLoad()
  },
  { deep: true, immediate: false },
)

watch(
  () => authStore.userRole,
  (role) => {
    if (role !== 'dealer' || activeTab.value === 'applications') return
    activeTab.value = 'applications'
    closeAllDropdowns()
    if (hasMounted) loadTabData()
  },
  { immediate: true },
)

function lastDayOfMonth(month: string): string | undefined {
  const [yearText, monthText] = month.split('-')
  const year = Number(yearText)
  const monthIndex = Number(monthText)
  if (!year || !monthIndex) return undefined
  const date = new Date(year, monthIndex, 0)
  return `${yearText}-${monthText}-${String(date.getDate()).padStart(2, '0')}`
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  hasMounted = true
  loadTabData()
  document.addEventListener('click', onClickOutside)
})

onBeforeUnmount(() => {
  hasMounted = false
  if (currentAbort) currentAbort.abort()
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
.analytics-dashboard {
  padding: 16px;
  background: #F0F2F5;
  min-height: 100vh;
}

/* Filter Bar */
.filter-bar {
  background: #ffffff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
  margin-bottom: 16px;
  padding: 12px 16px;
}

.filter-bar-inner {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 140px;
  flex: 1 1 0;
}

.filter-label {
  font-size: 12px;
  font-weight: 500;
  color: #6b7280;
}

.filter-date-range {
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-date-input {
  padding: 6px 8px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  color: #111827;
  background: #fff;
  min-width: 0;
  flex: 1 1 0;
}

.filter-date-sep {
  color: #9ca3af;
  font-size: 13px;
}

.filter-select {
  padding: 6px 24px 6px 8px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  color: #111827;
  background: #fff;
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 6px center;
  background-repeat: no-repeat;
  background-size: 16px;
  min-width: 0;
}

.filter-select_button {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
  background-image: none;
  cursor: pointer;
}

.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
  padding-bottom: 1px;
}

.filter-btn {
  padding: 6px 14px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: none;
}

.filter-btn_reset {
  background: transparent;
  color: #6b7280;
}

.filter-btn_reset:hover {
  color: #111827;
  background: #f3f4f6;
}

/* Tabs */
.tabs-bar {
  background: #ffffff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
  margin-bottom: 16px;
  overflow-x: auto;
}

.tabs-nav {
  display: flex;
  min-width: max-content;
}

.tab-button {
  flex-shrink: 0;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
  color: #6b7280;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
  white-space: nowrap;
  background: none;
  border-top: none;
  border-left: none;
  border-right: none;
  cursor: pointer;
}

.tab-button:hover {
  color: #111827;
  background: #f9fafb;
}

.tab-button.active {
  color: #0077CC;
  border-bottom-color: #0077CC;
  background: #f0f9ff;
}

/* Dash Grid */
.dash-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 16px;
}

.kpi-span-3 {
  grid-column: span 3;
  padding: 16px;
}

.chart-wide {
  grid-column: span 12;
}

.chart-half {
  grid-column: span 6;
}

@media (max-width: 1024px) {
  .kpi-span-3 {
    grid-column: span 4;
  }
  .chart-half {
    grid-column: span 12;
  }
}

/* ============================================================ */
/* Modern look (appended — overrides the base rules above)      */
/* ============================================================ */

.analytics-dashboard {
  padding: 22px 24px 40px;
  background:
    radial-gradient(1200px 400px at 100% -10%, #eaf2ff 0%, rgba(234, 242, 255, 0) 60%),
    #f4f6f9;
}

/* Page header */
.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.dash-title {
  font-size: 23px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.dash-subtitle {
  margin-top: 3px;
  font-size: 13px;
  color: #64748b;
}

.dash-refresh {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  cursor: pointer;
  transition: all 0.15s ease;
}

.dash-refresh:hover:not(:disabled) {
  border-color: #c7d2e0;
  color: #0f172a;
  box-shadow: 0 2px 6px rgba(16, 24, 40, 0.08);
}

.dash-refresh:disabled {
  opacity: 0.6;
  cursor: default;
}

.dash-refresh-icon.spinning {
  animation: dash-spin 0.9s linear infinite;
}

@keyframes dash-spin {
  to {
    transform: rotate(360deg);
  }
}

/* Filter bar */
.filter-bar {
  border: 1px solid #e8ebf1;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 4px 12px rgba(16, 24, 40, 0.03);
  padding: 14px 16px;
}

/* Compact uniform grid — filters never stretch; they tile neatly and wrap. */
.filter-bar-inner {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
  gap: 10px 12px;
  align-items: end;
}

.filter-group {
  min-width: 0;
  flex: initial;
}

/* Date range needs room for both inputs. */
.filter-group--date {
  grid-column: span 2;
}

/* Reset sits on its own trailing row, right-aligned. */
.filter-actions {
  grid-column: 1 / -1;
  margin-left: 0;
  justify-content: flex-end;
  padding-bottom: 0;
}

/* Uniform control height for a tidy single-line look. */
.filter-date-input,
.filter-select,
.filter-select_button {
  height: 36px;
  box-sizing: border-box;
}

.filter-select_button {
  font-size: 13px;
  color: #111827;
}

.filter-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #94a3b8;
}

.filter-date-input,
.filter-select {
  border: 1px solid #dbe0e8;
  border-radius: 9px;
  padding: 8px 10px;
  font-size: 13px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.filter-select {
  padding-right: 26px;
}

.filter-date-input:focus,
.filter-select:focus,
.filter-select_button:focus-visible {
  outline: none;
  border-color: #0077cc;
  box-shadow: 0 0 0 3px rgba(0, 119, 204, 0.15);
}

.filter-dropdown {
  border-radius: 10px !important;
  border-color: #e8ebf1 !important;
  box-shadow: 0 10px 30px rgba(16, 24, 40, 0.12) !important;
}

.filter-btn_reset {
  border: 1px solid #e2e8f0;
  border-radius: 9px;
}

/* Tabs — pill style */
.tabs-bar {
  border: 1px solid #e8ebf1;
  border-radius: 14px;
  padding: 5px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}

.tabs-nav {
  gap: 3px;
}

.tab-button {
  border-radius: 9px;
  padding: 9px 15px;
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  border-bottom: none !important;
  transition: all 0.15s ease;
}

.tab-button:hover {
  color: #0f172a;
  background: #f1f5f9;
}

.tab-button.active {
  color: #ffffff;
  background: linear-gradient(180deg, #1f8fe6 0%, #0077cc 100%);
  border-bottom: none !important;
  box-shadow: 0 2px 6px rgba(0, 119, 204, 0.3);
}

/* Cards — elevated, rounded, hover lift (scoped to this dashboard) */
.analytics-dashboard :deep(.widget-card) {
  border-radius: 14px;
  border: 1px solid #ecf0f5;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 4px 14px rgba(16, 24, 40, 0.035);
  transition: box-shadow 0.18s ease, transform 0.18s ease;
}

.analytics-dashboard :deep(.widget-card:hover) {
  box-shadow: 0 2px 4px rgba(16, 24, 40, 0.06), 0 12px 28px rgba(16, 24, 40, 0.08);
  transform: translateY(-2px);
}

.analytics-dashboard :deep(.widget-title) {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

/* KPI cards */
.analytics-dashboard :deep(.kpi-title) {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #94a3b8;
}

.analytics-dashboard :deep(.kpi-value) {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

/* Tables */
.analytics-dashboard :deep(.widget-card thead th) {
  background: #f8fafc;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #94a3b8;
  border-bottom: 1px solid #eef2f7;
}

.analytics-dashboard :deep(.widget-card thead th:first-child) {
  border-top-left-radius: 8px;
  border-bottom-left-radius: 8px;
}

.analytics-dashboard :deep(.widget-card thead th:last-child) {
  border-top-right-radius: 8px;
  border-bottom-right-radius: 8px;
}

.analytics-dashboard :deep(.widget-card tbody td) {
  font-variant-numeric: tabular-nums;
  color: #334155;
}

.analytics-dashboard :deep(.widget-card tbody tr:hover) {
  background: #f5f9ff;
}
</style>
