<script setup lang="ts">
import { computed } from 'vue'
import type { Theme } from '../types'
const props = defineProps<{ themes: Theme[] }>()
const points = computed(() => {
  const maxCount = Math.max(1, ...props.themes.map(t => t.review_count))
  return props.themes.slice(0, 10).map((theme, index) => {
    const trend = theme.trend ?? []
    const first = trend[0]?.review_count ?? theme.review_count
    const last = trend[trend.length - 1]?.review_count ?? first
    const momentum = first ? (last - first) / first : 0
    const x = 12 + ((index * 29 + 17) % 78)
    const y = 18 + ((index * 37 + 11) % 58)
    const z = theme.review_count / maxCount
    return { ...theme, x, y, z, momentum, size: 14 + Math.round(z * 26) }
  })
})
</script>

<template>
  <div class="scene" aria-label="三维主题态势图">
    <div class="axis axis-x">评论量 →</div>
    <div class="axis axis-y">趋势动量 ↑</div>
    <div class="depth-lines"></div>
    <button v-for="point in points" :key="point.theme_id" class="point" :style="{left:`${point.x}%`,top:`${point.y}%`,width:`${point.size}px`,height:`${point.size}px`,opacity:`${.52 + point.z*.48}`,boxShadow:`0 ${8 + point.z*16}px ${16 + point.z*22}px rgba(37,99,235,.22)`}" @click="$emit('select', point)">
      <span class="dot"></span><span class="label">{{ point.name }}</span>
    </button>
    <div v-if="!points.length" class="empty">暂无三维态势数据</div>
  </div>
</template>

<style scoped>
.scene{position:relative;height:310px;overflow:hidden;border-radius:18px;background:linear-gradient(145deg,#fbfdff,#f4f7fb 62%,#eef3f9);perspective:700px}
.scene:before{content:"";position:absolute;inset:36px 34px 34px 52px;border-left:1px solid #ced8e5;border-bottom:1px solid #ced8e5;transform:skewY(-7deg)}
.depth-lines{position:absolute;inset:42px 28px 38px 56px;background:repeating-linear-gradient(0deg,transparent 0 46px,rgba(148,163,184,.13) 47px),repeating-linear-gradient(90deg,transparent 0 70px,rgba(148,163,184,.11) 71px);transform:skewY(-7deg)}
.point{position:absolute;border:0;background:transparent;padding:0;z-index:2;cursor:pointer}.dot{display:block;width:100%;height:100%;border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff 0 10%,#60a5fa 30%,#2563eb 68%,#172554 100%);border:1px solid rgba(255,255,255,.85)}
.label{position:absolute;left:calc(100% + 7px);top:50%;translate:0 -50%;white-space:nowrap;font-size:11px;font-weight:700;color:#475569;background:rgba(255,255,255,.84);backdrop-filter:blur(5px);padding:3px 6px;border-radius:6px}.point:hover{z-index:5;transform:scale(1.15)}
.axis{position:absolute;color:#8a97a9;font-size:10px;font-weight:700;letter-spacing:.06em}.axis-x{right:22px;bottom:13px}.axis-y{left:12px;top:18px;writing-mode:vertical-rl;transform:rotate(180deg)}.empty{position:absolute;inset:0;display:grid;place-items:center;color:#94a3b8;font-size:13px}
</style>
