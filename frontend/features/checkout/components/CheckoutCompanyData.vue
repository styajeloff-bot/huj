<template>
  <div data-storefront-block="client.checkout" class="space-y-4 sm:space-y-6" style="color: var(--storefront-text,#000);">
    <!-- Loading -->
    <div v-if="loadingCompany || shouldShowAccountingLoading" class="text-center py-10">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <p class="mt-3 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем данные компании и бухгалтерскую отчётность…</p>
    </div>

    <!-- Company profile missing -->
    <div v-else-if="!isBankStatementMode && !companyData" class="p-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg">
      <p class="text-[color:var(--storefront-text-muted,#4b5563)] text-sm text-center">
        Данные компании ещё не загружены. Вы можете продолжить — на следующих шагах их можно заполнить вручную.
      </p>
    </div>

    <template v-else>
      <!-- Header: name + status + ids -->
      <div v-if="shouldShowCompanyData" class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg overflow-hidden">
        <div class="px-4 py-3 border-b border-[color:var(--storefront-border,#f3f4f6)] bg-gradient-to-r from-[var(--storefront-gradient-from,#eff6ff)] via-[var(--storefront-gradient-via,#ffffff)] to-[var(--storefront-gradient-to,#ffffff)]">
          <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div class="min-w-0">
              <h3 class="text-lg sm:text-xl font-semibold text-[color:var(--storefront-title,#111827)] leading-tight">
                {{ headerTitle }}
              </h3>
              <p v-if="headerSubtitle" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">{{ headerSubtitle }}</p>
            </div>
            <div class="flex flex-col items-end gap-2 shrink-0">
              <span v-if="companyStatus" class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium"
                :class="companyStatus.ok ? 'bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#047857)] border border-[color:var(--storefront-success-border,#a7f3d0)]' : 'bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#92400e)] border border-[color:var(--storefront-warning-border,#fde68a)]'">
                <span class="w-1.5 h-1.5 rounded-full mr-2" :class="companyStatus.ok ? 'bg-[color:rgb(var(--storefront-success-rgb,16_185_129)/var(--tw-bg-opacity,1))]' : 'bg-[color:rgb(var(--storefront-warning-rgb,245_158_11)/var(--tw-bg-opacity,1))]'"></span>
                {{ companyStatus.label }}
              </span>
              <button
                type="button"
                @click="onRefreshAccounting"
                :disabled="(accountingStatus as any) === 'loading'"
                class="storefront-action-secondary inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[color:var(--storefront-secondary-border,#d1d5db)] text-[color:var(--storefront-secondary-foreground,#374151)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-60 disabled:cursor-not-allowed"
              >
                Обновить
              </button>
            </div>
          </div>
          <div class="mt-3 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-xs text-[color:var(--storefront-text-muted,#4b5563)]">
            <div><span class="text-[color:var(--storefront-text-muted,#6b7280)]">ИНН:</span> <span class="font-mono text-[color:var(--storefront-text,#111827)]">{{ companyData?.inn || '—' }}</span></div>
            <div><span class="text-[color:var(--storefront-text-muted,#6b7280)]">КПП:</span> <span class="font-mono text-[color:var(--storefront-text,#111827)]">{{ companyData?.kpp || '—' }}</span></div>
            <div><span class="text-[color:var(--storefront-text-muted,#6b7280)]">ОГРН:</span> <span class="font-mono text-[color:var(--storefront-text,#111827)]">{{ companyData?.ogrn || '—' }}</span></div>
            <div><span class="text-[color:var(--storefront-text-muted,#6b7280)]">Регистрация:</span> <span class="text-[color:var(--storefront-text,#111827)]">{{ formatDate(registrationDate) || '—' }}</span></div>
          </div>
        </div>

        <!-- Tabs -->
        <div class="border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
          <nav class="flex gap-1 px-2 sm:px-4" aria-label="Разделы">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              @click="activeTab = tab.id"
              class="px-3 sm:px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors"
              :class="activeTab === tab.id
                ? 'border-[color:var(--storefront-selected-border,#2563eb)] text-[color:var(--storefront-secondary-foreground,#1d4ed8)]'
                : 'border-transparent text-[color:var(--storefront-secondary-foreground,#4b5563)] hover:text-[color:var(--storefront-secondary-hover-foreground,#111827)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'"
            >
              {{ tab.label }}
            </button>
          </nav>
        </div>

        <!-- ==== TAB: БФО ==== -->
        <div v-if="activeTab === 'accounting'" class="p-3 sm:p-4 space-y-4 sm:space-y-5">
          <!-- Status banner -->
          <div v-if="accountingStatus === 'not_found'" class="p-3 text-sm bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#bfdbfe)] rounded-md text-[color:var(--storefront-text,#1e40af)]">
            Федеральная налоговая служба не публикует бухгалтерскую отчётность по этой компании (обычно это новые организации или ИП).
          </div>
          <div v-else-if="accountingStatus === 'unavailable'" class="p-3 text-sm bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fde68a)] rounded-md text-[color:var(--storefront-warning-text,#78350f)] flex items-start justify-between gap-3">
            <span>Провайдер отчётности временно недоступен. Показываем кешированные данные, если они есть.</span>
            <button type="button" @click="onRefreshAccounting" class="storefront-action-ghost text-xs text-[color:var(--storefront-ghost-foreground,#92400e)] hover:text-[color:var(--storefront-ghost-hover-foreground,#451a03)] underline shrink-0">Повторить</button>
          </div>
          <div v-else-if="accountingStatus === 'error'" class="p-3 text-sm bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-md text-[color:var(--storefront-error-text,#991b1b)]">
            {{ accountingErrorMessage || 'Ошибка загрузки отчётности' }}
          </div>

          <template v-if="report && report.period_years.length > 0">
            <!-- Year picker + download buttons -->
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-xs text-[color:var(--storefront-text-muted,#6b7280)] mr-1">Отчётный год:</span>
                <button
                  v-for="year in report.period_years"
                  :key="year"
                  type="button"
                  @click="selectedYear = year"
                  class="storefront-action-primary px-3 py-1 text-sm font-medium rounded-md border transition-colors"
                  :class="selectedYear === year
                    ? 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] border-[color:var(--storefront-primary-border,#2563eb)]'
                    : 'bg-[color:rgb(var(--storefront-primary-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#374151)] border-[color:var(--storefront-primary-border,#d1d5db)] hover:border-[color:var(--storefront-primary-hover-border,#9ca3af)]'"
                >
                  {{ year }}
                </button>
                <span v-if="report.cached" class="ml-2 text-[11px] text-[color:var(--storefront-text-muted,#9ca3af)]">
                  {{ report.stale ? 'из кеша, возможно устарело' : `кеш, обновлено ${formatDate(report.last_fetch_at) || ''}` }}
                </span>
              </div>
              <div class="flex items-center gap-2 flex-wrap">
                <a v-if="selectedYearFile?.pdf_url" :href="selectedYearFile.pdf_url" target="_blank" rel="noopener"
                  class="storefront-action-primary inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] shadow-sm">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
                  Финансовая отчетность
                </a>
                <a v-if="selectedYearFile?.audit_pdf_url" :href="selectedYearFile.audit_pdf_url" target="_blank" rel="noopener"
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-link,#374151)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
                  Аудит
                </a>
                <a v-if="selectedYearFile?.clarification_pdf_url" :href="selectedYearFile.clarification_pdf_url" target="_blank" rel="noopener"
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-link,#374151)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
                  Пояснения
                </a>
              </div>
            </div>

            <!-- KPI cards -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3">
              <div v-for="kpi in kpiCards" :key="kpi.key" class="p-3 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
                <p class="text-[11px] text-[color:var(--storefront-text-muted,#6b7280)] leading-tight">{{ kpi.label }}</p>
                <p class="mt-1 text-base sm:text-lg font-semibold text-[color:var(--storefront-text,#111827)]">{{ formatAmount(kpi.value) }}</p>
                <p v-if="kpi.yoy !== null" class="mt-0.5 text-[11px] font-medium"
                  :class="kpi.yoy > 0 ? 'text-[color:var(--storefront-success-text,#059669)]' : kpi.yoy < 0 ? 'text-[color:var(--storefront-error-text,#dc2626)]' : 'text-[color:var(--storefront-text-muted,#6b7280)]'">
                  {{ kpi.yoy > 0 ? '▲' : kpi.yoy < 0 ? '▼' : '–' }}
                  {{ Math.abs(kpi.yoy).toFixed(1) }}% к {{ selectedYearMinus1 }}
                </p>
              </div>
            </div>

            <!-- Charts -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-3 sm:gap-4">
              <div class="p-3 sm:p-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
                <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)] mb-3">Выручка и чистая прибыль</h4>
                <div class="relative h-56 sm:h-64">
                  <canvas ref="revenueCanvas"></canvas>
                </div>
              </div>
              <div class="p-3 sm:p-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
                <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)] mb-3">Активы и капитал</h4>
                <div class="relative h-56 sm:h-64">
                  <canvas ref="balanceCanvas"></canvas>
                </div>
              </div>
            </div>

            <!-- BFO forms — collapsed by default per bo.nalog.gov.ru style -->
            <SectionTable
              title="Бухгалтерский баланс (форма 1)"
              :rows="report.balance_sheet"
              :years="balanceYears"
              accent="border-[color:var(--storefront-border,#2563eb)]"
            />

            <SectionTable
              title="Отчёт о финансовых результатах (форма 2)"
              :rows="report.financial_result"
              :years="twoYears"
              accent="border-[color:var(--storefront-success-border,#059669)]"
            />

            <SectionTable
              v-if="report.capital_change.length > 0"
              title="Отчёт об изменениях капитала (форма 3)"
              :rows="report.capital_change"
              :years="twoYears"
              accent="border-[color:var(--storefront-info-border,#9333ea)]"
            />

            <SectionTable
              v-if="report.cash_flow.length > 0"
              title="Отчёт о движении денежных средств (форма 4)"
              :rows="report.cash_flow"
              :years="twoYears"
              accent="border-[color:var(--storefront-warning-border,#d97706)]"
            />

            <!-- Ratios (collapsed by default) -->
            <CollapsibleSection
              v-if="report.computed_ratios.length > 0"
              title="Финансовые коэффициенты"
              accent="border-[color:var(--storefront-info-border,#4f46e5)]"
            >
              <div class="p-3 sm:p-4 grid grid-cols-1 md:grid-cols-2 gap-2">
                <div v-for="r in report.computed_ratios" :key="r.key"
                  class="flex items-center justify-between gap-3 px-3 py-2 rounded-md border"
                  :class="ratioBandClass(r.band)">
                  <div class="min-w-0">
                    <p class="text-sm font-medium text-[color:var(--storefront-text,#111827)] truncate">{{ r.name }}</p>
                    <p class="text-[11px] text-[color:var(--storefront-text-muted,#6b7280)] truncate">{{ r.hint }}</p>
                  </div>
                  <span class="text-sm font-semibold text-[color:var(--storefront-text,#111827)] shrink-0 font-mono">{{ r.value !== null ? r.value.toFixed(2) : '—' }}</span>
                </div>
              </div>
            </CollapsibleSection>

            <!-- Audit (collapsed by default) -->
            <CollapsibleSection
              v-if="report.audit_report"
              title="Аудитор"
              accent="border-[color:var(--storefront-error-border,#dc2626)]"
            >
              <div class="p-3 sm:p-4 grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <div><span class="text-[color:var(--storefront-text-muted,#6b7280)]">Наименование:</span> <span class="text-[color:var(--storefront-text,#111827)]">{{ report.audit_report.auditor_name || '—' }}</span></div>
                <div><span class="text-[color:var(--storefront-text-muted,#6b7280)]">ИНН:</span> <span class="text-[color:var(--storefront-text,#111827)] font-mono">{{ report.audit_report.auditor_inn || '—' }}</span></div>
                <div><span class="text-[color:var(--storefront-text-muted,#6b7280)]">ОГРН:</span> <span class="text-[color:var(--storefront-text,#111827)] font-mono">{{ report.audit_report.auditor_ogrn || '—' }}</span></div>
                <div v-if="report.audit_report.pdf_url"><a :href="report.audit_report.pdf_url" target="_blank" rel="noopener" class="text-[color:var(--storefront-link,#2563eb)] hover:underline">Открыть заключение</a></div>
              </div>
            </CollapsibleSection>
          </template>
        </div>

        <!-- ==== TAB: Реквизиты ==== -->
        <div v-else-if="activeTab === 'requisites'" class="p-3 sm:p-4 space-y-4 sm:space-y-5">
          <div>
            <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)] mb-2">Основные сведения</h4>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-2 text-sm">
              <Field label="Полное название" :value="(companyData?.full_name as string | null) || (companyData?.name as string | null) || (orgInfo?.full_name as string | null)" />
              <Field label="Краткое название" :value="(companyData?.short_name as string | null) || (orgInfo?.short_name as string | null)" />
              <Field label="Организационно-правовая форма" :value="(companyData?.legal_form as string | null)" />
              <Field label="ИНН" :value="(companyData?.inn as string | null) || (orgInfo?.inn as string | null)" mono />
              <Field label="КПП" :value="(companyData?.kpp as string | null) || (orgInfo?.kpp as string | null)" mono />
              <Field label="ОГРН" :value="(companyData?.ogrn as string | null) || (orgInfo?.ogrn as string | null)" mono />
              <Field label="ОКПО" :value="(companyData?.okpo as string | null)" mono />
              <Field label="ОКАТО" :value="(companyData?.okato as string | null)" mono />
              <Field label="ОКОПФ" :value="(orgInfo?.okopf as string | null)" />
              <Field label="ОКВЭД" :value="(orgInfo?.okved2 as string | null) || (companyData?.main_okved_code as string | null)" />
              <Field label="Статус" :value="(orgInfo?.status as string | null)" />
              <Field label="Дата регистрации" :value="formatDate(registrationDate)" />
              <Field label="Адрес (ФНС)" :value="(orgInfo?.address as string | null)" />
              <Field label="ИФНС" :value="taxAuthorityLabel" />
            </div>
          </div>

          <div>
            <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)] mb-2">Адрес</h4>
            <div class="grid grid-cols-1 gap-y-2 text-sm">
              <Field label="Юридический адрес" :value="(companyData?.legal_address as string | null)" />
              <Field label="Фактический адрес" :value="(companyData?.actual_address as string | null)" />
            </div>
          </div>

          <div v-if="hasMainOkved || additionalOkvedList.length > 0">
            <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)] mb-2">Виды деятельности (ОКВЭД)</h4>
            <div v-if="hasMainOkved" class="text-sm mb-2">
              <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Основной:</span>
              <span class="ml-1 font-mono text-[color:var(--storefront-text,#111827)]">{{ companyData?.main_okved_code }}</span>
              <span v-if="companyData?.main_okved_description" class="ml-1 text-[color:var(--storefront-text,#374151)]">— {{ companyData?.main_okved_description }}</span>
            </div>
            <div v-if="additionalOkvedList.length > 0" class="space-y-1">
              <div v-for="(okved, index) in additionalOkvedList" :key="index" class="text-sm">
                <span class="font-mono text-[color:var(--storefront-text,#111827)]">{{ okved.code }}</span>
                <span v-if="okved.description" class="ml-1 text-[color:var(--storefront-text,#374151)]">— {{ okved.description }}</span>
              </div>
            </div>
          </div>

          <div>
            <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)] mb-2">Руководитель</h4>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-2 text-sm">
              <Field label="ФИО" :value="(companyData?.director_full_name as string | null)" />
              <Field label="Должность" :value="(companyData?.director_position as string | null)" />
              <Field label="ИНН" :value="(companyData?.director_inn as string | null)" mono />
            </div>
          </div>

          <div v-if="hasBankData">
            <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)] mb-2">Банковские реквизиты</h4>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-2 text-sm">
              <Field label="БИК" :value="(companyData?.bank_bik as string | null)" mono />
              <Field label="Банк" :value="(companyData?.bank_name as string | null)" />
              <Field label="Расчётный счёт" :value="(companyData?.bank_account_number as string | null)" mono />
            </div>
          </div>

          <div v-if="hasFinancialMeta">
            <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)] mb-2">Финансовая справка</h4>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-x-4 gap-y-2 text-sm">
              <Field label="Уставный капитал" :value="companyData?.authorized_capital !== null && companyData?.authorized_capital !== undefined ? formatAmount(Number(companyData?.authorized_capital)) : null" />
              <Field label="Чистая прибыль" :value="companyData?.net_profit !== null && companyData?.net_profit !== undefined ? formatAmount(Number(companyData?.net_profit)) : null" />
              <Field label="Отчётный год" :value="(companyData?.reporting_year as number | null)?.toString()" />
            </div>
          </div>
        </div>

        <!-- ==== TAB: Учредители ==== -->
        <div v-else-if="activeTab === 'founders'" class="p-3 sm:p-4">
          <div v-if="foundersList.length === 0" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Сведения об учредителях отсутствуют.</div>
          <div v-else class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="text-xs text-[color:var(--storefront-text-muted,#6b7280)] uppercase bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
                  <th class="px-3 py-2 text-left font-medium">ФИО / Наименование</th>
                  <th class="px-3 py-2 text-left font-medium">ИНН</th>
                  <th class="px-3 py-2 text-right font-medium">Доля</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
                <tr v-for="(f, i) in foundersList" :key="i">
                  <td class="px-3 py-2 text-[color:var(--storefront-text,#111827)]">{{ f.name || '—' }}</td>
                  <td class="px-3 py-2 text-[color:var(--storefront-text,#111827)] font-mono">{{ f.inn || '—' }}</td>
                  <td class="px-3 py-2 text-[color:var(--storefront-text,#111827)] text-right font-semibold">{{ f.share ? `${f.share}%` : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <BankStatementDashboard
        v-if="isBankStatementMode"
        :company-id="props.companyId"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { useNotificationCompanyRequest } from '~/features/notifications'
const { request: notificationRequest } = useNotificationCompanyRequest()
import { Chart, registerables } from 'chart.js'
import { defineComponent, h } from 'vue'
import BankStatementDashboard from './bank-statements/BankStatementDashboard.vue'
import { useCheckoutAccounting } from '~/features/checkout/composables/useCheckoutAccounting'
import type { AccountingReport, AccountingRow, AccountingYearFile, FinancialRatio } from '~/features/checkout/composables/useCheckoutAccounting'
import type { UUID } from '~/types/ids'
import { normalizeCompanyFounders, resolveCompanyRegistrationDate } from '~/features/checkout/utils/companyProfileDisplay'
import type { CompanyFounderDisplay } from '~/features/checkout/utils/companyProfileDisplay'

Chart.register(...registerables)

// --- Lightweight inline components used by the template (Field / SectionTable).
// Keeping them inside the SFC avoids splintering one screen into five files;
// they have no props beyond the primitives shown here.

const Field = defineComponent({
  name: 'CompanyField',
  props: {
    label: { type: String, required: true },
    value: { type: [String, Number] as unknown as () => string | number | null | undefined, default: null },
    mono: { type: Boolean, default: false },
  },
  setup(props) {
    return () => {
      const v = props.value
      const text = v === null || v === undefined || v === '' ? '—' : String(v)
      return h('div', null, [
        h('div', { class: 'text-[11px] text-[color:var(--storefront-text-muted,#6b7280)] leading-tight' }, props.label),
        h('div', { class: ['text-sm text-[color:var(--storefront-text,#111827)] mt-0.5', props.mono ? 'font-mono' : ''] }, text),
      ])
    }
  },
})

interface BfoTableRow { code: string; name: string; values: Record<string, number | null> }

/** Collapsible section with a prominent coloured header. Default collapsed;
 * native <details> handles click-to-toggle. */
const CollapsibleSection = defineComponent({
  name: 'CollapsibleSection',
  props: {
    title: { type: String, required: true },
    accent: { type: String, default: 'border-[color:var(--storefront-border,#2563eb)]' },
    open: { type: Boolean, default: false },
  },
  setup(props, { slots }) {
    return () =>
      h(
        'details',
        {
          class: 'rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] overflow-hidden group',
          open: props.open || undefined,
        },
        [
          h(
            'summary',
            {
              class: [
                'flex items-center justify-between px-4 py-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] cursor-pointer',
                'hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] select-none border-l-4',
                props.accent,
                'list-none [&::-webkit-details-marker]:hidden [&::marker]:hidden',
              ],
            },
            [
              h('h4', { class: 'text-sm font-semibold text-[color:var(--storefront-text,#111827)]' }, props.title),
              h(
                'svg',
                {
                  class: 'w-4 h-4 text-[color:var(--storefront-text-muted,#6b7280)] transition-transform group-open:rotate-90',
                  fill: 'none',
                  stroke: 'currentColor',
                  viewBox: '0 0 24 24',
                },
                [
                  h('path', {
                    'stroke-linecap': 'round',
                    'stroke-linejoin': 'round',
                    'stroke-width': '2',
                    d: 'M9 5l7 7-7 7',
                  }),
                ],
              ),
            ],
          ),
          h('div', { class: 'border-t border-[color:var(--storefront-border,#e5e7eb)]' }, slots.default?.()),
        ],
      )
  },
})

const SectionTable = defineComponent({
  name: 'AccountingSectionTable',
  props: {
    title: { type: String, required: true },
    rows: { type: Array as () => BfoTableRow[], required: true },
    years: { type: Array as () => number[], required: true },
    accent: { type: String, default: 'border-[color:var(--storefront-border,#2563eb)]' },
  },
  setup(props) {
    const nf = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
    const fmt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : nf.format(Math.round(v)))
    return () => {
      if (props.rows.length === 0) return null
      return h(
        CollapsibleSection,
        { title: props.title, accent: props.accent },
        {
          default: () =>
            h('div', { class: 'overflow-x-auto' }, [
              h('table', { class: 'min-w-full text-sm' }, [
                h('thead', null, [
                  h('tr', { class: 'text-xs text-[color:var(--storefront-text-muted,#6b7280)] uppercase bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]' }, [
                    h('th', { class: 'px-3 py-2 text-left font-medium w-20' }, 'Код'),
                    h('th', { class: 'px-3 py-2 text-left font-medium' }, 'Наименование'),
                    ...props.years.map((y) => h('th', { class: 'px-3 py-2 text-right font-medium' }, String(y))),
                  ]),
                ]),
                h('tbody', { class: 'divide-y divide-[color:var(--storefront-border,#f3f4f6)]' }, props.rows.map((row) =>
                  h('tr', { key: row.code }, [
                    h('td', { class: 'px-3 py-1.5 font-mono text-[color:var(--storefront-text-muted,#6b7280)] text-xs' }, row.code),
                    h('td', { class: 'px-3 py-1.5 text-[color:var(--storefront-text,#111827)]' }, row.name),
                    ...props.years.map((y) => h('td', { class: 'px-3 py-1.5 text-right text-[color:var(--storefront-text,#111827)] font-mono tabular-nums' }, fmt(row.values[String(y)]))),
                  ]),
                )),
              ]),
            ]),
        },
      )
    }
  },
})

const props = defineProps<{
  companyId: UUID | null
  companyProfile?: Record<string, unknown> | null
  taxSystem?: string | null
}>()

const config = useRuntimeConfig()

const isBankStatementMode = computed(() => {
  const value = String(props.taxSystem || '').toLowerCase()
  return value === 'usn'
    || value === 'ausn'
    || value.includes('усн')
    || value.includes('аусн')
    || value.includes('автоусн')
})

// --- State: company profile (replaces old editable form)
const loadingCompany = ref(false)
const companyData = ref<Record<string, unknown> | null>(null)

// --- State: accounting (uses shared composable)
const {
  status: accountingStatus,
  report,
  errorMessage: accountingErrorMessage,
  fetchAccounting,
  refreshAccounting,
} = useCheckoutAccounting()
const hasFnsAccountingData = computed(() => Boolean(
  report.value && report.value.period_years.length > 0,
))
const shouldShowCompanyData = computed(() => {
  if (!companyData.value) return false
  if (!isBankStatementMode.value) return true
  return hasFnsAccountingData.value
})
const shouldShowAccountingLoading = computed(() => {
  return !isBankStatementMode.value && accountingStatus.value === 'loading'
})

// --- UI state
const tabs = [
  { id: 'accounting', label: 'Бухгалтерская отчётность' },
  { id: 'requisites', label: 'Реквизиты' },
  { id: 'founders', label: 'Учредители' },
] as const
type TabId = typeof tabs[number]['id']
const activeTab = ref<TabId>('accounting')
const selectedYear = ref<number | null>(null)

// --- Computed from company profile
const orgInfo = computed(() => report.value?.organization ?? null)
const headerTitle = computed(() => {
  const cd = companyData.value
  if (!cd) return ''
  return (cd.short_name as string) || (cd.full_name as string) || (cd.name as string) || 'Компания'
})
const headerSubtitle = computed(() => {
  const cd = companyData.value
  if (!cd) return ''
  return (cd.full_name as string) && cd.full_name !== cd.short_name ? (cd.full_name as string) : ''
})
const companyStatus = computed<{ ok: boolean; label: string } | null>(() => {
  const s = (orgInfo.value?.status || '').toString().toLowerCase()
  if (!s) return null
  const ok = s.includes('действ')
  return { ok, label: orgInfo.value?.status || '' }
})
const registrationDate = computed(() => {
  return resolveCompanyRegistrationDate(companyData.value, orgInfo.value)
})
const taxAuthorityLabel = computed(() => {
  const name = orgInfo.value?.tax_authority_name
  const code = orgInfo.value?.tax_authority_code
  if (!name || !code) return null
  return `${name} (код ${code})`
})

const additionalOkvedList = computed<Array<{ code: string; description?: string }>>(() => {
  const source = companyData.value?.additional_okved_list
  if (!source) return []
  try {
    if (Array.isArray(source)) return source as Array<{ code: string; description?: string }>
    if (typeof source === 'string') return JSON.parse(source)
  } catch {
    // swallow
  }
  return []
})
const hasMainOkved = computed(() => !!companyData.value?.main_okved_code)
const hasBankData = computed(() => !!(companyData.value?.bank_bik || companyData.value?.bank_name || companyData.value?.bank_account_number))
const hasFinancialMeta = computed(() => !!(companyData.value?.authorized_capital || companyData.value?.net_profit || companyData.value?.reporting_year))

const foundersList = computed<CompanyFounderDisplay[]>(() => {
  return normalizeCompanyFounders(
    companyData.value?.founders,
    companyData.value?.director_inn as string | null | undefined,
  )
})


// --- Derived from accounting report + selected year
const selectedYearFile = computed<AccountingYearFile | null>(() => {
  if (!report.value || selectedYear.value === null) return null
  return report.value.year_files.find((f: AccountingYearFile) => f.year === selectedYear.value) ?? null
})
const selectedYearMinus1 = computed(() => (selectedYear.value ?? 0) - 1)
const balanceYears = computed(() => {
  if (selectedYear.value === null) return [] as number[]
  return [selectedYear.value, selectedYear.value - 1, selectedYear.value - 2]
})
const twoYears = computed(() => {
  if (selectedYear.value === null) return [] as number[]
  return [selectedYear.value, selectedYear.value - 1]
})

/** Row lookup by BFO code across the selected year. */
const valueByCode = (rows: AccountingReport['balance_sheet'], code: string, year: number | null): number | null => {
  if (year === null) return null
  const row = rows.find((r) => r.code === code)
  if (!row) return null
  const raw = row.values[String(year)]
  return raw === undefined ? null : raw
}

const kpiCards = computed(() => {
  if (!report.value || selectedYear.value === null) return []
  const r = report.value
  const y = selectedYear.value
  const p = y - 1
  const curr = (code: string, rows: typeof r.balance_sheet) => valueByCode(rows, code, y)
  const prev = (code: string, rows: typeof r.balance_sheet) => valueByCode(rows, code, p)
  const yoy = (a: number | null, b: number | null): number | null => {
    if (a === null || b === null || b === 0) return null
    return ((a - b) / Math.abs(b)) * 100
  }
  return [
    { key: 'revenue', label: 'Выручка', value: curr('2110', r.financial_result), yoy: yoy(curr('2110', r.financial_result), prev('2110', r.financial_result)) },
    { key: 'profit', label: 'Чистая прибыль', value: curr('2400', r.financial_result), yoy: yoy(curr('2400', r.financial_result), prev('2400', r.financial_result)) },
    { key: 'assets', label: 'Активы', value: curr('1600', r.balance_sheet), yoy: yoy(curr('1600', r.balance_sheet), prev('1600', r.balance_sheet)) },
    { key: 'equity', label: 'Капитал', value: curr('1300', r.balance_sheet), yoy: yoy(curr('1300', r.balance_sheet), prev('1300', r.balance_sheet)) },
  ]
})

// --- Charts
const revenueCanvas = ref<HTMLCanvasElement | null>(null)
const balanceCanvas = ref<HTMLCanvasElement | null>(null)
// Chart.js generic ties the instance type to the chart's `type`; keep these
// untyped (any) — they hold either the line or the bar instance.
let revenueChart: any = null
let balanceChart: any = null

const renderCharts = () => {
  if (!process.client || !report.value) return
  const r = report.value

  // Gather all years present across FR and balance, sorted ascending.
  const yearsAsc = [...new Set([...(r.period_years || [])])].sort((a, b) => a - b)
  if (yearsAsc.length === 0) return

  const revRow = r.financial_result.find((row: AccountingRow) => row.code === '2110')
  const profRow = r.financial_result.find((row: AccountingRow) => row.code === '2400')
  const assetsRow = r.balance_sheet.find((row: AccountingRow) => row.code === '1600')
  const equityRow = r.balance_sheet.find((row: AccountingRow) => row.code === '1300')

  const toSeries = (row: AccountingRow | undefined) => yearsAsc.map((y: number) => row?.values[String(y)] ?? null)

  // --- Revenue + net profit line
  if (revenueCanvas.value) {
    revenueChart?.destroy()
    revenueChart = new Chart(revenueCanvas.value.getContext('2d')!, {
      type: 'line',
      data: {
        labels: yearsAsc.map(String),
        datasets: [
          { label: 'Выручка', data: toSeries(revRow), borderColor: 'rgb(37, 99, 235)', backgroundColor: 'rgba(37, 99, 235, 0.15)', tension: 0.25, fill: true },
          { label: 'Чистая прибыль', data: toSeries(profRow), borderColor: 'rgb(16, 185, 129)', backgroundColor: 'rgba(16, 185, 129, 0.15)', tension: 0.25, fill: true },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatAmount(ctx.parsed.y as number)}` } },
        },
        scales: {
          y: { beginAtZero: false, ticks: { callback: (v) => formatAxisAmount(Number(v)) } },
        },
      },
    })
  }

  // --- Assets vs equity bar
  if (balanceCanvas.value) {
    balanceChart?.destroy()
    balanceChart = new Chart(balanceCanvas.value.getContext('2d')!, {
      type: 'bar',
      data: {
        labels: yearsAsc.map(String),
        datasets: [
          { label: 'Активы', data: toSeries(assetsRow), backgroundColor: 'rgba(59, 130, 246, 0.8)' },
          { label: 'Капитал', data: toSeries(equityRow), backgroundColor: 'rgba(249, 115, 22, 0.8)' },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatAmount(ctx.parsed.y as number)}` } },
        },
        scales: {
          y: { beginAtZero: true, ticks: { callback: (v) => formatAxisAmount(Number(v)) } },
        },
      },
    })
  }
}

