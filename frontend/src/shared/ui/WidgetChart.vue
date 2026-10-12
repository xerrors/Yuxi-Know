<template>
  <figure class="widget-chart" :aria-label="node.label">
    <template v-if="node.data.length">
      <div v-if="node.showLegend !== false" class="widget-chart-legend" aria-label="图例">
        <button
          v-for="(series, index) in node.series"
          :key="series.dataKey"
          type="button"
          :aria-pressed="!hiddenSeries.includes(series.dataKey)"
          :disabled="disabled"
          @click="toggleSeries(series.dataKey)"
        >
          <span
            class="widget-chart-swatch"
            :style="{ background: colors[index] }"
            aria-hidden="true"
          ></span
          >{{ series.label || series.dataKey }}
        </button>
      </div>
      <div
        ref="canvas"
        class="widget-chart-canvas"
        :style="{ height: `${node.height || 240}px` }"
        role="img"
        :aria-label="`${node.label}，可展开查看数据`"
      ></div>
      <p v-if="hiddenSeries.length === node.series.length" class="widget-chart-empty" role="status">
        已隐藏所有系列，点击图例恢复。
      </p>
      <details class="widget-chart-data">
        <summary>查看图表数据</summary>
        <div class="widget-chart-table-scroll">
          <table>
            <caption>
              {{
                node.label
              }}
            </caption>
            <thead>
              <tr>
                <th scope="col">类别</th>
                <th v-for="series in node.series" :key="series.dataKey" scope="col">
                  {{ series.label || series.dataKey }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in node.data" :key="index">
                <th scope="row">{{ row[node.xAxis] }}</th>
                <td v-for="series in node.series" :key="series.dataKey">
                  {{ row[series.dataKey] }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </template>
    <p v-else class="widget-chart-empty" role="status">暂无图表数据</p>
  </figure>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { init, use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { useThemeStore } from '@/shared/model/theme'

use([BarChart, LineChart, GridComponent, TooltipComponent, SVGRenderer])
const props = defineProps({ node: { type: Object, required: true }, disabled: Boolean })
const theme = useThemeStore()
const canvas = ref(null)
const colors = ref([])
const hiddenSeries = ref([])
let chart
let observer

onMounted(() => {
  if (!canvas.value) return
  observer = new ResizeObserver(drawChart)
  observer.observe(canvas.value)
  drawChart()
})
watch(() => theme.isDark, drawChart, { flush: 'post' })
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})

/** 只切换当前图表的查看状态，不发出业务动作。 */
function toggleSeries(key) {
  hiddenSeries.value = hiddenSeries.value.includes(key)
    ? hiddenSeries.value.filter((item) => item !== key)
    : [...hiddenSeries.value, key]
  drawChart()
}

/** 根据受限数据构建图表，主题与尺寸变化时更新同一实例。 */
function drawChart() {
  if (!canvas.value?.clientWidth) return
  const css = getComputedStyle(canvas.value)
  const color = (name) => css.getPropertyValue(name).trim()
  colors.value = ['--main-700', '--second-700', '--color-info-900'].map(color)
  chart ||= init(canvas.value, null, { renderer: 'svg' })
  chart.resize()
  chart.setOption(
    {
      animation: false,
      color: colors.value,
      grid: { left: 0, right: 8, top: 16, bottom: 8 },
      tooltip: {
        trigger: 'axis',
        renderMode: 'richText',
        confine: true,
        backgroundColor: color('--widget-surface'),
        borderColor: color('--widget-border'),
        textStyle: { color: color('--gray-900') }
      },
      xAxis: {
        type: 'category',
        data: props.node.data.map((row) => row[props.node.xAxis]),
        axisLine: { lineStyle: { color: color('--widget-border') } },
        axisTick: { show: false },
        axisLabel: {
          color: color('--widget-muted'),
          fontSize: 11,
          width: 52,
          overflow: 'truncate',
          hideOverlap: true
        }
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: color('--widget-muted'), fontSize: 11 },
        splitNumber: 4,
        splitLine: { lineStyle: { color: color('--widget-border'), type: 'dashed' } }
      },
      series: props.node.series.map((series) => ({
        type: series.type,
        name: series.label || series.dataKey,
        data: hiddenSeries.value.includes(series.dataKey)
          ? []
          : props.node.data.map((row) => row[series.dataKey]),
        barMaxWidth: 28,
        itemStyle: { borderRadius: series.type === 'bar' ? [4, 4, 0, 0] : 0 },
        symbolSize: 6,
        lineStyle: { width: 2.5 },
        emphasis: { focus: 'series' }
      }))
    },
    true
  )
}
</script>

<style lang="less">
.yuxi-widget .widget-chart {
  margin: 0;
  width: 100%;
  min-width: 0;
  .widget-chart-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    margin-bottom: 8px;
  }
  .widget-chart-legend button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 0;
    background: transparent;
    color: var(--widget-muted);
    font: inherit;
    font-size: 12px;
    padding: 4px 0;
    cursor: pointer;
  }
  .widget-chart-legend button[aria-pressed='false'] {
    opacity: 0.5;
    text-decoration: line-through;
  }
  .widget-chart-legend button:disabled {
    cursor: not-allowed;
  }
  .widget-chart-legend button:focus-visible {
    outline: 2px solid var(--main-700);
    outline-offset: 3px;
  }
  .widget-chart-swatch {
    width: 10px;
    height: 10px;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .widget-chart-canvas {
    width: 100%;
    min-width: 0;
  }
  .widget-chart-empty {
    font-size: 13px;
    color: var(--widget-muted);
    margin: 8px 0;
  }
  .widget-chart-data {
    margin-top: 8px;
    font-size: 12px;
    color: var(--widget-muted);
  }
  .widget-chart-data summary {
    cursor: pointer;
  }
  .widget-chart-table-scroll {
    max-height: 240px;
    overflow: auto;
  }
  table {
    width: 100%;
    margin: 8px 0 0;
    border-collapse: collapse;
    font-size: 12px;
  }
  th,
  td {
    padding: 6px 8px;
    text-align: start;
    border-bottom: 1px solid var(--widget-border);
    white-space: nowrap;
  }
  caption {
    text-align: start;
    padding: 8px;
  }
}
</style>
