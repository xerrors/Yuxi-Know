const MAX_SOURCE_LENGTH = 24000
const MAX_NODES = 100
const MAX_DEPTH = 8
const containerTypes = new Set(['Card', 'ListView', 'ListViewItem', 'Row', 'Col', 'Form', 'ImageGroup'])
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
  Form: ['children', 'onSubmitAction', ...layoutProperties],
  Title: ['value', ...textProperties],
  Text: ['value', ...textProperties],
  Caption: ['value', ...textProperties],
  Badge: ['label', 'color', 'variant', 'size', 'pill'],
  Icon: ['name', 'size', 'color'],
  Chart: ['label', 'data', 'series', 'xAxis', 'showLegend', 'height'],
  Image: ['src', 'path', 'alt', 'caption', 'fit', 'aspectRatio'],
  ImageGroup: ['children'],
  Divider: [],
  Spacer: [],
  Button: [
    'label',
    'style',
    'onClickAction',
    'submit',
    'color',
    'variant',
    'size',
    'pill',
    'block',
    'iconStart',
    'iconEnd'
  ],
  Input: ['name', 'label', 'placeholder', 'defaultValue', 'required'],
  Textarea: ['name', 'label', 'placeholder', 'defaultValue', 'required'],
  Select: ['name', 'label', 'options', 'defaultValue', 'required', 'placeholder']
}

