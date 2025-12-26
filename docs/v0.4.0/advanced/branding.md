# 品牌自定义

系统支持完整的品牌信息自定义，包括 Logo、组织名称、版权信息等。

## 配置方法

### 1. 复制模板文件

```bash
cp src/config/static/info.template.yaml src/config/static/info.local.yaml
```

### 2. 编辑品牌信息

在 `src/config/static/info.local.yaml` 中配置：

<<< @/../src/config/static/info.template.yaml

上述中提到的 ICON 预设了下面这些，如果需要更多的 ICONS，可以手动从 `lucide-vue-next` 中引入。

<<< @/../web/src/views/HomeView.vue#icon_mapping{js}

### 3. 环境变量配置

在 `.env` 文件中指定配置文件路径：

```bash
YUXI_BRAND_FILE_PATH=src/config/static/info.local.yaml
```

::: tip 配置优先级
`info.local.yaml` > `info.template.yaml`（默认）
:::


## 样式定制

系统配色主要保存在 `web/src/assets/css/base.css` 中：

- 替换 `--main-*` 相关变量即可改变配色
- 支持主题色、辅助色等完整定制
- 实时预览，无需重启服务

**主要变量**:

```css
:root {
  --main-color: #1890ff;        /* 主色调 */
  --main-1000: #f0f2f5;          /* 色板 */
  --main-900: #e6f7ff;           /* 色板 */
  /* ... 其他色板 */
}

```

**此外**，`web/src/stores/theme.js` 中也包含了主题相关的配置（需要修改 `colorPrimary`），可根据需要修改。

## 修改首页

首页提供了一个插槽组件 `web/src/components/ProjectOverview.vue`，可以在该组件中自定义项目介绍，当前为空文件。（借助 AI 编程可以设计出更好看的首页的）
