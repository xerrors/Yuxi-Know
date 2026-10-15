const MAX_SOURCE_LENGTH = 24000
const MAX_NODES = 100
const MAX_DEPTH = 8
const containerTypes = new Set(['Card', 'ListView', 'ListViewItem', 'Row', 'Col', 'ImageGroup'])
const textTypes = new Set(['Title', 'Text', 'Caption'])
const layoutProperties = ['gap', 'padding', 'align', 'justify', 'flex']
const textProperties = ['size', 'weight', 'textAlign', 'color']
const WIDGET_ICON_NAMES = [
  'book-open',
  'document',
  'lightbulb',
  'info',
  'check',
  'plus',
  'search',
  'chevron-right'
]
const properties = {
  Card: ['children', 'size', 'padding'],
  ListView: ['children'],
  ListViewItem: ['children', 'onClickAction', 'gap', 'align'],
  Row: ['children', ...layoutProperties],
  Col: ['children', ...layoutProperties],
  Title: ['value', ...textProperties],
  Text: ['value', ...textProperties],
  Caption: ['value', ...textProperties],
  Badge: ['label', 'color', 'variant', 'size', 'pill'],
  Icon: ['name', 'size', 'color'],
  Chart: ['label', 'data', 'series', 'xAxis', 'showLegend', 'height'],
  Image: ['src', 'path', 'alt', 'caption', 'fit', 'aspectRatio'],
  ImageGroup: ['children'],
  Divider: [],
  Spacer: []
}

