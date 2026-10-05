<template>
  <div data-storefront-block="client.cart"
    v-if="!cartHydrationReady"
    class="min-h-screen bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] py-8 sm:py-10"
    aria-busy="true"
    aria-label="Загрузка корзины"
  >
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="mb-8">
        <h1 class="text-2xl sm:text-3xl font-bold text-[color:var(--storefront-title,#111827)] tracking-tight">Корзина</h1>
        <p class="mt-2 text-sm sm:text-base text-[color:var(--storefront-text-muted,#4b5563)]">{{ isSpecialEquipmentCatalogVisible ? 'Транспортные средства и спецтехника в одной корзине' : 'Выберите автомобили для оформления заявки' }}</p>
      </div>
      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-8" aria-hidden="true">
        <div class="overflow-hidden rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
          <div class="border-b border-[color:var(--storefront-border,#e5e7eb)] px-4 py-5 sm:px-6">
            <div class="h-5 w-52 animate-pulse rounded bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" />
          </div>
          <div class="grid gap-4 p-4 sm:p-6">
            <div
              v-for="index in 2"
              :key="index"
              class="h-32 animate-pulse rounded-xl bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] motion-reduce:animate-none"
            />
          </div>
        </div>
        <div class="h-80 animate-pulse rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" />
      </div>
      <span class="sr-only" role="status">Загружаем корзину</span>
    </div>
  </div>

  <template v-else>
    <ExchangeCartPage v-if="authStore.isLeasingCompany" />
    <div data-storefront-block="client.cart" v-else class="min-h-screen bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] py-8 sm:py-10">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-2xl sm:text-3xl font-bold text-[color:var(--storefront-title,#111827)] tracking-tight">Корзина</h1>
        <p class="mt-2 text-sm sm:text-base text-[color:var(--storefront-text-muted,#4b5563)]">{{ isSpecialEquipmentCatalogVisible ? 'Транспортные средства и спецтехника в одной корзине' : 'Выберите автомобили для оформления заявки' }}</p>
      </div>

      <!-- Loading State -->
      <div v-if="cartStore.loading || (isSpecialEquipmentCatalogVisible && specialEquipmentShell.cartLoading && specialEquipmentShell.cartItems.length === 0)" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      </div>

      <!-- Empty Cart -->
      <div
        v-else-if="unifiedCartEmpty && (!isSpecialEquipmentCatalogVisible || (specialEquipmentShell.cartInitialized && !specialEquipmentShell.cartLoading && !specialEquipmentShell.cartError))"
        class="text-center py-12"
      >
        <div class="max-w-md mx-auto">
          <svg class="h-24 w-24 text-[color:var(--storefront-icon,#9ca3af)] mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6h13.5l-1.5 9H8.5L6 6z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6L4 4H2"></path><circle cx="9" cy="20" r="1.5" stroke-width="2"></circle><circle cx="18" cy="20" r="1.5" stroke-width="2"></circle></svg>
          <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)] mb-2">Корзина пуста</h3>
          <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-6">Добавьте спецтехнику из каталога</p>
          <div class="flex flex-wrap justify-center gap-3">
            <NuxtLink :to="publicRoute('/special-equipment')" class="storefront-action-primary inline-flex min-h-11 items-center px-6 py-3 border border-transparent text-base font-medium rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2">
              {{ pageTitle('special_equipment_catalog') }}
            </NuxtLink>
          </div>
        </div>
      </div>

      <!-- Cart Content -->
      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8 items-start">
        <!-- Cart Items -->
        <div class="min-w-0">
          <section
            v-if="unifiedCartItems.length > 0 || (isSpecialEquipmentCatalogVisible && specialEquipmentShell.cartError)"
            class="rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] overflow-hidden shadow-sm"
            aria-labelledby="transport-vehicles-cart-title"
          >
            <!-- Cart Header -->
            <div class="px-4 sm:px-6 py-4 border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
              <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <h2 id="transport-vehicles-cart-title" class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">
                  Транспортные средства ({{ unifiedCartItems.length }})
                </h2>
                <div class="flex items-center gap-3 sm:gap-4 flex-wrap text-sm">
                  <button 
                    @click="selectAll" 
                    :disabled="allSelected"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)] whitespace-nowrap font-medium"
                  >
                    Выбрать все
                  </button>
                  <span class="inline text-[color:var(--storefront-text,#d1d5db)]" aria-hidden="true">|</span>
                  <button 
                    @click="unselectAll"
                    :disabled="!hasUnifiedSelection"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)] whitespace-nowrap font-medium"
                  >
                    Снять выбор
                  </button>
                  <span class="inline text-[color:var(--storefront-text,#d1d5db)]" aria-hidden="true">|</span>
                  <button 
                    @click="clearCart"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#991b1b)] whitespace-nowrap ml-auto sm:ml-0 font-medium"
                  >
                    Очистить
                  </button>
                </div>
              </div>
            </div>

            <div
              v-if="isSpecialEquipmentCatalogVisible && specialEquipmentShell.cartError"
              class="border-b border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-warning-text,#78350f)] sm:px-6"
              role="status"
            >
              {{ specialEquipmentShell.cartError }}
              <button type="button" class="storefront-action-ghost ml-2 font-semibold underline" @click="specialEquipmentShell.loadCart({ force: true, resolveGuestProducts: true })">
                Повторить
              </button>
            </div>

            <!-- Cart Items List: catalog items (no price/VIN) first -->
            <div v-if="catalogItems.length > 0" class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
              <div class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
                <CartComponentsCartItemCard
                  v-for="item in catalogItems"
                  :key="item.cart_id"
                  :item="item"
                  :unavailable-status="item.unavailable_status"
                  :max-quantity="getMaxQuantity(item)"
                  :equipment-catalog="equipmentCatalog"
                  :service-catalog="serviceCatalog"
                  :calculation-support-programs="calculationData?.support_program_details || []"
                  @update-selection="updateSelection"
                  @update-quantity="updateItemQuantity"
                  @update-price="updateItemPrice"
                  @update-comment="updateItemComment"
                  @update-additional-options="updateItemAdditionalOptions"
                  @remove="removeItem"
                  @detach="detachSpecialEquipmentItem"
                  @open-calculation="openCalculationModal(item)"
                />
              </div>
            </div>

            <!-- Cart Items List: purchasable items (with price and VIN) -->
            <div v-if="stockItems.length > 0">
              <div class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
                <CartComponentsCartItemCard
                  v-for="item in stockItems"
                  :key="item.cart_id"
                  :item="item"
                  :unavailable-status="item.unavailable_status"
                  :max-quantity="getMaxQuantity(item)"
                  :equipment-catalog="equipmentCatalog"
                  :service-catalog="serviceCatalog"
                  :calculation-support-programs="calculationData?.support_program_details || []"
                  @update-selection="updateSelection"
                  @update-quantity="updateItemQuantity"
                  @update-price="updateItemPrice"
                  @update-comment="updateItemComment"
                  @update-additional-options="updateItemAdditionalOptions"
                  @remove="removeItem"
                  @detach="detachSpecialEquipmentItem"
                  @open-calculation="openCalculationModal(item)"
                />
              </div>
            </div>

            <div
              v-for="productId in isSpecialEquipmentCatalogVisible ? specialEquipmentShell.unresolvedCartIds : []"
              :key="productId"
              class="flex items-center justify-between gap-3 border-t border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-4 py-4 sm:px-6"
            >
              <p class="text-sm text-[color:var(--storefront-warning-text,#451a03)]">Карточка транспортного средства временно недоступна</p>
              <button type="button" class="storefront-action-ghost text-sm font-semibold text-[color:var(--storefront-ghost-foreground,#b91c1c)]" @click="removeUnresolvedProduct(productId)">
                Удалить
              </button>
            </div>
          </section>

          <!-- Итого по выбранным (как в макете), но сейчас это говно скрыто -->
          <div
            v-if="calculationData && unifiedSelectedItems.length"
            class="mt-6 rounded-2xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-sm overflow-hidden hidden"
          >
            <div class="px-5 sm:px-6 py-5 border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
              <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                <div class="min-w-0">
                  <h3 class="text-xl font-bold text-[color:var(--storefront-title,#111827)] tracking-tight">Итого по транспортным средствам</h3>
                  <div class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)] space-y-1">
                    <div>
                      <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Выбрано транспортных средств:</span>
                      <span class="font-medium text-[color:var(--storefront-text,#111827)] ml-1">{{ unifiedSelectedCount }}</span>
                    </div>
                    <div>
                      <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Стоимость:</span>
                      <span class="font-semibold text-[color:var(--storefront-text,#111827)] ml-1">{{ formatPrice(unifiedTotalAmount) }}</span>
                    </div>
                  </div>
                </div>
                <div class="text-left sm:text-right shrink-0">
                  <div class="text-[11px] font-medium uppercase tracking-wide text-[color:var(--storefront-text-muted,#9ca3af)]">Условия</div>
                  <div class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
                    {{ downPaymentPercent }}% аванс · {{ leaseTermMonths }} мес.
                  </div>
                </div>
              </div>
            </div>

            <div class="p-5 sm:p-6 space-y-4">
              <div
                v-for="item in unifiedSelectedItems"
                :key="item.cart_id"
                class="rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[#F8F9FA] p-4 sm:p-5"
              >
                <div class="flex items-start gap-3">
                  <div class="w-16 h-16 sm:w-[72px] sm:h-[72px] rounded-lg bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden flex-shrink-0 flex items-center justify-center">
                    <img
                      v-if="vehicleImageSrc(item)"
                      :src="vehicleImageSrc(item)"
                      :alt="`${item.mark_name} ${item.model_name}`"
                      class="w-full h-full object-contain"
                      onerror="this.src='/images/car-placeholder.png'"
                    >
                    <div v-else class="text-[color:var(--storefront-text-muted,#9ca3af)]">
                      <svg class="text-[color:var(--storefront-icon,inherit)] w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                      </svg>
                    </div>
                  </div>

                  <div class="min-w-0 flex-1">
                    <div class="flex items-start justify-between gap-2">
                      <h4 class="font-semibold text-[color:var(--storefront-title,#111827)] leading-snug pr-1">
                        {{ item.mark_name }} {{ item.model_name }}
                      </h4>
                      <button
                        type="button"
                        class="storefront-action-ghost shrink-0 -mt-0.5 -mr-0.5 p-1.5 rounded-lg text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,229_231_235)/0.8)] transition-colors"
                        aria-label="Удалить автомобиль из корзины"
                        @click="removeItemWithConfirm(item.ref, item.cart_id)"
                      >
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"/>
                        </svg>
                      </button>
                    </div>
                    <div v-if="getSupportBadgeText(item)" class="mt-2">
                      <span class="inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-full bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#065f46)] border border-[color:rgb(var(--storefront-success-border-rgb,209_250_229)/0.8)]">
                        {{ getSupportBadgeText(item) }}
                      </span>
                    </div>
                  </div>
                </div>

                <div class="mt-3 rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3.5 py-3">
                  <div class="text-sm text-[color:var(--storefront-text,#111827)] mb-2">
                    {{ lineItemCalcTitle(item) }}
                  </div>
                  <div class="text-sm text-[color:var(--storefront-text,#374151)] leading-relaxed">
                    <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Платеж:</span>
                    <span class="font-semibold text-[color:var(--storefront-text,#111827)]">{{ formatPrice(getMonthlyPaymentN(item)) }}</span>
                    <span class="text-[color:var(--storefront-text,#d1d5db)] mx-1.5 sm:mx-2" aria-hidden="true">|</span>
                    <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Первый взнос:</span>
                    <span class="font-semibold text-[color:var(--storefront-text,#111827)]">{{ downPaymentPercent }}%</span>
                    <span class="text-[color:var(--storefront-text,#d1d5db)] mx-1.5 sm:mx-2" aria-hidden="true">|</span>
                    <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Срок:</span>
                    <span class="font-semibold text-[color:var(--storefront-text,#111827)]">{{ leaseTermMonths }} мес.</span>
                  </div>
                </div>
              </div>

              <div class="pt-4 border-t border-[color:var(--storefront-border,#e5e7eb)]">
                <div class="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
                  <div class="text-sm text-[color:var(--storefront-text,#374151)]">
                    <div class="font-bold text-[color:var(--storefront-text,#111827)]">Расчет всей заявки</div>
                    <div class="mt-1.5 leading-relaxed">
                      <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Платеж:</span>
                      <span class="font-semibold text-[color:var(--storefront-text,#111827)]">{{ formatPrice(overallMonthlyPayment) }}</span>
                      <span class="text-[color:var(--storefront-text,#d1d5db)] mx-1.5 sm:mx-2" aria-hidden="true">|</span>
                      <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Первый взнос:</span>
                      <span class="font-semibold text-[color:var(--storefront-text,#111827)]">{{ downPaymentPercent }}%</span>
                      <span class="text-[color:var(--storefront-text,#d1d5db)] mx-1.5 sm:mx-2" aria-hidden="true">|</span>
                      <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Срок:</span>
                      <span class="font-semibold text-[color:var(--storefront-text,#111827)]">{{ leaseTermMonths }} мес.</span>
                    </div>
                  </div>
                  <div class="sm:text-right">
                    <div class="text-[11px] font-medium uppercase tracking-wide text-[color:var(--storefront-text-muted,#9ca3af)]">Стоимость имущества</div>
                    <div class="text-xl font-bold text-[color:var(--storefront-text,#111827)] mt-0.5">{{ formatPrice(unifiedTotalAmount) }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Cart Summary & Calculator -->
        <div v-if="!unifiedCartEmpty" class="min-w-0">
          <div class="rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-sm sticky top-6 lg:top-8 overflow-hidden">
            <!-- Summary -->
            <div class="px-5 sm:px-6 py-5 border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
              <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Итого по транспортным средствам</h3>
              <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
                Выбрано транспортных средств:
                <span class="font-medium text-[color:var(--storefront-text,#111827)]">{{ unifiedSelectedCount }}</span>
              </p>
            </div>

            <!-- Leasing Calculator -->
            <div class="px-5 sm:px-6 py-5 border-b border-[color:var(--storefront-border,#e5e7eb)]">
              <CartCalculatorCartLeasingCalculator 
                ref="calculatorRef"
                :total-amount="unifiedTotalAmount"
                :additional-amount="calculatorAdditionalAmount"
                :total-discount="cartStore.totalDiscount"
                :support-display-mode="cartStore.supportDisplayMode"
                :selected-vehicles="selectedVehicleIds"
                :vehicle-price-overrides="vehiclePriceOverrides"
                :vehicle-quantities="vehicleQuantities"
                @calculation-change="onCalculationChange"
              />
            </div>

            <!-- Выгода -->
            <div v-if="appliedDiscountsTotal > 0" class="px-5 sm:px-6 py-4 border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
              <h3 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)] mb-1 flex items-center gap-1.5">
                <svg class="w-4 h-4 text-[color:var(--storefront-success-icon,#16a34a)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                Выгода
              </h3>
              <p class="text-xs text-[color:var(--storefront-text-muted,#4b5563)] mb-1">На выбранные транспортные средства</p>
              <p class="text-lg font-bold text-[color:var(--storefront-success-text,#15803d)]">−{{ formatPrice(appliedDiscountsTotal) }}</p>
            </div>

            <!-- Выгода от базовой цены на выбранные ТС -->
            <div v-if="cartStore.totalDiscount > 0" class="px-5 sm:px-6 py-4 border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
              <h3 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)] mb-1 flex items-center gap-1.5">
                <svg class="w-4 h-4 text-[color:var(--storefront-success-icon,#16a34a)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                Выгода
              </h3>
              <p class="text-xs text-[color:var(--storefront-text-muted,#4b5563)] mb-1">На выбранные транспортные средства</p>
              <p class="text-lg font-bold text-[color:var(--storefront-success-text,#15803d)]">{{ formatPrice(cartStore.totalDiscount) }}</p>
            </div>

            <!-- Action Buttons -->
            <div class="px-5 sm:px-6 py-5 space-y-3">
              <button class="storefront-action-primary"
                @click="handleCheckoutClick"
                :disabled="!canLeaseUnifiedSelection"
                :class="[
                  'block w-full text-center py-3 px-4 rounded-lg font-medium shadow-sm transition-colors',
                  canLeaseUnifiedSelection
                    ? 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]'
                    : 'bg-[color:rgb(var(--storefront-primary-rgb,209_213_219)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#6b7280)] cursor-not-allowed pointer-events-none'
                ]"
              >
                Получить специальное предложение
              </button>

              <div v-if="purchasableSelectedItems.length > 0" class="space-y-1">
                <button
                  type="button"
                  @click="handlePurchaseClick"
                  :disabled="isPurchaseBlocked"
                  :title="isPurchaseBlocked ? purchaseBlockedTooltip : undefined"
                  class="storefront-action-secondary block w-full text-center py-3 px-4 rounded-lg font-medium shadow-sm transition-colors border"
                  :class="[
                    !isPurchaseBlocked
                      ? 'border-[color:var(--storefront-border,#d1d5db)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]'
                      : 'border-gray-200 bg-gray-100 text-gray-400 cursor-not-allowed'
                  ]"
                >
                  {{ purchaseButtonLabel }}
                </button>
                <p v-if="isPurchaseBlocked" class="text-xs text-[color:var(--storefront-warning-text,#b45309)] text-center px-1">
                  {{ purchaseBlockedTooltip }}
                </p>
              </div>

              <NuxtLink 
                :to="continueSelectionLocation"
                class="block w-full text-center py-3 px-4 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg text-[color:var(--storefront-link,#1f2937)] font-medium hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
              >
                Продолжить выбор
              </NuxtLink>

              <button
                type="button"
                :disabled="!hasUnifiedSelection || generatingCartPdf"
                class="storefront-action-ghost block w-full text-center py-3 px-4 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-lg text-[color:var(--storefront-secondary-foreground,#1f2937)] font-medium hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50 disabled:cursor-not-allowed"
                @click="downloadCartPdf"
              >
                {{ generatingCartPdf ? 'Формирование PDF...' : 'Скачать PDF' }}
              </button>

              <div v-if="showCartEmailForm" class="mt-3 p-3 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] space-y-2">
                <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Email для отправки</label>
                <input
                  v-model="cartEmailToSend"
                  type="email"
                  placeholder="email@example.com"
                  class="storefront-control block w-full rounded-md border border-[color:var(--storefront-border,#d1d5db)] py-2 px-3 text-sm focus:border-[color:var(--storefront-border,#3b82f6)] focus:outline-none focus:ring-1 focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                />
                <div class="flex gap-2">
                  <button
                    type="button"
                    class="storefront-action-ghost flex-1 py-2 px-3 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-md text-sm font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
                    @click="showCartEmailForm = false; cartEmailToSend = ''"
                  >
                    Отмена
                  </button>
                  <button
                    type="button"
                    :disabled="sendingCartEmail || !cartEmailToSend"
                    class="storefront-action-primary flex-1 py-2 px-3 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-md text-sm font-medium hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] disabled:opacity-50 disabled:cursor-not-allowed"
                    @click="sendCartByEmail"
                  >
                    {{ sendingCartEmail ? 'Отправка...' : 'Отправить' }}
                  </button>
                </div>
              </div>
              <button
                v-else
                type="button"
                :disabled="!hasUnifiedSelection || sendingCartEmail"
                class="storefront-action-ghost block w-full text-center py-3 px-4 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-lg text-[color:var(--storefront-secondary-foreground,#1f2937)] font-medium hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50 disabled:cursor-not-allowed"
                @click="showCartEmailForm = true"
              >
                Отправить на почту
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AuthModal 
      v-if="showAuthModal"
      :initial-step="pendingCheckoutAction === 'leasing' ? 'register' : 'login'"
      @close="cancelAuthentication"
      @authenticated="handleAuthenticated"
    />

    <CartComponentsCartItemCalculationModal
      :show="showCalculationModal"
      :item="calculationModalItem"
      :calculator-params="calculationModalParams"
      :vehicle-calculation-data="calculationModalVehicleData"
      @close="handleCalculationModalClose"
      @support-change="handleSupportChange"
    />

    <CommercePurchaseModal
      :show="showPurchaseModal"
      :items="purchaseSelections"
      @close="handlePurchaseModalClose"
      @success="handlePurchaseSuccess"
    />

    </div>
  </template>
