---
name: chat-widgets
description: "普通聊天的分类数值比较、图片介绍卡片、推荐选项续聊使用本 Skill：用户给出各类数值并想直观比较时绘制柱状图；给出图片地址并要图文介绍时展示图片卡片；要从几个推荐或方案中选一个继续时展示可点击列表。这三类请求应主动读取并使用本 Skill，无需用户说组件、按钮、Skill 或 JSON。也支持时间趋势折线图和短表单；明确要求纯文字、源码或概念解释时使用 Markdown。"
version: "2026.10.12"
---

# 对话组件

## 普通聊天的直接响应

按用户目的选结构，先完成数据获取工具，再在最终回复中输出下列对应模板，替换全部示例文字、数据和图片地址：

| 用户目的 | 最终回复 |
|---|---|
| 给出分类数值，希望直观比较、查看主要占比 | 简短结论 + Card 中的柱状图 + 单位与来源 |
| 给出图片地址，希望图文介绍或继续规划 | Card 中的原地址图片、标题、短文；有继续意图时放草稿按钮 |
| 推荐多个安排/方案，方便选一个继续 | Card 中的 ListView，每项标题、理由、compose 动作 |

这些短请求直接在回复里呈现内容即可。组件无需创建文件、执行脚本或更新待办。每个模板的开头是三个反引号紧接 `widget`，结尾是三个反引号。协议使用 Markdown 围栏，`<widget>` 标签不会被渲染。所有要展示的围栏放在最后一次工具调用之后的最终回复中，用户才能在正式消息里看到它。

### 分类比较模板

```widget
{
  "type": "Card",
  "size": "full",
  "children": [
    {
      "type": "Title",
      "value": "阅读时长对比"
    },
    {
      "type": "Caption",
      "value": "示例数据 · 单位：分钟"
    },
    {
      "type": "Chart",
      "label": "四类阅读时长",
      "xAxis": "category",
      "data": [
        {
          "category": "论文",
          "minutes": 120
        },
        {
          "category": "技术文档",
          "minutes": 80
        },
        {
          "category": "笔记",
          "minutes": 45
        },
        {
          "category": "网页",
          "minutes": 60
        }
      ],
      "series": [
        {
          "type": "bar",
          "dataKey": "minutes",
          "label": "阅读时长"
        }
      ]
    }
  ]
}
```

分类和数值逐项对应用户数据。时间趋势沿用结构，将 series.type 改为 line，横轴使用日期。

### 图片卡片模板

```widget
{
  "type": "Card",
  "size": "full",
  "children": [
    {
      "type": "Title",
      "value": "周末去户外"
    },
    {
      "type": "Image",
      "src": "https://example.com/replace-with-real-image.jpg",
      "alt": "用户提供的户外风景图片",
      "aspectRatio": 1.5
    },
    {
      "type": "Text",
      "value": "给自己半天闲暇，放慢脚步，轻松度过周末。"
    },
    {
      "type": "Button",
      "label": "继续规划行程",
      "style": "primary",
      "block": true,
      "onClickAction": {
        "type": "compose",
        "text": "请帮我继续规划半天的户外行程。"
      }
    }
  ]
}
```

示例地址为保留域名占位符，替换为用户提供或已确认存在的实际地址。尚未实际读取画面时，说明与 alt 沿用用户描述；继续规划按钮只填入草稿。

### 推荐选择模板

```widget
{
  "type": "Card",
  "children": [
    {
      "type": "Title",
      "value": "选一个安排继续"
    },
    {
      "type": "ListView",
      "children": [
        {
          "type": "ListViewItem",
          "onClickAction": {
            "type": "compose",
            "text": "请细化公园散步的半天计划。"
          },
          "children": [
            {
              "type": "Title",
              "value": "公园散步",
              "size": "sm"
            },
            {
              "type": "Text",
              "value": "准备少，节奏慢，适合轻松走走。"
            }
          ]
        },
        {
          "type": "ListViewItem",
          "onClickAction": {
            "type": "compose",
            "text": "请细化逛博物馆的半天计划。"
          },
          "children": [
            {
              "type": "Title",
              "value": "逛博物馆",
              "size": "sm"
            },
            {
              "type": "Text",
              "value": "室内活动，按自己的兴趣随意参观。"
            }
          ]
        },
        {
          "type": "ListViewItem",
          "onClickAction": {
            "type": "compose",
            "text": "请细化咖啡馆读书的半天计划。"
          },
          "children": [
            {
              "type": "Title",
              "value": "咖啡馆读书",
              "size": "sm"
            },
            {
              "type": "Text",
              "value": "找个安静位置，一杯咖啡配一本书。"
            }
          ]
        }
      ]
    }
  ]
}
```

每项用完整标题、简短理由和对应的续聊草稿。输出项数按用户要求，省略无用的装饰属性。

## 共同协议

输出前先完成结构检查：根对象、children 数组及每个节点都完整；所有键和字符串使用成对双引号；字段来自下表，括号与围栏闭合。JSON 按模板跨行缩进，每个节点独立成对象。最终回复只输出检查完成的组件；需要修改的草案在输出前修正，用户看到的是一份完整定稿。

