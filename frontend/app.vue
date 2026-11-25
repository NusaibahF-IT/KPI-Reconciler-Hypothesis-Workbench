<template>
  <div class="min-h-screen bg-canvas text-tx pb-16">
    <header class="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur-md">
      <div class="wrap h-16 flex items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl bg-sun border-[1.5px] border-ink shadow-sticker grid place-items-center font-mono font-black text-ink text-sm">
            KH
          </div>
          <div>
            <h1 class="text-base md:text-lg font-extrabold tracking-tight text-tx leading-none">
              KPI Reconciler &amp; Business Hypothesis Workbench
            </h1>
            <p class="text-[11px] font-mono text-tx/65 mt-0.5">
              FastAPI + DuckDB + Nuxt 3 · Verify Numbers → Hypothesize → Analyst Decision
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2.5">
          <span
            class="hidden sm:inline-flex items-center gap-1.5 chip font-mono"
            :class="apiHealthy ? 'bg-act/15 border-act/50 text-tx' : 'bg-mag/15 border-mag/50 text-mag'"
          >
            <span class="w-2 h-2 rounded-full" :class="apiHealthy ? 'bg-act' : 'bg-mag'" />
            {{ apiHealthy ? 'API Connected' : 'API Offline' }}
          </span>
          <button type="button" class="btn btn-outline text-xs py-1.5 px-3" @click="toggleTheme">
            {{ isDark ? '☀ Light' : '☾ Dark' }}
          </button>
        </div>
      </div>
    </header>

    <main class="wrap pt-8 space-y-6">
      <DatasetLoaderPanel
        :samples="samples"
        :active-sample-id="activeSampleId"
        :loading="loading"
        @load-sample="loadSample"
        @upload-files="uploadFiles"
      />

      <div v-if="errorMsg" class="p-4 rounded-xl bg-mag/15 border border-mag/50 text-sm font-semibold text-mag">
        {{ errorMsg }}
      </div>

      <template v-if="analysis">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex flex-wrap gap-2">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              class="btn text-xs py-2 px-4"
              :class="activeTab === tab.id ? 'btn-primary' : 'btn-outline'"
              @click="activeTab = tab.id"
            >
              {{ tab.label }}
            </button>
          </div>
          <span class="text-xs font-mono text-tx/65">
            Active Case: <strong>{{ analysis.dataset_name }}</strong>
          </span>
        </div>

        <ReconciliationGate
          v-if="activeTab === 'reconcile'"
          :independent="analysis.independent"
          :reconciliation="analysis.reconciliation"
          :snapshot-items="analysis.snapshot_items"
          :dimensions="analysis.roles?.dimensions || []"
          :reconciling="reconciling"
          @re-reconcile="handleReconcile"
        />

        <HypothesisExplorer
          v-else-if="activeTab === 'hypotheses'"
          :report="analysis.hypothesis_report"
          :hypotheses="hypotheses"
          :numeric-cols="analysis.roles?.numeric_cols || []"
          :binary-flag-cols="analysis.roles?.binary_flag_cols || []"
          :reanalyzing="loading"
          @change-columns="handleColumnOverride"
        />

        <InsightMemoBuilder
          v-else-if="activeTab === 'memo'"
          :dataset-name="analysis.dataset_name"
          :reconciliation="analysis.reconciliation"
          :hypotheses="hypotheses"
          :api-base="apiBase"
        />
      </template>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

const config = useRuntimeConfig()
const apiBase = config.public.apiBase

const isDark = ref(false)
const apiHealthy = ref(false)
const samples = ref([])
const activeSampleId = ref(null)
const uploadedFiles = ref(null)
const loading = ref(false)
const reconciling = ref(false)
const errorMsg = ref('')
const analysis = ref(null)
const hypotheses = ref([])
const activeTab = ref('reconcile')

