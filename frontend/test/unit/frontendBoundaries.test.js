import assert from 'node:assert/strict'
import test from 'node:test'
import { ESLint } from 'eslint'

const eslint = new ESLint()

const rejections = [
  ['src/modules/session/model/invalid.js', "import '@/pages/AgentView.vue'"],
  ['src/modules/agents/ui/invalid.js', "export { default } from '../../../app/App.vue'"],
  ['src/shared/ui/invalid.js', "const load = () => import('@/modules/agents/model/agent'); load()"],
  ['src/shared/lib/invalid.js', "export * from '@/apis/base'"],
  ['src/pages/invalid.js', "import '@/components/AgentChatComponent.vue'"],
  ['src/modules/agents/model/invalid.js', "import '@/modules/../pages/AgentView.vue'"],
  ['src/shared/lib/invalid.js', "import '@/shared/../modules/agents/model/agent'"],
  [
    'src/modules/session/model/invalid.js',
    'const load = () => import(`@/pages/AgentView.vue`); load()'
  ],
  ['src/modules/session/model/invalid.js', "import '/src/pages/AgentView.vue'"]
]

const moduleEntryRejections = [
  [
    'src/modules/session/model/invalid.js',
    "import { useAgentStore } from '@/modules/agents/model/agent'"
  ],
  [
    'src/modules/session/model/invalid.js',
    "import { useAgentStore } from '@//modules/agents/model/agent'"
  ],
  [
    'src/modules/session/model/invalid.js',
    "import { useAgentStore } from '/src//modules/agents/model/agent'"
  ],
  [
    'src/modules/session/model/invalid.js',
    "import { useAgentStore } from '@/../src/modules/agents/model/agent'"
  ],
  [
    'src/modules/session/model/invalid.js',
    "import { useAgentStore } from '../../../../src/modules/agents/model/agent'"
  ],
  [
    'src/modules/session/model/invalid.js',
    "import { useAgentStore } from '@/modules/agents/ui.js'"
  ],
  [
    'src/modules/session/model/invalid.js',
    "export { default } from '@/modules/agents/model/agent'"
  ],
  [
    'src/modules/session/model/invalid.js',
    "const load = () => import('@/modules/agents/model/agent'); load()"
  ],
  [
    'src/modules/session/ui/invalid.vue',
    "<script setup>\nimport { useAgentStore } from '@/modules/agents/model/agent'\n</script>"
  ]
]

for (const [file, source] of rejections) {
  test(`拒绝越界引用：${file} → ${source}`, async () => {
    const [result] = await eslint.lintText(source, { filePath: file })
    assert.ok(
      result.messages.some((message) => message.ruleId === 'architecture/boundaries'),
      JSON.stringify(result.messages)
    )
  })
}

for (const [file, source] of moduleEntryRejections) {
  test(`拒绝跨模块内部路径：${file} → ${source}`, async () => {
    const [result] = await eslint.lintText(source, { filePath: file })
    assert.ok(
      result.messages.some(
        (message) =>
          message.ruleId === 'architecture/boundaries' && message.messageId === 'moduleEntry'
      ),
      JSON.stringify(result.messages)
    )
  })
}

test('页面装配业务模块、领域复用 shared、领域之间引用不被误拒绝', async () => {
  for (const [file, source] of [
    ['src/pages/example.js', "import '@/modules/session/ui/SessionWorkspace.vue'"],
    ['src/modules/agents/ui/example.js', "import '@/shared/ui/ActionDropdown.vue'"],
    ['src/modules/session/model/example.js', "import { useAgentStore } from '@/modules/agents'"],
    [
      'src/modules/session/model/example.js',
      "import { useAgentStore } from '@/modules/agents/index.js'"
    ],
    [
      'src/modules/session/model/example.js',
      "import { useAgentStore } from '@/modules/agents/index'"
    ],
    ['src/modules/session/model/example.js', "import { useAgentStore } from '@/modules/agents/'"],
    [
      'src/modules/session/ui/example.vue',
      "<script setup>\nimport ModelSelectorComponent from '@/modules/agents/ui/ModelSelectorComponent.vue'\n</script>"
    ],
    [
      'src/modules/agents/ui/example.js',
      "import { useAgentStore } from '@/modules/agents/model/agent'"
    ]
  ]) {
    const [result] = await eslint.lintText(source, { filePath: file })
    assert.equal(
      result.messages.filter((message) => message.ruleId === 'architecture/boundaries').length,
      0,
      JSON.stringify(result.messages)
    )
  }
})