回答以普通 Markdown 说明结论和上下文。在卡片、图表、图片能清晰呈现内容，或选择选项能帮助用户继续对话时，补充一个顶格、完整闭合的 `widget` 围栏，内容是严格 JSON。每个围栏的根为 `Card` 或 `ListView`；围栏外继续放背景、完整明细和来源。用用户语言表达标签与动作，只展示已有数据或明确标注的示例数据。

先完成数据获取、计划更新等工具调用，再在最终给用户的回复中输出完整组件。组件若只出现在工具调用前的过程消息中，用户可能只看到过程摘要；最终回复必须包含需要展示的 `widget` 围栏。不要仅宣称“图表已绘制”或“图片已展示”。用户请求多张图时，分别输出多个完整围栏，每个图表保留自己的标题、单位与数据来源。

定稿时按属性表核对定义：字段名和字符串使用成对双引号，只保留当前组件支持的属性，省略未使用的可选字段。Divider、Spacer 的完整定义只有 `{"type":"Divider"}`、`{"type":"Spacer"}`。

这是 Yuxi 借鉴 ChatKit 命名的组件子集。前端使用固定 Vue 组件与双主题样式；字段、大小写和属性必须符合下表。只使用表内属性，不输出 HTML、CSS、脚本、事件代码或任意服务端动作。

| 组件 | 属性与用途 |
|---|---|
| Card | `children`；可选 `size`：sm、md（默认，最大 440px）、lg、full；`padding` |
| Row、Col | `children`；可选 `gap`、`padding`、`align`、`justify`、`flex`；Row 在窄屏换行 |
| ListView | `children`，只放 ListViewItem |
| ListViewItem | `children`；可选 `gap`、`align`、`onClickAction`；有动作时整行可点击，内部只能放非交互组件 |
| Title、Text、Caption | `value`；可选 `size`、`weight`、`textAlign`、`color` |
| Badge | `label`；可选 `color`：secondary、success、warning、danger、info；`variant`：solid、soft（默认）、outline；`size`：sm、md、lg；`pill` |
| Chart | `label`（图表说明）、`data`、`series`、`xAxis`；可选 `showLegend`、`height`；柱状图/折线图 |
| Image | `src`、`alt`（非空图片说明）；可选 `fit`：cover、contain；`aspectRatio`：0.5–3 的数字 |
| Icon | `name`：book-open、document、lightbulb、info、check、plus、search、chevron-right；可选 `size`：xs、sm、md、lg、xl；`color` |
| Divider、Spacer | 只有 `type`；分割线、弹性空白 |
| Button | `label`；可选 `style`：primary、secondary；普通按钮必须有 `onClickAction`；`color`：primary、secondary；`variant`：solid、soft、outline、ghost；`size`：sm、md、lg；`pill`、`block`、`iconStart`、`iconEnd` |
| Form | `children` 和 `onSubmitAction`；可选与 Row/Col 相同的布局属性；不可嵌套 |
| Input、Textarea | Form 内使用；`name`、`label`；可选 `placeholder`、`defaultValue`、`required` |
| Select | Form 内使用；`name`、`label`、`options: [{label,value}]`；可选 `placeholder`、`defaultValue`、`required` |

`gap`、`padding` 为 0–8 整数，每单位 4px。`align` 为 start、center、end、baseline、stretch；`justify` 为 start、center、end、between、around、evenly；`flex` 为 0、1、"auto"。不要使用像素字符串、任意颜色或 CSS 对象。

需要让标题占满一行剩余空间时，把 Title 放在 `{"type":"Col","flex":1,"children":[...]}` 中；文字组件保留文本属性，布局属性由外层 Row/Col 承载。

文本 `size`：Title 支持 xs、sm、md、lg、xl、2xl；Text 支持 xs、sm、md、lg、xl；Caption 支持 sm、md、lg。`weight` 为 normal、medium、semibold、bold；`textAlign` 为 start、center、end。文本和 Icon 的 `color` 为 primary、secondary、tertiary、success、warning、danger、info；省略时沿用默认文本层次。图标名也用于按钮 iconStart/iconEnd。pill、block 为布尔值。Button 显式 color/variant 优先于 style；默认是 secondary outline，style:primary 默认使用 primary solid。

摘要用 Title（lg）+ Text + Caption；统计用 Row 和 Col（gap:1、flex:1）；推荐列表用可点击 ListViewItem，标题旁放 chevron-right，保留完整标题；短表单只放 2–4 个字段，用 Textarea 输入多行目标，提交按钮使用 block:true。每个组件保持一个主动作，辅助动作用 outline 或 ghost。双主题由前端调整表面、控件、边框与对比度，模型只选择语义颜色。

## 图表与图片组合

组件用于呈现内容，也可有下一步动作；不必为了使用组件而添加表单。比较分类用柱状图，观察时间趋势用折线图；Card 内放 Title、Caption、Chart，末尾按需要补充 Button。图片可与标题、说明、标签组合为内容卡片。