</template>

<script setup lang="ts">
import ExchangeCartPage from '~/features/exchange/pages/ExchangeCartPage.vue'
import AuthModal from '~/features/auth/components/AuthModal.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { useHydrationReady } from '~/composables/useHydrationReady'
import { createCartApi } from '~/features/cart/api/cartApi'
import { useCartPdf } from '~/features/cart/composables/useCartPdf'
import { useCartEmail } from '~/features/cart/composables/useCartEmail'
import { useUnifiedCartMutations } from '~/features/cart/composables/useUnifiedCartMutations'
import { vehicleCommerceCartLine } from '~/features/cart/adapters/vehicleCommerceCartLine'
import { useVehicleAvailability } from '~/features/cars/composables/useVehicleAvailability'
import { createCalculatorApi } from '~/features/calculator/api/calculatorApi'
import CommercePurchaseModal from '~/features/commerce/components/CommercePurchaseModal.vue'
import {
  commerceCartAdditionalAmount,
  commerceCartBillableQuantity,
  commerceCartManualLeasingError,
  commerceCartPurchaseSelections,
  commerceCartRequiresManualLeasingConditions,
  commerceCartSelectedCount,
  commerceCartTotalAmount,
  commerceCartVehicleIds,
  commerceCheckoutLines,
  moneyMinorUnits,
  MONEY_MINOR_SCALE,
  selectedCommerceCartLines,
  type CommerceCartLine,
} from '~/features/commerce/cartProjection'
import type { CommerceCreateOrderResult, CommerceItemRef } from '~/features/commerce/types'
import { getCommerceLineDiscountSummary } from '~/utils/vehicleDiscount'
import { specialEquipmentCommerceCartLine } from '~/features/specialEquipment/adapters/specialEquipmentCommerceCartLine'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { useSpecialEquipmentCommerceShellStore } from '~/features/specialEquipment/store/commerceShell'
import { useStorefront } from '~/features/storefront'
const cartHydrationReady = useHydrationReady()
const cartStore = useCartStore()
const authStore = useAuthStore()
const favoritesStore = useFavoritesStore()
const { formatPrice } = useFormatPrice()
const checkoutStore = useCheckoutStore()
const router = useRouter()
const visibilityStore = useSectionVisibilityStore()
const specialEquipmentShell = useSpecialEquipmentCommerceShellStore()
const config = useRuntimeConfig()
const toast = useToast(), { apiPath, pageTitle, publicRoute } = useStorefront()
const cartApi = createCartApi(config, apiPath), calculatorApi = createCalculatorApi(config)
const isSpecialEquipmentCatalogVisible = computed(() => visibilityStore.isSectionVisible('public', 'special_equipment_catalog'))
const { generatingCartPdf, downloadCartPdf: _downloadCartPdf } = useCartPdf(config)
const { sendingCartEmail, sendCartByEmail: _sendCartByEmail } = useCartEmail(config)

