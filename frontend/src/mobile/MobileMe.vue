<template>
  <div class="mobile-page">
    <section class="mobile-hero">
      <span>我的</span>
      <h1>{{ displayName }}</h1>
      <p>{{ roleLabel }} · {{ deptText }}</p>
    </section>

    <section class="mobile-card">
      <div class="mobile-section-head">
        <h2>身份信息</h2>
      </div>
      <div class="mobile-info-list">
        <label>
          <span>工号</span>
          <input v-model.trim="draft.userId" placeholder="请输入工号" />
        </label>
        <p><b>角色</b><span>{{ roleLabel }}</span></p>
        <p><b>科室</b><span>{{ deptText }}</span></p>
      </div>
      <button class="mobile-primary" type="button" @click="save">保存工号</button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useMobileShell } from '../composables/useMobileShell'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const shell = useMobileShell()
const draft = reactive({
  userId: auth.userId || auth.userName,
})

const roleLabelMap: Record<string, string> = {
  doctor: '医生',
  nurse: '护士',
  head_nurse: '护士长',
  director: '主任',
  respiratory: '呼吸治疗',
  nutrition: '营养支持',
  admin: '管理',
  unknown: '未识别角色',
}
const displayName = computed(() => draft.userId || '移动端用户')
const roleLabel = computed(() => roleLabelMap[shell.role.value] || '临床')
const deptText = computed(() => shell.deptLabel.value || '未关联科室')

function save() {
  auth.updateAccount({
    user_id: draft.userId,
    userName: draft.userId,
  })
  router.replace({ path: '/m/me', query: shell.identityQuery({ userName: draft.userId }) })
}
</script>
