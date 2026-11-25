<template>
  <div class="space-y-6">
    <section class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      <div
        v-for="(val, key) in displayKpis"
        :key="key"
        class="card-bento p-4"
      >
        <span class="text-[11px] font-extrabold uppercase tracking-wider text-tx/65 block">{{ key }}</span>
        <strong class="text-lg md:text-xl font-black font-mono text-tx mt-1 block">
          {{ formatKpiValue(key, val) }}
        </strong>
      </div>
    </section>

    <section class="card-bento p-6 space-y-5">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div class="flex items-center gap-2.5 flex-wrap">
            <h3 class="text-lg font-extrabold text-tx">{{ t.gate1Title }}</h3>
            <span
              class="px-2.5 py-0.5 rounded-md text-xs font-mono font-extrabold border border-ink"
              :class="gateBadgeClass"
            >
              {{ reconciliation.overall_gate }}
            </span>
          </div>
          <p class="text-xs text-tx/70 mt-1">{{ t.gate1Desc }}</p>
        </div>

        <div class="flex flex-wrap gap-2">
          <button type="button" class="btn btn-outline text-xs py-1.5 px-3" @click="addRow">
            {{ t.addAssertion }}
          </button>
          <button type="button" :disabled="reconciling" class="btn btn-mint text-xs py-1.5 px-4" @click="runAssertions">
            {{ reconciling ? t.checking : t.runAssertions }}
          </button>
        </div>
      </div>

      <div class="p-3.5 rounded-xl bg-canvas border border-line flex flex-wrap items-center gap-3 text-xs">
        <span class="font-extrabold text-tx">{{ t.scenarioFilter }}</span>
        <select v-model="sliceCol" class="px-3 py-1.5 rounded-lg border border-line bg-card text-tx font-mono">
          <option value="">{{ t.allData }}</option>
          <option v-for="dim in dimensions" :key="dim" :value="dim">{{ dim }}</option>
        </select>
        <input
          v-if="sliceCol"
          v-model="sliceVal"
          type="text"
          :placeholder="t.slicePlaceholder"
          class="px-3 py-1.5 rounded-lg border border-line bg-card text-tx font-mono"
        />
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse text-xs">
          <thead>
            <tr class="border-b border-line text-tx/70 uppercase text-[11px]">
              <th class="py-2.5 pr-3">{{ t.colMetric }}</th>
              <th class="py-2.5 pr-3">{{ t.colDash }}</th>
              <th class="py-2.5 pr-3">{{ t.colIndep }}</th>
              <th class="py-2.5 pr-3">{{ t.colDiff }}</th>
              <th class="py-2.5 pr-3">{{ t.colStatus }}</th>
              <th class="py-2.5">{{ t.colDiagnosis }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, idx) in editableRows"
              :key="idx"
              class="border-b border-line/70 align-middle"
            >
              <td class="py-2.5 pr-3">
                <input
                  v-model="row.metric"
                  type="text"
                  class="w-44 px-2.5 py-1 rounded-lg border border-line bg-canvas text-tx font-mono text-xs"
                />
              </td>
              <td class="py-2.5 pr-3">
                <input
                  v-model.number="row.dashboard_value"
                  type="number"
                  step="any"
                  class="w-32 px-2.5 py-1 rounded-lg border border-line bg-canvas text-tx font-mono text-xs"
                />
              </td>
              <td class="py-2.5 pr-3 font-mono font-bold">
                {{ matchedResult(row.metric)?.independent_value ?? '-' }}
              </td>
              <td class="py-2.5 pr-3 font-mono">
                {{ matchedResult(row.metric)?.abs_diff ?? '-' }}
              </td>
              <td class="py-2.5 pr-3">
                <span
                  v-if="matchedResult(row.metric)"
                  class="px-2 py-0.5 rounded-full text-[11px] font-extrabold"
                  :class="matchedResult(row.metric).status === 'MATCH' ? 'bg-act/20 text-tx' : 'bg-mag/15 text-mag'"
                >
                  {{ matchedResult(row.metric).status }}
                </span>
              </td>
              <td class="py-2.5 text-tx/80">
                {{ matchedResult(row.metric)?.diagnosis || '-' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        v-if="reconciliation.overall_gate === 'FAIL'"
        class="p-4 rounded-xl bg-mag/10 border border-mag/40 text-xs font-semibold text-mag"
      >
        {{ t.failAlert }}
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  independent: { type: Object, required: true },
  reconciliation: { type: Object, required: true },
  snapshotItems: { type: Array, default: () => [] },
  dimensions: { type: Array, default: () => [] },
  reconciling: { type: Boolean, default: false },
  t: { type: Object, required: true }
})

const emit = defineEmits(['re-reconcile'])

const editableRows = ref([])
const sliceCol = ref('')
const sliceVal = ref('')

watch(
  () => props.snapshotItems,
  (items) => {
    editableRows.value = (items || []).map((it) => ({
      metric: it.metric,
      dashboard_value: Number(it.dashboard_value)
    }))
    if (editableRows.value.length === 0) {
      const k = props.independent?.kpis || {}
      const firstSumKey = Object.keys(k).find((key) => key.startsWith('Sum ('))
      editableRows.value = [
        { metric: 'Total Rows', dashboard_value: k['Total Rows'] || 0 },
        ...(firstSumKey ? [{ metric: firstSumKey, dashboard_value: k[firstSumKey] || 0 }] : [])
      ]
    }
  },
  { immediate: true }
)

const displayKpis = computed(() => {
  const k = props.independent?.kpis || {}
  return Object.fromEntries(Object.entries(k).slice(0, 5))
})

const gateBadgeClass = computed(() => {
  const g = props.reconciliation?.overall_gate
  if (g === 'PASS') return 'bg-act text-ink'
  if (g === 'FAIL') return 'bg-mag text-white'
  return 'bg-sun text-ink'
})

function matchedResult(metricName) {
  return (props.reconciliation?.results || []).find(
    (r) => r.metric?.toLowerCase() === String(metricName || '').trim().toLowerCase()
  )
}

function addRow() {
  editableRows.value.push({ metric: 'Median Order Value', dashboard_value: 0 })
}

function runAssertions() {
  emit('re-reconcile', {
    snapshotItems: editableRows.value,
    sliceCol: sliceCol.value,
    sliceVal: sliceVal.value
  })
}

function formatKpiValue(key, val) {
  if (val === null || val === undefined) return '-'
  if (key.includes('%') && val <= 1) return `${(val * 100).toFixed(2)}%`
  if (key.includes('%')) return `${val}%`
  return Number(val).toLocaleString()
}
</script>
