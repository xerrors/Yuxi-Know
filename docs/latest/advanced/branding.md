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

**此外**，`web/src/stores/theme.js` 中也包含了主题相关的配置（需要修改 `colorPrimary`），可根据需要修改。
```
