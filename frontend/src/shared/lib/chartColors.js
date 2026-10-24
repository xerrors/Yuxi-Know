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

    // 分类调色板只承载类别区分，不复用成功/警告/错误等状态语义色，
    // 避免 antd 高饱和状态色混入堆叠图破坏整体协调。
    const paletteVars = [
      ['--chart-palette-1', '#70b3c4'],
      ['--chart-palette-2', '#8491c8'],
      ['--chart-palette-3', '#dcbd74'],
      ['--chart-palette-4', '#dd8b88'],
      ['--chart-palette-5', '#9cc68b'],
      ['--chart-palette-6', '#af8dc4'],
      ['--chart-palette-7', '#e0a385'],
      ['--chart-palette-8', '#72b696'],
      ['--chart-palette-9', '#d897c0'],
      ['--chart-palette-10', '#a0a0a0']
    ]

    const paletteColors = paletteVars.map(([n, f]) => pick(n, f))

    const merged = paletteColors.filter(Boolean)

    colorPalette = merged
    isInitialized = true
  } catch (e) {
    console.warn('Failed to build color palette from CSS variables, using fallback:', e)
    // Fallback palette
    colorPalette = [
      '#70b3c4',
      '#8491c8',
      '#dcbd74',
      '#dd8b88',
      '#9cc68b',
      '#af8dc4',
      '#e0a385',
      '#72b696',
      '#d897c0',
      '#a0a0a0'
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
