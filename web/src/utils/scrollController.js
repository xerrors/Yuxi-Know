import { nextTick } from 'vue'

/**
 * 滚动控制工具类
 */
export class ScrollController {
  constructor(containerSelector = '.chat', options = {}) {
    this.containerSelector = containerSelector
    this.options = {
      threshold: 100,
      scrollDelay: 100,
      retryDelays: [50, 150],
      ...options
    }

    this.scrollTimer = null
    this.isUserScrolling = false
    this.shouldAutoScroll = true
    this.isProgrammaticScroll = false

    // Bind the context of 'this' for the event handler
    this.handleScroll = this.handleScroll.bind(this)
  }

  /**
   * 获取滚动容器
   * @returns {Element|null}
   */
  getContainer() {
    return document.querySelector(this.containerSelector)
  }

  /**
   * 检查是否在底部
   * @returns {boolean}
   */
  isAtBottom() {
    const container = this.getContainer()
    if (!container) return false

    const { threshold } = this.options
    return container.scrollHeight - container.scrollTop - container.clientHeight <= threshold
  }

  /**
   * 处理滚动事件
   */
  handleScroll() {
    if (this.scrollTimer) {
      clearTimeout(this.scrollTimer)
    }

    // 如果是程序性滚动，忽略此次事件
    if (this.isProgrammaticScroll) {
      this.isProgrammaticScroll = false
      return
    }

    // 标记用户正在滚动
    this.isUserScrolling = true

    // 检查是否在底部
    this.shouldAutoScroll = this.isAtBottom()

    // 滚动结束后一段时间重置用户滚动状态
    this.scrollTimer = setTimeout(() => {
      this.isUserScrolling = false
    }, this.options.scrollDelay)
  }

  /**
   * 智能滚动到底部
   * @param {boolean} force - 是否强制滚动
   */
  async scrollToBottom(force = false) {
    await nextTick()

    // 只有在应该自动滚动时才执行（除非强制）
    if (!force && !this.shouldAutoScroll) return

    const container = this.getContainer()
    if (!container) return

    // 标记为程序性滚动
    this.isProgrammaticScroll = true

    const scrollOptions = {
      top: container.scrollHeight,
      behavior: 'smooth'
    }

    // 立即滚动
    container.scrollTo(scrollOptions)

    // 多次重试确保滚动成功
    this.options.retryDelays.forEach((delay, index) => {
      setTimeout(() => {
        if (force || this.shouldAutoScroll) {
          this.isProgrammaticScroll = true
          const behavior = index === this.options.retryDelays.length - 1 ? 'auto' : 'smooth'
          container.scrollTo({
            top: container.scrollHeight,
            behavior
          })
        }
      }, delay)
    })
  }

  async scrollToBottomStaticForce() {
    const container = this.getContainer()
    if (!container) return

    // 标记为程序性滚动
    this.isProgrammaticScroll = true

    const scrollOptions = {
      top: container.scrollHeight,
      behavior: 'auto'
    }

    container.scrollTo(scrollOptions)
  }

  /**
   * 启用自动滚动
   */
  enableAutoScroll() {
    this.shouldAutoScroll = true
  }

  /**
   * 禁用自动滚动
   */
  disableAutoScroll() {
    this.shouldAutoScroll = false
  }

  /**
   * 获取滚动状态
   */
  getScrollState() {
    return {
      isUserScrolling: this.isUserScrolling,
      shouldAutoScroll: this.shouldAutoScroll,
      isAtBottom: this.isAtBottom()
    }
  }

  /**
   * 清理定时器
   */
  cleanup() {
    if (this.scrollTimer) {
      clearTimeout(this.scrollTimer)
      this.scrollTimer = null
    }
  }

  /**
   * 重置滚动状态
   */
  reset() {
    this.cleanup()
    this.isUserScrolling = false
    this.shouldAutoScroll = true
    this.isProgrammaticScroll = false
  }
}

/**
 * 创建默认的滚动控制器实例
 */
export const createScrollController = (containerSelector, options) => {
  return new ScrollController(containerSelector, options)
}

export default ScrollController
