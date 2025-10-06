<template>
  <a-card title="知识库使用情况" :loading="loading" class="dashboard-card">
    <!-- 知识库概览 -->
    <div class="stats-overview">
      <a-row :gutter="16">
        <a-col :span="8">
          <a-statistic
            title="知识库总数"
            :value="knowledgeStats?.total_databases || 0"
            :value-style="{ color: 'var(--chart-info)' }"
            suffix="个"
          />
        </a-col>
        <a-col :span="8">
          <a-statistic
            title="文件总数"
            :value="knowledgeStats?.total_files || 0"
            :value-style="{ color: 'var(--chart-success)' }"
            suffix="个"
          />
        </a-col>
        <a-col :span="8">
          <a-statistic
            title="存储容量"
            :value="formattedStorageSize"
            :value-style="{ color: 'var(--chart-warning)' }"
          />
        </a-col>
      </a-row>
    </div>

    <a-divider />

    <!-- 图表区域：拆分为两行 -->
    <a-row :gutter="24" style="margin-bottom: 16px;">
      <!-- 数据库类型分布 -->
      <a-col :span="24">
        <div class="chart-container">
          <div class="chart-header">
            <h4>数据库类型分布</h4>
            <div class="legend" v-if="dbTypeLegend.length">
              <div class="legend-item" v-for="(item, idx) in dbTypeLegend" :key="item.name">
                <span class="legend-color" :style="{ backgroundColor: getLegendColorByIndex(idx) }"></span>
                <span class="legend-label">{{ item.name }}</span>
              </div>
            </div>
          </div>
          <div ref="dbTypeChartRef" class="chart chart--thin"></div>
        </div>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <!-- 文件类型分布 -->
      <a-col :span="24">
        <div class="chart-container">
          <h4>文件类型分布</h4>
          <div ref="fileTypeChartRef" class="chart"></div>
        </div>
      </a-col>
    </a-row>

    <!-- 详细统计信息 -->
    <!-- <a-divider />
    <a-row :gutter="16">
      <a-col :span="8">
        <a-statistic
          title="平均每库文件数"
          :value="averageFilesPerDatabase"
          suffix="个"
          :precision="1"
        />
      </a-col>
      <a-col :span="8">
        <a-statistic
          title="平均每文件节点数"
          :value="averageNodesPerFile"
          suffix="个"
          :precision="1"
        />
      </a-col>
      <a-col :span="8">
        <a-statistic
          title="平均节点大小"
          :value="averageNodeSize"
          suffix="KB"
          :precision="2"
        />
      </a-col>
    </a-row> -->
  </a-card>
</template>

<script setup>
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import * as echarts from 'echarts'

// Props
const props = defineProps({
  knowledgeStats: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  }
})

// Chart refs
const dbTypeChartRef = ref(null)
const fileTypeChartRef = ref(null)
let dbTypeChart = null
let fileTypeChart = null

// 计算属性
const formattedStorageSize = computed(() => {
  const size = props.knowledgeStats?.total_storage_size || 0
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(2)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(2)} MB`
  return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`
})

// const averageFilesPerDatabase = computed(() => {
//   const databases = props.knowledgeStats?.total_databases || 0
//   const files = props.knowledgeStats?.total_files || 0
//   return databases > 0 ? files / databases : 0
// })

// const averageNodeSize = computed(() => {
//   const nodes = props.knowledgeStats?.total_nodes || 0
//   const size = props.knowledgeStats?.total_storage_size || 0
//   return nodes > 0 ? size / (nodes * 1024) : 0 // 转换为KB
// })

// 颜色数组 - 基于主题色的协调调色板
const colorPalette = [
  '#3996ae', // 主色调
  '#5faec2', // 主色调浅色
  '#82c3d6', // 主色调更浅
  '#a3d8e8', // 主色调最浅
  '#24839a', // 主色调深色
  '#046a82', // 主色调更深
  '#035065', // 主色调最深
  '#c4eaf5', // 极浅色
  '#e1f6fb', // 背景色
  '#f2fbfd'  // 最浅背景色
]

const getColorByIndex = (index) => {
  return colorPalette[index % colorPalette.length]
}

// 图例/分段颜色：与 base.css 中的 --chart-palette-* 保持一致（使用固定 HEX）
const legendPalette = [
  '#3996ae', // --chart-palette-1 -> var(--chart-primary)
  '#028ea0', // --chart-palette-2
  '#00b8a9', // --chart-palette-3
  '#f2c94c', // --chart-palette-4
  '#eb5757', // --chart-palette-5
  '#2f80ed', // --chart-palette-6
  '#9b51e0', // --chart-palette-7
  '#56ccf2', // --chart-palette-8
  '#6fcf97', // --chart-palette-9
  '#333333'  // --chart-palette-10
]
const getLegendColorByIndex = (index) => legendPalette[index % legendPalette.length]


