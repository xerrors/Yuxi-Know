import assert from 'node:assert/strict'
import test from 'node:test'
import { parseWidget, widgetFormMessage } from '../../src/shared/lib/chatWidgets.js'

/** 用实际填写场景验证协议和提交后的用户消息。 */
const form = () => ({
  type: 'Form',
  onSubmitAction: { type: 'send_message', payload: { text: '按以下条件安排行程。' } },
  children: [
    { type: 'Input', name: 'city', label: '目的地', required: true },
    {
      type: 'DatePicker',
      name: 'date',
      label: '日期',
      min: '2026-10-17',
      max: '2026-12-31',
      required: true
    },
    {
      type: 'RadioGroup',
      name: 'pace',
      label: '节奏',
      required: true,
      options: [
        { label: '轻松', value: 'relaxed' },
        { label: '紧凑', value: 'busy' }
      ]
    },
    { type: 'Textarea', name: 'notes', label: '备注', rows: 3 },
    { type: 'Button', label: '提交并安排', submit: true, style: 'primary' }
  ]
})
const parse = (node) => parseWidget(JSON.stringify(node))

test('表单保留真实字段值，单选按可见标签发送，空选填项明确表达', () => {
  const node = parse(form())
  const result = widgetFormMessage(node, [
    ['city', '南京'],
    ['date', '2026-10-24'],
    ['pace', 'relaxed'],
    ['notes', '']
  ])
  assert.equal(
    result,
    '按以下条件安排行程。\n目的地：南京\n日期：2026-10-24\n节奏：轻松\n备注：未填写'
  )
  assert.throws(() => widgetFormMessage(node, [['city', '   ']]), /请填写目的地/)
  assert.throws(() => widgetFormMessage(node, [['city', 'a'.repeat(4001)]]), /最多填写 4000/)
  assert.throws(
    () =>
      widgetFormMessage(node, [
        ['city', '南京'],
        ['date', '2026-10-24'],
        ['pace', 'unknown']
      ]),
    /有效的节奏/
  )
})

for (const [name, change, error] of [
  [
    '未知动作',
    (f) => {
      f.onSubmitAction.type = 'delete_project'
    },
    /只支持 send_message/
  ],
  [
    '动作额外属性',
    (f) => {
      f.onSubmitAction.url = '/api/delete'
    },
    /只支持 send_message/
  ],
  [
    '动作缺少文字',
    (f) => {
      f.onSubmitAction.payload = {}
    },
    /只支持 send_message/
  ],
  [
    '嵌套表单',
    (f) => {
      f.children.push(form())
    },
    /不能嵌套/
  ],
  [
    '重复字段',
    (f) => {
      f.children[1].name = 'city'
    },
    /字段名重复/
  ],
  [
    '危险字段名',
    (f) => {
      f.children[0].name = 'constructor'
    },
    /合法字段名/
  ],
  [
    '字段缺少标签',
    (f) => {
      f.children[0].label = ''
    },
    /非空 label/
  ],
  [
    '非法默认值',
    (f) => {
      f.children[0].defaultValue = {}
    },
    /defaultValue 必须是字符串/
  ],
  [
    '错误布尔值',
    (f) => {
      f.children[0].required = 'true'
    },
    /required 必须是布尔值/
  ],
  [
    '非法多行高度',
    (f) => {
      f.children[3].rows = 0
    },
    /rows 必须/
  ],
  [
    '空单选',
    (f) => {
      f.children[2].options = []
    },
    /1–20/
  ],
  [
    '重复选项',
    (f) => {
      f.children[2].options[1].value = 'relaxed'
    },
    /互不重复/
  ],
  [
    '非法预选',
    (f) => {
      f.children[2].defaultValue = 'unknown'
    },
    /defaultValue 必须对应/
  ],
  [
    '非法日期',
    (f) => {
      f.children[1].defaultValue = '2026-02-30'
    },
    /有效的 YYYY-MM-DD/
  ],
  [
    '反向日期范围',
    (f) => {
      f.children[1].min = '2027-01-01'
    },
    /日期范围/
  ],
  [
    '默认日期越界',
    (f) => {
      f.children[1].defaultValue = '2026-01-01'
    },
    /日期范围/
  ],
  [
    '提交按钮另带动作',
    (f) => {
      f.children[4].onClickAction = f.onSubmitAction
    },
    /使用 Form 动作/
  ],
  [
    '表单按钮缺少 submit',
    (f) => {
      delete f.children[4].submit
    },
    /表单内请使用/
  ],
  [
    '按钮缺少标签',
    (f) => {
      f.children[4].label = ''
    },
    /Button 需要非空 label/
  ],
  [
    '非法按钮图标',
    (f) => {
      f.children[4].iconStart = 'unknown'
    },
    /图标名称/
  ],
  [
    '缺少提交按钮',
    (f) => {
      f.children.pop()
    },
    /需要输入字段和/
  ],
  [
    '缺少输入字段',
    (f) => {
      f.children = [f.children.at(-1)]
    },
    /需要输入字段和/
  ]
]) {
  test(`表单边界拒绝：${name}`, () => {
    const node = form()
    change(node)
    assert.throws(() => parse(node), error)
  })
}

test('表单外输入和提交按钮、可点击列表中的表单均被拒绝', () => {
  for (const node of [form().children[0], form().children.at(-1)])
    assert.throws(() => parse({ type: 'Card', children: [node] }), /必须.*Form/)
  assert.throws(
    () =>
      parse({
        type: 'ListView',
        children: [
          {
            type: 'ListViewItem',
            onClickAction: { type: 'compose', text: '继续' },
            children: [form()]
          }
        ]
      }),
    /不能包含交互控件/
  )
})

test('图文容器组合和独立 Button 使用现有布局并限制发送动作', () => {
  const action = form().onSubmitAction
  const node = {
    type: 'Card',
    children: [
      {
        type: 'Row',
        children: [
          {
            type: 'Col',
            flex: 1,
            children: [{ type: 'Image', src: 'https://example.com/a.png', alt: '参考图' }]
          },
          {
            type: 'Col',
            flex: 1,
            children: [
              { type: 'Text', value: '与图片对应的说明' },
              {
                type: 'Button',
                label: '生成计划',
                onClickAction: action,
                variant: 'outline',
                iconEnd: 'chevron-right'
              }
            ]
          }
        ]
      }
    ]
  }
  assert.deepEqual(parse(node), node)
  node.children[0].children[1].children[1].onClickAction = {
    type: 'open_url',
    url: 'https://example.com'
  }
  assert.throws(() => parse(node), /独立 Button 只支持/)
})