import type {
  CalculatorParams,
  CartCalculationData,
  CartCalculatorResponse,
  CartItemLike,
  CartPerVehicleCalculation,
  LeasingCalculationResult,
} from '~/features/cart/types'
import type { UUID } from '~/types/ids'

type CheckoutCalculationPayload = Omit<CartCalculationData, 'calculation'> & {
  calculation?: LeasingCalculationResult
}

const setCheckoutCalculation = (calculation: CartCalculationData) => {
  const payload: CheckoutCalculationPayload = {
    ...calculation,
    calculation: calculation.calculation ?? undefined,
  }
  const writeCalculation = checkoutStore.setCalculation as unknown as (
    value: CheckoutCalculationPayload
  ) => void
  writeCalculation(payload)
}

const calculationData = ref<CartCalculationData | null>(null)
const calculatorRef = ref<{ recalculate: () => Promise<boolean> } | null>(null)
const calculatorKey = ref(0)
const showCartEmailForm = ref(false)
const cartEmailToSend = ref('')
const showAuthModal = ref(false)
const showPurchaseModal = ref(false)
const vehicleStatusMap = ref(new Map<UUID, string>())
const vehicleMaxQuantityMap = ref(new Map<UUID, number>())
const pendingCheckoutAction = ref<'leasing' | 'purchase' | null>(null)
const completedPurchaseRefs = ref<CommerceItemRef[]>([])
const equipmentCatalog = ref<Array<{ equipment_code: string; equipment_display_name: string }>>([])
const serviceCatalog = ref<Array<{ service_code: string; service_display_name: string }>>([])
const unifiedCartItems = computed<CommerceCartLine[]>(() => {
  const vehicleLines = cartStore.items.map((item) => ({
    ...vehicleCommerceCartLine(item),
    unavailable_status: getUnavailableStatus(item),
  }))
  const specialLines = isSpecialEquipmentCatalogVisible.value ? specialEquipmentShell.cartItems.map(item => specialEquipmentCommerceCartLine(item, publicRoute)) : []
  const specialTitles = new Map(specialLines.map(line => [
    line.cart_id,
    `${line.mark_name} ${line.model_name}`.trim(),
  ]))
  return [
    ...vehicleLines,
    ...specialLines.map(line => ({
      ...line,
      parent_title: line.parent_cart_id ? specialTitles.get(line.parent_cart_id) ?? null : null,
    })),
  ]
})
const unifiedSelectedItems = computed(() => selectedCommerceCartLines(unifiedCartItems.value))
const unifiedSelectedCount = computed(() => commerceCartSelectedCount(unifiedCartItems.value))
const unifiedTotalAmount = computed(() => commerceCartTotalAmount(unifiedCartItems.value))
const calculatorAdditionalAmount = computed(() => commerceCartAdditionalAmount(unifiedCartItems.value))
const selectedVehicleIds = computed(() => commerceCartVehicleIds(unifiedCartItems.value))
const unifiedCartEmpty = computed(() => unifiedCartItems.value.length === 0 && (!isSpecialEquipmentCatalogVisible.value || specialEquipmentShell.unresolvedCartIds.length === 0))
const hasUnifiedSelection = computed(() => unifiedSelectedItems.value.length > 0)
const canLeaseUnifiedSelection = computed(() =>
  unifiedSelectedItems.value.length > 0
  && unifiedSelectedItems.value.every(item => item.capabilities.can_lease))
