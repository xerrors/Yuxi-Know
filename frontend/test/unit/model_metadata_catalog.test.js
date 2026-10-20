import test from 'node:test'
import assert from 'node:assert/strict'
import { providers } from '@opencode-ai/models/snapshot'
import { createTestServer } from '../helpers/createTestServer.js'
import { resolveModelDisplayMetadata } from '../../src/modules/settings/model/modelMetadata.js'

test('构建投影保留完整模型覆盖与显示结果，并缩减序列化体积', async () => {
  const server = await createTestServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  try {
    const { loadModelMetadataCatalog } = await server.ssrLoadModule('/src/modules/settings/model/modelMetadata.js')
    const { providers: compact } = await loadModelMetadataCatalog()
    assert.deepEqual(Object.keys(compact), Object.keys(providers))
    for (const [providerId, provider] of Object.entries(providers)) {
      assert.deepEqual(Object.keys(compact[providerId].models), Object.keys(provider.models))
      for (const id of Object.keys(provider.models)) {
        assert.deepEqual(
          resolveModelDisplayMetadata(compact, providerId, { id }),
          resolveModelDisplayMetadata(providers, providerId, { id }),
          `${providerId}/${id}`
        )
      }
    }
    assert.ok(JSON.stringify(compact).length < JSON.stringify(providers).length * 0.4)
    const remote = {
      id: 'missing',
      input_modalities: ['image'],
      context_length: 1234,
      pricing: { prompt: '0.000001', completion: '0.000002' }
    }
    assert.deepEqual(resolveModelDisplayMetadata(compact, 'missing', remote), {
      matched: false,
      inputModalities: ['image'],
      context: 1234,
      contextLabel: '1K',
      isOneMillionContext: false,
      vision: true,
      price: { input: 1, output: 2 }
    })
  } finally {
    await server.close()
  }
})
