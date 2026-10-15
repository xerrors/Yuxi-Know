import assert from 'node:assert/strict'
import test from 'node:test'
import { parseWidget } from '../../src/shared/lib/chatWidgets.js'

/** 使用合法天气图表定位单个错误字段。 */
const weatherChart = () => ({
  type: 'Chart', label: '每日最高/最低温', xAxis: 'date',
  data: [{ date: '10/15', high: 25, low: 17 }, { date: '10/16', high: 27, low: 19 }],
  series: [
    { type: 'line', dataKey: 'high', label: '最高温' },
    { type: 'line', dataKey: 'low', label: '最低温' }
  ]
})

/** 经实际组件树解析入口校验图表。 */
const parseChart = (chart) => parseWidget(JSON.stringify({ type: 'Card', children: [chart] }))

for (const [name, change, message] of [
  ['data 非数组', chart => { chart.data = {} }, 'Chart data 必须是数组'],
  ['超过记录上限', chart => { chart.data = Array(61).fill(chart.data[0]) }, 'Chart data 最多 60 条记录，当前为 61 条'],
  ['记录不是对象', chart => { chart.data[1] = null }, 'Chart data 第 2 条必须是对象'],
  ['记录是数组', chart => { chart.data[1] = [] }, 'Chart data 第 2 条必须是对象'],
  ['横轴列名与数据不匹配', chart => { chart.xAxis = 'category' }, 'Chart data 第 1 条缺少横轴字段 "category"（由 xAxis 指定）'],
  ['横轴值不是字符串', chart => { chart.data[1].date = 15 }, 'Chart data 第 2 条字段 "date" 必须是非空字符串，且不超过 4000 字符'],
  ['横轴值为空', chart => { chart.data[1].date = '  ' }, 'Chart data 第 2 条字段 "date" 必须是非空字符串，且不超过 4000 字符'],
  ['横轴值过长', chart => { chart.data[1].date = 'a'.repeat(4001) }, 'Chart data 第 2 条字段 "date" 必须是非空字符串，且不超过 4000 字符'],
  ['缺少系列值', chart => { delete chart.data[1].low }, 'Chart data 第 2 条缺少系列字段 "low"（由 series.dataKey 指定）'],
  ['系列值不是数字', chart => { chart.data[1].high = '27' }, 'Chart data 第 2 条字段 "high" 必须是有限数字'],
  ['系列值为 null', chart => { chart.data[1].high = null }, 'Chart data 第 2 条字段 "high" 必须是有限数字'],
  ['系列值超范围', chart => { chart.data[1].low = -1e12 - 1 }, 'Chart data 第 2 条字段 "low" 的绝对值不能超过 1e12'],
  ['未声明数据字段', chart => { chart.data[1].extra = 1 }, 'Chart data 第 2 条包含未声明的字段 "extra"'],
  ['series 非数组', chart => { chart.series = {} }, 'Chart series 必须是包含 1–3 项的数组'],
  ['series 为空', chart => { chart.series = [] }, 'Chart series 必须是包含 1–3 项的数组'],
  ['系列不是对象', chart => { chart.series[1] = null }, 'Chart series 第 2 项必须是对象'],
  ['系列类型错误', chart => { chart.series[1].type = 'pie' }, 'Chart series 第 2 项字段 "type" 只支持 bar/line'],
  ['系列列名非法', chart => { chart.series[1].dataKey = 'bad key' }, 'Chart series 第 2 项字段 "dataKey" 必须是合法数据列名'],
  ['系列列名与横轴冲突', chart => { chart.series[1].dataKey = 'date' }, 'Chart series 第 2 项字段 "dataKey" 不能与 xAxis 字段 "date" 相同'],
  ['系列列名重复', chart => { chart.series[1].dataKey = 'high' }, 'Chart series 第 2 项字段 "dataKey" 重复："high"'],
  ['系列标签错误', chart => { chart.series[1].label = '' }, 'Chart series 第 2 项字段 "label" 必须是非空字符串，且不超过 4000 字符'],
  ['系列属性不支持', chart => { chart.series[1].color = 'red' }, 'Chart series 第 2 项包含不支持的字段 "color"']
]) {
  test(`Chart 错误定位：${name}`, () => {
    const chart = weatherChart()
    change(chart)
    assert.throws(() => parseChart(chart), { message })
  })
}

test('Chart 合法记录和边界仍可解析，JSON物理行数不影响记录上限', () => {
  for (const length of [0, 7, 60]) {
    const chart = weatherChart()
    chart.data = Array.from({ length }, (_, index) => ({ date: `第 ${index + 1} 天`, high: 1e12, low: -1e12 }))
    const source = JSON.stringify({ type: 'Card', children: [chart] }, null, 2)
    if (length === 60) assert.ok(source.split('\n').length > 60)
    assert.deepEqual(parseWidget(source).children[0], chart)
  }
})

test('Chart 字段引用适用于任意合法列名，同步改名有效，遗漏同步仍拒绝', () => {
  for (const [axis, value] of [['bucket', 'value'], ['observed_at', 'latency_ms'], ['stage', 'count']]) {
    const chart = {
      type: 'Chart', label: '字段引用', xAxis: axis,
      series: [{ type: 'bar', dataKey: value }],
      data: [{ [axis]: 'A', [value]: 0 }, { [axis]: 'B', [value]: -1 }]
    }
    assert.deepEqual(parseChart(chart).children[0], chart)
    chart.xAxis = 'missing_column'
    assert.throws(() => parseChart(chart), {
      message: 'Chart data 第 1 条缺少横轴字段 "missing_column"（由 xAxis 指定）'
    })
  }
})