const continueSelectionLocation = computed(() => publicRoute('/special-equipment'))

const isPurchasable = (item: CommerceCartLine) => {
  const hasPrice = (Number(item.base_price) || 0) > 0 || (Number(item.discount_price) || 0) > 0
  return hasPrice && !item.is_model_order && (item.capabilities.can_buy || item.capabilities.can_preorder)
}
const catalogItems = computed(() => unifiedCartItems.value.filter(item => !isPurchasable(item)))
const stockItems = computed(() => unifiedCartItems.value.filter(item => isPurchasable(item)))
const purchasableSelectedItems = computed(() => unifiedSelectedItems.value.filter(item => isPurchasable(item)))
const purchaseSelections = computed(() => commerceCartPurchaseSelections(purchasableSelectedItems.value))

const appliedDiscountsTotal = computed(() => {
  const totalMinor = selectedCommerceCartLines(unifiedCartItems.value)
    .filter(line => line.ref.type === 'special_equipment')
    .reduce((sum, line) => {
      const s = getCommerceLineDiscountSummary(line)
      return s ? sum + moneyMinorUnits(s.amount) * commerceCartBillableQuantity(line) : sum
    }, 0)
  return totalMinor / MONEY_MINOR_SCALE
})

const purchaseBlockedTooltip = 'Для покупки ограничьте количество наличием или оформите лизинговую заявку.'

