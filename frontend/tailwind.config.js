const storefrontRegistry = require('./features/storefront/colorRegistry.json')
const defaultTheme = require('tailwindcss/defaultTheme')
const plugin = require('tailwindcss/plugin')

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./components/**/*.{js,vue,ts}",
    "./features/**/*.{vue,ts}",
    "./layouts/**/*.vue",
    "./pages/**/*.vue",
    "./plugins/**/*.{js,ts}",
    "./nuxt.config.{js,ts}",
    "./app.vue"
  ],
  theme: {
    extend: {
      colors: {
        ...Object.fromEntries(Object.keys(storefrontRegistry.tokens).map(token => [
          `storefront-${token}`,
          `rgb(var(--storefront-${token}-rgb) / <alpha-value>)`,
        ])),
      },
      borderRadius: {
        'storefront-control': 'var(--storefront-radius-control)',
        'storefront-surface': 'var(--storefront-radius-surface)',
        'storefront-inner': 'var(--storefront-radius-inner)',
      },
      fontFamily: {
        'sans': ['var(--storefront-font-family, Mulish)', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'Noto Sans', 'sans-serif'],
      }
    },
  },
  plugins: [
    plugin(({ addUtilities }) => {
      // Tailwind's shadow-color utility replaces every layer's alpha with 1.
      // Keep its native geometry/alpha and substitute only the storefront RGB.
      // Dedicated size utilities also retain that RGB in hover/focus variants,
      // without changing ordinary workspace shadow-* utilities.
      addUtilities(Object.fromEntries(Object.entries(defaultTheme.boxShadow).map(([size, value]) => [
        `.storefront-shadow${size === 'DEFAULT' ? '' : `-${size}`}`,
        {
          '--tw-shadow': value === 'none' ? '0 0 #0000' : value.replaceAll(
            'rgb(0 0 0 /', 'rgb(var(--storefront-shadow-rgb, 0 0 0) /',
          ),
          'box-shadow': 'var(--tw-ring-offset-shadow, 0 0 #0000), var(--tw-ring-shadow, 0 0 #0000), var(--tw-shadow)',
        },
      ])))
    }),
  ],
}
