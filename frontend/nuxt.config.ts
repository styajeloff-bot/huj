import { applyStorefrontRoutes } from './features/storefront/routeManifest'

const yandexMetrikaId = process.env.NUXT_PUBLIC_YANDEX_METRIKA_ID || '103750838'
const yandexMetrikaEnabled = process.env.NUXT_PUBLIC_YANDEX_METRIKA_ENABLED !== 'false'
const publicApiBase = process.env.NUXT_PUBLIC_API_BASE ?? ''
const apiInternalBase = process.env.NUXT_API_INTERNAL_BASE || ''

const yandexMetrikaScripts = yandexMetrikaEnabled
  ? [
      {
        innerHTML: `
          (function(m,e,t,r,i,k,a){
            m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
            m[i].l=1*new Date();
            for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
            k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
          })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=${yandexMetrikaId}', 'ym');

          ym(${yandexMetrikaId}, 'init', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", accurateTrackBounce:true, trackLinks:true});
        `,
        type: 'text/javascript'
      }
    ]
  : []

const yandexMetrikaNoscript = yandexMetrikaEnabled
  ? [
      {
        innerHTML: `<div><img src="https://mc.yandex.ru/watch/${yandexMetrikaId}" style="position:absolute; left:-9999px;" alt="" /></div>`
      }
    ]
  : []

export default defineNuxtConfig({
  hooks: {
    'pages:extend'(pages) {
      applyStorefrontRoutes(pages)
    },
  },
  devtools: { enabled: process.env.NODE_ENV !== 'production' },
  vite: {
    resolve: {
      alias: {
        '#app-manifest': '~/app/nuxt-app-manifest-shim.ts',
      },
    },
  },
  modules: [
    '@nuxtjs/tailwindcss',
    ['@pinia/nuxt', {
      storesDirs: [
        'stores',
        'features/cart/store',
        'features/checkout/store',
        'features/favorites/store',
        'features/purchases/store',
        'features/exchange/store',
      ],
    }],
  ],
  css: ['~/assets/css/main.css'],
  
  components: {
    dirs: [
      {
        path: '~/features',
        pathPrefix: true
      },
      {
        path: '~/components',
        pathPrefix: false
      }
    ]
  },
  
  experimental: {
    payloadExtraction: false
  },
  
  runtimeConfig: {
    // Disabled by default. Local/CI browser tests opt in at server runtime so
    // they can deterministically exercise the SSR error and client Retry path.
    e2eFaultInjectionEnabled: false,
    apiInternalBase,
    public: {
      apiBase: publicApiBase,
      siteUrl: process.env.NUXT_SITE_URL || 'https://multileasing.ru',
      verboxEnabled: process.env.NUXT_PUBLIC_VERBOX_ENABLED !== 'false',
    }
  },

  ssr: true,
  compatibilityDate: '2025-08-06',
  devServer: {
    host: process.env.NITRO_HOST || '0.0.0.0',
    port: parseInt(process.env.NITRO_PORT || '3000')
  },
  app: {
    head: {
      title: 'CarCraft Multileasing - Лизинг автомобилей для бизнеса',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=768, initial-scale=1' },
        { name: 'description', content: 'Лизинг автомобилей для бизнеса. Быстрое оформление, выгодные условия, широкий выбор автомобилей. CarCraft Multileasing - ваш надежный партнер в автолизинге.' },
        { name: 'keywords', content: 'лизинг автомобилей, автолизинг, лизинг для бизнеса, CarCraft, мультилизинг, лизинг авто' },
        { name: 'author', content: 'CarCraft Multileasing' },
        { property: 'og:title', content: 'CarCraft Multileasing - Лизинг автомобилей' },
        { property: 'og:description', content: 'Лизинг автомобилей для бизнеса. Быстрое оформление, выгодные условия.' },
        { property: 'og:type', content: 'website' },
        { property: 'og:site_name', content: 'CarCraft Multileasing' }
      ],
      link: [
        { rel: 'icon', type: 'image/png', href: '/images/favicon.png' },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Mulish:ital,wght@0,200..1000;1,200..1000&display=swap' }
      ],
      script: [
        ...yandexMetrikaScripts,
        // {
        //   src: 'https://app.uiscom.ru/static/cs.min.js?k=5gFQ5F56BW_2TKErgUaABMZiLQFmO01C',
        //   type: 'text/javascript',
        //   async: true
        // }
      ],
      noscript: yandexMetrikaNoscript
    }
  }
})