const isPurchaseBlocked = computed(() =>
  purchasableSelectedItems.value.some(item =>
    item.ref.type === 'special_equipment'
    && item.allow_overstock
    && typeof item.available_count === 'number'
    && item.quantity > item.available_count
  )
)

const purchaseButtonLabel = computed(() => {
  const hasOnOrder = purchasableSelectedItems.value.some(item => item.capabilities.can_preorder && !item.capabilities.can_buy)
  const hasBuy = purchasableSelectedItems.value.some(item => item.capabilities.can_buy)
  if (hasOnOrder && !hasBuy) return 'Предзаказ'
  if (hasBuy && !hasOnOrder) return 'Купить'
  return 'Купить онлайн'
})
const vehiclePriceOverrides = computed<Record<UUID, number>>(() => {
  const overrides: Record<UUID, number> = {}
  for (const item of unifiedSelectedItems.value) {
    if (item.ref.type !== 'vehicle') continue
    const customPrice = Number(item.custom_price ?? 0)
    if (customPrice > 0) {
      overrides[item.ref.id] = customPrice
    }
  }
  return overrides
})
const vehicleQuantities = computed<Record<UUID, number>>(() => {
  const quantities: Record<UUID, number> = {}
  for (const item of unifiedSelectedItems.value) {
    if (item.ref.type !== 'vehicle') continue
    const quantity = Math.max(1, Number(item.quantity) || 1)
    quantities[item.ref.id] = quantity
  }
  return quantities
})