Chart.data 为 0–60 个对象，每行只包含 xAxis 指定的类别列和 series 指定的数值列。类别为非空字符串，数值为有限数字（绝对值不超过 1e12），可以为 0 或负数。series 为 1–3 个 `{type:"bar"或"line",dataKey:"列名",label:"图例文字"}`；dataKey 唯一且不同于 xAxis。列名使用字母开头的字母/数字/下划线，最多 40 字符，禁用 constructor、prototype、__proto__。height 是 180–400 的整数像素值，默认 240；showLegend 默认 true。不要输出 ECharts option、formatter、函数或任意系列属性；单位放 Caption。未给出数据时不要编造结果，使用空 data 或明确标记示例数据。

天气预报、价格等时效请求使用实际查询结果绘图。优先使用已提供的联网查询或对应领域工具，例如可用的 `web_search`。搜索配额耗尽或查询失败时更换公开来源；若现有沙盒允许只读网络查询，可以直接读取公开逐日预报 API，按原工具审批处理。[Open-Meteo](https://open-meteo.com/en/docs) 的 `https://api.open-meteo.com/v1/forecast` 提供 `daily=temperature_2m_max,temperature_2m_min`，设置当地时区和 `forecast_days=7`，按返回的 daily.time 及温度列绘图；坐标对应实际城市。来源不覆盖所需日期时继续查询其他来源。

写明来源、查询时间、日期范围和单位。比如两个城市未来七天的天气，分别用两个 Chart 展示每天最高/最低温，两个系列均为 line。真实时效请求的全部渠道失败时，说明缺失或使用空 data，不用示例数值填充图表，即使标注“示例”也不满足该请求。示例数据仅用于用户明确要求演示组件的场景。

每城在围栏外提供实际查询 URL 的 Markdown 来源链接，返回的天气网格坐标不替换原查询坐标。摘要只描述实际日期与温度，不推断降温成因；天气现象只在工具提供明确文字或已核对天气码映射时补充。图例标明最高/最低温即可，具体线条颜色由前端随主题决定。

绘制每日最高/最低温时优先使用逐日预报字段。小时预报采样的最大/最小值只标为“采样最高/最低温”，缺少全天时段时在图卡中注明；未来的预报值不能称为实测值。

Image.src 只接受无凭据的 HTTPS URL 或同源 `/...` 路径，不能用协议相对 URL、data/file/javascript URL、宿主机或沙盒路径。只使用已知存在的图片地址，不猜测路径；图片来源和说明放 Caption，alt 描述图片内容。尚未实际读取图片时，alt 和说明沿用用户描述，保留已知内容。fit 默认 cover，aspectRatio 默认 16/9。

## 草稿动作与短表单

动作只有 `{"type":"compose","text":"希望填写到下一条消息的内容"}`。普通 Button 的 `onClickAction` 填此对象；Form 的 `onSubmitAction` 填此对象，表单内提交按钮使用 `submit: true`，省略 `onClickAction`。表单内普通按钮也携带当前字段，但只有 submit 按钮触发必填校验。提交后前端把动作 text 和表单可见标签/值追加到消息草稿，用户检查后发送；点击本身不调用工具、不保存业务数据，也不表示任务完成。不要把这种按钮当成审批、支付、删除或权限确认。

字段 name 使用字母开头的字母、数字和下划线，最多 40 字符且在围栏内唯一，避开 constructor、prototype。选择器最多 30 个非空、唯一 value 选项，默认值必须匹配选项。required 和 submit 使用 JSON 布尔值。单个文本最多 4000 字符，单个围栏最多 24000 字符、100 个节点、8 层；优先保持 3–5 项信息和 1 个主动作。

```widget
{
  "type": "Card",
  "children": [
    {
      "type": "Title",
      "value": "你想怎样开始研究？"
    },
    {
      "type": "Caption",
      "value": "填写后生成消息草稿，请检查后发送。"
    },
    {
      "type": "Form",
      "onSubmitAction": {
        "type": "compose",
        "text": "请按照以下偏好制定研究计划。"
      },
      "children": [
        {
          "type": "Input",
          "name": "topic",
          "label": "研究主题",
          "required": true
        },
        {
          "type": "Select",
          "name": "depth",
          "label": "研究深度",
          "defaultValue": "quick",
          "options": [
            {
              "label": "快速了解",
              "value": "quick"
            },
            {
              "label": "深入研究",
              "value": "deep"
            }
          ]
        },
        {
          "type": "Button",
          "label": "填写到消息草稿",
          "style": "primary",
          "block": true,
          "iconStart": "check",
          "submit": true
        }
      ]
    }
  ]
}
```

用户要直接继续某个方向时，用普通按钮：`{"type":"Button","label":"展开关键主题","onClickAction":{"type":"compose","text":"请展开上文的关键主题，并标注来源。"}}`。回答生成期间控件只读；围栏未闭合时显示生成状态，非法 JSON 或不支持的属性显示错误和原始内容。无法表达时改用普通 Markdown，复杂完整页面可作为独立交付物，不补造组件或宣称按钮已执行。