onBeforeUnmount(() => {
  revenueChart?.destroy()
  balanceChart?.destroy()
})

// --- Formatters
const ruAmount = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
const formatAmount = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—'
  return `${ruAmount.format(Math.round(value))} ₽`
}
const formatAxisAmount = (value: number): string => {
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} млрд`
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} млн`
  if (abs >= 1_000) return `${(value / 1_000).toFixed(0)} тыс`
  return String(value)
}
const formatDate = (raw: string | null | undefined): string => {
  if (!raw) return ''
  try {
    const d = new Date(raw)
    if (Number.isNaN(d.getTime())) return raw
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return raw
  }
}
const ratioBandClass = (band: FinancialRatio['band']): string => {
  switch (band) {
    case 'good': return 'border-[color:var(--storefront-success-border,#a7f3d0)] bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/var(--tw-bg-opacity,1))]'
    case 'warn': return 'border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))]'
    case 'bad': return 'border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))]'
    default: return 'border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]'
  }
}
// --- Fetch
const applyCompanyProfile = async (profile: Record<string, unknown> | null | undefined) => {
  companyData.value = profile ? { ...profile } : null
  const inn = (profile?.inn as string) || ''
  if (inn) await fetchAccounting(inn)
}

const fetchCompany = async () => {
  if (!props.companyId) {
    await applyCompanyProfile(props.companyProfile || null)
    return
  }
  loadingCompany.value = true
  try {
    const resp = await notificationRequest<Record<string, unknown>>(`/api/v1/companies/${props.companyId}/profile`, {
      baseURL: config.public.apiBase,
      credentials: 'include',
    })
    await applyCompanyProfile({ ...(props.companyProfile || {}), ...(resp || {}) })
  } catch (err) {
    console.error('Error fetching company profile:', err)
    await applyCompanyProfile(props.companyProfile || null)
  } finally {
    loadingCompany.value = false
  }
}

