import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createServer } from 'vite'

/** 为每个测试服务隔离 Vite 缓存，并在关闭时清理。 */
export async function createTestServer(config = {}) {
  const cacheDir = await mkdtemp(path.join(tmpdir(), 'yuxi-vite-test-'))
  try {
    const server = await createServer({ ...config, cacheDir })
    const close = server.close.bind(server)
    server.close = async () => {
      try {
        await close()
      } finally {
        await rm(cacheDir, { recursive: true, force: true })
      }
    }
    return server
  } catch (error) {
    await rm(cacheDir, { recursive: true, force: true })
    throw error
  }
}
