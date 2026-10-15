import assert from 'node:assert/strict'
import test from 'node:test'

import { MessageProcessor } from '../../src/modules/session/model/messageProcessor.js'

const knowledgeBases = [{ name: '财税库' }, { name: 'DifyKB' }, { name: 'LightGraphKB' }]

test('流式与历史只消费统一展示字段，不解释供应商元数据', () => {
  for (const message of [
    { content: 'OK', reasoning_content: '先检查。' },
    { content: 'OK', reasoning_content: '先检查。', content_blocks: [{ type: 'reasoning', reasoning: '先检查。' }] }
  ]) {
    assert.deepEqual(MessageProcessor.parseAssistantMessageBody(message), { content: 'OK', reasoningContent: '先检查。' })
  }
  assert.deepEqual(MessageProcessor.parseAssistantMessageBody({
    content: 'OK', additional_kwargs: { reasoning_content: '不在页面恢复' },
    content_blocks: [{ type: 'reasoning', reasoning: '不在页面恢复' }]
  }), { content: 'OK', reasoningContent: '' })

})

test('交付物只归属于调用 present_artifacts 的对话', () => {
  const artifactSession = {
    messages: [
      {
        type: 'ai',
        tool_calls: [
          {
            name: 'present_artifacts',
            tool_call_result: { content: '已将交付物展示给用户' },
            args: JSON.stringify({
              filepaths: [
                '/home/user/workspace/outputs/bubble_sort.py',
                '/home/user/workspace/outputs/bubble_sort.js'
              ]
            })
          },
          {
            function: { name: 'present_artifacts' },
            status: 'success',
            args: { filepaths: ['/home/user/workspace/outputs/bubble_sort.py'] }
          }
        ]
      }
    ]
  }
  const laterSession = {
    messages: [{ type: 'human', content: '运行 Python 的' }]
  }

  assert.deepEqual(MessageProcessor.extractArtifactsFromMessageGroup(artifactSession), [
    '/home/user/workspace/outputs/bubble_sort.py',
    '/home/user/workspace/outputs/bubble_sort.js'
  ])
  assert.deepEqual(MessageProcessor.extractArtifactsFromMessageGroup(laterSession), [])
})

test('交付物忽略历史图片类型，保序去重，失败与待执行调用不展示', () => {
  const group = {
    messages: [
      {
        type: 'ai',
        tool_calls: [
          {
            name: 'present_artifacts',
            status: 'success',
            args: { filepaths: ['/a.png', '/report.md'] }
          },
          {
            function: {
              name: 'present_artifacts',
              arguments: JSON.stringify({ filepaths: ['/a.png'], type: 'image' })
            },
            status: 'success'
          },
          {
            name: 'present_artifacts',
            status: 'error',
            args: { filepaths: ['/missing.png'], type: 'image' },
            tool_call_result: { content: 'Error: 文件不存在' }
          },
          { name: 'present_artifacts', args: { filepaths: ['/pending.png'], type: 'image' } },
          {
            name: 'present_artifacts',
            args: { filepaths: ['/failed.png'], type: 'image' },
            tool_call_result: { status: 'error', content: 'Error: 文件不存在' }
          },
          { name: 'present_artifacts', status: 'success', args: '{invalid' }
        ]
      }
    ]
  }
  assert.deepEqual(MessageProcessor.extractArtifactsFromMessageGroup(group), [
    '/a.png',
    '/report.md'
  ])
})

