import type { UUID } from '~/types/ids'

export type StorefrontPageStatus = 'draft' | 'published'

export type SectionLayoutType = 'container' | 'full_width'

export interface PageGlobalSettings {
  title?: string
  description?: string
  keywords?: string
  primary_color?: string
  background_color?: string
  surface_color?: string
  text_color?: string
  border_radius?: string
  font_id?: string | null
  font_family?: string
  custom_css?: string
  [key: string]: unknown
}

export interface SectionStyles {
  padding?: string
  margin?: string
  padding_top?: number
  padding_bottom?: number
  padding_left?: number
  padding_right?: number
  margin_top?: number
  margin_bottom?: number
  background_color?: string
  background_image?: string
  background_size?: 'cover' | 'contain' | 'auto'
  background_position?: string
  border_color?: string
  border_width?: number
  border_radius?: number | string
  custom_classes?: string
  [key: string]: unknown
}

export interface ColumnStyles {
  padding?: string
  padding_top?: number
  padding_bottom?: number
  padding_left?: number
  padding_right?: number
  background_color?: string
  border_radius?: number | string
  align?: 'top' | 'center' | 'bottom'
  custom_classes?: string
  [key: string]: unknown
}

export type WidgetType =
  | 'hero_banner'
  | 'leasing_calculator'
  | 'product_showcase'
  | 'features_grid'
  | 'lead_form'
  | 'partners_carousel'
  | 'rich_text'
  | 'faq_accordion'
  | 'contacts_block'
  | 'cta_strip'
  | 'spacer_divider'

export interface WidgetStyles {
  margin_top?: number
  margin_bottom?: number
  padding_top?: number
  padding_bottom?: number
  padding_left?: number
  padding_right?: number
  background_color?: string
  text_color?: string
  border_radius?: number | string
  align?: 'left' | 'center' | 'right'
  custom_css_classes?: string
  [key: string]: unknown
}

// Specific Widget Props

export interface HeroBannerWidgetProps {
  title: string
  subtitle?: string
  cta_text?: string
  cta_link?: string
  cta_anchor?: string
  secondary_cta_text?: string
  secondary_cta_link?: string
  badge_text?: string
  background_image?: string
  overlay_opacity?: number
  align?: 'left' | 'center' | 'right'
}

export interface LeasingCalculatorWidgetProps {
  title?: string
  subtitle?: string
  default_cost?: number
  min_cost?: number
  max_cost?: number
  default_term_months?: number
  min_term_months?: number
  max_term_months?: number
  default_down_payment_percent?: number
  min_down_payment_percent?: number
  max_down_payment_percent?: number
  interest_rate_percent?: number
  show_apply_button?: boolean
  cta_text?: string
  cta_action?: 'open_lead_form' | 'scroll_to_form' | 'redirect'
  cta_link?: string
}

export interface ProductShowcaseWidgetProps {
  title?: string
  subtitle?: string
  category_ids?: string[]
  mark_ids?: string[]
  item_count?: number
  mode?: 'grid' | 'carousel'
  columns_count?: 2 | 3 | 4
  sort_by?: 'newest' | 'price_asc' | 'price_desc'
  show_price?: boolean
  show_cta?: boolean
  cta_text?: string
  view_all_link?: string
}

export interface FeaturesGridItem {
  id?: string
  icon: string
  title: string
  description: string
}

export interface FeaturesGridWidgetProps {
  title?: string
  subtitle?: string
  columns?: 2 | 3 | 4
  items: FeaturesGridItem[]
}

export interface LeadFormWidgetProps {
  title?: string
  subtitle?: string
  show_inn?: boolean
  show_phone?: boolean
  show_name?: boolean
  show_comment?: boolean
  show_category?: boolean
  submit_button_text?: string
  success_message?: string
  pdn_agreement_text?: string
  category_options?: string[]
}

export interface PartnersCarouselItem {
  id?: string
  name: string
  logo_url: string
  link?: string
}

