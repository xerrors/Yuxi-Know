/**
 * Chart Color Palette Utility
 * 统一的图表调色盘工具函数
 * 从 CSS 变量中动态获取颜色，确保与主题保持一致
 */

let colorPalette = []
let isInitialized = false

/**
 * Build color palette from CSS variables in base.css
 * 从 base.css 中的 CSS 变量构建调色盘
 */
const buildColorPalette = () => {
  try {
    const root = document.documentElement
    const styles = getComputedStyle(root)

    const pick = (name, fallback) => {
      const v = styles.getPropertyValue(name)
      return v && v.trim() ? v.trim() : fallback
    }

    // Base chart colors
    const baseVars = [
      ['--chart-primary', '#3996ae'],
      ['--chart-success', '#52c41a'],
      ['--chart-warning', '#faad14'],
      ['--chart-error', '#f5222d'],
      ['--chart-secondary', '#722ed1'],
      ['--chart-accent', '#13c2c2'],
    ]

    // Extended palette colors
    const paletteVars = [
      ['--chart-palette-1', '#3996ae'],
      ['--chart-palette-2', '#028ea0'],
      ['--chart-palette-3', '#00b8a9'],
      ['--chart-palette-4', '#f2c94c'],
      ['--chart-palette-5', '#eb5757'],
      ['--chart-palette-6', '#2f80ed'],
      ['--chart-palette-7', '#9b51e0'],
      ['--chart-palette-8', '#56ccf2'],
      ['--chart-palette-9', '#6fcf97'],
      ['--chart-palette-10', '#333333'],
    ]

    const baseColors = baseVars.map(([n, f]) => pick(n, f))
    const paletteColors = paletteVars.map(([n, f]) => pick(n, f))

    // Priority: palette first, then base colors
    const merged = [...paletteColors, ...baseColors]
      .filter(Boolean)
      .filter((c, idx, arr) => arr.indexOf(c) === idx) // Remove duplicates

    colorPalette = merged
    isInitialized = true
  } catch (e) {
    console.warn('Failed to build color palette from CSS variables, using fallback:', e)
    // Fallback palette
    colorPalette = [
      '#3996ae', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2',
      '#fa8c16', '#1890ff', '#95de64', '#69c0ff'
    ]
    isInitialized = true
  }
}

/**
 * Get color by index from the palette
 * 根据索引从调色盘中获取颜色
 * @param {number} index - Color index
 * @returns {string} Color value
 */
export const getColorByIndex = (index) => {
  if (!isInitialized || colorPalette.length === 0) {
    buildColorPalette()
  }
  return colorPalette[index % colorPalette.length]
}

/**
 * Get the entire color palette
 * 获取完整的调色盘
 * @returns {Array<string>} Color palette array
 */
export const getColorPalette = () => {
  if (!isInitialized || colorPalette.length === 0) {
    buildColorPalette()
  }
  return [...colorPalette] // Return a copy
}

/**
 * Get specific chart colors by name
 * 根据名称获取特定的图表颜色
 * @param {string} colorName - Color name (primary, success, warning, error, secondary, accent)
 * @returns {string} Color value
 */
export const getChartColor = (colorName) => {
  const colorMap = {
    primary: '#3996ae',
    success: '#52c41a',
    warning: '#faad14',
    error: '#f5222d',
    secondary: '#722ed1',
    accent: '#13c2c2'
  }

  try {
    const root = document.documentElement
    const styles = getComputedStyle(root)
    const cssVarName = `--chart-${colorName}`
    const value = styles.getPropertyValue(cssVarName)
    return value && value.trim() ? value.trim() : colorMap[colorName] || colorMap.primary
  } catch (e) {
    return colorMap[colorName] || colorMap.primary
  }
}

/**
 * Truncate legend text for better display
 * 截断图例文本以便更好地显示
 * @param {string} name - Legend name
 * @param {number} maxLength - Maximum length (default: 20)
 * @returns {string} Truncated name
 */
export const truncateLegend = (name, maxLength = 20) => {
  if (!name) return ''
  return name.length > maxLength ? name.slice(0, maxLength) + '…' : name
}

/**
 * Initialize the color palette (call this when DOM is ready)
 * 初始化调色盘（在 DOM 准备好时调用）
 */
export const initColorPalette = () => {
  buildColorPalette()
}

// Auto-initialize when module is loaded
if (typeof window !== 'undefined' && document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initColorPalette)
} else if (typeof window !== 'undefined') {
  initColorPalette()
}