const showCalculationModal = ref(false)
const calculationModalItem = ref<CommerceCartLine | null>(null)
const specialItemCalculation = ref<CartCalculatorResponse | null>(null)
const calculationModalParams = computed<CalculatorParams | null>(() => {
  if (!calculationData.value) return null
  const d = calculationData.value
  return {
    down_payment_percent: d.down_payment_percent ?? 20,
    lease_term_months: d.lease_term_months ?? 36,
    buyout_percent: d.buyout_percent ?? 0
  }
})

const calculationModalVehicleData = computed(() => {
  if (!calculationModalItem.value || !calculationData.value) return null
  if (calculationModalItem.value.ref.type === 'special_equipment') {
    const response = specialItemCalculation.value
    return {
      calculation: response?.calculation ?? null,
      calculation_without_support: null,
      support_breakdown: null,
      support_per_program: [],
      support_program_details: [],
      eligible_program_ids: [],
    }
  }
  const vid = calculationModalItem.value.ref.id
  const perVehicle = calculationData.value.calculations_per_vehicle.find((row) => row.vehicle_id === vid)
  const eligibleRow = calculationData.value.eligible_support_program_ids_by_vehicle.find((row) => row.vehicle_id === vid)
  return {
    calculation: perVehicle?.calculation ?? null,
    calculation_without_support: perVehicle?.calculation_without_support ?? null,
    support_breakdown: perVehicle?.support_breakdown ?? null,
    support_per_program: calculationData.value.support_per_program ?? [],
    support_program_details: calculationData.value.support_program_details ?? [],
    eligible_program_ids: eligibleRow?.program_ids ?? []
  }
})

const downPaymentPercent = computed(() => calculationData.value?.down_payment_percent ?? 20)
const leaseTermMonths = computed(() => calculationData.value?.lease_term_months ?? 36)

const overallMonthlyPayment = computed(() => {
  const c = calculationData.value?.calculation
  return c?.monthlyPayment != null ? Number(c.monthlyPayment) : 0
})

const calculationsPerVehicleById = computed(() => {
  const map = new Map<UUID, CartPerVehicleCalculation>()
  const rows = calculationData.value?.calculations_per_vehicle || []
  for (const row of rows) {
    map.set(row.vehicle_id, row)
  }
  return map
})

function vehicleImageSrc(item: CommerceCartLine): string | undefined {
  return item.image_url ?? undefined
}

const SUPPORT_TYPE_LABELS = {
  down_payment_compensation: 'Поддержка ПВ',
  vehicle_discount_dealer_compensation: 'Поддержка на ТС',
  vehicle_discount_dealer_invoice: 'Поддержка на ТС',
  leasing_interest_compensation: 'Поддержка процентов'
}

