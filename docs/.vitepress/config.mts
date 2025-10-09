import { defineConfig } from 'vitepress'
import markdownItTaskCheckbox from 'markdown-it-task-checkbox'


// https://vitepress.dev/reference/site-config
export default defineConfig({
  lang: 'zh-CN',
  title: "Yuxi-Know Docs",
  description: "文档中心",
  markdown: {
    config: (md) => {
      md.use(markdownItTaskCheckbox)
    }
  },
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    logo: "/favicon.svg",
    nav: [
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
    ],


    footer: {
      message: '本项目基于 MIT License 开源，欢迎使用和贡献。',
      copyright: 'Copyright © 2025-present Yuxi'
    },


    editLink: {
      pattern: 'https://github.com/xerrors/Yuxi-Know/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页'
    },

    lastUpdated: {
      text: '最后更新时间',
      formatOptions: {
        dateStyle: 'full',
        timeStyle: 'medium'
      }
    },

    search: {
      provider: 'local'
    },


    docFooter: {
      prev: '上一页',
      next: '下一页'
    }
  },
})
