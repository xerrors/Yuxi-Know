import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { computed, ref, watch } from 'vue'
import { createPinia, defineStore, disposePinia } from 'pinia'

/** 使用真实响应式 Store，隔离浏览器偏好与持久化边界。 */
function fixture(saved = null, preferredDark = false) {
  const systemDark = ref(preferredDark)
  const storage = new Map(saved === null ? [] : [['theme', saved]])
  const classes = new Set()
  const document = { documentElement: { classList: {
    add: (name) => classes.add(name),
    remove: (name) => classes.delete(name)
  } } }
  const source = readFileSync(new URL('../../src/shared/model/theme.js', import.meta.url), 'utf8')
    .replace(/^import .*\n/gm, '')
    .replace('export const useThemeStore =', 'return')
  const useThemeStore = new Function(
    'ref', 'computed', 'watch', 'defineStore', 'theme', 'usePreferredDark',
    'localStorage', 'document', 'getComputedStyle', source
  )(
    ref, computed, watch, defineStore, { darkAlgorithm: 'dark', defaultAlgorithm: 'light' },
    () => systemDark,
    { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    document, () => ({ getPropertyValue: () => classes.has('dark') ? '#222222' : '#eeeeee' })
  )
  const pinia = createPinia()
  const store = useThemeStore(pinia)
  return { store, systemDark, storage, classes, dispose: () => disposePinia(pinia) }
}

test('主题按 light、dark、auto 轮换并保存选择，自动模式实时更新根节点和控件', () => {
  const f = fixture()
  try {
    assert.equal(f.store.themeMode, 'light')
    for (const mode of ['dark', 'auto', 'light']) {
      f.store.toggleTheme()
      assert.equal(f.store.themeMode, mode)
      assert.equal(f.storage.get('theme'), mode)
    }
    f.store.setTheme('auto')
    for (const dark of [true, false, true]) {
      f.systemDark.value = dark
      assert.equal(f.store.isDark, dark)
      assert.equal(f.classes.has('dark'), dark)
      assert.equal(f.store.currentTheme.algorithm, dark ? 'dark' : 'light')
      assert.equal(f.store.currentTheme.token.colorPrimary, dark ? '#222222' : '#eeeeee')
      assert.equal(f.storage.get('theme'), 'auto')
    }
    f.store.setTheme(false)
    f.systemDark.value = false
    f.systemDark.value = true
    assert.equal(f.store.isDark, false)
    assert.equal(f.storage.get('theme'), 'light')
    f.store.setTheme(true)
    f.systemDark.value = false
    assert.equal(f.store.isDark, true)
    assert.equal(f.storage.get('theme'), 'dark')
  } finally {
    f.dispose()
  }
})

test('重载保留三种选择，默认浅色，auto 初始化解析浏览器偏好', () => {
  for (const saved of [null, 'invalid', 'light', 'dark', 'auto']) {
    for (const preferred of [true, false]) {
      const f = fixture(saved, preferred)
      try {
        const dark = saved === 'dark' || (saved === 'auto' && preferred)
        assert.equal(f.store.themeMode, ['light', 'dark', 'auto'].includes(saved) ? saved : 'light')
        assert.equal(f.store.isDark, dark)
        assert.equal(f.classes.has('dark'), dark)
        assert.equal(f.store.currentTheme.algorithm, dark ? 'dark' : 'light')
      } finally {
        f.dispose()
      }
    }
  }
})
