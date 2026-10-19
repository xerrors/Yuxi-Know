import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parseMcpManifest } from '../../src/modules/extensions/model/mcpManifest.js'

const manifest = (entry, slug = 'example-mcp') => JSON.stringify({ mcpServers: { [slug]: entry } })
const connection = { type: 'http', url: 'https://example.com/mcp' }

test('清单分离连接和展示信息，HTTP 归一为运行时传输', () => {
  assert.deepEqual(parseMcpManifest(manifest({
    ...connection,
    headers: { Authorization: 'Bearer example' },
    timeout: 30,
    extra_data: { name: 'Example', description: '说明' }
  })), [{
    slug: 'example-mcp', name: 'Example', transport: 'streamable_http',
    url: 'https://example.com/mcp', headers: { Authorization: 'Bearer example' },
    timeout: 30, description: '说明'
  }])
})

test('支持 SSE、多条远程配置、缺省展示名称和空输入', () => {
  assert.deepEqual(parseMcpManifest(''), [])
  const result = parseMcpManifest(JSON.stringify({ mcpServers: {
    first: connection,
    second: { transport: 'sse', url: 'http://example.com/sse' }
  } }))
  assert.deepEqual(result.map(({ name, transport }) => [name, transport]), [
    ['first', 'streamable_http'], ['second', 'sse']
  ])
})

for (const [entry, pattern] of [
  [{ type: 'stdio', command: 'sh', args: ['-c', 'echo unsafe'] }, /不支持的字段/],
  [{ type: 'stdio', url: connection.url }, /只支持/],
  [{ ...connection, env: {} }, /不支持的字段/],
  [{ ...connection, type: 'sse', transport: 'streamable_http' }, /不一致/],
  [{ ...connection, url: 'file:///tmp/test' }, /HTTP URL/],
  [{ ...connection, url: 'example.com' }, /HTTP URL/],
  [{ ...connection, extra_data: { command: 'sh' } }, /extra_data/],
  [{ ...connection, headers: { Authorization: 42 } }, /headers/],
  [{ ...connection, timeout: 0 }, /正整数/],
  [{ ...connection, timeout: 1.5 }, /正整数/],
  [{ ...connection, extra_data: { tags: ['docs'] } }, /extra_data/],
  [{ ...connection, extra_data: { icon: '📚' } }, /extra_data/],
  [{ ...connection, extra_data: null }, /extra_data/]
]) {
  test(`清单拒绝非法字段 ${JSON.stringify(entry)}`, () => {
    assert.throws(() => parseMcpManifest(manifest(entry)), pattern)
  })
}

test('拒绝无效清单与非法标识', () => {
  assert.throws(() => parseMcpManifest('{'), /JSON/)
  assert.throws(() => parseMcpManifest('{}'), /mcpServers/)
  assert.throws(() => parseMcpManifest(manifest(connection, '../unsafe')), /标识/)
})
