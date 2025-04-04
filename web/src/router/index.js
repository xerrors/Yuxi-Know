import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue';
import BlankLayout from '@/layouts/BlankLayout.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'main',
      component: BlankLayout,
      children: [
        {
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
          name: 'ChatComp',
          component: () => import('../views/ChatView.vue'),
          meta: { keepAlive: true }
        }
      ]
    },
    // {
    //   path: '/agent',
    //   name: 'agent',
    //   component: AppLayout,
    //   children: [
    //     {
    //       path: '',
    //       name: 'AgentMain',
    //       component: () => import('../views/AgentView.vue'),
    //       meta: { keepAlive: true }
    //     },
    //     {
    //       path: ':agent_id',
    //       name: 'AgentSinglePage',
    //       component: () => import('../components/AgentSingleViewComponent.vue'),
    //       meta: { keepAlive: false }
    //     }
    //   ]
    // },
    {
      path: '/agent/:agent_id',
      name: 'AgentSinglePage',
      component: () => import('../views/AgentSingleView.vue'),
    },
    {
      path: '/graph',
      name: 'graph',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'GraphComp',
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
          name: 'DatabaseComp',
          component: () => import('../views/DataBaseView.vue'),
          meta: { keepAlive: true }
        },
        {
          path: ':database_id',
          name: 'DatabaseInfoComp',
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
          name: 'SettingComp',
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
          name: 'ToolsComp',
          component: () => import('../views/ToolsView.vue'),
          meta: { keepAlive: true }
        },
        {
          path: 'text-chunking',
          name: 'TextChunking',
          component: () => import('../components/tools/TextChunkingComponent.vue'),
        },
        {
          path: 'pdf2txt',
          name: 'PDF_to_TXT',
          component: () => import('../components/tools/ConvertToTxtComponent.vue'),
        },
        {
          path: 'agent',
          name: 'Agent',
          component: () => import('../views/AgentView.vue'),
          meta: { keepAlive: true }
        }
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
