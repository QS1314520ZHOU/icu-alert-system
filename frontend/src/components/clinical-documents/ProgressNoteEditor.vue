<template>
  <div class="system-ap-workspace">
    <nav class="system-nav" aria-label="系统A/P导航">
      <button
        v-for="card in localDraft.system_ap"
        :key="card.id"
        type="button"
        :class="['system-nav-item', `tone-${card.priority}`, { 'is-active': activeCardId === card.id }]"
        @click="activeCardId = card.id"
      >
        <span>{{ shortTitle(card.title) }}</span>
        <strong>{{ priorityLabel(card.priority) }}</strong>
        <em>{{ card.review_status === 'reviewed' ? '已复核' : card.review_status === 'edited' ? '已编辑' : '待复核' }}</em>
      </button>
    </nav>

    <article v-if="activeCard" :class="['system-card', `tone-${activeCard.priority}`]">
      <header class="system-card-head">
        <div class="system-title-wrap">
          <span class="system-kicker">{{ priorityLabel(activeCard.priority) }} · {{ statementCount(activeCard) }}条结构化陈述</span>
          <h3>{{ displayTitle(activeCard.title) }}</h3>
          <p>{{ cardSummary(activeCard) }}</p>
        </div>
        <select :value="activeCard.review_status" :disabled="readonly" @change="updateReviewStatus(activeCard.id, ($event.target as HTMLSelectElement).value)">
          <option value="unreviewed">待复核</option>
          <option value="reviewed">已复核</option>
          <option value="edited">已编辑</option>
        </select>
      </header>

      <div v-if="cleanMissingItems(activeCard.missing_data).length" class="missing-data">
        <strong>缺失数据</strong>
        <span v-for="item in cleanMissingItems(activeCard.missing_data)" :key="item">{{ item }}</span>
      </div>

      <div class="statement-grid">
        <section v-for="group in groups" :key="group.key" class="statement-group">
          <div class="statement-group-head">
            <h4>{{ group.label }}</h4>
            <button type="button" :disabled="readonly" @click="addStatement(activeCard.id, group.key)">添加</button>
          </div>
          <div v-if="activeCard[group.key].length" class="statement-list">
            <article v-for="stmt in activeCard[group.key]" :key="stmt.id" :class="['statement', `kind-${stmt.kind}`]">
              <div class="statement-meta">
                <span>{{ kindLabel(stmt.kind) }}</span>
                <span v-if="stmt.confidence">置信度：{{ confidenceLabel(stmt.confidence) }}</span>
                <span v-if="stmt.review_required">需复核</span>
              </div>
              <textarea
                :value="stmt.text"
                :disabled="readonly"
                rows="2"
                @input="updateStatementText(activeCard.id, group.key, stmt.id, ($event.target as HTMLTextAreaElement).value)"
              />
              <div class="statement-foot">
                <div class="evidence-row">
                  <button v-for="ref in stmt.evidence_refs" :key="ref" type="button" @click="emit('open-evidence', [ref])">[{{ ref }}]</button>
                  <span v-if="!stmt.evidence_refs.length" class="muted">无直接引用</span>
                </div>
                <button type="button" :disabled="readonly" class="delete-btn" @click="removeStatement(activeCard.id, group.key, stmt.id)">删除</button>
              </div>
              <div v-if="cleanMissingItems(stmt.missing_data).length" class="statement-missing">待补：{{ formatMissingList(stmt.missing_data) }}</div>
            </article>
          </div>
          <div v-else class="empty-text">暂无{{ group.label }}。</div>
        </section>
      </div>
    </article>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type {
  ClinicalStatement,
  Citation,
  RoundingWorkbenchDraft,
  SystemAPCard,
} from '../../api/clinicalDocuments'

type StatementGroupKey = 'status' | 'trend' | 'assessment' | 'plan_items'

const props = defineProps<{
  draft: RoundingWorkbenchDraft
  citations: Citation[]
  context?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  'update:draft': [draft: RoundingWorkbenchDraft]
  'open-evidence': [refs: string[]]
}>()

const localDraft = ref<RoundingWorkbenchDraft>(clone(props.draft))
const activeCardId = ref(props.draft?.system_ap?.[0]?.id || '')

