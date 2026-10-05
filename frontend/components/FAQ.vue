<template>
  <section data-storefront-block="home.faq" class="bg-storefront-surface py-16">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="text-center mb-12">
        <h2 class="mb-4 text-3xl font-bold text-storefront-title">
          Часто задаваемые вопросы
        </h2>
        <p class="text-lg text-storefront-text-muted">
          Ответы на популярные вопросы о лизинге автомобилей
        </p>
      </div>

      <div class="space-y-4">
        <div 
          v-for="(item, index) in faqItems" 
          :key="index"
          class="rounded-storefront-surface border border-storefront-border"
        >
          <button
            @click="toggleItem(index)"
            class="storefront-action-ghost w-full rounded-storefront-control px-6 py-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2"
            :class="{ 'bg-storefront-surface-muted': openItems.includes(index) }"
          >
            <div class="flex min-w-0 items-center justify-between gap-3">
              <h3 class="min-w-0 flex-1 text-lg font-medium text-storefront-title [overflow-wrap:anywhere]">
                {{ item.question }}
              </h3>
              <svg 
                class="h-5 w-5 shrink-0 transform text-storefront-icon transition-transform duration-200"
                :class="{ 'rotate-180': openItems.includes(index) }"
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
              </svg>
            </div>
          </button>
          
          <div 
            v-if="openItems.includes(index)"
            class="px-6 pb-4"
          >
            <div class="leading-relaxed text-storefront-text-muted">
              {{ item.answer }}
            </div>
          </div>
        </div>
      </div>

      <div class="text-center mt-12">
        <p class="mb-4 text-storefront-text-muted">
          Не нашли ответ на свой вопрос?
        </p>
        <div class="flex flex-col sm:flex-row gap-4 justify-center">
          <a 
            :href="`mailto:${contact_email}`"
            class="btn-secondary inline-flex items-center justify-center"
          >
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
            </svg>
            {{ contact_email }}
          </a>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'

const { contact_email } = useStorefront()
const openItems = ref<number[]>([])

const faqItems = ref([
  {
    question: 'Что такое лизинг и чем он отличается от кредита?',
    answer: 'Лизинг — это долгосрочная аренда автомобиля с правом выкупа. В отличие от кредита, при лизинге автомобиль остается в собственности лизинговой компании до полной выплаты. Это позволяет получить налоговые льготы и более гибкие условия финансирования.'
  },
  {
    question: 'Какой минимальный аванс?',
    answer: 'Минимальный аванс составляет от 10% от стоимости автомобиля. Некоторые лизинговые компании предлагают программы с нулевым взносом или отсрочкой платежей.'
  },
  {
    question: 'Можно ли досрочно погасить лизинговый договор?',
    answer: 'Да, большинство лизинговых компаний предусматривают возможность досрочного погашения. При этом могут действовать специальные условия и комиссии, которые прописываются в договоре.'
  },
  {
    question: 'Что происходит с автомобилем в конце срока лизинга?',
    answer: 'По окончании срока лизинга у вас есть несколько вариантов: выкупить автомобиль по остаточной стоимости, продлить договор лизинга, или вернуть автомобиль лизинговой компании.'
  },
  {
    question: 'Какие налоговые льготы дает лизинг?',
    answer: 'При лизинге лизинговые платежи относятся на расходы, что уменьшает налог на прибыль. Также применяется ускоренная амортизация (коэффициент до 3), что позволяет быстрее списать стоимость имущества.'
  },
  {
    question: 'Можно ли оформить страховку через лизинговую компанию?',
    answer: 'Да, большинство лизинговых компаний предлагают комплексные страховые продукты. Обычно это КАСКО, ОСАГО и страхование жизни заемщика. Стоимость страховки может быть включена в лизинговые платежи.'
  },
  {
    question: 'Сколько времени занимает рассмотрение заявки?',
    answer: 'Стандартное время рассмотрения заявки составляет от 1 до 3 рабочих дней. При предоставлении полного пакета документов и положительной кредитной истории решение может быть принято в течение нескольких часов.'
  }
])

const toggleItem = (index: number) => {
  const itemIndex = openItems.value.indexOf(index)
  if (itemIndex > -1) {
    openItems.value.splice(itemIndex, 1)
  } else {
    openItems.value.push(index)
  }
}
</script>
