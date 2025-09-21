<template>
  <div class="user-management">
    <!-- 头部区域 -->
    <div class="header-section">
      <div class="header-content">
        <h3 class="title">用户管理</h3>
        <p class="description">管理系统用户，请谨慎操作。删除用户后该用户将无法登录系统。</p>
      </div>
      <a-button type="primary" @click="showAddUserModal" class="add-btn">
        <template #icon><PlusOutlined /></template>
        添加用户
      </a-button>
    </div>

    <!-- 主内容区域 -->
    <div class="content-section">
      <a-spin :spinning="userManagement.loading">
        <div v-if="userManagement.error" class="error-message">
          <a-alert type="error" :message="userManagement.error" show-icon />
        </div>

        <div class="table-container">
          <a-table
            :dataSource="userManagement.users"
            :columns="userColumns"
            rowKey="id"
            :pagination="{
              pageSize: 10,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条记录`
            }"
            :scroll="{ x: 1200, y: 'calc(100vh - 300px)' }"
            class="user-table"
            bordered
          >
            <!-- 角色列自定义渲染 -->
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'role'">
                <a-tag :color="getRoleColor(record.role)" class="role-tag">
                  {{ getRoleLabel(record.role) }}
                </a-tag>
              </template>

              <!-- 时间列格式化 -->
              <template v-if="column.key === 'created_at' || column.key === 'last_login'">
                <span class="time-text">{{ formatTime(record[column.key]) }}</span>
              </template>

              <!-- 手机号列 -->
              <template v-if="column.key === 'phone_number'">
                <span class="phone-text">{{ record.phone_number || '-' }}</span>
              </template>

              <!-- 用户ID列 -->
              <template v-if="column.key === 'user_id'">
                <span class="user-id-text">{{ record.user_id || '-' }}</span>
              </template>

              <!-- 操作列 -->
              <template v-if="column.key === 'action'">
                <div class="table-actions">
                  <a-tooltip title="编辑用户">
                    <a-button type="text" size="small" @click="showEditUserModal(record)" class="action-btn">
                      <EditOutlined />
                    </a-button>
                  </a-tooltip>
                  <a-tooltip title="删除用户">
                    <a-button
                      type="text"
                      size="small"
                      danger
                      @click="confirmDeleteUser(record)"
                      :disabled="record.id === userStore.userId || (record.role === 'superadmin' && userStore.userRole !== 'superadmin')"
                      class="action-btn"
                    >
                      <DeleteOutlined />
                    </a-button>
                  </a-tooltip>
                </div>
              </template>
            </template>
          </a-table>
        </div>
      </a-spin>
    </div>

    <!-- 用户表单模态框 -->
    <a-modal
      v-model:open="userManagement.modalVisible"
      :title="userManagement.modalTitle"
      @ok="handleUserFormSubmit"
      :confirmLoading="userManagement.loading"
      @cancel="userManagement.modalVisible = false"
      :maskClosable="false"
      width="480px"
      class="user-modal"
    >
      <a-form layout="vertical" class="user-form">
        <a-form-item label="用户名" required class="form-item">
          <a-input
            v-model:value="userManagement.form.username"
            placeholder="请输入用户名（2-20个字符）"
            size="large"
            @blur="validateAndGenerateUserId"
            :maxlength="20"
          />
          <div v-if="userManagement.form.usernameError" class="error-text">
            {{ userManagement.form.usernameError }}
          </div>
        </a-form-item>

        <!-- 显示自动生成的用户ID -->
        <a-form-item v-if="userManagement.form.generatedUserId || userManagement.editMode" label="用户ID" class="form-item">
          <a-input
            :value="userManagement.form.generatedUserId"
            placeholder="自动生成"
            size="large"
            disabled
            :addon-before="userManagement.editMode ? '已存在ID' : '登录ID'"
          />
          <div v-if="!userManagement.editMode" class="help-text">此ID将用于登录，根据用户名自动生成</div>
          <div v-else class="help-text">编辑模式下不能修改用户ID</div>
        </a-form-item>

        <!-- 手机号字段 -->
        <a-form-item label="手机号" class="form-item">
          <a-input
            v-model:value="userManagement.form.phoneNumber"
            placeholder="请输入手机号（可选，可用于登录）"
            size="large"
            :maxlength="11"
          />
          <div v-if="userManagement.form.phoneError" class="error-text">
            {{ userManagement.form.phoneError }}
          </div>
        </a-form-item>

        <template v-if="userManagement.editMode">
          <div class="password-toggle">
            <a-checkbox v-model:checked="userManagement.displayPasswordFields">
              修改密码
            </a-checkbox>
          </div>
        </template>

        <template v-if="!userManagement.editMode || userManagement.displayPasswordFields">
          <a-form-item label="密码" required class="form-item">
            <a-input-password
              v-model:value="userManagement.form.password"
              placeholder="请输入密码"
              size="large"
            />
          </a-form-item>

          <a-form-item label="确认密码" required class="form-item">
            <a-input-password
              v-model:value="userManagement.form.confirmPassword"
              placeholder="请再次输入密码"
              size="large"
            />
          </a-form-item>
        </template>

        <a-form-item label="角色" class="form-item">
          <a-select v-model:value="userManagement.form.role" size="large">
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
import { notification, Modal } from 'ant-design-vue';
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
    generatedUserId: '', // 自动生成的user_id
    phoneNumber: '', // 手机号
    password: '',
    confirmPassword: '',
    role: 'user', // 默认角色
    usernameError: '', // 用户名错误信息
    phoneError: '' // 手机号错误信息
  },
  displayPasswordFields: true, // 编辑时是否显示密码字段
});

// 添加验证用户名并生成user_id的函数
const validateAndGenerateUserId = async () => {
  const username = userManagement.form.username.trim();

  // 清空之前的错误和生成的ID
  userManagement.form.usernameError = '';
  userManagement.form.generatedUserId = '';

  if (!username) {
    return;
  }

  // 在编辑模式下，不需要重新生成user_id
  if (userManagement.editMode) {
    return;
  }

  try {
    const result = await userStore.validateUsernameAndGenerateUserId(username);
    userManagement.form.generatedUserId = result.user_id;
  } catch (error) {
    userManagement.form.usernameError = error.message || '用户名验证失败';
  }
};

// 验证手机号格式
const validatePhoneNumber = (phone) => {
  if (!phone) {
    return true; // 手机号可选
  }

  // 中国大陆手机号格式验证
  const phoneRegex = /^1[3-9]\d{9}$/;
  return phoneRegex.test(phone);
};

// 监听密码字段显示状态变化
watch(() => userManagement.displayPasswordFields, (newVal) => {
  // 当取消显示密码字段时，清空密码输入
  if (!newVal) {
    userManagement.form.password = '';
    userManagement.form.confirmPassword = '';
  }
});

// 监听手机号输入变化
watch(() => userManagement.form.phoneNumber, (newPhone) => {
  userManagement.form.phoneError = '';

  if (newPhone && !validatePhoneNumber(newPhone)) {
    userManagement.form.phoneError = '请输入正确的手机号格式';
  }
});

// 格式化时间显示
const formatTime = (timeStr) => {
  if (!timeStr) return '-';
  const date = new Date(timeStr);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

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
    generatedUserId: '',
    phoneNumber: '',
    password: '',
    confirmPassword: '',
    role: 'user',  // 默认角色为普通用户
    usernameError: '',
    phoneError: ''
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
    generatedUserId: user.user_id || '', // 编辑模式显示现有的user_id
    phoneNumber: user.phone_number || '',
    password: '',
    confirmPassword: '',
    role: user.role,
    usernameError: '',
    phoneError: ''
  };
  userManagement.displayPasswordFields = false; // 默认不显示密码字段
  userManagement.modalVisible = true;
};

// 处理用户表单提交
const handleUserFormSubmit = async () => {
  try {
    // 简单验证
    if (!userManagement.form.username.trim()) {
      notification.error({ message: '用户名不能为空' });
      return;
    }

    // 验证用户名长度
    if (userManagement.form.username.trim().length < 2 || userManagement.form.username.trim().length > 20) {
      notification.error({ message: '用户名长度必须在 2-20 个字符之间' });
      return;
    }

    // 验证手机号
    if (userManagement.form.phoneNumber && !validatePhoneNumber(userManagement.form.phoneNumber)) {
      notification.error({ message: '请输入正确的手机号格式' });
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
        username: userManagement.form.username.trim(),
        role: userManagement.form.role
      };

      // 添加手机号字段
      if (userManagement.form.phoneNumber) {
        updateData.phone_number = userManagement.form.phoneNumber;
      }

      // 如果显示了密码字段并且填写了密码，才更新密码
      if (userManagement.displayPasswordFields && userManagement.form.password) {
        updateData.password = userManagement.form.password;
      }

      await userStore.updateUser(userManagement.editUserId, updateData);
      notification.success({ message: '用户更新成功' });
    } else {
      // 创建新用户
      const createData = {
        username: userManagement.form.username.trim(),
        password: userManagement.form.password,
        role: userManagement.form.role
      };

      // 添加手机号字段（如果填写了）
      if (userManagement.form.phoneNumber) {
        createData.phone_number = userManagement.form.phoneNumber;
      }

      await userStore.createUser(createData);
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

// 删除用户
const confirmDeleteUser = (user) => {
  // 自己不能删除自己
  if (user.id === userStore.userId) {
    notification.error({ message: '不能删除自己的账户' });
    return;
  }

  // 确认对话框
  Modal.confirm({
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
    width: 60,
    align: 'center'
  },
  {
    title: '用户名',
    dataIndex: 'username',
    key: 'username',
    width: 120
  },
  {
    title: '用户ID',
    dataIndex: 'user_id',
    key: 'user_id',
    width: 120
  },
  {
    title: '手机号',
    dataIndex: 'phone_number',
    key: 'phone_number',
    width: 120,
    customRender: ({ text }) => text || '-'
  },
  {
    title: '角色',
    dataIndex: 'role',
    key: 'role',
    width: 100,
    align: 'center'
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 140,
    align: 'center'
  },
  {
    title: '最后登录',
    dataIndex: 'last_login',
    key: 'last_login',
    width: 140,
    align: 'center'
  },
  {
    title: '操作',
    key: 'action',
    width: 100,
    align: 'center'
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

  .header-section {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;

    .header-content {
      flex: 1;

      .description {
        font-size: 14px;
        color: #8c8c8c;
        margin: 0;
        line-height: 1.4;
        margin-bottom: 16px;
      }
    }

  }

  .content-section {
    overflow: hidden;

    .error-message {
      padding: 16px 24px;
    }

    .table-container {
      max-height: calc(100vh - 300px);
      overflow: hidden;

      .user-table {
        :deep(.ant-table-thead > tr > th) {
          background: #fafafa;
          font-weight: 600;
          color: #262626;
          border-bottom: 2px solid #f0f0f0;
        }

        :deep(.ant-table-tbody > tr > td) {
          padding: 12px 16px;
          border-bottom: 1px solid #f5f5f5;
        }

        :deep(.ant-table-tbody > tr:hover > td) {
          background: #f8f9ff;
        }

        :deep(.ant-pagination) {
          margin: 16px 24px;
        }

        // 自定义滚动条样式
        :deep(.ant-table-body) {
          scrollbar-width: thin;
          scrollbar-color: #d9d9d9 transparent;

          &::-webkit-scrollbar {
            width: 8px;
            height: 8px;
          }

          &::-webkit-scrollbar-track {
            background: #f5f5f5;
            border-radius: 4px;
          }

          &::-webkit-scrollbar-thumb {
            background: #d9d9d9;
            border-radius: 4px;

            &:hover {
              background: #bfbfbf;
            }
          }
        }
      }
    }
  }

  .role-tag {
    font-weight: 500;
    border-radius: 4px;
    padding: 2px 8px;
  }

  .time-text {
    font-size: 13px;
    color: #595959;
  }

  .phone-text, .user-id-text {
    font-size: 13px;
    color: #262626;
    font-family: 'Monaco', 'Consolas', monospace;
  }

  .table-actions {
    display: flex;
    gap: 4px;
    justify-content: center;

    .action-btn {
      width: 32px;
      height: 32px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;

      &:hover {
        transform: scale(1.1);
      }

      &.ant-btn-dangerous:hover {
        background: #fff2f0;
        border-color: #ffccc7;
        color: #ff4d4f;
      }
    }
  }
}

.user-modal {
  :deep(.ant-modal-header) {
    padding: 20px 24px;
    border-bottom: 1px solid #f0f0f0;

    .ant-modal-title {
      font-size: 16px;
      font-weight: 600;
      color: #262626;
    }
  }

  :deep(.ant-modal-body) {
    padding: 24px;
  }

  .user-form {
    .form-item {
      margin-bottom: 20px;

      :deep(.ant-form-item-label) {
        padding-bottom: 4px;

        label {
          font-weight: 500;
          color: #262626;
        }
      }
    }

    .error-text {
      color: #ff4d4f;
      font-size: 12px;
      margin-top: 4px;
      line-height: 1.3;
    }

    .help-text {
      color: #8c8c8c;
      font-size: 12px;
      margin-top: 4px;
      line-height: 1.3;
    }

    .password-toggle {
      margin-bottom: 16px;

      :deep(.ant-checkbox-wrapper) {
        font-weight: 500;
        color: #495057;
      }
    }
  }
}
</style>