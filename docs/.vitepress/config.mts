import { defineConfig } from 'vitepress'
import markdownItTaskCheckbox from 'markdown-it-task-checkbox'


// https://vitepress.dev/reference/site-config
export default defineConfig({
  lang: 'zh-CN',
  title: "Yuxi-Know",
  description: "语析",
  base: '/Yuxi-Know/',
  markdown: {
    config: (md) => {
      md.use(markdownItTaskCheckbox)
    }
  },
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    logo: "/favicon.svg",
    nav: [
      {
        text: 'Version',
        items: [
          { text: 'Latest (开发版)', link: '/latest/intro/quick-start' },
          { text: 'v0.4.0 (稳定版)', link: '/v0.4.0/intro/quick-start' }
        ]
      }
    ],

    sidebar: {
      '/latest/': [
        {
          text: '简介',
          items: [
            { text: '什么是 Yuxi-Know？', link: '/latest/intro/project-overview' },
            { text: '快速开始', link: '/latest/intro/quick-start' },
            { text: '模型配置', link: '/latest/intro/model-config' },
            { text: '知识库与知识图谱', link: '/latest/intro/knowledge-base' },
            { text: '知识库评估', link: '/latest/intro/evaluation' }
          ]
        },
        {
          text: '高级配置',
          items: [
            { text: '配置系统详解', link: '/latest/advanced/configuration' },
            { text: '文档解析', link: '/latest/advanced/document-processing' },
            { text: '智能体', link: '/latest/advanced/agents-config' },
            { text: '品牌自定义', link: '/latest/advanced/branding' },
            { text: '其他配置', link: '/latest/advanced/misc' },
            { text: '生产部署', link: '/latest/advanced/deployment' }
          ]
        },
        {
          text: '更新日志',
          items: [
            { text: '路线图', link: '/latest/changelog/roadmap' },
            { text: '参与贡献', link: '/latest/changelog/contributing' },
            { text: '常见问题', link: '/latest/changelog/faq' },
            { text: '迁移至 v0.5', link: '/latest/changelog/migrate_to_v0-5' }
          ]
        }
      ],
      '/v0.4.0/': [
        {
          text: '简介',
          items: [
            { text: '什么是 Yuxi-Know？', link: '/v0.4.0/intro/project-overview' },
            { text: '快速开始', link: '/v0.4.0/intro/quick-start' },
            { text: '模型配置', link: '/v0.4.0/intro/model-config' },
            { text: '知识库与知识图谱', link: '/v0.4.0/intro/knowledge-base' },
            { text: '知识库评估', link: '/v0.4.0/intro/evaluation' }
          ]
        },
        {
          text: '高级配置',
          items: [
            { text: '配置系统详解', link: '/v0.4.0/advanced/configuration' },
            { text: '文档解析', link: '/v0.4.0/advanced/document-processing' },
            { text: '智能体', link: '/v0.4.0/advanced/agents-config' },
            { text: '品牌自定义', link: '/v0.4.0/advanced/branding' },
            { text: '其他配置', link: '/v0.4.0/advanced/misc' },
            { text: '生产部署', link: '/v0.4.0/advanced/deployment' }
          ]
        }
      ],
    },

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
