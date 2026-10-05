<template>
  <div class="storefront-builder-widget py-6" :style="containerStyle">
    <!-- Header -->
    <div v-if="config.title || config.subtitle" class="mb-8 text-center">
      <h2 class="text-2xl font-bold tracking-tight storefront-builder-text sm:text-3xl">
        {{ config.title }}
      </h2>
      <p v-if="config.subtitle" class="mt-2 text-base storefront-builder-text-muted">
        {{ config.subtitle }}
      </p>
    </div>

    <!-- Accordion Items -->
    <div class="mx-auto max-w-3xl divide-y divide-slate-200 rounded-xl border storefront-builder-border storefront-builder-surface">
      <div
        v-for="(item, index) in faqList"
        :key="item.id || index"
        class="group"
      >
        <button
          type="button"
          class="flex w-full items-center justify-between px-6 py-5 text-left text-base font-semibold storefront-builder-text transition storefront-builder-hover-surface focus:outline-none focus-visible:ring-2 storefront-builder-focus"
          :aria-expanded="openIndices.has(index)"
          @click="toggleItem(index)"
        >
          <span>{{ item.question }}</span>
          <span class="ml-4 flex-shrink-0 storefront-builder-text-muted storefront-builder-group-hover-primary-text">
            <svg
              class="h-5 w-5 transform transition-transform duration-200"
              :class="openIndices.has(index) ? 'rotate-180 storefront-builder-primary-text' : ''"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </span>
        </button>

        <div
          v-if="openIndices.has(index)"
          class="px-6 pb-5 pt-1 text-sm leading-relaxed storefront-builder-text-muted"
        >
          {{ item.answer }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { widgetColorStyles } from '../utils/widgetStyles'
import { ref, computed, onMounted } from 'vue'
import type { FaqAccordionWidgetProps, FaqAccordionItem, WidgetStyles } from '../types'

const props = defineProps<{
  props?: FaqAccordionWidgetProps
  styles?: WidgetStyles
}>()

const defaultFaq: FaqAccordionItem[] = [
  {
    question: 'Какие документы нужны для подачи заявки на лизинг?',
    answer: 'Для предварительного решения достаточно предоставить карточку компании (реквизиты) и копию паспорта руководителя. Бухгалтерская отчетность запрашивается только при сумме финансирования от 15 млн рублей.',
  },
  {
    question: 'Какой минимальный первоначальный взнос (аванс)?',
    answer: 'Минимальный аванс начинается от 0% для постоянных клиентов и компаний с хорошей финансовой историей. Стандартный аванс по рынку составляет от 10% до 20%.',
  },
  {
    question: 'Сколько времени занимает одобрение заявки?',
    answer: 'Предварительное одобрение формируется скоринговой системой за 15-30 минут. Окончательное решение и подготовка договора занимает от 1 рабочего дня.',
  },
  {
    question: 'Можно ли оформить технику в лизинг на недавно открытое юридическое лицо?',
    answer: 'Да, у нас есть партнерские программы финансирования для компаний и индивидуальных предпринимателей со сроком регистрации от 3 месяцев, либо при наличии поручительства.',
  },
]

const config = computed<FaqAccordionWidgetProps>(() => ({
  title: 'Часто задаваемые вопросы',
  subtitle: 'Ответы на популярные вопросы об условиях и процессе лизинга',
  items: defaultFaq,
  open_first: true,
  ...props.props,
}))

const faqList = computed(() => {
  return config.value.items && config.value.items.length > 0
    ? config.value.items
    : defaultFaq
})

const openIndices = ref<Set<number>>(new Set())

const toggleItem = (idx: number) => {
  if (openIndices.value.has(idx)) {
    openIndices.value.delete(idx)
  } else {
    openIndices.value.add(idx)
  }
}

onMounted(() => {
  if (config.value.open_first ?? true) {
    openIndices.value.add(0)
  }
})

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  return s
})
</script>