export interface PartnersCarouselWidgetProps {
  title?: string
  subtitle?: string
  items: PartnersCarouselItem[]
  grayscale?: boolean
}

export interface RichTextWidgetProps {
  html_content: string
  max_width?: 'full' | 'narrow' | 'wide'
}

export interface FaqAccordionItem {
  id?: string
  question: string
  answer: string
}

export interface FaqAccordionWidgetProps {
  title?: string
  subtitle?: string
  items: FaqAccordionItem[]
  open_first?: boolean
}

export interface ContactsBlockWidgetProps {
  title?: string
  subtitle?: string
  show_address?: boolean
  address?: string
  show_phone?: boolean
  phone?: string
  show_email?: boolean
  email?: string
  show_requisites?: boolean
  requisites?: string
  show_map?: boolean
  map_url?: string
  working_hours?: string
}

export interface CtaStripWidgetProps {
  title: string
  subtitle?: string
  button_text: string
  button_link: string
  secondary_button_text?: string
  secondary_button_link?: string
  background_style?: 'primary' | 'dark' | 'gradient' | 'light'
}

export interface SpacerDividerWidgetProps {
  height_px: number
  show_divider?: boolean
  divider_style?: 'solid' | 'dashed' | 'dotted'
  divider_color?: string
  divider_width_percent?: number
}

export type WidgetPropsMap = {
  hero_banner: HeroBannerWidgetProps
  leasing_calculator: LeasingCalculatorWidgetProps
  product_showcase: ProductShowcaseWidgetProps
  features_grid: FeaturesGridWidgetProps
  lead_form: LeadFormWidgetProps
  partners_carousel: PartnersCarouselWidgetProps
  rich_text: RichTextWidgetProps
  faq_accordion: FaqAccordionWidgetProps
  contacts_block: ContactsBlockWidgetProps
  cta_strip: CtaStripWidgetProps
  spacer_divider: SpacerDividerWidgetProps
}

export interface Widget<T = Record<string, any>> {
  id: UUID
  type: WidgetType
  is_hidden?: boolean
  props: T
  styles?: WidgetStyles
}

// Aliases for editor interoperability
export type WidgetInstance = Widget

export interface WidgetDefinition {
  type: WidgetType
  title: string
  name?: string
  description: string
  icon: string
  category: 'promo' | 'catalog' | 'interaction' | 'content' | 'layout'
  defaultProps: Record<string, any>
  defaultStyles?: WidgetStyles
}

export interface Column {
  id: UUID
  width: number // 1..12
  styles?: ColumnStyles
  widgets: Widget[]
}

export interface Section {
  id: UUID
  name: string
  layout_type: SectionLayoutType
  styles?: SectionStyles
  columns: Column[]
}

export interface PageLayout {
  settings: PageGlobalSettings
  sections: Section[]
}

export interface StorefrontPageSummary {
  id: UUID
  storefront_id: UUID
  page_key: string
  title: string
  slug: string
  is_system: boolean
  status: StorefrontPageStatus
  version: number
  has_unpublished_draft: boolean
  published_at: string | null
  updated_at: string
}

export type StorefrontPageListItem = StorefrontPageSummary

export interface StorefrontPage {
  id: UUID
  storefront_id: UUID
  page_key: string
  title: string
  slug: string
  is_system: boolean
  status: StorefrontPageStatus
  version: number
  has_unpublished_draft: boolean
  draft_layout: PageLayout
  published_layout: PageLayout | null
  published_at: string | null
  created_at: string
  updated_at: string
}

export type StorefrontPageDetail = StorefrontPage

export interface StorefrontPageRevision {
  id: UUID
  page_id: UUID
  version: number
  summary: string
  layout_snapshot: PageLayout
  created_by?: UUID | null
  created_by_name?: string | null
  created_at: string
}