// 初始化数据库类型分布图 - 横向分段条
const dbTypeLegend = ref([])
const initDbTypeChart = () => {
  if (!dbTypeChartRef.value || !props.knowledgeStats?.databases_by_type) return

  const entries = Object.entries(props.knowledgeStats.databases_by_type)
    .map(([type, count]) => ({ name: type || '未知', value: count }))
    .filter(item => item.value > 0)

  // update legend data
  dbTypeLegend.value = entries

  if (!dbTypeChart) {
    dbTypeChart = echarts.init(dbTypeChartRef.value)
  }

  const total = entries.reduce((sum, item) => sum + item.value, 0)

  // Build stacked bar series, but render with neutral color and separators
  const series = entries.map((item, idx) => ({
    name: item.name,
    type: 'bar',
    stack: 'total',
    barWidth: 28,
    data: [item.value],
    itemStyle: {
      color: getLegendColorByIndex(idx),
      borderColor: '#ffffff',
      borderWidth: 2,
      borderJoin: 'miter'
    },
    emphasis: {
      itemStyle: {
        color: getLegendColorByIndex(idx)
      }
    }
  }))

  const option = {
    animation: false,
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e8e8e8',
      borderWidth: 1,
      textStyle: { color: '#666' },
      formatter: (params) => {
        const value = params.value || 0
        return `${params.seriesName}: ${value}/${total}`
      }
    },
    grid: { left: 0, right: 0, top: 10, bottom: 10, containLabel: false },
    xAxis: {
      type: 'value',
      show: false,
      max: total > 0 ? total : undefined
    },
    yAxis: {
      type: 'category',
      show: false,
      data: ['all']
    },
    series
  }

  dbTypeChart.setOption(option, true)
}

// 初始化文件类型分布图
const initFileTypeChart = () => {
  if (!fileTypeChartRef.value) return

  fileTypeChart = echarts.init(fileTypeChartRef.value)

  // 检查是否有文件类型数据 - 兼容旧字段名和新字段名
  const fileTypesData = props.knowledgeStats?.files_by_type || props.knowledgeStats?.file_type_distribution || {}
  if (Object.keys(fileTypesData).length > 0) {
    const data = Object.entries(fileTypesData).map(([type, count]) => ({
      name: type || '未知',
      value: count
    }))

    const option = {
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#e8e8e8',
        borderWidth: 1,
        textStyle: {
          color: '#666'
        },
        formatter: '{a} <br/>{b}: {c} ({d}%)'
      },
      series: [{
        name: '文件类型',
        type: 'pie',
        radius: ['30%', '70%'],
        center: ['50%', '60%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 6,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: true,
          formatter: '{b}: {c}'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: '14',
            fontWeight: 'bold',
            color: '#333'
          },
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        },
        labelLine: {
          show: true
        },
        data: data,
        color: legendPalette
      }]
    }

    fileTypeChart.setOption(option)
  } else {
    // 如果没有文件类型数据，显示一个占位图表
    const option = {
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#e8e8e8',
        borderWidth: 1,
        textStyle: {
          color: '#666'
        },
        formatter: '{a} <br/>{b}: {c} ({d}%)'
      },
      series: [{
        name: '文件类型',
        type: 'pie',
        radius: ['30%', '70%'],
        center: ['50%', '60%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 6,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: true,
          formatter: '{b}: {c}'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: '14',
            fontWeight: 'bold',
            color: '#333'
          },
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        },
        labelLine: {
          show: true
        },
        data: [
          { name: '暂无数据', value: 1 }
        ],
        color: ['#e1f6fb']
      }]
    }

    fileTypeChart.setOption(option)
  }
}

// 更新图表
const updateCharts = () => {
  nextTick(() => {
    initDbTypeChart()
    initFileTypeChart()
  })
}

// 监听数据变化
watch(() => props.knowledgeStats, () => {
  updateCharts()
}, { deep: true })

// 窗口大小变化时重新调整图表
const handleResize = () => {
  if (dbTypeChart) dbTypeChart.resize()
  if (fileTypeChart) fileTypeChart.resize()
}

onMounted(() => {
  updateCharts()
  window.addEventListener('resize', handleResize)
})

// 组件卸载时清理
const cleanup = () => {
  window.removeEventListener('resize', handleResize)
  if (dbTypeChart) {
    dbTypeChart.dispose()
    dbTypeChart = null
  }
  if (fileTypeChart) {
    fileTypeChart.dispose()
    fileTypeChart = null
  }
}

// 导出清理函数供父组件调用
defineExpose({
  cleanup
})
</script>

<style scoped lang="less">
// KnowledgeStatsComponent 特有的样式
.chart-container {
  .chart-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;

    h4 {
      margin: 0;
    }

    .legend {
      display: flex;
      gap: 12px;
      align-items: center;

      .legend-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: #666;
      }

      .legend-color {
        width: 10px;
        height: 10px;
        border-radius: 2px;
      }
    }
  }

  .chart {
    height: 300px;
    width: 100%;
  }

  .chart--thin {
    height: 80px;
  }
}
</style>