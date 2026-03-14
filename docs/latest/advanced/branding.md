# 品牌自定义

Yuxi-Know 支持完整的品牌自定义，包括 Logo、组织名称、版权信息等，方便企业用户进行品牌定制。

## 品牌信息配置

### 步骤 1：复制模板文件

```bash
cp src/config/static/info.template.yaml src/config/static/info.local.yaml
```

### 步骤 2：编辑品牌信息

在 `src/config/static/info.local.yaml` 中配置你的品牌信息：

- 应用名称
- 组织名称
- Logo
- 版权信息等

### 步骤 3：指定配置文件

在 `.env` 中指定配置文件路径：

```env
YUXI_BRAND_FILE_PATH=src/config/static/info.local.yaml
```

::: tip 配置优先级
`info.local.yaml` > `info.template.yaml`（默认）
:::

### Icon 定制

系统预设了多种 Icon，如需更多图标，可以从 `lucide-vue-next` 中引入。

## 样式定制

系统支持完整的主题色定制。配置文件位于 `web/src/assets/css/base.css`：

```css
:root {
  --main-color: #1890ff;        /* 主色调 */
  --main-1000: #f0f2f5;          /* 色板 */
  --main-900: #e6f7ff;           /* 色板 */
  /* ... 其他色板 */
}
```

修改配色变量后，界面会实时更新，无需重启服务。

此外，`web/src/stores/theme.js` 中的 `colorPrimary` 也需要同步修改。

## 首页定制

首页的「项目介绍」部分是一个插槽组件，位于 `web/src/components/ProjectOverview.vue`。可以根据需要自定义展示内容。
