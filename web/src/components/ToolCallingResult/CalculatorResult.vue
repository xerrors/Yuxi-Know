<template>
  <div class="calculator-result">
    <div class="calc-header">
      <h4><NumberOutlined /> 计算结果</h4>
    </div>

    <div class="calc-display">
      <div class="result-container">
        <div class="result-value">{{ formatNumber(data) }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { message } from 'ant-design-vue'
import { NumberOutlined, CopyOutlined } from '@ant-design/icons-vue'
import { useClipboard } from '@vueuse/core'

const props = defineProps({
  data: {
    type: Number,
    required: true
  }
})

const { copy } = useClipboard()

// 计算属性
const isInteger = computed(() => Number.isInteger(props.data))

const showScientificNotation = computed(() => {
  const absValue = Math.abs(props.data)
  return absValue >= 1e6 || (absValue > 0 && absValue < 1e-3)
})

// 方法
const formatNumber = (num) => {
  if (typeof num !== 'number') return String(num)

  // 处理特殊值
  if (!isFinite(num)) {
    if (num === Infinity) return '∞'
    if (num === -Infinity) return '-∞'
    if (isNaN(num)) return 'NaN'
  }

  // 使用本地化格式
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: 10,
    useGrouping: true
  }).format(num)
}

const getNumberType = () => {
  if (!isFinite(props.data)) {
    if (isNaN(props.data)) return 'NaN'
    return '无穷大'
  }

  if (isInteger.value) {
    if (props.data === 0) return '零'
    if (props.data > 0) return '正整数'
    return '负整数'
  }

  if (props.data > 0) return '正数'
  if (props.data < 0) return '负数'
  return '数字'
}

const getNumberTypeColor = () => {
  if (!isFinite(props.data)) return 'red'
  if (props.data === 0) return 'default'
  if (props.data > 0) return 'green'
  return 'orange'
}

const getDecimalPlaces = () => {
  if (isInteger.value) return 0
  const decimalPart = String(props.data).split('.')[1]
  return decimalPart ? decimalPart.length : 0
}

const copyResult = async () => {
  try {
    await copy(String(props.data))
    message.success('计算结果已复制到剪贴板')
  } catch (error) {
    message.error('复制失败')
  }
}
</script>

<style lang="less" scoped>
.calculator-result {
  background: var(--gray-0);
  border-radius: 8px;
  border: 1px solid var(--gray-200);

  .calc-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--gray-200);
    background: var(--gray-50);

    h4 {
      margin: 0;
      color: var(--main-color);
      font-size: 14px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 6px;
    }
  }

  .calc-display {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 8px;
    padding: 16px;
    background: var(--main-10);
    border-radius: 6px;
    border: 1px solid var(--main-200);

    .result-container {
      display: flex;
      align-items: center;
      gap: 10px;
      flex: 1;

      .result-label {
        font-size: 13px;
        color: var(--gray-600);
        font-weight: 500;
      }

      .result-value {
        font-size: 20px;
        font-weight: 600;
        color: var(--main-color);
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        word-break: break-all;
      }
    }

    .result-actions {
      display: flex;
      gap: 6px;
    }
  }

  .scientific-notation {
    margin: 0 8px 8px 8px;
    padding: 8px 10px;
    background: var(--gray-50);
    border-radius: 4px;
    display: flex;
    align-items: center;
    gap: 8px;

    .notation-label {
      font-size: 12px;
      color: var(--gray-600);
    }

    .notation-value {
      font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
      font-size: 13px;
      color: var(--main-color);
      font-weight: 500;
    }
  }

  .number-info {
    padding: 0 8px 8px 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;

    .number-detail {
      color: var(--gray-600);
      background: var(--gray-100);
      padding: 2px 6px;
      border-radius: 3px;
    }
  }
}
</style>