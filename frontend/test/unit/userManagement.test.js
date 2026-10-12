import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import test from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, reactive, ref } from 'vue'

test('用户类型默认排除 APP 身份，切换类型回到第一页并保留搜索条件', async () => {
  const source = await fs.readFile(
    new URL('../../src/modules/settings/ui/UserManagementComponent.vue', import.meta.url), 'utf8'
  )
  const { descriptor } = parse(source)
  const executable = compileScript(descriptor, { id: 'user-management' }).content
    .replace(/^import[\s\S]*?from '[^']+'\n/gm, '').replace('export default', 'return')
  const requests = []
  const watches = []
  let unmount
  const deps = {
    reactive, computed, ref,
    watch: (read, run) => watches.push({ read, run }),
    onMounted() {}, onUnmounted: (run) => { unmount = run },
    useUserStore: () => ({ isSuperAdmin: true, userId: 1 }),
    authApi: { getUsersPage: async (params) => {
      requests.push(params)
      return { items: [], total: 0 }
    } },
    departmentApi: {}, message: {}, Modal: {},
    formatDateTime: (value) => value,
    isPasswordLongEnough: () => true, MIN_PASSWORD_LENGTH: 8,
    FallbackAvatar: {},
    ...Object.fromEntries(['Plus', 'SquarePen', 'Trash2', 'User', 'UserLock', 'UserStar', 'RefreshCw', 'Search'].map((name) => [name, {}]))
  }
  const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
  const page = component.setup({}, { expose() {} })
  try {
    const endUser = { id: 2, user_kind: 'end_user', role: 'user', username: 'app-visitor' }
    assert.equal(page.isUserEditDisabled(endUser), true)
    page.showEditUserModal(endUser)
    assert.equal(page.userManagement.modalVisible, false)
    assert.equal(page.userManagement.editUserId, null)
    const human = { ...endUser, user_kind: 'human', username: 'product-user' }
    assert.equal(page.isUserEditDisabled(human), false)
    page.showEditUserModal(human)
    assert.equal(page.userManagement.modalVisible, true)
    assert.equal(page.userManagement.form.username, 'product-user')
    await page.fetchUsers()
    assert.equal(requests[0].userKind, 'human')
    page.userManagement.currentPage = 3
    page.userManagement.searchKeyword = 'visitor'
    page.userManagement.userKindFilter = 'end_user'
    const filterWatch = watches.find(({ read }) => Array.isArray(read()))
    assert.deepEqual(filterWatch.read(), ['visitor', '', '', 'end_user'])
    filterWatch.run()
    assert.equal(page.userManagement.currentPage, 1)
    assert.equal(page.hasActiveFilters.value, true)
    await page.fetchUsers()
    assert.deepEqual(requests.at(-1), {
      offset: 0, limit: 20, search: 'visitor', departmentId: '', role: '', userKind: 'end_user'
    })
    page.userManagement.userKindFilter = 'all'
    await page.fetchUsers()
    assert.equal(requests.at(-1).userKind, 'all')
  } finally {
    unmount()
  }
})
