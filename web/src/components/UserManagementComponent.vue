<template>
  <div class="user-management">
    <h3>用户管理</h3>
    <p>用户管理，请谨慎操作，一旦删除用户，该用户将无法登录。</p>
    <a-button type="primary" @click="showAddUserModal">
      <template #icon><PlusOutlined /></template>
      添加用户
    </a-button>

    <a-spin :spinning="userManagement.loading">
      <div v-if="userManagement.error" class="error-message">
        {{ userManagement.error }}
      </div>

      <a-table
        :dataSource="userManagement.users"
        :columns="userColumns"
        rowKey="id"
        :pagination="{ pageSize: 10 }"
      >
        <!-- 角色列自定义渲染 -->
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'role'">
            <a-tag :color="getRoleColor(record.role)">{{ getRoleLabel(record.role) }}</a-tag>
          </template>

          <!-- 操作列 -->
          <template v-if="column.key === 'action'">
            <div class="table-actions">
              <a-button type="link" @click="showEditUserModal(record)">
                <EditOutlined />
              </a-button>
              <a-button
                type="link"
                danger
                @click="confirmDeleteUser(record)"
                :disabled="record.id === userStore.userId || (record.role === 'superadmin' && userStore.userRole !== 'superadmin')"
              >
                <DeleteOutlined />
              </a-button>
            </div>
          </template>
        </template>
      </a-table>
    </a-spin>

    <!-- 用户表单模态框 -->
    <a-modal
      v-model:visible="userManagement.modalVisible"
      :title="userManagement.modalTitle"
      @ok="handleUserFormSubmit"
      :confirmLoading="userManagement.loading"
      @cancel="userManagement.modalVisible = false"
      :maskClosable="false"
    >
      <a-form layout="vertical">
        <a-form-item label="用户名" required>
          <a-input v-model:value="userManagement.form.username" placeholder="请输入用户名" />
        </a-form-item>
        <template v-if="userManagement.editMode">
          <div class="password-toggle">
            <a-checkbox v-model:checked="userManagement.displayPasswordFields">
              修改密码
            </a-checkbox>
          </div>
        </template>

        <template v-if="!userManagement.editMode || userManagement.displayPasswordFields">
          <a-form-item label="密码" required>
            <a-input-password v-model:value="userManagement.form.password" placeholder="请输入密码" />
          </a-form-item>

          <a-form-item label="确认密码" required>
            <a-input-password v-model:value="userManagement.form.confirmPassword" placeholder="请再次输入密码" />
          </a-form-item>
        </template>

        <a-form-item label="角色">
          <a-select v-model:value="userManagement.form.role">
            <a-select-option value="user">普通用户</a-select-option>
            <a-select-option value="admin" v-if="userStore.isSuperAdmin">管理员</a-select-option>
            <a-select-option value="superadmin" v-if="userStore.isSuperAdmin">超级管理员</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { reactive, onMounted, watch } from 'vue';
import { notification } from 'ant-design-vue';
import { useUserStore } from '@/stores/user';
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined
} from '@ant-design/icons-vue';

const userStore = useUserStore();

// 用户管理相关状态
const userManagement = reactive({
  loading: false,
  users: [],
  error: null,
  modalVisible: false,
  modalTitle: '添加用户',
  editMode: false,
  editUserId: null,
  form: {
    username: '',
    password: '',
    confirmPassword: '',
    role: 'user' // 默认角色
  },
  displayPasswordFields: true, // 编辑时是否显示密码字段
});

// 监听密码字段显示状态变化
watch(() => userManagement.displayPasswordFields, (newVal) => {
  // 当取消显示密码字段时，清空密码输入
  if (!newVal) {
    userManagement.form.password = '';
    userManagement.form.confirmPassword = '';
  }
});

// 获取用户列表
const fetchUsers = async () => {
  try {
    userManagement.loading = true;
    const users = await userStore.getUsers();
    userManagement.users = users;
    userManagement.error = null;
  } catch (error) {
    console.error('获取用户列表失败:', error);
    userManagement.error = '获取用户列表失败';
  } finally {
    userManagement.loading = false;
  }
};

// 打开添加用户模态框
const showAddUserModal = () => {
  userManagement.modalTitle = '添加用户';
  userManagement.editMode = false;
  userManagement.editUserId = null;
  userManagement.form = {
    username: '',
    password: '',
    confirmPassword: '',
    role: 'user'  // 默认角色为普通用户
  };
  userManagement.displayPasswordFields = true;
  userManagement.modalVisible = true;
};