const groups: Array<{ key: StatementGroupKey; label: string; defaultKind: ClinicalStatement['kind'] }> = [
  { key: 'status', label: '当前状态', defaultKind: 'fact' },
  { key: 'trend', label: '趋势判断', defaultKind: 'inference' },
  { key: 'assessment', label: '评估', defaultKind: 'inference' },
  { key: 'plan_items', label: '今日计划', defaultKind: 'recommendation' },
]

const activeCard = computed(() => {
  return localDraft.value.system_ap.find((card) => card.id === activeCardId.value) || localDraft.value.system_ap[0]
})

watch(
  () => props.draft,
  (next) => {
    const local = JSON.stringify(localDraft.value)
    const incoming = JSON.stringify(next || {})
    if (local !== incoming) localDraft.value = clone(next)
    if (!activeCardId.value || !next?.system_ap?.some((card) => card.id === activeCardId.value)) {
      activeCardId.value = next?.system_ap?.[0]?.id || ''
    }
  },
  { deep: true, immediate: true },
)

function commit() {
  emit('update:draft', clone(localDraft.value))
}

function updateReviewStatus(cardId: string, value: string) {
  const card = findCard(cardId)
  if (!card) return
  card.review_status = value as SystemAPCard['review_status']
  commit()
}

function updateStatementText(cardId: string, groupKey: StatementGroupKey, statementId: string, text: string) {
  const stmt = findStatement(cardId, groupKey, statementId)
  if (!stmt) return
  stmt.text = text
  const card = findCard(cardId)
  if (card && card.review_status !== 'edited') card.review_status = 'edited'
  commit()
}

function addStatement(cardId: string, groupKey: StatementGroupKey) {
  const card = findCard(cardId)
  const group = groups.find((item) => item.key === groupKey)
  if (!card || !group) return
  card[groupKey].push({
    id: `${card.system}_${groupKey}_${Date.now()}`,
    kind: group.defaultKind,
    text: '',
    evidence_refs: [],
    missing_data: group.defaultKind === 'fact' ? ['事实依据'] : [],
    review_required: true,
  })
  card.review_status = 'edited'
  activeCardId.value = card.id
  commit()
}

function removeStatement(cardId: string, groupKey: StatementGroupKey, statementId: string) {
  const card = findCard(cardId)
  if (!card) return
  card[groupKey] = card[groupKey].filter((stmt) => stmt.id !== statementId)
  card.review_status = 'edited'
  commit()
}

function findCard(cardId: string) {
  return localDraft.value.system_ap.find((card) => card.id === cardId)
}

function findStatement(cardId: string, groupKey: StatementGroupKey, statementId: string) {
  const card = findCard(cardId)
  return card?.[groupKey].find((stmt) => stmt.id === statementId)
}

function statementCount(card: SystemAPCard) {
  return card.status.length + card.trend.length + card.assessment.length + card.plan_items.length
}

function missingLabel(value: string): string {
  const map: Record<string, string> = {
    FiO2: '吸氧浓度',
    PEEP: '呼气末正压',
    'P/F ratio': '氧合指数',
    RASS: '镇静评分',
    'CAM-ICU': '谵妄评估',
    '抗菌药疗程天数': '抗菌药疗程',
    bedside: '',
  }
  return map[value] || value
}

function cleanMissingItems(items: string[] = []): string[] {
  return items
    .map((item) => missingLabel(String(item || '').trim()))
    .filter((item) => Boolean(item && item !== '床旁记录' && item !== '事实依据'))
}

function formatMissingList(items: string[] = []): string {
  return cleanMissingItems(items).join('、')
}

function cardSummary(card: SystemAPCard) {
  return (
    card.assessment.find((item) => item.text)?.text ||
    card.status.find((item) => item.text)?.text ||
    card.plan_items.find((item) => item.text)?.text ||
    '待查房补充该系统评估。'
  )
}

function shortTitle(title: string) {
  const normalized = displayTitle(title)
  return (normalized.split('/')[0] || '').trim() || normalized
}

function displayTitle(title: string) {
  const text = String(title || '').trim()
  const legacyPrefixMap: Record<string, string> = {
    Neuro: '神经',
    Resp: '呼吸 / 氧合',
    CV: '循环 / 灌注',
    'Renal/Fluid': '肾脏 / 液体',
    'GI/Nutrition': '消化 / 营养',
    ID: '感染',
    Heme: '血液 / 凝血',
    Endo: '内分泌 / 代谢',
    'Lines/Devices': '管路 / 装置',
    Goals: '今日目标 / 夜间预案',
  }
  for (const [prefix, label] of Object.entries(legacyPrefixMap)) {
    if (text === prefix || text.startsWith(`${prefix} `)) return label
  }
  return text
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value || {}))
}