function getSupportBadgeText(item: CommerceCartLine) {
  if (!item?.has_support || !item?.support_type) return ''
  const type = item.support_type
  const label = (SUPPORT_TYPE_LABELS as Record<string, string>)[type] || type
  const params = item.support_params
  if (!params || typeof params !== 'object') return label

  const value = params.value
  const valueType = params.value_type
  if (value == null || Number.isNaN(Number(value))) return label

  if (valueType === 'percent') return `${label}: ${value}%`
  if (valueType === 'amount') return `${label}: ${formatPrice(Number(value))}`

  return `${label}: ${formatPrice(Number(value))}`
}

function lineItemCalcTitle(item: CommerceCartLine) {
  const quantity = Math.max(1, Number(item.quantity) || 1)
  return quantity > 1 ? `Расчет на ${quantity} ТС` : 'Расчет на 1 ТС'
}

function getMonthlyPayment1(item: CommerceCartLine) {
  if (item.ref.type !== 'vehicle') return 0
  const row = calculationsPerVehicleById.value.get(item.ref.id)
  const m = row?.calculation?.monthlyPayment
  return m != null ? Math.round(Number(m)) : 0
}

function getMonthlyPaymentN(item: CommerceCartLine) {
  const q = Number(item.quantity) || 1
  return Math.round(getMonthlyPayment1(item) * q)
}

function downloadCartPdf() {
  if (!hasUnifiedSelection.value) return
  const params = calculationModalParams.value || {}
  _downloadCartPdf(unifiedSelectedItems.value, calculationData.value, params, unifiedTotalAmount.value, toast)
}

function sendCartByEmail() {
  if (!cartEmailToSend.value || !hasUnifiedSelection.value) return
  const params = calculationModalParams.value || {}
  _sendCartByEmail(
    cartEmailToSend.value,
    unifiedSelectedItems.value,
    calculationData.value,
    params,
    unifiedTotalAmount.value,
    toast,
    () => { showCartEmailForm.value = false; cartEmailToSend.value = '' },
  )
}


async function openCalculationModal(item: CommerceCartLine) {
  calculationModalItem.value = item
  specialItemCalculation.value = null
  if (item.ref.type === 'special_equipment' && calculationModalParams.value) {
    const price = (Number(item.custom_price) || Number(item.base_price) || 0) * item.quantity
    const params = calculationModalParams.value
    try {
      specialItemCalculation.value = await calculatorApi.calculate<CartCalculatorResponse>({
        total_amount: price,
        down_payment: Math.round(price * params.down_payment_percent / 100),
        down_payment_percent: params.down_payment_percent,
        lease_term_months: params.lease_term_months,
        buyout_amount: Math.round(price * (params.buyout_percent ?? 0) / 100),
        vehicle_ids: [],
        selected_support: {},
      })
    } catch {
      toast.error('Не удалось рассчитать выбранную спецтехнику')
    }
  }
  showCalculationModal.value = true
}


const onCalculationChange = (calculation: CartCalculationData | null) => {
  calculationData.value = calculation
  if (!calculation) checkoutStore.setCalculation(null)
}

const recalculateCart = async (): Promise<boolean> => {
  if (calculatorRef.value && typeof calculatorRef.value.recalculate === 'function') {
    return calculatorRef.value.recalculate()
  }
  calculationData.value = null
  checkoutStore.setCalculation(null)
  return false
}

const requireFreshCheckoutCalculation = async (): Promise<boolean> => {
  checkoutStore.setCalculation(null)
  const calculated = await recalculateCart()
  if (!calculated || !calculationData.value?.calculation) {
    toast.error('Не удалось получить актуальный расчёт. Проверьте параметры и повторите.')
    return false
  }
  setCheckoutCalculation(calculationData.value)
  return true
}
const validateManualLeasingCheckout = (): boolean => {
  const manualConditionsError = commerceCartManualLeasingError(unifiedCartItems.value)
  if (!manualConditionsError) return true
  toast.error(manualConditionsError)
  return false
}

const prepareLeasingCheckoutState = async (startNewAttempt = true): Promise<boolean> => {
  if (!canLeaseUnifiedSelection.value) return false
  if (!validateManualLeasingCheckout()) return false

  checkoutStore.setCalculation(null)
  const needsManualConditions = commerceCartRequiresManualLeasingConditions(unifiedCartItems.value)
  if (
    authStore.isAuthenticated &&
    !needsManualConditions &&
    !await requireFreshCheckoutCalculation()
  ) return false

  checkoutStore.setVehicles([])
  checkoutStore.setCommerceItems(commerceCheckoutLines(unifiedCartItems.value))
  if (startNewAttempt) checkoutStore.startApplicationCreateAttempt()
  return true
}

const continueLeasingCheckout = async (): Promise<void> => {
  const nextRoute = authStore.isClient ? '/application/new' : '/cart/conditions'
  await router.push(publicRoute(nextRoute))
}

const {
  allSelected,
  clearCart,
  removeItem,
  removeItemWithConfirm,
  selectAll,
  unselectAll,
  updateItemAdditionalOptions,
  updateItemComment,
  updateItemPrice,
  updateItemQuantity,
  updateSelection,
} = useUnifiedCartMutations({
  items: unifiedCartItems,
  recalculate: recalculateCart,
  onCleared: () => { calculationData.value = null },
})

const handleCalculationModalClose = () => {
  showCalculationModal.value = false
}

const handleSupportChange = () => {
  void recalculateCart()
}

const handleCheckoutClick = async () => {
  if (!await prepareLeasingCheckoutState()) return
  if (!authStore.isAuthenticated) {
    pendingCheckoutAction.value = 'leasing'
    showAuthModal.value = true
    return
  }

  await continueLeasingCheckout()
}