// 打开编辑用户模态框
const showEditUserModal = (user) => {
  userManagement.modalTitle = '编辑用户';
  userManagement.editMode = true;
  userManagement.editUserId = user.id;
  userManagement.form = {
    username: user.username,
    password: '',
    confirmPassword: '',
    role: user.role
  };
  userManagement.displayPasswordFields = true; // 默认显示密码字段
  userManagement.modalVisible = true;
};

// 处理用户表单提交
const handleUserFormSubmit = async () => {
  try {
    // 简单验证
    if (!userManagement.form.username) {
      notification.error({ message: '用户名不能为空' });
      return;
    }

    if (userManagement.displayPasswordFields) {
      if (!userManagement.form.password) {
        notification.error({ message: '密码不能为空' });
        return;
      }

      if (userManagement.form.password !== userManagement.form.confirmPassword) {
        notification.error({ message: '两次输入的密码不一致' });
        return;
      }
    }

    userManagement.loading = true;

    // 根据模式决定创建还是更新用户
    if (userManagement.editMode) {
      // 创建更新数据对象
      const updateData = {
        username: userManagement.form.username,
        role: userManagement.form.role
      };

      // 如果显示了密码字段并且填写了密码，才更新密码
      if (userManagement.displayPasswordFields && userManagement.form.password) {
        updateData.password = userManagement.form.password;
      }

      await userStore.updateUser(userManagement.editUserId, updateData);
      notification.success({ message: '用户更新成功' });
    } else {
      await userStore.createUser({
        username: userManagement.form.username,
        password: userManagement.form.password,
        role: userManagement.form.role
      });
      notification.success({ message: '用户创建成功' });
    }

    // 重新获取用户列表
    await fetchUsers();
    userManagement.modalVisible = false;
  } catch (error) {
    console.error('用户操作失败:', error);
    notification.error({
      message: '操作失败',
      description: error.message || '请稍后重试'
    });
  } finally {
    userManagement.loading = false;
  }
};

// 切换是否显示密码字段（编辑用户时使用）
const togglePasswordFields = () => {
  userManagement.displayPasswordFields = !userManagement.displayPasswordFields;
  if (!userManagement.displayPasswordFields) {
    userManagement.form.password = '';
    userManagement.form.confirmPassword = '';
  }
};

// 删除用户
const confirmDeleteUser = (user) => {
  // 自己不能删除自己
  if (user.id === userStore.userId) {
    notification.error({ message: '不能删除自己的账户' });
    return;
  }

  // 确认对话框
  const { modal } = notification;

  modal.confirm({
    title: '确认删除用户',
    content: `确定要删除用户 "${user.username}" 吗？此操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        userManagement.loading = true;
        await userStore.deleteUser(user.id);
        notification.success({ message: '用户删除成功' });
        // 重新获取用户列表
        await fetchUsers();
      } catch (error) {
        console.error('删除用户失败:', error);
        notification.error({
          message: '删除失败',
          description: error.message || '请稍后重试'
        });
      } finally {
        userManagement.loading = false;
      }
    }
  });
};

// 用户表格列定义
const userColumns = [
  {
    title: 'ID',
    dataIndex: 'id',
    key: 'id',
    width: 80
  },
  {
    title: '用户名',
    dataIndex: 'username',
    key: 'username'
  },
  {
    title: '角色',
    dataIndex: 'role',
    key: 'role',
    width: 120
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 180
  },
  {
    title: '最后登录',
    dataIndex: 'last_login',
    key: 'last_login',
    width: 180
  },
  {
    title: '操作',
    key: 'action',
    width: 120
  }
];

// 角色显示辅助函数
const getRoleLabel = (role) => {
  switch (role) {
    case 'superadmin': return '超级管理员';
    case 'admin': return '管理员';
    case 'user': return '普通用户';
    default: return role;
  }
};

// 角色标签颜色
const getRoleColor = (role) => {
  switch (role) {
    case 'superadmin': return 'red';
    case 'admin': return 'blue';
    case 'user': return 'green';
    default: return 'default';
  }
};

// 在组件挂载时获取用户列表
onMounted(() => {
  fetchUsers();
});
</script>

<style lang="less" scoped>
.user-management {
  margin-top: 20px;

  h3 {
    margin-bottom: 10px;
  }

  p {
    margin-bottom: 20px;
  }

  .error-message {
    color: red;
    margin: 10px 0;
  }

  .table-actions {
    button {
      padding: 0 4px;
    }
  }

  .password-toggle {
    margin-bottom: 16px;
  }
}
</style>