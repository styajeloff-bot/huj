<script setup lang="ts">
import { useStorefront } from '~/features/storefront'

definePageMeta({ middleware: ['auth'] })
const { publicRoute } = useStorefront()
await navigateTo(publicRoute('/cabinet?tab=my-cars'), { redirectCode: 301 })
</script>