const handlePurchaseClick = () => {
  if (isPurchaseBlocked.value) {
    toast.error(purchaseBlockedTooltip)
    return
  }
  if (!authStore.isAuthenticated) {
    pendingCheckoutAction.value = 'purchase'
    showAuthModal.value = true
    return
  }
  showPurchaseModal.value = true
}

const handlePurchaseSuccess = (results: CommerceCreateOrderResult[]) => {
  completedPurchaseRefs.value = results.flatMap(result => result.orders.map(order => order.item))
}

const handlePurchaseModalClose = async () => {
  showPurchaseModal.value = false
  if (completedPurchaseRefs.value.length === 0) return
  const purchased = [...completedPurchaseRefs.value]
  completedPurchaseRefs.value = []
  await Promise.all(purchased
    .filter(item => item.type === 'vehicle')
    .map(item => removeItem(item)))
  await Promise.all([
    cartStore.initialize(),
    ...(isSpecialEquipmentCatalogVisible.value ? [specialEquipmentShell.loadCart({ force: true, resolveGuestProducts: true })] : []),
  ])
  await refreshVehicleStatuses()
}

const removeUnresolvedProduct = async (productId: UUID) => {
  try {
    await specialEquipmentShell.removeProductCartItems(productId)
  } catch (requestError: unknown) {
    console.error(requestError)
    toast.error('Не удалось удалить недоступную позицию из корзины')
  }
}

const detachSpecialEquipmentItem = async (cartItemId: UUID) => {
  try {
    await specialEquipmentShell.updateCartItem(cartItemId, { parent_item_id: null })
    await recalculateCart()
    toast.success('Надстройка отделена и оставлена в корзине')
  } catch (requestError: unknown) {
    console.error(requestError)
    toast.error('Не удалось отделить надстройку от комплекта')
  }
}

const handleAuthenticated = async () => {
  showAuthModal.value = false
  const pendingAction = pendingCheckoutAction.value
  pendingCheckoutAction.value = null
  await Promise.all([
    favoritesStore.mergeGuestFavorites(),
    cartStore.transferGuestCartToServer(),
    ...(isSpecialEquipmentCatalogVisible.value ? [specialEquipmentShell.mergeGuestState()] : []),
  ])
  if (isSpecialEquipmentCatalogVisible.value) await specialEquipmentShell.loadCart({ force: true, resolveGuestProducts: true })

  if (pendingAction === 'purchase') {
    if (isPurchaseBlocked.value) {
      toast.error(purchaseBlockedTooltip)
      return
    }
    showPurchaseModal.value = true
    return
  }

  if (pendingAction !== 'leasing') return
  checkoutStore.migrateGuestStateToCurrentUser()
  if (!await prepareLeasingCheckoutState(false)) return
  await continueLeasingCheckout()
}

const cancelAuthentication = () => {
  showAuthModal.value = false
  pendingCheckoutAction.value = null
}

const { checkAvailability, getAvailableCounts } = useVehicleAvailability()

async function refreshVehicleStatuses() {
  const vehicleIds = cartStore.items.map(item => item.vehicle_id)
  if (!vehicleIds.length) return
  try {
    const statuses = await checkAvailability(vehicleIds) as Array<{ vehicle_id: UUID; status: string }>
    const map = new Map<UUID, string>()
    for (const s of statuses) {
      if (s.status !== 'available') {
        map.set(s.vehicle_id, s.status)
      }
    }
    vehicleStatusMap.value = map
  } catch {
    // non-critical
  }
}

function getUnavailableStatus(item: CartItemLike) {
  const status = vehicleStatusMap.value.get(item.vehicle_id)
  return status === undefined ? '' : status
}

async function refreshAvailableCounts() {
  const vehicleIds = cartStore.items.map(item => item.vehicle_id)
  if (!vehicleIds.length) return
  try {
    const counts = await getAvailableCounts(vehicleIds) as Array<{ vehicle_id: UUID; available_count: number }>
    const map = new Map<UUID, number>()
    for (const c of counts) {
      map.set(c.vehicle_id, c.available_count)
    }
    vehicleMaxQuantityMap.value = map
  } catch {
    // non-critical
  }
}

function getMaxQuantity(item: CommerceCartLine) {
  if (item.ref.type === 'special_equipment') return Math.max(1, item.available_count ?? 1)
  const quantity = vehicleMaxQuantityMap.value.get(item.ref.id)
  return quantity
}

onMounted(async () => {
  if (authStore.isLeasingCompany) {
    return
  }
  await loadAdditionalOptionCatalogs()
  await Promise.all([
    cartStore.initialize(),
    ...(isSpecialEquipmentCatalogVisible.value ? [specialEquipmentShell.loadCart({ resolveGuestProducts: true })] : []),
  ])
  refreshVehicleStatuses()
  refreshAvailableCounts()
})

async function loadAdditionalOptionCatalogs() {
  try {
    const equipments = await cartApi.getEquipments()
    const services = await cartApi.getServices()
    equipmentCatalog.value = equipments.items || []
    serviceCatalog.value = services.items || []
  } catch (err) {
    console.error('Error loading additional option catalogs:', err)
  }
}

useSeoMeta({
  title: 'Корзина - CarCraft Multileasing',
  description: isSpecialEquipmentCatalogVisible.value ? 'Управление транспортными средствами и спецтехникой в одной корзине' : 'Управление автомобилями в корзине'
})
</script>