const tabs = [
  { id: 'reconcile', label: '1. KPI Reconciliation Gate' },
  { id: 'hypotheses', label: '2. Candidate Business Hypotheses' },
  { id: 'memo', label: '3. Analyst Insight Memo' }
]

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
}

async function init() {
  try {
    const h = await fetch(`${apiBase}/api/health`)
    apiHealthy.value = h.ok
    const s = await fetch(`${apiBase}/api/samples`)
    if (s.ok) {
      const data = await s.json()
      samples.value = data.samples || []
    }
  } catch {
    apiHealthy.value = false
  }
}

async function loadSample(caseId, targetMetric = null, flagCol = null) {
  activeSampleId.value = caseId
  uploadedFiles.value = null
  loading.value = true
  errorMsg.value = ''
  try {
    const params = new URLSearchParams()
    if (targetMetric) params.set('target_metric', targetMetric)
    if (flagCol) params.set('flag_col', flagCol)
    const qs = params.toString() ? `?${params.toString()}` : ''
    const resp = await fetch(`${apiBase}/api/analyze/sample/${caseId}${qs}`, { method: 'POST' })
    if (!resp.ok) throw new Error(`Failed to analyze sample (${resp.status})`)
    const data = await resp.json()
    analysis.value = data
    hypotheses.value = data.hypothesis_report?.hypotheses || []
  } catch (err) {
    errorMsg.value = err.message || 'Error connecting to API.'
  } finally {
    loading.value = false
  }
}

async function uploadFiles({ quantFile, sentimentFile, snapshotFile }, targetMetric = null, flagCol = null) {
  activeSampleId.value = null
  uploadedFiles.value = { quantFile, sentimentFile, snapshotFile }
  loading.value = true
  errorMsg.value = ''
  try {
    const form = new FormData()
    form.append('quant_file', quantFile)
    if (sentimentFile) form.append('sentiment_file', sentimentFile)
    if (snapshotFile) form.append('snapshot_file', snapshotFile)
    if (targetMetric) form.append('target_metric', targetMetric)
    if (flagCol) form.append('flag_col', flagCol)
    const resp = await fetch(`${apiBase}/api/analyze/upload`, { method: 'POST', body: form })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `Failed to analyze upload (${resp.status})`)
    }
    const data = await resp.json()
    analysis.value = data
    hypotheses.value = data.hypothesis_report?.hypotheses || []
  } catch (err) {
    errorMsg.value = err.message || 'Error analyzing uploaded files.'
  } finally {
    loading.value = false
  }
}

function handleColumnOverride({ targetMetric, flagCol }) {
  if (uploadedFiles.value?.quantFile) {
    uploadFiles(uploadedFiles.value, targetMetric, flagCol)
  } else if (activeSampleId.value) {
    loadSample(activeSampleId.value, targetMetric, flagCol)
  }
}

async function handleReconcile({ snapshotItems, sliceCol, sliceVal }) {
  reconciling.value = true
  errorMsg.value = ''
  try {
    const form = new FormData()
    form.append('snapshot_json', JSON.stringify(snapshotItems))
    if (sliceCol) form.append('slice_col', sliceCol)
    if (sliceVal) form.append('slice_val', sliceVal)

    if (uploadedFiles.value?.quantFile) {
      form.append('quant_file', uploadedFiles.value.quantFile)
      if (uploadedFiles.value.sentimentFile) form.append('sentiment_file', uploadedFiles.value.sentimentFile)
    } else if (activeSampleId.value) {
      form.append('sample_id', activeSampleId.value)
    }

    const resp = await fetch(`${apiBase}/api/reconcile`, { method: 'POST', body: form })
    if (!resp.ok) throw new Error('Reconciliation failed.')
    const data = await resp.json()
    analysis.value = {
      ...analysis.value,
      independent: data.independent,
      reconciliation: data.reconciliation,
      snapshot_items: snapshotItems
    }
  } catch (err) {
    errorMsg.value = err.message
  } finally {
    reconciling.value = false
  }
}

onMounted(() => {
  init()
})
</script>
