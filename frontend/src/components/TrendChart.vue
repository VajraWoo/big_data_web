<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import type { TrendPoint } from '../types'

echarts.use([GridComponent, TooltipComponent, LineChart, CanvasRenderer])
const props = defineProps<{ points: TrendPoint[] }>()
const host = ref<HTMLElement>()
let chart: echarts.ECharts | undefined
const option = computed(() => ({
  tooltip: { trigger: 'axis' }, grid: { left: 42, right: 18, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: props.points.map(point => point.month) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'line', smooth: true, data: props.points.map(point => point.review_count), lineStyle: { color: '#2563eb' }, itemStyle: { color: '#2563eb' }, areaStyle: { color: 'rgba(37,99,235,.12)' } }],
}))
onMounted(() => { if (host.value) { chart = echarts.init(host.value); chart.setOption(option.value) } })
watch(option, value => chart?.setOption(value, true))
onBeforeUnmount(() => chart?.dispose())
</script>

<template><div ref="host" class="trend-chart" role="img" aria-label="主题月度评论趋势"></div></template>

<style scoped>.trend-chart { height: 240px; width: 100%; }</style>