test('知识库来源与历史消息保持独立的归一化语义', () => {
  const group = {
    messages: [
      {
        type: 'ai',
        tool_calls: [
          {
            name: '财税库',
            tool_call_result: {
              content: JSON.stringify([
                {
                  content: 'A',
                  score: 0.9,
                  metadata: { source: 'doc-a', chunk_id: 'c1', file_id: 'f1', chunk_index: 1 }
                },
                {
                  content: 'A',
                  score: 0.8,
                  metadata: { source: 'doc-a', chunk_id: 'c1', file_id: 'f1', chunk_index: 1 }
                }
              ])
            }
          },
          {
            name: 'LightGraphKB',
            tool_call_result: {
              content: JSON.stringify({
                data: {
                  chunks: [
                    {
                      content: 'B',
                      score: 0.4,
                      metadata: { source: 'doc-b', chunk_id: 'c2', file_id: 'f2', chunk_index: 2 }
                    }
                  ]
                }
              })
            }
          },
          {
            name: 'not_kb_tool',
            tool_call_result: {
              content: JSON.stringify([{ content: 'X', score: 0.99, metadata: { chunk_id: 'cx' } }])
            }
          },
          {
            name: 'DifyKB',
            tool_call_result: { content: 'not-json' }
          }
        ]
      }
    ]
  }

  const chunks = MessageProcessor.extractKnowledgeChunksFromMessageGroup(group, knowledgeBases)

  assert.equal(chunks.some((chunk) => chunk.content === 'A' && chunk.kb_name === '财税库'), true)
  assert.equal(
    chunks.some((chunk) => chunk.content === 'B' && chunk.kb_name === 'LightGraphKB'),
    true
  )
  assert.equal(chunks.some((chunk) => chunk.content === 'X'), false)
  assert.equal(chunks.some((chunk) => chunk.kb_name === 'DifyKB'), false)
  assert.equal(chunks.filter((chunk) => chunk.metadata?.chunk_id === 'c1').length, 1)

  const idxA = chunks.findIndex((chunk) => chunk.content === 'A')
  const idxB = chunks.findIndex((chunk) => chunk.content === 'B')
  assert.equal(idxA < idxB, true)

  const runGroups = MessageProcessor.convertServerHistoryToMessages([
    { type: 'human', content: '排队输入一' },
    { type: 'human', content: '排队输入二' },
    {
      type: 'human',
      content: '{"language":"python"}',
      extra_metadata: { source: 'ask_user_question_resume' }
    },
    { type: 'ai', content: '这是 Python 版本', run_id: 'run-1' }
  ])

  assert.equal(runGroups.length, 3)
  assert.equal(runGroups[0].messages.length, 1)
  assert.equal(runGroups[0].messages[0].content, '排队输入一')
  assert.equal(runGroups[1].messages.length, 1)
  assert.equal(runGroups[1].messages[0].content, '排队输入二')
  assert.equal(runGroups[2].messages.at(-1).content, '这是 Python 版本')
  assert.equal(runGroups[2].messages.at(-1).isLast, true)
  assert.equal(runGroups[2].status, 'finished')

  assert.deepEqual(
    MessageProcessor.parseAssistantMessageBody({
      type: 'ai',
      content: '<think>推理过程</think>最终答案'
    }),
    { content: '<think>推理过程</think>最终答案', reasoningContent: '' }
  )
})


test('History 按 Run ID 分组，保留零消息 Run、续写和无关联旧消息', () => {
  const runs = [
    { id: 'run-a', status: 'completed', timing: { created_at: '2026-09-05T00:00:00Z' } },
    { id: 'run-resume', run_type: 'resume', created_by_run_id: 'run-a', status: 'completed', timing: { created_at: '2026-09-05T00:00:01Z' } },
    { id: 'run-empty', status: 'failed', timing: { created_at: '2026-09-05T00:00:02Z' } }
  ]
  const history = [
    { id: 'h', type: 'human', run_id: 'run-a', content: '问题' },
    { id: 'resume', type: 'ai', run_id: 'run-resume', content: '续写' },
    { id: 'a', type: 'ai', run_id: 'run-a', content: '首次回答' },
    { id: 'old', type: 'ai', content: '没有 Run 的旧回答', created_at: '2026-09-04T00:00:00Z' }
  ]
  const groups = MessageProcessor.convertServerHistoryToMessages(history, runs)
  assert.deepEqual(groups.map((group) => group.run?.id), [undefined, 'run-a', 'run-resume', 'run-empty'])
  assert.deepEqual(groups[1].messages.map((message) => message.id), ['h', 'a'])
  assert.equal(groups[2].messages[0].content, '续写')
  assert.equal(groups[3].messages.length, 0)
  assert.equal(groups[3].run.status, 'failed')
  assert.equal(groups[0].messages[0].id, 'old')
  assert.equal(history[2].isLast, undefined)
})
