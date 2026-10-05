import type { Component } from 'vue'
import type { WidgetType } from '../types'
import WidgetHeroBanner from './WidgetHeroBanner.vue'
import WidgetLeasingCalculator from './WidgetLeasingCalculator.vue'
import WidgetProductShowcase from './WidgetProductShowcase.vue'
import WidgetFeaturesGrid from './WidgetFeaturesGrid.vue'
import WidgetLeadForm from './WidgetLeadForm.vue'
import WidgetPartnersCarousel from './WidgetPartnersCarousel.vue'
import WidgetRichText from './WidgetRichText.vue'
import WidgetFaqAccordion from './WidgetFaqAccordion.vue'
import WidgetContactsBlock from './WidgetContactsBlock.vue'
import WidgetCtaStrip from './WidgetCtaStrip.vue'
import WidgetSpacerDivider from './WidgetSpacerDivider.vue'

export {
  WidgetHeroBanner,
  WidgetLeasingCalculator,
  WidgetProductShowcase,
  WidgetFeaturesGrid,
  WidgetLeadForm,
  WidgetPartnersCarousel,
  WidgetRichText,
  WidgetFaqAccordion,
  WidgetContactsBlock,
  WidgetCtaStrip,
  WidgetSpacerDivider,
}

export const WIDGET_COMPONENTS: Record<WidgetType, Component> = {
  hero_banner: WidgetHeroBanner,
  leasing_calculator: WidgetLeasingCalculator,
  product_showcase: WidgetProductShowcase,
  features_grid: WidgetFeaturesGrid,
  lead_form: WidgetLeadForm,
  partners_carousel: WidgetPartnersCarousel,
  rich_text: WidgetRichText,
  faq_accordion: WidgetFaqAccordion,
  contacts_block: WidgetContactsBlock,
  cta_strip: WidgetCtaStrip,
  spacer_divider: WidgetSpacerDivider,
}
