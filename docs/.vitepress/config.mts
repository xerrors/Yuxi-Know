import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: "Yuxi-Know Docs",
  description: "文档中心",
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    nav: [
      { text: 'Home', link: '/' },
      { text: '简介', link: '/intro/quick-start' },
      { text: '更新日志', link: '/changelog/update' }
    ],

    sidebar: [
      {
        text: '简介',
        items: [
          { text: '快速开始', link: '/intro/quick-start' }
        ]
      },
      {
        text: '更新日志',
        items: [
          { text: '更新日志', link: '/changelog/update' }
        ]
      }
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/xerrors/Yuxi-Know' }
    ]
  }
})