function priorityLabel(priority: string) {
  const map: Record<string, string> = { critical: '危急', high: '高', medium: '中', low: '低' }
  return map[priority] || priority
}

function kindLabel(kind: string) {
  const map: Record<string, string> = { fact: '事实', inference: '推断', recommendation: '建议' }
  return map[kind] || kind
}

function confidenceLabel(confidence: string) {
  const map: Record<string, string> = { low: '低', medium: '中', high: '高' }
  return map[confidence] || confidence
}
</script>

<style scoped>
.system-ap-workspace {
  display: grid;
  gap: 8px;
  min-height: 0;
}

.system-nav {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
}

.system-nav-item {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 2px 6px;
  align-items: center;
  min-height: 50px;
  padding: 7px 8px;
  border: 1px solid #edf1f7;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  text-align: left;
  cursor: pointer;
}

.system-nav-item.is-active {
  border-color: var(--brand);
  background: var(--bg-surface);
}

.system-nav-item.tone-critical,
.system-nav-item.tone-high {
  border-left: 4px solid #f97316;
}

.system-nav-item span {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.system-nav-item strong {
  color: var(--warning);
  font-size: 11px;
}

.system-nav-item em {
  grid-column: 1 / -1;
  color: var(--text-muted);
  font-size: 11px;
  font-style: normal;
}

.system-card {
  min-height: 0;
  background: var(--bg-surface);
  border: 1px solid #edf1f7;
  border-radius: var(--card-radius);
  padding: 10px;
}

.system-card.tone-critical,
.system-card.tone-high {
  border-color: var(--warning-soft);
}

.system-card-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.system-title-wrap {
  min-width: 0;
}

.system-card-head h3 {
  margin: 2px 0;
  color: var(--text-primary);
  font-size: 15px;
}

.system-card-head p {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.system-kicker {
  color: var(--warning);
  font-size: 12px;
  font-weight: 700;
}

.system-card-head select,
.statement-group-head button,
.delete-btn {
  border: 1px solid #d0d5dd;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 12px;
}

.system-card-head select {
  flex: 0 0 auto;
  padding: 4px 8px;
}

.statement-group-head button,
.delete-btn {
  padding: 3px 7px;
  cursor: pointer;
}

.missing-data {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  color: var(--warning);
  font-size: 12px;
}

.missing-data span {
  padding: 2px 7px;
  border-radius: var(--card-radius);
  background: var(--warning-soft);
}

.statement-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  align-items: start;
}

.statement-group {
  min-width: 0;
  border: 1px solid #edf1f7;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  padding: 8px;
}

.statement-group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.statement-group-head h4 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.statement-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.statement {
  border: 1px solid #edf1f7;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  padding: 7px;
}

.statement.kind-fact {
  border-left: 4px solid #1677ff;
}

.statement.kind-inference {
  border-left: 4px solid #d97706;
}

.statement.kind-recommendation {
  border-left: 4px solid #16a34a;
}

.statement-meta {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin-bottom: 5px;
}

.statement-meta span {
  padding: 1px 6px;
  border-radius: var(--card-radius);
  background: var(--bg-surface-2);
  color: var(--text-muted);
  font-size: 11px;
}

.statement textarea {
  width: 100%;
  min-height: 42px;
  resize: vertical;
  border: 1px solid #d0d5dd;
  border-radius: var(--card-radius);
  padding: 6px 8px;
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: 13px;
  line-height: 1.5;
}

.statement-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-top: 5px;
}

.evidence-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.evidence-row button {
  border: none;
  background: transparent;
  padding: 0 3px;
  color: var(--brand);
  font-size: 12px;
  cursor: pointer;
}

.muted,
.empty-text {
  color: var(--text-muted);
  font-size: 12px;
}

.statement-missing {
  margin-top: 5px;
  color: var(--warning);
  font-size: 12px;
}

@media (max-width: 1200px) {
  .system-nav {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .statement-grid {
    grid-template-columns: 1fr;
  }
}
</style>