export interface StorefrontTemplate {
  id: UUID
  code: string
  name: string
  description: string | null
  category: 'general' | 'leasing' | 'promo' | string
  preview_image_url: string | null
  layout: PageLayout
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface StorefrontPreset {
  schema_version: string
  title: string
  page_key: string
  layout: PageLayout
  exported_at?: string
  metadata?: Record<string, unknown>
}

export interface StorefrontPresetPreviewResponse {
  is_valid: boolean
  schema_version: string
  sections_count: number
  widgets_count: number
  widget_types: WidgetType[]
  warnings: string[]
}

export type PresetPreview = StorefrontPresetPreviewResponse

export interface CreateStorefrontPagePayload {
  title: string
  page_key: string
  slug: string
  template_code?: string
}

export interface SaveDraftPayload {
  title?: string
  expected_version: number
  summary?: string
  draft_layout: PageLayout
}

export interface PublishPagePayload {
  expected_version: number
}

export interface ImportPresetPayload {
  preset_data: StorefrontPreset
  expected_version: number
  summary?: string
}

export interface StorefrontPageListResponse {
  items: StorefrontPageSummary[]
}

export interface StorefrontPageRevisionListResponse {
  items: StorefrontPageRevision[]
}

export interface StorefrontTemplateListResponse {
  items: StorefrontTemplate[]
}

export interface StorefrontMediaUploadResponse {
  url: string
  storage_key?: string
}

export interface PublicStorefrontPageResponse {
  id?: UUID
  storefront_id?: UUID
  page_key?: string
  title?: string
  slug?: string
  layout?: PageLayout | null
  version?: number
  fallback_layout?: boolean
}

export function createEmptyLayout(): PageLayout {
  return {
    settings: {
      title: '',
      description: '',
      keywords: '',
      primary_color: '#2563EB',
      background_color: '#FFFFFF',
      surface_color: '#FFFFFF',
      text_color: '#1F2937',
      border_radius: 'medium',
    },
    sections: [],
  }
}

const WIDGET_DEFINITIONS_LIST: WidgetDefinition[] = [
  {
    type: 'hero_banner',
    title: 'Главный баннер',
    name: 'Главный баннер',
    description: 'Промо-баннер с заголовком, CTA кнопкой и фоновым изображением',
    icon: 'SparklesIcon',
    category: 'promo',
    defaultProps: {
      title: 'Мы — больше, чем лизинг',
      subtitle: 'Подай одну заявку — получи несколько одобрений на особых условиях для юридических лиц',
      cta_text: 'Оформить заявку',
      cta_link: '/special-equipment',
      badge_text: 'Лизинг 2026',
      align: 'left',
      overlay_opacity: 40,
    },
  },
  {
    type: 'leasing_calculator',
    title: 'Лизинговый калькулятор',
    name: 'Лизинговый калькулятор',
    description: 'Интерактивный расчет платежей и экономии по налогам',
    icon: 'CalculatorIcon',
    category: 'interaction',
    defaultProps: {
      title: 'Лизинговый калькулятор',
      subtitle: 'Рассчитайте ежемесячный платёж и выгоду по налогам',
      default_cost: 3000000,
      min_cost: 500000,
      max_cost: 20000000,
      default_term_months: 36,
      default_down_payment_percent: 20,
      show_apply_button: true,
      cta_text: 'Подать заявку',
    },
  },
  {
    type: 'product_showcase',
    title: 'Витрина техники',
    name: 'Витрина техники',
    description: 'Сетка или карусель предложений спецтехники из каталога',
    icon: 'TruckIcon',
    category: 'catalog',
    defaultProps: {
      title: 'Каталог спецтехники',
      subtitle: 'Техника в наличии с возможностью оформления в лизинг за 1 день',
      item_count: 4,
      columns_count: 4,
      show_price: true,
      show_cta: true,
      cta_text: 'В лизинг',
    },
  },
  {
    type: 'features_grid',
    title: 'Преимущества / УТП',
    name: 'Преимущества / УТП',
    description: 'Сетка карточек с иконками, заголовками и описанием преимуществ',
    icon: 'ShieldCheckIcon',
    category: 'content',
    defaultProps: {
      title: 'Преимущества работы с нами',
      subtitle: 'Почему выбирают Carcraft для финансирования техники',
      columns: 4,
      items: [
        {
          icon: 'clock',
          title: 'Решение за 1 день',
          description: 'Быстрое рассмотрение заявки по 2 документам',
        },
        {
          icon: 'percent',
          title: 'Аванс от 0%',
          description: 'Индивидуальные условия лизинга с минимальным изъятием средств',
        },
        {
          icon: 'shield',
          title: 'Надежные партнеры',
          description: 'Топ-15 аккредитованных лизинговых компаний России',
        },
        {
          icon: 'tax',
          title: 'Экономия до 40%',
          description: 'Полный зачет НДС и уменьшение налога на прибыль',
        },
      ],
    },
  },
  {
    type: 'lead_form',
    title: 'Форма заявки',
    name: 'Форма заявки',
    description: 'Форма сбора лидов с ИНН, телефоном и согласием на обработку ПДн',
    icon: 'EnvelopeIcon',
    category: 'interaction',
    defaultProps: {
      title: 'Оставить заявку на лизинг',
      subtitle: 'Заполните форму, и мы подберем предложения от лучших лизингодателей',
      show_inn: true,
      show_phone: true,
      show_name: true,
      show_comment: true,
      show_category: true,
      submit_button_text: 'Отправить заявку',
    },
  },
  {
    type: 'partners_carousel',
    title: 'Логотипы партнеров',
    name: 'Логотипы партнеров',
    description: 'Блок логотипов банков и лизинговых компаний',
    icon: 'BuildingOfficeIcon',
    category: 'content',
    defaultProps: {
      title: 'Наши партнеры',
      subtitle: 'Ведущие аккредитованные лизинговые компании России',
      grayscale: true,
      items: [],
    },
  },
  {
    type: 'rich_text',
    title: 'Текстовый блок',
    name: 'Текстовый блок',
    description: 'Форматированный текст (HTML) с безопасной санитизацией',
    icon: 'DocumentTextIcon',
    category: 'content',
    defaultProps: {
      html_content: '<h2>О компании</h2><p>Описание услуг и преимуществ для клиентов.</p>',
      max_width: 'wide',
    },
  },
  {
    type: 'faq_accordion',
    title: 'Вопросы и ответы (FAQ)',
    name: 'Вопросы и ответы (FAQ)',
    description: 'Раскрывающийся аккордеон с популярными вопросами и ответами',
    icon: 'QuestionMarkCircleIcon',
    category: 'content',
    defaultProps: {
      title: 'Часто задаваемые вопросы',
      subtitle: 'Ответы на популярные вопросы об условиях лизинга',
      open_first: true,
      items: [],
    },
  },
  {
    type: 'contacts_block',
    title: 'Контакты и реквизиты',
    name: 'Контакты и реквизиты',
    description: 'Карточка контактов компании, телефоны, email и карта',
    icon: 'MapPinIcon',
    category: 'content',
    defaultProps: {
      title: 'Контакты и реквизиты',
      subtitle: 'Свяжитесь с нами удобным способом',
      show_phone: true,
      show_email: true,
      show_address: true,
      show_requisites: true,
    },
  },
  {
    type: 'cta_strip',
    title: 'Призыв к действию (CTA)',
    name: 'Призыв к действию (CTA)',
    description: 'Яркая конверсионная плашка с кнопкой действия',
    icon: 'MegaphoneIcon',
    category: 'promo',
    defaultProps: {
      title: 'Нужна помощь в выборе техники или расчете лизинга?',
      subtitle: 'Оставьте заявку, и наш специалист свяжется с вами',
      button_text: 'Получить консультацию',
      button_link: '#lead-form',
      background_style: 'primary',
    },
  },
  {
    type: 'spacer_divider',
    title: 'Отступ / Разделитель',
    name: 'Отступ / Разделитель',
    description: 'Настраиваемый вертикальный отступ или разделительная линия',
    icon: 'ArrowsUpDownIcon',
    category: 'layout',
    defaultProps: {
      height_px: 32,
      show_divider: true,
      divider_style: 'solid',
      divider_width_percent: 100,
    },
  },
]

// Support both Array methods (.map, .filter) and dictionary indexing (WIDGET_REGISTRY[type])
export type WidgetRegistryMap = WidgetDefinition[] & Record<string, WidgetDefinition>

const registryMap: Record<string, WidgetDefinition> = {}
for (const def of WIDGET_DEFINITIONS_LIST) {
  registryMap[def.type] = def
}

export const WIDGET_REGISTRY: WidgetRegistryMap = Object.assign(
  [...WIDGET_DEFINITIONS_LIST],
  registryMap,
)

export const BUILT_IN_TEMPLATES: StorefrontTemplate[] = [
  {
    id: '00000000-0000-0000-0000-000000000001',
    code: 'classic-leasing',
    name: 'Классический лизинг',
    description: 'Универсальный шаблон для лизинговой компании: промо-баннер, калькулятор, преимущества и форма заявки',
    category: 'leasing',
    preview_image_url: null,
    is_active: true,
    layout: {
      settings: {
        title: 'Лизинг автотранспорта и спецтехники для бизнеса',
        description: 'Выгодные программы лизинга от ведущих компаний',
      },
      sections: [
        {
          id: 'sec-hero',
          name: 'Первый экран',
          layout_type: 'container',
          styles: { padding_top: 24, padding_bottom: 24 },
          columns: [
            {
              id: 'col-hero',
              width: 12,
              widgets: [
                {
                  id: 'w-hero',
                  type: 'hero_banner',
                  is_hidden: false,
                  props: {
                    title: 'Мы — больше, чем лизинг',
                    subtitle: 'Подай одну заявку — получи несколько одобрений на особых условиях для юридических лиц',
                    cta_text: 'Оформить заявку',
                    cta_link: '#lead-form',
                    badge_text: 'Лизинг 2026',
                  },
                },
              ],
            },
          ],
        },
        {
          id: 'sec-calc',
          name: 'Калькулятор лизинга',
          layout_type: 'container',
          styles: { padding_top: 32, padding_bottom: 32 },
          columns: [
            {
              id: 'col-calc',
              width: 12,
              widgets: [
                {
                  id: 'w-calc',
                  type: 'leasing_calculator',
                  is_hidden: false,
                  props: {
                    title: 'Лизинговый калькулятор',
                    subtitle: 'Рассчитайте ежемесячный платёж и выгоду по налогам',
                    default_cost: 3000000,
                  },
                },
              ],
            },
          ],
        },
        {
          id: 'sec-features',
          name: 'Преимущества',
          layout_type: 'container',
          styles: { padding_top: 32, padding_bottom: 32 },
          columns: [
            {
              id: 'col-features',
              width: 12,
              widgets: [
                {
                  id: 'w-features',
                  type: 'features_grid',
                  is_hidden: false,
                  props: {
                    title: 'Преимущества мультилизинга',
                    subtitle: 'Получите максимальную выгоду от сотрудничества с ведущими лизинговыми компаниями',
                    columns: 4,
                  },
                },
              ],
            },
          ],
        },
        {
          id: 'sec-lead',
          name: 'Форма заявки',
          layout_type: 'container',
          styles: { padding_top: 32, padding_bottom: 32 },
          columns: [
            {
              id: 'col-lead',
              width: 12,
              widgets: [
                {
                  id: 'w-lead',
                  type: 'lead_form',
                  is_hidden: false,
                  props: {
                    title: 'Оставить заявку на лизинг',
                    subtitle: 'Заполните форму, и мы подберем предложения от аккредитованных лизинговых компаний',
                  },
                },
              ],
            },
          ],
        },
      ],
    },
  },
  {
    id: '00000000-0000-0000-0000-000000000002',
    code: 'equipment-showcase',
    name: 'Каталожная витрина спецтехники',
    description: 'Шаблон с фокусом на демонстрацию техники в наличии, фильтрацию и каталог',
    category: 'promo',
    preview_image_url: null,
    is_active: true,
    layout: {
      settings: {
        title: 'Каталог спецтехники в лизинг',
        description: 'Широкий выбор техники с оформлением за 1 день',
      },
      sections: [
        {
          id: 'sec-eq-hero',
          name: 'Баннер каталога',
          layout_type: 'container',
          styles: { padding_top: 24, padding_bottom: 24 },
          columns: [
            {
              id: 'col-eq-hero',
              width: 12,
              widgets: [
                {
                  id: 'w-eq-hero',
                  type: 'hero_banner',
                  is_hidden: false,
                  props: {
                    title: 'Спецтехника в наличии и под заказ',
                    subtitle: 'Выгодный лизинг от 0% аванса с быстрой доставкой по РФ',
                    cta_text: 'Выбрать технику',
                    cta_link: '/special-equipment',
                  },
                },
              ],
            },
          ],
        },
        {
          id: 'sec-eq-showcase',
          name: 'Витрина',
          layout_type: 'container',
          styles: { padding_top: 32, padding_bottom: 32 },
          columns: [
            {
              id: 'col-eq-showcase',
              width: 12,
              widgets: [
                {
                  id: 'w-eq-showcase',
                  type: 'product_showcase',
                  is_hidden: false,
                  props: {
                    title: 'Популярные предложения спецтехники',
                    item_count: 8,
                    columns_count: 4,
                  },
                },
              ],
            },
          ],
        },
      ],
    },
  },
  {
    id: '00000000-0000-0000-0000-000000000003',
    code: 'promo-landing',
    name: 'Лизинговый промо-лендинг',
    description: 'Конверсионный посадочный лендинг под акцию со спецпредложением, таймингом и FAQ',
    category: 'promo',
    preview_image_url: null,
    is_active: true,
    layout: {
      settings: {
        title: 'Специальные условия лизинга',
        description: 'Акция на коммерческий транспорт и спецтехнику',
      },
      sections: [
        {
          id: 'sec-pr-hero',
          name: 'Промо баннер',
          layout_type: 'container',
          styles: { padding_top: 24, padding_bottom: 24 },
          columns: [
            {
              id: 'col-pr-hero',
              width: 12,
              widgets: [
                {
                  id: 'w-pr-hero',
                  type: 'hero_banner',
                  is_hidden: false,
                  props: {
                    title: 'Спецусловия на лизинг автотранспорта',
                    subtitle: 'Субсидированные ставки и ускоренное оформление до конца месяца',
                    cta_text: 'Получить расчет',
                    cta_link: '#lead-form',
                    badge_text: 'Спецпредложение',
                  },
                },
              ],
            },
          ],
        },
        {
          id: 'sec-pr-cta',
          name: 'CTA плашка',
          layout_type: 'container',
          styles: { padding_top: 16, padding_bottom: 16 },
          columns: [
            {
              id: 'col-pr-cta',
              width: 12,
              widgets: [
                {
                  id: 'w-pr-cta',
                  type: 'cta_strip',
                  is_hidden: false,
                  props: {
                    title: 'Оформите заявку прямо сейчас и зафиксируйте ставку',
                    subtitle: 'Бесплатная консультация финансового эксперта',
                    button_text: 'Подать заявку',
                    button_link: '#lead-form',
                  },
                },
              ],
            },
          ],
        },
        {
          id: 'sec-pr-faq',
          name: 'FAQ',
          layout_type: 'container',
          styles: { padding_top: 32, padding_bottom: 32 },
          columns: [
            {
              id: 'col-pr-faq',
              width: 12,
              widgets: [
                {
                  id: 'w-pr-faq',
                  type: 'faq_accordion',
                  is_hidden: false,
                  props: {
                    title: 'Вопросы и ответы по спецпрограмме',
                  },
                },
              ],
            },
          ],
        },
      ],
    },
  },
]
