<template>
  <section data-storefront-block="shared.form" class="space-y-2 rounded-lg border border-[color:var(--storefront-success-border,#bbf7d0)] bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/0.8)] p-3">
    <h4 class="text-sm font-semibold text-[color:var(--storefront-success-text,#166534)]">
      {{ selectedPrograms.length === 1 ? 'Поддержка для этого ТС' : 'Поддержки для этого ТС' }}
    </h4>

    <p v-if="!sortedPrograms.length" class="text-[color:var(--storefront-text-muted,#6b7280)]">
      Нет доступных программ поддержки.
    </p>
    <div v-else class="space-y-2 text-xs sm:text-sm">
      <div
        v-for="program in sortedPrograms"
        :key="program.id"
        class="overflow-hidden rounded-lg border bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] transition-colors"
        :class="isSelected(program.id) ? 'border-[color:var(--storefront-success-border,#6ee7b7)]' : 'border-[color:var(--storefront-border,#e5e7eb)]'"
      >
        <button
          type="button"
          class="w-full px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60"
          :class="isSelected(program.id) ? 'bg-[color:rgb(var(--storefront-primary-rgb,236_253_245)/var(--tw-bg-opacity,1))]' : 'hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]'"
          :disabled="!isSelected(program.id) && Boolean(compatibilityError(program))"
          @click="toggle(program)"
        >
          <span class="flex items-center gap-2">
            <span
              aria-hidden="true"
              class="grid h-5 w-5 shrink-0 place-items-center rounded border"
              :class="isSelected(program.id) ? 'border-[color:var(--storefront-primary-border,#059669)] bg-[color:rgb(var(--storefront-primary-rgb,5_150_105)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)]' : 'border-[color:var(--storefront-primary-border,#d1d5db)] bg-[color:rgb(var(--storefront-primary-rgb,255_255_255)/var(--tw-bg-opacity,1))]'"
            >
              <span v-if="isSelected(program.id)">✓</span>
            </span>
            <span class="font-medium text-[color:var(--storefront-primary-foreground,#111827)]">{{ program.name }}</span>
          </span>
          <span
            v-if="compatibilityError(program)"
            class="mt-1 block pl-7 text-xs text-[color:var(--storefront-primary-foreground,#dc2626)]"
          >
            {{ compatibilityError(program) }}
          </span>
        </button>

        <div
          v-if="isSelected(program.id)"
          class="space-y-1 border-t border-[color:var(--storefront-success-border,#d1fae5)] px-3 py-2 text-[color:var(--storefront-text-muted,#4b5563)]"
        >
          <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span>{{ supportTypeLabel(program.support_type) }}</span>
            <span v-if="Number(program.support_amount) > 0">
              {{ formatPrice(Number(program.support_amount)) }}
            </span>
          </div>
          <div
            v-for="conduct in billConductionLines(program)"
            :key="`conduct-${program.id}-${conduct.dates}`"
            class="mt-0.5"
          >
            <span class="text-[color:var(--storefront-text-muted,#6b7280)]">{{ conduct.label }}</span>
            {{ conduct.dates }}
          </div>
          <div
            v-if="showBulletins && billOfLadingFiles(program).length"
            class="flex flex-col gap-1"
          >
            <span class="text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ billOfLadingFiles(program).length > 1 ? 'Бюллетени:' : 'Бюллетень:' }}
            </span>
            <div
              v-for="file in billOfLadingFiles(program)"
              :key="file.id || file.file_path || file.file_name || file.bill_date"
              class="flex flex-wrap items-center gap-2"
            >
              <a
                v-if="billFileUrl(file)"
                :href="billFileUrl(file) || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="text-[color:var(--storefront-link,#2563eb)] hover:underline"
              >
                {{ file.file_name || formatDate(file.bill_date) || 'Скачать' }}
              </a>
              <span v-else>{{ file.file_name || formatDate(file.bill_date) }}</span>
            </div>
          </div>
          <div v-if="programPeriod(program)" class="mt-1">
            <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Период:</span>
            {{ programPeriod(program) }}
          </div>
        </div>
      </div>
    </div>

    <p v-if="errorMessage" class="mt-2 text-xs text-[color:var(--storefront-error-text,#b91c1c)]">{{ errorMessage }}</p>
  </section>
</template>

<script setup lang="ts">
import type { SupportBadgeProgram, SupportType } from '~/types/support'
import { supportCandidateCompatibilityError } from '~/types/support'
import type { UUID } from '~/types/ids'

type BillOfLadingFile = {
  id?: UUID
  bill_date?: string
  file_name?: string
  file_path?: string
}

type BillOfLading = BillOfLadingFile & {
  files?: BillOfLadingFile[]
}

const props = withDefaults(defineProps<{
  programs: readonly SupportBadgeProgram[]
  selectedIds: readonly UUID[]
  showBulletins?: boolean
  errorMessage?: string
  apiBase?: string
}>(), {
  showBulletins: false,
  errorMessage: '',
  apiBase: '',
})

const emit = defineEmits<{
  change: [selectedIds: UUID[]]
}>()

const { formatPrice } = useFormatPrice()
const sortedPrograms = computed(() => [...props.programs].sort(
  (left, right) => left.id.localeCompare(right.id),
))
const selectedIdSet = computed(() => new Set(props.selectedIds))
const selectedPrograms = computed(() => (
  sortedPrograms.value.filter(program => selectedIdSet.value.has(program.id))
))

const isSelected = (programId: UUID): boolean => selectedIdSet.value.has(programId)

const compatibilityError = (program: SupportBadgeProgram): string | null => {
  if (isSelected(program.id)) return null
  return supportCandidateCompatibilityError(program, selectedPrograms.value)
}

function toggle(program: SupportBadgeProgram) {
  const selected = new Set(props.selectedIds)
  if (selected.has(program.id)) {
    selected.delete(program.id)
  } else {
    if (compatibilityError(program)) return
    selected.add(program.id)
  }
  emit('change', [...selected].sort((left, right) => left.localeCompare(right)))
}

function supportTypeLabel(type: SupportType | null): string {
  if (type === 'down_payment_compensation') return 'Поддержка первого взноса'
  if (type === 'vehicle_discount_dealer_compensation') return 'Поддержка на ТС (поддержка дилеру)'
  if (type === 'vehicle_discount_dealer_invoice') return 'Поддержка на ТС (уменьшение счёта)'
  if (type === 'leasing_interest_compensation') return 'Поддержка процентов по лизингу'
  return type || 'Поддержка'
}

function billOfLadingFiles(program: SupportBadgeProgram): BillOfLadingFile[] {
  const bill = program.bill_of_lading as BillOfLading | null | undefined
  if (!bill) return []
  if (Array.isArray(bill.files)) {
    return bill.files.filter(file => Boolean(
      file.file_path || file.file_name || file.bill_date,
    ))
  }
  return bill.file_path || bill.file_name || bill.bill_date ? [bill] : []
}

function formatDate(value: string | null | undefined): string {
  if (!value) return ''
  const [year, month, day] = value.slice(0, 10).split('-')
  return year && month && day ? `${day}.${month}.${year}` : value.slice(0, 10)
}

function billConductionLines(program: SupportBadgeProgram): Array<{ label: string; dates: string }> {
  const dates = [...new Set(
    billOfLadingFiles(program)
      .map(file => file.bill_date?.slice(0, 10))
      .filter((value): value is string => Boolean(value)),
  )].sort()
  if (!dates.length) return []
  return [{
    label: dates.length > 1 ? 'Даты проведения: ' : 'Дата проведения: ',
    dates: dates.map(formatDate).join(', '),
  }]
}

function billFileUrl(file: BillOfLadingFile): string | null {
  const path = file.file_path
  if (!path) return null
  if (/^https?:\/\//.test(path)) return path
  const apiBase = props.apiBase.replace(/\/$/, '')
  return apiBase ? `${apiBase}${path}` : path
}

function programPeriod(program: SupportBadgeProgram): string {
  if (!program.starts_at && !program.ends_at) return ''
  if (program.starts_at && !program.ends_at) return 'Бессрочный'
  if (!program.starts_at) return `до ${formatDate(program.ends_at)}`
  return `${formatDate(program.starts_at)} — ${formatDate(program.ends_at)}`
}
</script>
