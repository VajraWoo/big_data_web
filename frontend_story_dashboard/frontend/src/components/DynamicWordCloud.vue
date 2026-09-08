<script setup lang="ts">
import { computed } from 'vue'
import type { Theme } from '../types'
const props = defineProps<{ themes: Theme[] }>()
const words = computed(() => {
  const max = Math.max(1, ...props.themes.map(theme => theme.review_count))
  return props.themes.slice(0, 12).map((theme, index) => ({
    ...theme,
    size: 18 + Math.round((theme.review_count / max) * 24),
    delay: `${(index % 6) * -.8}s`,
    rotate: index % 5 === 0 ? '-4deg' : index % 4 === 0 ? '3deg' : '0deg',
  }))
})
</script>

<template>
  <div class="cloud" aria-label="动态主题词云">
    <button v-for="word in words" :key="word.theme_id" class="cloud-word" :style="{fontSize: `${word.size}px`, animationDelay: word.delay, transform: `rotate(${word.rotate})`}" @click="$emit('select', word)">
      {{ word.name }}
    </button>
    <div v-if="!words.length" class="empty">暂无可展示主题</div>
  </div>
</template>

<style scoped>
.cloud{min-height:260px;display:flex;align-content:center;justify-content:center;align-items:center;flex-wrap:wrap;gap:10px 18px;padding:18px;overflow:hidden}
.cloud-word{border:0;background:transparent;color:#1e293b;font-weight:800;line-height:1;letter-spacing:-.04em;cursor:pointer;animation:float 4.8s ease-in-out infinite;transition:.2s ease}
.cloud-word:nth-child(3n){color:#2563eb}.cloud-word:nth-child(4n){color:#475569}.cloud-word:nth-child(5n){color:#7c3aed}
.cloud-word:hover{transform:scale(1.08)!important;opacity:.78}.empty{color:#94a3b8;font-size:13px}
@keyframes float{0%,100%{translate:0 0}50%{translate:0 -7px}}
</style>