/** 校验模型输出的有限组件树，拒绝脚本、任意属性与未知动作。 */
export function parseWidget(source) {
  if (source.length > MAX_SOURCE_LENGTH) throw new Error('组件 JSON 超过 24000 字符')
  const root = JSON.parse(source)
  if (!['Card', 'ListView', 'Image', 'ImageGroup'].includes(root?.type))
    throw new Error('根组件必须是 Card、ListView、Image 或 ImageGroup')
  let count = 0
  const isTextValue = (value) => typeof value === 'string' && value.length <= 4000
  const isComposeAction = (value) =>
    value &&
    value.type === 'compose' &&
    isTextValue(value.text) &&
    value.text.trim() &&
    Object.keys(value).every((key) => ['type', 'text'].includes(key))

  /** 在渲染边界检查节点类型和属性。 */
  function visit(node, depth, inActionItem = false) {
    if (++count > MAX_NODES || depth > MAX_DEPTH)
      throw new Error('组件树超过 100 个节点或 8 层深度')
    const allowed = Object.hasOwn(properties, node?.type) ? properties[node.type] : null
    if (!allowed || Object.keys(node).some((key) => key !== 'type' && !allowed.includes(key))) {
      throw new Error('组件类型或属性不受支持')
    }
    if (inActionItem && (node.type === 'Chart' || node.onClickAction))
      throw new Error('可点击列表项不能包含交互控件')
    const enums = {
      align: ['start', 'center', 'end', 'baseline', 'stretch'],
      justify: ['start', 'center', 'end', 'between', 'around', 'evenly'],
      flex: [0, 1, 'auto'],
      weight: ['normal', 'medium', 'semibold', 'bold'],
      textAlign: ['start', 'center', 'end'],
      variant: ['solid', 'soft', 'outline'],
      size: {
        Card: ['sm', 'md', 'lg', 'full'],
        Title: ['xs', 'sm', 'md', 'lg', 'xl', '2xl'],
        Icon: ['xs', 'sm', 'md', 'lg', 'xl'],
        Text: ['xs', 'sm', 'md', 'lg', 'xl']
      }[node.type] || ['sm', 'md', 'lg']
    }
    for (const [key, values] of Object.entries(enums)) {
      if (node[key] !== undefined && !values.includes(node[key]))
        throw new Error(`${key} 属性不受支持`)
    }
    for (const key of ['gap', 'padding']) {
      if (
        node[key] !== undefined &&
        (!Number.isInteger(node[key]) || node[key] < 0 || node[key] > 8)
      )
        throw new Error(`${key} 必须是 0–8 的整数，单位为 4px`)
    }
    if (node.pill !== undefined && typeof node.pill !== 'boolean')
      throw new Error('pill 必须是布尔值')
    if (node.color !== undefined) {
      const colors =
        node.type === 'Badge'
          ? ['secondary', 'success', 'warning', 'danger', 'info']
          : ['primary', 'secondary', 'tertiary', 'success', 'warning', 'danger', 'info']
      if (!colors.includes(node.color)) throw new Error('组件颜色不受支持')
    }
    if (node.type === 'Icon' && !WIDGET_ICON_NAMES.includes(node.name))
      throw new Error('图标名称不受支持')
    if (node.type === 'Chart') {
      if (!isTextValue(node.label) || !node.label.trim()) throw new Error('Chart 需要非空 label')
      const isColumnKey = (value) =>
        typeof value === 'string' &&
        /^[a-zA-Z][a-zA-Z0-9_]{0,39}$/.test(value) &&
        !['constructor', 'prototype', '__proto__'].includes(value)
      if (!isColumnKey(node.xAxis)) throw new Error('Chart xAxis 必须是合法数据列名')
      if (!Array.isArray(node.series) || !node.series.length || node.series.length > 3)
        throw new Error('Chart series 必须是包含 1–3 项的数组')
      const seriesKeys = new Set()
      for (const [index, series] of node.series.entries()) {
        const location = `Chart series 第 ${index + 1} 项`
        if (!series || typeof series !== 'object' || Array.isArray(series))
          throw new Error(`${location}必须是对象`)
        if (!['bar', 'line'].includes(series.type))
          throw new Error(`${location}字段 "type" 只支持 bar/line`)
        if (!isColumnKey(series.dataKey))
          throw new Error(`${location}字段 "dataKey" 必须是合法数据列名`)
        if (series.dataKey === node.xAxis)
          throw new Error(`${location}字段 "dataKey" 不能与 xAxis 字段 "${node.xAxis}" 相同`)
        if (seriesKeys.has(series.dataKey))
          throw new Error(`${location}字段 "dataKey" 重复："${series.dataKey}"`)
        seriesKeys.add(series.dataKey)
        if (series.label !== undefined && (!isTextValue(series.label) || !series.label.trim()))
          throw new Error(`${location}字段 "label" 必须是非空字符串，且不超过 4000 字符`)
        const extraKey = Object.keys(series).find((key) => !['type', 'dataKey', 'label'].includes(key))
        if (extraKey !== undefined) throw new Error(`${location}包含不支持的字段 "${extraKey}"`)
      }
      if (!Array.isArray(node.data)) throw new Error('Chart data 必须是数组')
      if (node.data.length > 60)
        throw new Error(`Chart data 最多 60 条记录，当前为 ${node.data.length} 条`)
      const columns = [node.xAxis, ...seriesKeys]
      for (const [index, row] of node.data.entries()) {
        const location = `Chart data 第 ${index + 1} 条`
        if (!row || typeof row !== 'object' || Array.isArray(row))
          throw new Error(`${location}必须是对象`)
        if (!Object.hasOwn(row, node.xAxis))
          throw new Error(`${location}缺少横轴字段 "${node.xAxis}"（由 xAxis 指定）`)
        if (!isTextValue(row[node.xAxis]) || !row[node.xAxis].trim())
          throw new Error(`${location}字段 "${node.xAxis}" 必须是非空字符串，且不超过 4000 字符`)
        for (const { dataKey } of node.series) {
          if (!Object.hasOwn(row, dataKey))
            throw new Error(`${location}缺少系列字段 "${dataKey}"（由 series.dataKey 指定）`)
          if (!Number.isFinite(row[dataKey]))
            throw new Error(`${location}字段 "${dataKey}" 必须是有限数字`)
          if (Math.abs(row[dataKey]) > 1e12)
            throw new Error(`${location}字段 "${dataKey}" 的绝对值不能超过 1e12`)
        }
        const extraKey = Object.keys(row).find((key) => !columns.includes(key))
        if (extraKey !== undefined) throw new Error(`${location}包含未声明的字段 "${extraKey}"`)
      }
      if (
        node.height !== undefined &&
        (!Number.isInteger(node.height) || node.height < 180 || node.height > 400)
      )
        throw new Error('Chart height 必须是 180–400 的整数')
      if (node.showLegend !== undefined && typeof node.showLegend !== 'boolean')
        throw new Error('Chart showLegend 必须是布尔值')
    }
    if (node.type === 'Image') {
      if ((node.src !== undefined) === (node.path !== undefined))
        throw new Error('Image 必须指定 src 或 path 之一')
      if (node.path !== undefined) {
        if (
          !isTextValue(node.path) ||
          !node.path.startsWith('/') ||
          node.path.startsWith('//') ||
          /[\\\0]/.test(node.path) ||
          node.path.includes('://') ||
          node.path.split('/').includes('..')
        )
          throw new Error('Image path 必须是无跳转的沙盒虚拟绝对路径')
      } else {
        if (!isTextValue(node.src) || !node.src || /[\s\\]/.test(node.src))
          throw new Error('Image src 必须是 HTTPS URL 或同源绝对路径')
        let url
        try {
          url = new URL(node.src, 'https://widget.invalid')
        } catch {
          throw new Error('Image src 必须是 HTTPS URL 或同源绝对路径')
        }
        if (
          (!node.src.startsWith('https://') &&
            (!node.src.startsWith('/') || node.src.startsWith('//'))) ||
          url.protocol !== 'https:' ||
          url.username ||
          url.password
        )
          throw new Error('Image src 必须是无凭据的 HTTPS URL 或同源绝对路径')
      }
      if (!isTextValue(node.alt) || !node.alt.trim()) throw new Error('Image 需要非空 alt')
      if (node.caption !== undefined && (!isTextValue(node.caption) || !node.caption.trim()))
        throw new Error('Image caption 必须是非空短语')
      if (node.fit !== undefined && !['cover', 'contain'].includes(node.fit))
        throw new Error('Image fit 只支持 cover/contain')
      if (
        node.aspectRatio !== undefined &&
        (!Number.isFinite(node.aspectRatio) || node.aspectRatio < 0.5 || node.aspectRatio > 3)
      )
        throw new Error('Image aspectRatio 必须是 0.5–3 的数字')
    }
    if (textTypes.has(node.type) && !isTextValue(node.value))
      throw new Error('文本组件需要 value 字符串')
    if (node.type === 'Badge' && !isTextValue(node.label))
      throw new Error('组件需要 label 字符串')
    if (
      node.type === 'ListViewItem' &&
      node.onClickAction !== undefined &&
      !isComposeAction(node.onClickAction)
    )
      throw new Error('列表项只支持 compose 动作和非空 text')
    if (containerTypes.has(node.type)) {
      if (!Array.isArray(node.children)) throw new Error('容器需要 children 数组')
      if (node.type === 'ImageGroup' && !node.children.length)
        throw new Error('ImageGroup 至少需要一张图片')
      for (const child of node.children) {
        if (node.type === 'ImageGroup' && child?.type !== 'Image')
          throw new Error('ImageGroup 只能包含 Image')
        if (node.type === 'ListView' && child?.type !== 'ListViewItem')
          throw new Error('ListView 只能包含 ListViewItem')
        visit(
          child,
          depth + 1,
          inActionItem || (node.type === 'ListViewItem' && !!node.onClickAction)
        )
      }
    }
  }
  visit(root, 1)
  return root
}

/** 在 Markdown token 边界只提升显式启用且闭合的 widget 围栏。 */
export function widgetFencePlugin(md) {
  const original = md.renderer.rules.fence
  md.renderer.rules.fence = (tokens, index, options, env, renderer) => {
    const token = tokens[index]
    if (!env.widgets || token.info.trim() !== 'widget')
      return original(tokens, index, options, env, renderer)
    const lastLine = env.widgetLines?.[token.map[1] - 1] || ''
    const closing = new RegExp(`^ {0,3}${token.markup[0]}{${token.markup.length},}\\s*$`)
    const closed = closing.test(lastLine)
    const lines = env.sourceLines
      ? ` data-source-start="${token.map[0] + 1}" data-source-end="${token.map[1]}"`
      : ''
    return `<div class="widget-preview-render"${lines}><pre class="widget-source" hidden>${md.utils.escapeHtml(token.content)}</pre><div class="widget-mount" data-widget-closed="${closed}"></div></div>`
  }
}
