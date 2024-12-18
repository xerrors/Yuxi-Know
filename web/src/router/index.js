import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue';
import BlankLayout from '@/layouts/BlankLayout.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: BlankLayout,
      children: [        {
          path: '',
          name: 'Home',
          component: () => import('../views/HomeView.vue'),
          meta: { keepAlive: true }
        }
      ]
    },
    {
      path: '/chat',
      name: 'chat',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'Chat',
          component: () => import('../views/ChatView.vue'),
          meta: { keepAlive: true }
        }
      ]
    },
    {
      path: '/graph',
      name: 'graph',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'Graph',
          component: () => import('../views/GraphView.vue'),
          meta: { keepAlive: false }
        }
      ]
    },
    {
      path: '/database',
      name: 'database',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'Database',
          component: () => import('../views/DataBaseView.vue'),
          meta: { keepAlive: true }
        },
        {
          path: ':database_id',
          name: 'databaseInfo',
          component: () => import('../views/DataBaseInfoView.vue'),
          meta: { keepAlive: false }
        }
      ]
    },
    {
      path: '/setting',
      name: 'setting',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'Setting',
          component: () => import('../views/SettingView.vue'),
          meta: { keepAlive: true }
        }
      ]
    },
    {
      path: '/tools',
      name: 'tools',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'ToolsView',
          component: () => import('../views/ToolsView.vue'),
          meta: { keepAlive: true }
        },
        {
          path: 'text-chunking',
          name: 'TextChunking',
          component: () => import('../components/TextChunkingComponent.vue'),
        },
        {
          path: 'pdf2txt',
          name: 'PDF_to_TXT',
          component: () => import('../components/ConvertToTxtComponent.vue'),
        },
      ]
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('../views/EmptyView.vue')
    },
  ]
})

export default router
