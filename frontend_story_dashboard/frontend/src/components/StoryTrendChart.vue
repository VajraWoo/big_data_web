<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import type { Theme } from '../types'

echarts.use([GridComponent, LegendComponent, TooltipComponent, LineChart, CanvasRenderer])
const props = defineProps<{ themes: Theme[] }>()
const host = ref<HTMLElement>()
let chart: echarts.ECharts | undefined

const option = computed(() => {
  const months = Array.from(new Set(props.themes.flatMap(theme => (theme.trend ?? []).map(point => point.month)))).sort()
  return {
    animationDuration: 700,
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(17,24,39,.92)', borderWidth: 0, textStyle: { color: '#fff' } },
    legend: { top: 0, right: 6, itemWidth: 12, itemHeight: 6, textStyle: { color: '#64748b', fontSize: 11 } },
    grid: { left: 42, right: 18, top: 46, bottom: 28 },
    xAxis: { type: 'category', boundaryGap: false, data: months, axisLine: { lineStyle: { color: '#dce3ec' } }, axisLabel: { color: '#8490a3' } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#eef2f7' } }, axisLabel: { color: '#8490a3' } },
    series: props.themes.map((theme, index) => ({
      name: theme.name,
      type: 'line',
      smooth: true,
      showSymbol: false,
      symbolSize: 7,
      data: months.map(month => theme.trend?.find(point => point.month === month)?.review_count ?? null),
      lineStyle: { width: index === 0 ? 4 : 2 },
      areaStyle: index === 0 ? { opacity: .08 } : undefined,
      emphasis: { focus: 'series' },
    })),
  }
})

function resize() { chart?.resize() }
onMounted(() => {
  if (!host.value) return
  chart = echarts.init(host.value)
  chart.setOption(option.value)
  window.addEventListener('resize', resize)
})
watch(option, value => chart?.setOption(value, true), { deep: true })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart?.dispose() })
</script>

<template><div ref="host" class="story-trend" role="img" aria-label="核心主题月度走势"></div></template>
<style scoped>.story-trend{width:100%;height:330px}</style>
