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
          name: 'home',
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
      path: '/database',
      name: 'database',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'database',
          component: () => import('../views/DataBaseView.vue'),
          meta: { keepAlive: true }
        },
        {
          path: ':database_id',
          name: 'databaseInfo',
          component: () => import('../views/DataBaseInfoView.vue'),
        },
        {
          path: 'graph',
          name: 'graph',
          component: () => import('../views/GraphView.vue'),
          meta: { keepAlive: true }
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
          name: 'setting',
          component: () => import('../views/SettingView.vue'),
          meta: { keepAlive: true }
        }
      ]
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('../views/EmptyView.vue')
    }
    // {
    //   path: '/kg',
    //   name: 'knowledge-graph',
    //   // route level code-splitting
    //   // this generates a separate chunk (About.[hash].js) for this route
    //   // which is lazy-loaded when the route is visited.
    //   component: () => import('../views/GraphView.vue'),
    //   meta: { keepAlive: true }
    // },
    // {
    //   path: '/about',
    //   name: 'about',
    //   component: () => import('../views/AboutView.vue'),
    //   meta: { keepAlive: true }
    // }
  ]
})

export default router
