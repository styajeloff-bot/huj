<template>
  <div data-storefront-block="client.application" class="fixed inset-0 z-50 flex items-center justify-center bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.4)] p-4">
    <div class="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-xl bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-xl">
      <div class="sticky top-0 z-10 flex items-center justify-between border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-5">
        <div>
          <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">Детальная информация по заявке</h2>
          <p v-if="application" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
            Заявка {{ formatSourcedApplicationNumber(application, canViewApplicationSource(authStore.userRole)) }}
          </p>
          <ApplicationSourceBadge v-if="application && canViewApplicationSource(authStore.userRole)" :source="application.source_type" class="mt-1" />
        </div>
        <button type="button" class="storefront-action-ghost rounded-lg px-3 py-2 text-[color:var(--storefront-ghost-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))]" @click="emit('close')">
          Закрыть
        </button>
      </div>

      <div v-if="loading" class="p-10 text-center text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем заявку...</div>
      <div v-else-if="error" class="m-5 rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-4 text-[color:var(--storefront-error-text,#b91c1c)]">
        {{ error }}
      </div>

      <div v-else-if="application" class="space-y-6 p-5">
        <section class="grid grid-cols-1 gap-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] p-4 md:grid-cols-2">
          <div>
            <h3 class="mb-3 text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Компания-заявитель</h3>
            <InfoRow label="Название" :value="application.company?.name || application.company_name" />
            <InfoRow label="ИНН" :value="application.company?.inn || application.company_inn" />
            <InfoRow label="КПП" :value="application.company?.kpp" />
            <InfoRow label="ОГРН" :value="application.company?.ogrn" />
            <InfoRow label="Юр. адрес" :value="application.company?.legal_address" />
            <InfoRow label="Факт. адрес" :value="application.company?.actual_address" />
          </div>

          <div>
            <h3 class="mb-3 text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Контакты и условия</h3>
            <InfoRow label="Телефон" :value="applicationPhone" />
            <InfoRow label="Контактное лицо" :value="application.owner?.name || application.name" />
            <InfoRow label="Общая стоимость" :value="formatApplicationAmount(totalAmount)" />
            <InfoRow label="Стоимость ТС" :value="formatApplicationAmount(vehicleOnlyAmount || totalAmount)" />
            <InfoRow label="Количество единиц" :value="String(totalQuantity)" />
            <InfoRow label="Аванс" :value="application.down_payment_percent ? `${application.down_payment_percent}%` : null" />
            <InfoRow label="Срок лизинга" :value="application.lease_term_months ? `${application.lease_term_months} мес.` : null" />
          </div>
        </section>

        <section class="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] p-4">
          <div>
            <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Анкета клиента</h3>
            <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Сведения по заявке доступны на отдельной странице.</p>
          </div>
          <NuxtLink
            :to="questionnaireLocation(application.id, 'applications', { notificationCompanyId: props.notificationCompanyId })"
            class="storefront-action-primary inline-flex rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-4 py-2 text-sm font-medium text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]"
          >
            Открыть анкету
          </NuxtLink>
        </section>

        <ApplicationDealerDistribution
          v-if="authStore.isDistributor"
          :application-id="application.id"
          :positions="application.dealer_distribution ?? []"
          @updated="handleDealerAssigned"
        />

        <RotatingSupportBadge
          v-if="!hasNormalizedApplicationItems && applicationSupportPrograms.length"
          :programs="applicationSupportPrograms"
        />

        <ApplicationSupportPrograms
          v-if="applicationSupportRows.length"
          :programs="applicationSupportRows"
          :link-enabled="canOpenSupportSection"
        />


        <CommerceApplicationItemsSummary
          v-if="hasNormalizedApplicationItems && applicationItems.length > 0"
          :items="applicationItems"
          :vehicle-status-overrides="vehicleStatusOverrides"
          :items-count="application.items_count"
          :total-items-price="application.total_items_price"
          :show-purpose-regions="authStore.isDealer || authStore.isClient"
        />
        <section
          v-if="authStore.isDealer && dealerRequestedPriceItems.length"
          class="rounded-xl border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] p-5"
          aria-labelledby="requested-price-items-title"
        >
          <div class="flex items-start justify-between gap-6">
            <div>
              <h3 id="requested-price-items-title" class="text-lg font-semibold text-[color:var(--storefront-warning-text,#451a03)]">Согласование стоимости</h3>
              <p class="mt-1 text-sm leading-relaxed text-[color:var(--storefront-warning-text,#78350f)]">Укажите точную цену для позиций, опубликованных с ценой по запросу.</p>
            </div>
            <span v-if="pendingRequestedPriceItems.length" class="rounded-full bg-[color:rgb(var(--storefront-warning-rgb,253_230_138)/var(--tw-bg-opacity,1))] px-3 py-1 text-sm font-semibold text-[color:var(--storefront-warning-text,#451a03)]">
              Ожидают: {{ pendingRequestedPriceItems.length }}
            </span>
          </div>
          <ul class="mt-4 grid gap-3 lg:grid-cols-2">
            <li v-for="item in dealerRequestedPriceItems" :key="`${item.type}:${item.id}`" class="rounded-lg border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <p class="font-semibold leading-snug text-[color:var(--storefront-text,#030712)]">{{ item.title }}</p>
                  <p class="mt-1 text-sm tabular-nums text-[color:var(--storefront-text-muted,#4b5563)]">{{ formatCommerceMoney(item.unit_price, item.currency_code) }} · {{ item.quantity }} шт.</p>
                  <span
                    class="mt-2 inline-flex rounded-full px-2.5 py-1 text-sm font-semibold"
                    :class="item.price_status === 'pending' ? 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#78350f)]' : 'bg-[color:rgb(var(--storefront-success-rgb,209_250_229)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#065f46)]'"
                  >
                    {{ item.price_status === 'pending' ? 'Выставить цену' : 'Цена выставлена' }}
                  </span>
                  <p v-if="item.price_set_at" class="mt-2 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Обновлено: {{ formatDate(item.price_set_at) }}</p>
                </div>
                <button
                  v-if="canChangeRequestedPrice"
                  type="button"
                  class="storefront-action-primary min-h-11 shrink-0 rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,29_78_216)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,30_64_175)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  @click="selectedRequestedPriceItem = item"
                >
                  {{ item.price_status === 'set' ? 'Изменить стоимость' : 'Выставить стоимость' }}
                </button>
              </div>
            </li>
          </ul>
          <p v-if="!canChangeRequestedPrice" class="mt-4 text-sm font-medium text-[color:var(--storefront-warning-text,#451a03)]">
            Изменение цены недоступно: заявка завершена или лизинговая компания уже назначена.
          </p>
        </section>

        <section v-if="actionableVehicles.length > 0 || !hasNormalizedApplicationItems">
          <h3 class="mb-4 text-lg font-semibold text-[color:var(--storefront-title,#111827)]">
            {{ hasNormalizedApplicationItems ? 'Автомобили: условия и действия' : 'Техника в заявке' }}
          </h3>

          <div v-if="actionableVehicles.length === 0" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] p-6 text-center text-[color:var(--storefront-text-muted,#6b7280)]">
            Техника не указана
          </div>
          <div v-else class="space-y-4">
            <article
              v-for="vehicle in actionableVehicles"
              :key="vehicleKey(vehicle)"
              class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4"
            >
              <div class="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <h4 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">{{ vehicleTitle(vehicle) }}</h4>
                  <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Количество: {{ vehicleQuantity(vehicle) }}</p>
                  <div
                    v-if="!authStore.isLeasingCompany && ((vehicle as any).overstock_requested_quantity ?? 0) > 0"
                    class="mt-2 rounded-md border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-2.5 py-1.5 text-xs text-[color:var(--storefront-warning-text,#92400e)]"
                  >
                    Клиент запросил сверх наличия: <strong>{{ (vehicle as any).overstock_requested_quantity }} шт.</strong> — не включено в заявку.
                  </div>
                  <RotatingSupportBadge
                    v-if="!hasNormalizedApplicationItems && vehicleSupportPrograms(vehicle).length"
                    class="mt-2"
                    :programs="vehicleSupportPrograms(vehicle)"
                  />
                </div>
                <div class="flex flex-col items-start gap-2 lg:items-end">
                  <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold" :class="vehicleStatusPresentation(vehicle).badgeClass">
                    {{ vehicleStatusPresentation(vehicle).label }}
                  </span>
                  <p v-if="vehicle.reserve_expires_at && ((vehicle.allocated_vehicle_ids?.length ?? 0) > 0 || !vehicleNeedsFulfillment(vehicle))" class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
                    Резерв до {{ formatDate(vehicle.reserve_expires_at) }}
                  </p>
                </div>
              </div>

              <p v-if="vehicle.can_manage_whole_vehicle === false" class="mb-4 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                Вам назначена часть позиции. Изменение условий и состава всей позиции недоступно.
              </p>
              <div v-if="!authStore.isDistributor || (canAssignEmployees && vehicle.assigned_dealer && vehicle.id && vehicle.can_manage_whole_vehicle !== false)" class="mb-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4">
                <div
                  v-if="!authStore.isDistributor"
                  data-testid="assigned-dealer-card"
                  class="rounded-lg border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] px-4 py-3"
                >
                  <div class="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div class="text-xs font-semibold uppercase tracking-wide text-[color:var(--storefront-text,#1d4ed8)]">
                        {{ !vehicle.assigned_dealer && vehicle.stock_dealer ? 'Дилер — владелец склада' : 'Назначенный дилер' }}
                      </div>
                      <div class="mt-1 text-base font-semibold text-[color:var(--storefront-text,#172554)]">
                        {{ assignedDealerLabel(vehicle) || 'Не назначен' }}
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="canAssignEmployees && vehicle.assigned_dealer && vehicle.id && vehicle.can_manage_whole_vehicle !== false" class="mt-4">
                  <p class="mb-3 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
                    Сотрудники выбираются из компании дилера этого автомобиля.
                    Основной и дополнительный сотрудник должны быть разными.
                  </p>

                  <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <EmployeeSearchDropdown
                      :application-id="application.id"
                      :application-vehicle-id="vehicle.id"
                      field="primary_employee_id"
                      label="Основной сотрудник"
                      :model-value="vehicle.primary_employee || null"
                      :excluded-employee-id="vehicle.additional_employee_id ?? null"
                      :excluded-employee-name="
                        vehicle.additional_employee?.name
                        || vehicle.additional_employee?.phone
                        || null
                      "
                      @update:model-value="setPrimaryEmployee(vehicle, $event)"
                      @saved="handleEmployeesSaved"
                    />
                    <EmployeeSearchDropdown
                      :application-id="application.id"
                      :application-vehicle-id="vehicle.id"
                      field="additional_employee_id"
                      label="Дополнительный сотрудник"
                      :model-value="vehicle.additional_employee || null"
                      :excluded-employee-id="vehicle.primary_employee_id ?? null"
                      :excluded-employee-name="
                        vehicle.primary_employee?.name
                        || vehicle.primary_employee?.phone
                        || null
                      "
                      @update:model-value="setAdditionalEmployee(vehicle, $event)"
                      @saved="handleEmployeesSaved"
                    />
                  </div>
                </div>
              </div>

              <div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                <InfoRow label="Двигатель" :value="vehicle.engine || vehicle.engine_type" />
                <InfoRow label="Коробка передач" :value="vehicle.transmission" />
                <InfoRow label="Привод" :value="vehicle.drive" />
                <InfoRow label="Цена в каталоге" :value="formatMaybePrice(baseVehiclePrice(vehicle))" />
                <InfoRow label="Поддержка" :value="formatSupport(vehicle.support)" />
                <InfoRow label="Выгода" :value="formatAdjustment(vehicle.discount_type, vehicle.discount_value, 'discount')" />
                <InfoRow class="lg:order-9" label="Надбавка" :value="formatAdjustment(vehicle.markup_type, vehicle.markup_value, 'markup')" />
                <InfoRow class="lg:order-7" label="Итоговая цена" :value="formatFinalPrice(vehicle.final_price ?? vehicle.unit_price)" />
                <InfoRow class="lg:order-8" label="Склад" :value="warehouseLocation(vehicle)" />
                <InfoRow class="lg:order-10" label="Компания-владелец склада" :value="vehicle.warehouse?.company_name" />
                <InfoRow class="lg:order-11" label="VIN" :value="vehicle.fulfillment_version || vehicleNeedsFulfillment(vehicle) ? (vehicle.allocated_vins?.filter(Boolean).join(', ') || 'Не подобраны') : (vehicle.vin || vehicle.vehicle_vin)" />
              </div>

              <div v-if="hasDiscount(vehicle) || hasMarkup(vehicle)" class="mt-4 space-y-2">
                <div v-if="hasDiscount(vehicle)" class="rounded-lg border border-[color:var(--storefront-success-border,#bbf7d0)] bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-success-text,#166534)]">
                  <span class="font-semibold">Выгода предложена:</span>
                  {{ formatAdjustment(vehicle.discount_type, vehicle.discount_value, 'discount') }}
                </div>
                <div v-if="hasMarkup(vehicle)" class="rounded-lg border border-[color:var(--storefront-warning-border,#fed7aa)] bg-[color:rgb(var(--storefront-warning-rgb,255_247_237)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-warning-text,#9a3412)]">
                  <span class="font-semibold">Надбавка установлена:</span>
                  {{ formatAdjustment(vehicle.markup_type, vehicle.markup_value, 'markup') }}
                </div>
                <div v-if="vehicle.final_price !== null && vehicle.final_price !== undefined" class="text-sm font-medium text-[color:var(--storefront-text,#1f2937)]">
                  Итоговая цена: {{ formatFinalPrice(vehicle.final_price) }}
                </div>
              </div>

              <div
                v-if="canManageDealerVehicleActions && vehicle.can_manage_whole_vehicle !== false"
                class="mt-5 flex flex-wrap gap-2 border-t border-[color:var(--storefront-border,#f3f4f6)] pt-4"
              >
                <template v-if="canManageDealerVehicleActions">
                  <button type="button" class="btn-secondary text-sm" @click="setAction(vehicle, 'reject')">
                    Отказать
                  </button>
                  <button type="button" class="btn-secondary text-sm" @click="setAction(vehicle, 'discount')">
                    Предложить выгоду
                  </button>
                  <button type="button" class="btn-secondary text-sm" @click="setAction(vehicle, 'markup')">
                    Сделать надбавку
                  </button>
                </template>
              </div>

              <VehicleFulfillmentPanel v-if="vehicle.id && vehicle.can_manage_whole_vehicle !== false" :key="`${vehicle.id}-${applicationRevision}`" class="mt-4" :application-vehicle-id="vehicle.id" @updated="fetchApplicationDetails(false); emit('updated')" />

              <CommerceApplicationItemComment :comment="vehicle.comment" />
              <ApplicationAdditionalOptionsEditor
                :application-id="props.applicationId"
                :vehicle="vehicle"
                :normalized="isNormalizedVehicle(vehicle)"
                :after-save="handleAdditionalOptionsSaved"
              />
              <div v-if="vehicle.dealer_comment" class="mt-4 rounded-lg bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-text,#1e3a8a)]">
                <span class="font-semibold">Комментарий дилера:</span> {{ vehicle.dealer_comment }}
              </div>

              <div v-if="vehicle.dealer_action_documents?.length" class="mt-4">
                <div class="mb-2 text-sm font-medium text-[color:var(--storefront-text,#374151)]">Документы дилера</div>
                <div class="flex flex-wrap gap-2">
                  <a
                    v-for="doc in vehicle.dealer_action_documents"
                    :key="String(doc.id || doc.file_url || doc.file_name)"
                    :href="doc.file_url ? notificationUrl(doc.file_url) : undefined"
                    target="_blank"
                    class="rounded-full bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] px-3 py-1 text-sm text-[color:var(--storefront-link,#374151)] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))]"
                  >
                    {{ doc.file_name || 'Документ' }}
                  </a>
                </div>
              </div>
            </article>
          </div>
        </section>
      </div>
    </div>

    <DealerRequestedPriceModal
      v-if="selectedRequestedPriceItem"
      :application-id="applicationId"
      :item="selectedRequestedPriceItem"
      @close="selectedRequestedPriceItem = null"
      @saved="handleRequestedPriceSaved"
    />

    <div v-if="actionType && actionVehicle" class="fixed inset-0 z-[60] flex items-center justify-center bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)] p-4">
      <div class="w-full max-w-xl rounded-xl bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-6 shadow-xl">
        <div class="mb-4 flex items-start justify-between gap-3">
          <div>
            <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">{{ actionTitle }}</h3>
            <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ vehicleTitle(actionVehicle) }}</p>
          </div>
          <button type="button" class="storefront-action-ghost rounded-lg px-2 py-1 text-[color:var(--storefront-ghost-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))]" @click="closeAction">
            ×
          </button>
        </div>

        <div v-if="actionType === 'reject'" class="mb-4 rounded-lg bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#991b1b)]">
          После подтверждения статус автомобиля станет «Не подтверждено».
        </div>

        <div v-if="actionType === 'replace'" class="mb-4 rounded-lg bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-warning-text,#92400e)]">
          Выберите сценарий замены. Можно связаться с клиентом без смены статуса или указать новый VIN-номер.
        </div>

        <label v-if="actionType === 'reserve'" class="mb-4 block">
          <span class="mb-1 block text-sm font-medium text-[color:var(--storefront-text,#374151)]">Дата окончания резерва</span>
          <input v-model="reserveExpiresAt" type="date" class="storefront-control input-field" />
        </label>

        <div v-if="actionType === 'discount' || actionType === 'markup'" class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label>
            <span class="mb-1 block text-sm font-medium text-[color:var(--storefront-text,#374151)]">{{ adjustmentLabel }}, ₽</span>
            <input v-model.number="adjustmentRubles" type="number" min="0" class="storefront-control input-field" @input="syncAdjustmentFromRubles" />
          </label>
          <label>
            <span class="mb-1 block text-sm font-medium text-[color:var(--storefront-text,#374151)]">{{ adjustmentLabel }}, %</span>
            <input v-model.number="adjustmentPercent" type="number" min="0" :max="actionType === 'discount' ? 100 : undefined" class="storefront-control input-field" @input="syncAdjustmentFromPercent" />
          </label>
          <PriceDisplayField label="Итоговая цена" :value="formatFinalPrice(finalPrice)" />
        </div>

        <div v-if="actionType === 'discount' || actionType === 'markup'" class="mb-4 grid grid-cols-1 items-end gap-3 sm:grid-cols-2">
          <PriceDisplayField label="Цена по каталогу" :value="formatFinalPrice(baseVehiclePrice(actionVehicle))" />
          <label class="flex min-h-10 cursor-pointer items-center gap-2 pb-2 text-sm font-medium text-[color:var(--storefront-label,#374151)]">
            <input v-model="showCatalogPrice" type="checkbox" class="storefront-control h-4 w-4 rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#2563eb)]" />
            <span>Отображать для клиента</span>
          </label>
        </div>

        <label v-if="showVinReplacementInput" class="mb-4 block">
          <span class="mb-1 block text-sm font-medium text-[color:var(--storefront-text,#374151)]">VIN-номер</span>
          <input
            v-model="vinReplacementValue"
            type="text"
            maxlength="20"
            class="storefront-control input-field"
            placeholder="Введите VIN-номер"
          />
        </label>

        <label class="mb-4 block">
          <span class="mb-1 block text-sm font-medium text-[color:var(--storefront-text,#374151)]">Комментарий дилера</span>
          <textarea v-model="actionComment" class="storefront-control input-field min-h-24" placeholder="Комментарий увидит клиент при наличии" />
        </label>

        <label class="mb-4 block">
          <span class="mb-1 block text-sm font-medium text-[color:var(--storefront-text,#374151)]">Документы</span>
          <input type="file" multiple class="storefront-control block w-full text-sm text-[color:var(--storefront-text,#374151)]" @change="onFilesSelected" />
          <span v-if="actionFiles.length" class="mt-1 block text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
            Выбрано файлов: {{ actionFiles.length }}
          </span>
        </label>

        <div v-if="actionError" class="mb-4 rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
          {{ actionError }}
        </div>

        <div class="flex flex-wrap justify-end gap-2">
          <button type="button" class="btn-secondary" @click="closeAction">Закрыть</button>
          <button
            v-if="actionType === 'reject'"
            type="button"
            class="btn-secondary"
            @click="openAction(actionVehicle, 'replace')"
          >
            Заменить ТС
          </button>
          <button
            v-if="actionType === 'replace' && !showVinReplacementInput"
            type="button"
            class="btn-secondary"
            @click="showVinReplacementInput = true"
          >
            Заменить VIN-номер
          </button>
          <button
            v-if="actionType === 'replace' && showVinReplacementInput"
            type="button"
            class="btn-primary"
            :disabled="actionSubmitting"
            @click="submitAction('replace_vin')"
          >
            Сохранить VIN
          </button>
          <button
            v-if="actionType === 'replace' && !showVinReplacementInput"
            type="button"
            class="btn-primary"
            :disabled="actionSubmitting"
            @click="submitAction('contact_client')"
          >
            Связаться с клиентом
          </button>
          <button
            v-else-if="actionType !== 'replace'"
            type="button"
            class="btn-primary"
            :disabled="actionSubmitting"
            @click="submitAction(actionType)"
          >
            {{ actionType === 'reject' ? 'Отказать' : 'Сохранить' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { useQuestionnaireNavigation } from '~/features/questionnaire'
import type { PropType } from 'vue'
import { provideNotificationCompanyContext, useNotificationCompanyRequest } from '~/features/notifications'
import {
  createApplicationsApi,
  parseApplicationsApiError,
  type Application,
  type ApplicationVehicle,
  type AssignedEmployee,
  type DealerVehicleActionPayload,
  type EntityId,
} from '~/features/applications/api/applicationsApi'
import VehicleFulfillmentPanel from '~/features/applications/components/VehicleFulfillmentPanel.vue'
import { vehicleNeedsFulfillment } from '~/features/applications/composables/useVehicleFulfillment'
import ApplicationDealerDistribution from './ApplicationDealerDistribution.vue'
import DealerRequestedPriceModal from '~/features/applications/components/DealerRequestedPriceModal.vue'
import EmployeeSearchDropdown from '~/features/applications/components/EmployeeSearchDropdown.vue'
import ApplicationSupportPrograms from '~/features/applications/components/ApplicationSupportPrograms.vue'
import ApplicationAdditionalOptionsEditor from '~/features/applications/components/ApplicationAdditionalOptionsEditor.vue'
import type { ApplicationSupportProgramRow } from '~/features/applications/applicationSupportPrograms'
import { calculateApplicationVehicleAmount } from '~/features/applications/applicationVehicleAmount'
import { applicationVehicleStatusPresentation } from '~/features/commerce/applicationVehicleStatusPresentation'
import { useAuthStore } from '~/features/auth/store/auth'
import { canViewApplicationSource, formatSourcedApplicationNumber } from '~/features/applications/sourceType'
import ApplicationSourceBadge from '~/features/applications/components/ApplicationSourceBadge.vue'
import CommerceApplicationItemComment from '~/features/commerce/components/CommerceApplicationItemComment.vue'
import CommerceApplicationItemsSummary from '~/features/commerce/components/CommerceApplicationItemsSummary.vue'
import { formatCommerceMoney } from '~/features/commerce/money'
import type { CommerceApplicationItem } from '~/features/commerce/types'
import RotatingSupportBadge from '~/components/support/RotatingSupportBadge.vue'
import { normalizeSupportPrograms, supportProgramsFromSnapshot } from '~/types/support'
import {
  formatSupportAmount,
  formatSupportProgramPricing,
} from '~/utils/supportProgramPresentation'

const InfoRow = defineComponent({
  props: {
    label: { type: String, required: true },
    value: {
      type: [String, Number, Boolean] as PropType<string | number | boolean | null | undefined>,
      default: null,
    },
  },
  setup(props) {
    return () => h('div', { class: 'text-sm' }, [
      h('div', { class: 'text-[color:var(--storefront-text-muted,#6b7280)]' }, props.label),
      h('div', { class: 'font-medium text-[color:var(--storefront-text,#111827)]' }, props.value || 'Не указано'),
    ])
  },
})

const PriceDisplayField = defineComponent({
  props: {
    label: { type: String, required: true },
    value: { type: String, required: true },
  },
  setup(props) {
    return () => h('label', [
      h('span', { class: 'mb-1 block text-sm font-medium text-[color:var(--storefront-text,#374151)]' }, props.label),
      h('input', {
        value: props.value,
        type: 'text',
        class: 'input-field',
        disabled: true,
      }),
    ])
  },
})

const props = defineProps<{
  applicationId: EntityId
  notificationCompanyId?: EntityId
}>()

const emit = defineEmits<{
  close: []
  updated: []
}>()

const config = useRuntimeConfig()
const { questionnaireLocation } = useQuestionnaireNavigation()
const notificationCompanyContext = provideNotificationCompanyContext(() => props.notificationCompanyId)
const { url: notificationUrl } = useNotificationCompanyRequest(notificationCompanyContext)
const applicationsApi = createApplicationsApi(config, notificationCompanyContext)
const authStore = useAuthStore()
const { formatPrice } = useFormatPrice()

const loading = ref(true)
const error = ref('')
const application = ref<Application | null>(null)
const applicationSupportPrograms = computed(() => normalizeSupportPrograms([
  ...normalizeSupportPrograms(application.value?.calculation?.support_program_details),
  ...(application.value?.items ?? []).flatMap((item) => {
    const direct = normalizeSupportPrograms(item.support_program_details)
    return direct.length ? direct : supportProgramsFromSnapshot(item.snapshot)
  }),
]))
const applicationSupportRows = computed<ApplicationSupportProgramRow[]>(() => (
  (application.value?.calculation?.support_per_program ?? []).map((row, index) => {
    const id = row.support_program_id ?? null
    const details = id
      ? applicationSupportPrograms.value.find(program => program.id === id)
      : undefined
    const name = row.name
      || row.support_name
      || row.support_program_name
      || details?.name
      || 'Поддержка'
    const explicitPricing = row.price_conditions || row.pricing_conditions
    const amount = row.totals?.amount
    const supportParams = row.support_params || details?.support_params
    let pricing = explicitPricing || ''
    if (!pricing && supportParams) {
      pricing = formatSupportProgramPricing({
        support_type: row.type || details?.support_type,
        support_params: supportParams,
      })
    }
    if (!pricing && amount !== null && amount !== undefined) {
      pricing = formatSupportAmount(amount)
    }
    if (!pricing) {
      pricing = formatSupportProgramPricing({
        support_type: row.type || details?.support_type,
        support_params: null,
      })
    }
    return {
      key: id || `${name}:${pricing}:${index}`,
      id,
      name,
      pricing,
    }
  })
))
const vehicleSupportPrograms = (vehicle: ApplicationVehicle) => {
  const vehicleId = vehicle.vehicle_id
  return applicationSupportPrograms.value.filter(program => (
    program.vehicle_id == null || program.vehicle_id === vehicleId
  ))
}
const selectedRequestedPriceItem = ref<CommerceApplicationItem | null>(null)

type ActionType = Extract<DealerVehicleActionPayload['action'], 'reject' | 'replace' | 'reserve' | 'discount' | 'markup' | 'contact_client' | 'replace_vin'>

const actionType = ref<ActionType | null>(null)
const actionVehicle = ref<ApplicationVehicle | null>(null)
const actionComment = ref('')
const reserveExpiresAt = ref('')
const adjustmentRubles = ref(0)
const adjustmentPercent = ref(0)
const finalPrice = ref(0)
const showCatalogPrice = ref(true)
const actionFiles = ref<File[]>([])
const actionSubmitting = ref(false)
const actionError = ref('')
const showVinReplacementInput = ref(false)
const vinReplacementValue = ref('')
const vehicles = computed(() => application.value?.vehicles || [])
const hasNormalizedApplicationItems = computed(() => Array.isArray(application.value?.items))
const applicationItems = computed<CommerceApplicationItem[]>(() => application.value?.items ?? [])
const dealerRequestedPriceItems = computed(() => applicationItems.value.filter(item => {
  if (item.type !== 'special_equipment') return false
  if (item.status && ['removed', 'replaced', 'rejected'].includes(item.status)) return false
  if (item.seller_company_id !== (notificationCompanyContext() ?? authStore.user?.company_id)) return false
  return item.price_on_request === true || item.snapshot?.price_on_request === true
}))
const pendingRequestedPriceItems = computed(() => dealerRequestedPriceItems.value.filter(
  item => item.price_status === 'pending',
))
const canChangeRequestedPrice = computed(() => application.value?.status === 'active'
  && (application.value.selected_leasing_companies?.length ?? 0) === 0)
const canOpenSupportSection = computed(() => (
  authStore.isDealer
  || authStore.isDistributor
  || authStore.isLeasingCompany
  || authStore.isCarCraftEmployee
))
const normalizedVehicleLineIds = computed(() => {
  const ids = new Set<string>()
  for (const item of applicationItems.value) {
    if (item.type === 'vehicle' || item.type === 'special_equipment') {
      if (item.id) ids.add(String(item.id))
      if (item.item_id) ids.add(String(item.item_id))
    }
  }
  return ids
})
const isNormalizedVehicle = (vehicle: ApplicationVehicle): boolean => {
  if (!hasNormalizedApplicationItems.value) return true
  if (normalizedVehicleLineIds.value.size === 0) return true
  return Boolean(
    (vehicle.id && normalizedVehicleLineIds.value.has(String(vehicle.id)))
    || (vehicle.vehicle_id && normalizedVehicleLineIds.value.has(String(vehicle.vehicle_id)))
  )
}
const actionableVehicles = computed(() => vehicles.value.filter(isNormalizedVehicle))
const totalAmount = computed(() =>
  application.value?.total_amount
  ?? application.value?.total_cost
  ?? application.value?.total_items_price
  ?? application.value?.total_vehicles_price
  ?? 0
)
const vehicleOnlyAmount = computed(() => application.value ? calculateApplicationVehicleAmount(application.value) : 0)
const formatApplicationAmount = (value: string | number | null | undefined): string => (
  typeof value === 'string' ? formatCommerceMoney(value) : formatPrice(value ?? 0)
)
const vehicleQuantity = (vehicle: ApplicationVehicle) => {
  const quantity = Number(vehicle.quantity)
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 1
}
const liveApplicationItems = computed(() => applicationItems.value.filter((item) => !item.status || !['removed', 'replaced', 'rejected'].includes(item.status)))
const totalQuantity = computed(() => application.value?.items_count
  ?? (hasNormalizedApplicationItems.value
    ? liveApplicationItems.value.reduce((sum, item) => sum + item.quantity, 0)
    : vehicles.value.reduce((sum, vehicle) => sum + vehicleQuantity(vehicle), 0)))
const canManageDealerVehicleActions = computed(() => authStore.isDealer || authStore.isDistributor)
const employeeAssignmentRoles = new Set(['dealer', 'distributor', 'carcraft_employee'])
const canAssignEmployees = computed(() =>
  Boolean(authStore.userRole && employeeAssignmentRoles.has(authStore.userRole)),
)
const assignedDealerLabel = (vehicle: ApplicationVehicle) => {
  const dealer = vehicle.assigned_dealer ?? vehicle.stock_dealer
  if (!dealer) return null
  return dealer.inn ? `${dealer.name} · ИНН ${dealer.inn}` : dealer.name
}

const phoneFromQuestionnaire = (payload: Record<string, unknown> | null | undefined): string | null => {
  const contacts = payload?.contacts
  if (!Array.isArray(contacts)) return null
  for (const contact of contacts) {
    if (contact && typeof contact === 'object' && 'phone' in contact) {
      const phone = String((contact as { phone?: unknown }).phone || '').trim()
      if (phone) return phone
    }
  }
  return null
}

const applicationPhone = computed(() => application.value?.phone
  || application.value?.company?.phone
  || application.value?.owner?.phone
  || phoneFromQuestionnaire(application.value?.questionnaire)
  || phoneFromQuestionnaire(application.value?.questionnaire_data)
  || null)

const actionTitle = computed(() => {
  switch (actionType.value) {
    case 'reject':
      return 'Отказать по автомобилю'
    case 'replace':
    case 'contact_client':
    case 'replace_vin':
      return 'Заменить ТС'
    case 'discount':
      return 'Предложить выгоду'
    case 'markup':
      return 'Сделать надбавку'
    case 'reserve':
      return 'Зарезервировать автомобиль'
    default:
      return ''
  }
})

const applicationRevision = ref(0)
const fetchApplicationDetails = async (showLoader = true) => {
  if (showLoader) loading.value = true
  error.value = ''
  try {
    const response = await applicationsApi.getApplicationById(props.applicationId)
    application.value = 'application' in response ? (response as { application: Application }).application : response
    applicationRevision.value++
  } catch (err) {
    error.value = parseApplicationsApiError(
      err,
      'Ошибка при загрузке заявки',
    ).message
  } finally {
    if (showLoader) loading.value = false
  }
}

const handleAdditionalOptionsSaved = async () => {
  await fetchApplicationDetails()
  emit('updated')
}

const vehicleKey = (vehicle: ApplicationVehicle) => vehicle.id ?? ''

const warehouseLocation = (vehicle: ApplicationVehicle) => {
  const warehouse = vehicle.warehouse
  const location = [warehouse?.city, warehouse?.address].filter(Boolean).join(', ')
  return location || vehicle.warehouse_address || null
}

const vehicleTitle = (vehicle: ApplicationVehicle) => {
  const mark = vehicle.mark_name || vehicle.mark_cyrillic_name || vehicle.brand
  const model = vehicle.model_name || vehicle.model_cyrillic_name || vehicle.model
  const parts = [mark, model, vehicle.group_name || vehicle.complectation_name].filter(Boolean)
  return parts.join(' ') || `Автомобиль ${vehicleKey(vehicle)}`
}

const vehicleStatus = (vehicle: ApplicationVehicle) => vehicle.status || vehicle.car_status || 'active'

const vehicleStatusPresentation = (vehicle: ApplicationVehicle) => {
  if (vehicleNeedsFulfillment(vehicle)) {
    return { ...applicationVehicleStatusPresentation('active'), label: 'Требуется подбор' }
  }
  return applicationVehicleStatusPresentation(vehicleStatus(vehicle))
}

const vehicleStatusOverrides = computed(() => new Map(
  actionableVehicles.value
    .filter((vehicle): vehicle is ApplicationVehicle & { id: EntityId } => Boolean(vehicle.id) && vehicleNeedsFulfillment(vehicle))
    .map(vehicle => [vehicle.id, vehicleStatusPresentation(vehicle)]),
))

const baseVehiclePrice = (vehicle: Partial<ApplicationVehicle> | null | undefined) => {
  const value = Number(vehicle?.unit_price ?? vehicle?.catalog_price ?? vehicle?.catalog_price_from ?? 0)
  return Number.isFinite(value) && value >= 0 ? value : 0
}

const formatMaybePrice = (value: unknown) => {
  const numeric = Number(value || 0)
  return numeric > 0 ? formatPrice(numeric) : 'Не указано'
}

const formatFinalPrice = (value: unknown) => {
  if (value === null || value === undefined || value === '') return 'Не указано'
  const numeric = Number(value)
  return Number.isFinite(numeric) && numeric >= 0 ? formatPrice(numeric) : 'Не указано'
}

type PriceAdjustmentAction = Extract<ActionType, 'discount' | 'markup'>

const adjustmentAmount = (
  type: string | null | undefined,
  value: number | string | null | undefined,
  basePrice: number,
  direction: PriceAdjustmentAction,
): number => {
  const numeric = Math.max(0, Number(value || 0))
  if (!Number.isFinite(numeric)) return 0
  if (type === 'percent_off' || type === 'percent_up') {
    return Math.round((basePrice * numeric) / 100)
  }
  if (direction === 'discount' && type === 'fixed_price') {
    return Math.max(0, basePrice - numeric)
  }
  return numeric
}

const formatAdjustment = (
  type: string | null | undefined,
  value: number | string | null | undefined,
  _direction: PriceAdjustmentAction,
): string => {
  const numeric = Number(value || 0)
  if (!Number.isFinite(numeric) || numeric <= 0) return 'Не указано'
  return type === 'percent_off' || type === 'percent_up'
    ? numeric.toLocaleString('ru-RU') + '%'
    : formatPrice(numeric)
}

const hasDiscount = (vehicle: ApplicationVehicle) => Number(vehicle.discount_value || 0) > 0
const hasMarkup = (vehicle: ApplicationVehicle) => Number(vehicle.markup_value || 0) > 0

const priceWithAdjustments = (
  vehicle: ApplicationVehicle,
  activeAction?: PriceAdjustmentAction,
  activeAmount?: number,
): number => {
  const basePrice = baseVehiclePrice(vehicle)
  const discount = activeAction === 'discount'
    ? Math.max(0, activeAmount || 0)
    : adjustmentAmount(vehicle.discount_type, vehicle.discount_value, basePrice, 'discount')
  const markup = activeAction === 'markup'
    ? Math.max(0, activeAmount || 0)
    : adjustmentAmount(vehicle.markup_type, vehicle.markup_value, basePrice, 'markup')
  return Math.max(0, basePrice - discount + markup)
}

const adjustmentLabel = computed(() => actionType.value === 'markup' ? 'Надбавка' : 'Выгода')

const formatSupport = (value: unknown) => {
  if (value === true) return 'Есть'
  if (value === false || value === null || value === undefined || value === '') return 'Не указано'
  return String(value)
}

const formatDate = (value: string | null | undefined) => {
  if (!value) return 'Не указано'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('ru-RU')
}

const resetActionState = () => {
  actionComment.value = ''
  reserveExpiresAt.value = ''
  adjustmentRubles.value = 0
  adjustmentPercent.value = 0
  finalPrice.value = 0
  showCatalogPrice.value = true
  actionFiles.value = []
  showVinReplacementInput.value = false
  vinReplacementValue.value = ''
  actionSubmitting.value = false
  actionError.value = ''
}

const setAction = (vehicle: ApplicationVehicle, type: ActionType) => {
  if (!isNormalizedVehicle(vehicle)) return
  resetActionState()
  actionType.value = type
  actionVehicle.value = vehicle
  const basePrice = baseVehiclePrice(vehicle)
  if (type === 'discount' || type === 'markup') {
    const currentAmount = type === 'discount'
      ? adjustmentAmount(vehicle.discount_type, vehicle.discount_value, basePrice, 'discount')
      : adjustmentAmount(vehicle.markup_type, vehicle.markup_value, basePrice, 'markup')
    adjustmentRubles.value = currentAmount
    adjustmentPercent.value = basePrice > 0
      ? Number(((currentAmount / basePrice) * 100).toFixed(2))
      : 0
    showCatalogPrice.value = type === 'discount'
      ? vehicle.discount_show_catalog_price !== false
      : vehicle.markup_show_catalog_price !== false
    actionComment.value = vehicle.dealer_comment || ''
    finalPrice.value = priceWithAdjustments(vehicle)
    return
  }
  finalPrice.value = basePrice
}

const openAction = setAction

const closeAction = () => {
  actionType.value = null
  actionVehicle.value = null
  resetActionState()
}

const syncAdjustmentFromRubles = () => {
  const basePrice = baseVehiclePrice(actionVehicle.value || {})
  const rubles = Math.max(0, Number(adjustmentRubles.value || 0))
  adjustmentPercent.value = basePrice > 0 ? Number(((rubles / basePrice) * 100).toFixed(2)) : 0
  const vehicle = actionVehicle.value
  const type = actionType.value
  finalPrice.value = vehicle && (type === 'discount' || type === 'markup')
    ? priceWithAdjustments(vehicle, type, rubles)
    : basePrice
}

const syncAdjustmentFromPercent = () => {
  const basePrice = baseVehiclePrice(actionVehicle.value || {})
  const percent = Math.max(0, Number(adjustmentPercent.value || 0))
  const rubles = basePrice > 0 ? Math.round((basePrice * percent) / 100) : 0
  adjustmentRubles.value = rubles
  const vehicle = actionVehicle.value
  const type = actionType.value
  finalPrice.value = vehicle && (type === 'discount' || type === 'markup')
    ? priceWithAdjustments(vehicle, type, rubles)
    : basePrice
}

const onFilesSelected = (event: Event) => {
  const input = event.target as HTMLInputElement
  actionFiles.value = Array.from(input.files || [])
}

const submitAction = async (type: ActionType | null) => {
  if (!type || !actionVehicle.value) return
  if (!isNormalizedVehicle(actionVehicle.value)) {
    actionError.value = 'Действие доступно только для автомобиля заявки'
    return
  }
  const applicationVehicleId = actionVehicle.value.id
  if (!applicationVehicleId) {
    actionError.value = 'Не найден идентификатор автомобиля заявки'
    return
  }
  if (type === 'reserve' && !reserveExpiresAt.value) {
    actionError.value = 'Укажите дату окончания резерва'
    return
  }
  if (type === 'replace_vin' && !vinReplacementValue.value.trim()) {
    actionError.value = 'Укажите VIN-номер'
    return
  }

  actionSubmitting.value = true
  actionError.value = ''
  const payload: DealerVehicleActionPayload = {
    action: type,
    comment: actionComment.value || null,
    files: actionFiles.value,
  }
  if (type === 'reserve') {
    payload.reserve_expires_at = reserveExpiresAt.value
  }
  if (type === 'discount') {
    payload.discount_type = 'rubles_off'
    payload.discount_value = adjustmentRubles.value
    payload.show_catalog_price = showCatalogPrice.value
    payload.final_price = finalPrice.value
  }
  if (type === 'markup') {
    payload.markup_type = 'rubles_up'
    payload.markup_value = adjustmentRubles.value
    payload.show_catalog_price = showCatalogPrice.value
    payload.final_price = finalPrice.value
  }
  if (type === 'replace_vin') {
    payload.vin = vinReplacementValue.value.trim()
  }

  try {
    await applicationsApi.runDealerVehicleAction(applicationVehicleId, payload)
    closeAction()
    await fetchApplicationDetails()
    emit('updated')
  } catch (err) {
    actionError.value = parseApplicationsApiError(
      err,
      'Ошибка при выполнении действия',
    ).message
  } finally {
    actionSubmitting.value = false
  }
}

const setPrimaryEmployee = (vehicle: ApplicationVehicle, employee: AssignedEmployee | null) => {
  vehicle.primary_employee = employee
  vehicle.primary_employee_id = employee?.id ?? null
}

const setAdditionalEmployee = (vehicle: ApplicationVehicle, employee: AssignedEmployee | null) => {
  vehicle.additional_employee = employee
  vehicle.additional_employee_id = employee?.id ?? null
}

const handleEmployeesSaved = async () => {
  await fetchApplicationDetails(false)
  emit('updated')
}

const handleDealerAssigned = async () => {
  await fetchApplicationDetails(false)
  emit('updated')
}

const handleRequestedPriceSaved = async () => {
  selectedRequestedPriceItem.value = null
  await fetchApplicationDetails(false)
  emit('updated')
}

onMounted(fetchApplicationDetails)
</script>