const onRefreshAccounting = async () => {
  const inn = (companyData.value?.inn as string) || ''
  if (!inn) return
  await refreshAccounting(inn)
}

watch(
  () => [props.companyId, props.companyProfile] as const,
  () => { fetchCompany() },
  { immediate: true },
)

// Default-select the newest year whenever a report lands.
watch(report, (r) => {
  if (r && r.period_years.length > 0 && selectedYear.value === null) {
    selectedYear.value = r.period_years[0]
  }
}, { immediate: true })

// Chart render is driven by a reactive trigger — not an imperative call —
// so it fires exactly once the accounting tab is in the DOM and laid out.
// Earlier we called `renderCharts()` right after fetch but while
// `loadingCompany` was still true: the <canvas> wasn't mounted yet, and
// Chart.js drew into a 0×0 box — hence the blank canvas until a tab switch.
watch(
  [report, activeTab, loadingCompany, accountingStatus],
  async () => {
    if (loadingCompany.value) return
    if (accountingStatus.value !== 'success') return
    if (activeTab.value !== 'accounting') return
    if (!report.value) return
    await nextTick()
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    renderCharts()
  },
  { flush: 'post' },
)

// --- Public interface consumed by the parent checkout page.
// `checkBeforeNext` always allows proceeding (per product decision: BFO is
// informational, not a gate). `editableData` mirrors `companyData` so the
// parent can still read bank_bik / bank_name / bank_account_number for the
// next step. No editing / save API — the screen is read-only.
const checkBeforeNext = () => ({ canProceed: true, emptyFields: [] as string[] })
const editableData = computed(() => companyData.value || {})

defineExpose({
  companyData,
  foundersList,
  editableData,
  checkBeforeNext,
})
</script>