/** 校验模型输出的有限组件树，拒绝脚本、任意属性与未知动作。 */
export function parseWidget(source) {
  if (source.length > MAX_SOURCE_LENGTH) throw new Error('组件 JSON 超过 24000 字符')
  const root = JSON.parse(source)
  if (!['Card', 'ListView', 'Image', 'ImageGroup'].includes(root?.type))
    throw new Error('根组件必须是 Card、ListView、Image 或 ImageGroup')
  let count = 0
  const names = new Set()
  const string = (value) => typeof value === 'string' && value.length <= 4000
  const action = (value) =>
    value &&
    value.type === 'compose' &&
    string(value.text) &&
    value.text.trim() &&
    Object.keys(value).every((key) => ['type', 'text'].includes(key))

  /** 在渲染边界检查字段类型和表单归属。 */
  function visit(node, depth, inForm = false, inActionItem = false) {
    if (++count > MAX_NODES || depth > MAX_DEPTH)
      throw new Error('组件树超过 100 个节点或 8 层深度')
    const allowed = Object.hasOwn(properties, node?.type) ? properties[node.type] : null
    if (!allowed || Object.keys(node).some((key) => key !== 'type' && !allowed.includes(key))) {
      throw new Error('组件类型或属性不受支持')
    }
    if (
      inActionItem &&
      (['Button', 'Form', 'Input', 'Textarea', 'Select', 'Chart'].includes(node.type) ||
        node.onClickAction)
    )
      throw new Error('可点击列表项不能包含交互控件')
    const enums = {
      align: ['start', 'center', 'end', 'baseline', 'stretch'],
      justify: ['start', 'center', 'end', 'between', 'around', 'evenly'],
      flex: [0, 1, 'auto'],
      weight: ['normal', 'medium', 'semibold', 'bold'],
      textAlign: ['start', 'center', 'end'],
      variant:
        node.type === 'Button'
          ? ['solid', 'soft', 'outline', 'ghost']
          : ['solid', 'soft', 'outline'],
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
    for (const key of ['pill', 'block']) {
      if (node[key] !== undefined && typeof node[key] !== 'boolean')
        throw new Error(`${key} 必须是布尔值`)
    }
    if (node.color !== undefined) {
      const colors =
        node.type === 'Button'
          ? ['primary', 'secondary']
          : node.type === 'Badge'
            ? ['secondary', 'success', 'warning', 'danger', 'info']
            : ['primary', 'secondary', 'tertiary', 'success', 'warning', 'danger', 'info']
      if (!colors.includes(node.color)) throw new Error('组件颜色不受支持')
    }
    for (const key of node.type === 'Icon' ? ['name'] : ['iconStart', 'iconEnd']) {
      if (
        (node.type === 'Icon' || node[key] !== undefined) &&
        !WIDGET_ICON_NAMES.includes(node[key])
      )
        throw new Error('图标名称不受支持')
    }
    if (node.type === 'Chart') {
      if (!string(node.label) || !node.label.trim()) throw new Error('Chart 需要非空 label')
      const key = (value) =>
        typeof value === 'string' &&
        /^[a-zA-Z][a-zA-Z0-9_]{0,39}$/.test(value) &&
        !['constructor', 'prototype', '__proto__'].includes(value)
      if (!key(node.xAxis)) throw new Error('Chart xAxis 必须是合法数据列名')
      if (
        !Array.isArray(node.series) ||
        !node.series.length ||
        node.series.length > 3 ||
        node.series.some(
          (series) =>
            !series ||
            !['bar', 'line'].includes(series.type) ||
            !key(series.dataKey) ||
            series.dataKey === node.xAxis ||
            (series.label !== undefined && (!string(series.label) || !series.label.trim())) ||
            Object.keys(series).some((key) => !['type', 'dataKey', 'label'].includes(key))
        ) ||
        new Set(node.series.map((series) => series.dataKey)).size !== node.series.length
      )
        throw new Error('Chart 需要 1–3 个 bar/line 系列，dataKey 合法且唯一')
      const columns = [node.xAxis, ...node.series.map((series) => series.dataKey)]
      if (
        !Array.isArray(node.data) ||
        node.data.length > 60 ||
        node.data.some(
          (row) =>
            !row ||
            typeof row !== 'object' ||
            Array.isArray(row) ||
            Object.keys(row).some((key) => !columns.includes(key)) ||
            !Object.hasOwn(row, node.xAxis) ||
            !string(row[node.xAxis]) ||
            !row[node.xAxis].trim() ||
            node.series.some(
              (series) =>
                !Object.hasOwn(row, series.dataKey) ||
                !Number.isFinite(row[series.dataKey]) ||
                Math.abs(row[series.dataKey]) > 1e12
            )
        )
      )
        throw new Error(
          'Chart data 最多 60 行，类别为非空字符串，系列值为有限数字（绝对值 ≤ 1e12）'
        )
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
        if (!string(node.path) || !node.path.startsWith('/') || node.path.startsWith('//') ||
            /[\\\0]/.test(node.path) || node.path.includes('://') || node.path.split('/').includes('..'))
          throw new Error('Image path 必须是无跳转的沙盒虚拟绝对路径')
      } else {
        if (!string(node.src) || !node.src || /[\s\\]/.test(node.src))
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
      if (!string(node.alt) || !node.alt.trim()) throw new Error('Image 需要非空 alt')
      if (node.caption !== undefined && (!string(node.caption) || !node.caption.trim()))
        throw new Error('Image caption 必须是非空短语')
      if (node.fit !== undefined && !['cover', 'contain'].includes(node.fit))
        throw new Error('Image fit 只支持 cover/contain')
      if (
        node.aspectRatio !== undefined &&
        (!Number.isFinite(node.aspectRatio) || node.aspectRatio < 0.5 || node.aspectRatio > 3)
      )
        throw new Error('Image aspectRatio 必须是 0.5–3 的数字')
    }
    if (textTypes.has(node.type) && !string(node.value))
      throw new Error('文本组件需要 value 字符串')
    if (
      ['Badge', 'Button', 'Input', 'Textarea', 'Select'].includes(node.type) &&
      !string(node.label)
    )
      throw new Error('组件需要 label 字符串')
    if (
      node.type === 'ListViewItem' &&
      node.onClickAction !== undefined &&
      !action(node.onClickAction)
    )
      throw new Error('列表项只支持 compose 动作和非空 text')
    if (node.type === 'Button') {
      if (node.style !== undefined && !['primary', 'secondary'].includes(node.style))
        throw new Error('Button 样式不受支持')
      if (node.submit !== undefined && typeof node.submit !== 'boolean')
        throw new Error('submit 必须是布尔值')
      if (node.submit) {
        if (!inForm || node.onClickAction !== undefined)
          throw new Error('提交按钮必须位于 Form 内且使用表单动作')
      } else if (!action(node.onClickAction)) throw new Error('按钮只支持 compose 动作和非空 text')
    }
    if (['Input', 'Textarea', 'Select'].includes(node.type)) {
      if (
        !inForm ||
        typeof node.name !== 'string' ||
        !/^[a-zA-Z][a-zA-Z0-9_]{0,39}$/.test(node.name) ||
        ['constructor', 'prototype', '__proto__'].includes(node.name) ||
        names.has(node.name)
      )
        throw new Error('字段必须位于 Form 内，name 合法且唯一')
      names.add(node.name)
      if (node.defaultValue !== undefined && !string(node.defaultValue))
        throw new Error('defaultValue 必须是字符串')
      if (node.required !== undefined && typeof node.required !== 'boolean')
        throw new Error('required 必须是布尔值')
      if (node.placeholder !== undefined && !string(node.placeholder))
        throw new Error('placeholder 必须是字符串')
      if (node.type === 'Select') {
        if (
          !Array.isArray(node.options) ||
          !node.options.length ||
          node.options.length > 30 ||
          node.options.some(
            (option) =>
              !option ||
              !string(option.label) ||
              !string(option.value) ||
              !option.value ||
              Object.keys(option).some((key) => !['label', 'value'].includes(key))
          ) ||
          new Set(node.options.map((option) => option.value)).size !== node.options.length
        )
          throw new Error('Select 需要 1–30 个 label/value 唯一选项')
        if (node.defaultValue && !node.options.some((option) => option.value === node.defaultValue))
          throw new Error('Select 默认值不在选项中')
      }
    }
    if (node.type === 'Form' && (inForm || !action(node.onSubmitAction)))
      throw new Error('Form 不能嵌套且需要 compose 提交动作')
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
          inForm || node.type === 'Form',
          inActionItem || (node.type === 'ListViewItem' && !!node.onClickAction)
        )
      }
    }
  }
  visit(root, 1)
  return root
}

/** 用字段的可见标签构造草稿，选择器提交用户看到的选项文字。 */
export function composeWidgetMessage(action, fields = []) {
  return [action.text, ...fields.map(({ label, value }) => `${label}：${value}`)].join('\n')
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
