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
import { NumberOutlined } from '@ant-design/icons-vue'

const props = defineProps({
  data: {
    type: Number,
    required: true
  }
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


</script>

<style lang="less" scoped>
.calculator-result {
  background: var(--gray-25);
  border-radius: 8px;

  .calc-header {
    padding: 12px 16px;

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
    padding: 16px;

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
        font-size: 1.1rem;
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
}
</style>