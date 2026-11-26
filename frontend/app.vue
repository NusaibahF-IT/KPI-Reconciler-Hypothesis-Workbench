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
            <p class="text-[11px] font-mono text-tx/65 mt-0.5">{{ t.subtitle }}</p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <!-- Language Filter (ID / EN) -->
          <div class="inline-flex rounded-full border border-line bg-card p-0.5 text-[11px] font-mono font-bold">
            <button
              type="button"
              class="px-2.5 py-1 rounded-full transition-colors"
              :class="lang === 'id' ? 'bg-field text-ink' : 'text-tx/70 hover:text-tx'"
              @click="setLang('id')"
            >
              ID
            </button>
            <button
              type="button"
              class="px-2.5 py-1 rounded-full transition-colors"
              :class="lang === 'en' ? 'bg-field text-ink' : 'text-tx/70 hover:text-tx'"
              @click="setLang('en')"
            >
              EN
            </button>
          </div>

          <span
            class="hidden sm:inline-flex items-center gap-1.5 chip font-mono"
            :class="apiHealthy ? 'bg-act/15 border-act/50 text-tx' : 'bg-mag/15 border-mag/50 text-mag'"
          >
            <span class="w-2 h-2 rounded-full" :class="apiHealthy ? 'bg-act' : 'bg-mag'" />
            {{ apiHealthy ? t.apiConnected : t.apiOffline }}
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
        :t="t"
        :upload-locked="uploadLocked"
        :owner-unlocked="ownerUnlocked"
        :unlocking="unlocking"
        :unlock-error="unlockError"
        @load-sample="(id) => loadSample(id)"
        @upload-files="(files) => uploadFiles(files)"
        @unlock-owner="handleUnlockOwner"
        @lock-owner="handleLockOwner"
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
            {{ t.activeCase }} <strong>{{ analysis.dataset_name }}</strong>
          </span>
        </div>

        <ReconciliationGate
          v-if="activeTab === 'reconcile'"
          :independent="analysis.independent"
          :reconciliation="analysis.reconciliation"
          :snapshot-items="analysis.snapshot_items"
          :dimensions="analysis.roles?.dimensions || []"
          :reconciling="reconciling"
          :t="t"
          @re-reconcile="handleReconcile"
        />

        <HypothesisExplorer
          v-else-if="activeTab === 'hypotheses'"
          :report="analysis.hypothesis_report"
          :hypotheses="hypotheses"
          :numeric-cols="analysis.roles?.numeric_cols || []"
          :binary-flag-cols="analysis.roles?.binary_flag_cols || []"
          :reanalyzing="loading"
          :t="t"
          @change-columns="handleColumnOverride"
        />

        <InsightMemoBuilder
          v-else-if="activeTab === 'memo'"
          :dataset-name="analysis.dataset_name"
          :reconciliation="analysis.reconciliation"
          :hypotheses="hypotheses"
          :api-base="apiBase"
          :lang="lang"
          :t="t"
        />
      </template>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { UI_TEXT } from '~/composables/useTranslations'

const config = useRuntimeConfig()
const apiBase = config.public.apiBase

const lang = ref('en')
const t = computed(() => UI_TEXT[lang.value] || UI_TEXT.en)

const isDark = ref(false)
const apiHealthy = ref(false)
const samples = ref([])
const activeSampleId = ref(null)
const uploadedFiles = ref(null)
const selectedColumns = ref({ targetMetric: null, flagCol: null })
const loading = ref(false)
const reconciling = ref(false)
const errorMsg = ref('')
const analysis = ref(null)
const hypotheses = ref([])
const activeTab = ref('reconcile')
const uploadLocked = ref(false)
const ownerUnlocked = ref(false)
const ownerCode = ref('')
const unlocking = ref(false)
const unlockError = ref('')

const tabs = computed(() => [
  { id: 'reconcile', label: t.value.tabReconcile },
  { id: 'hypotheses', label: t.value.tabHypotheses },
  { id: 'memo', label: t.value.tabMemo }
])

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
}

function setLang(nextLang) {
  if (lang.value === nextLang) return
  lang.value = nextLang
  if (uploadedFiles.value?.quantFile) {
    uploadFiles(uploadedFiles.value, selectedColumns.value.targetMetric, selectedColumns.value.flagCol)
  } else if (activeSampleId.value) {
    loadSample(activeSampleId.value, selectedColumns.value.targetMetric, selectedColumns.value.flagCol)
  }
}

function ownerHeaders() {
  return ownerCode.value ? { 'X-Owner-Code': ownerCode.value } : {}
}

async function init() {
  try {
    const h = await fetch(`${apiBase}/api/health`)
    apiHealthy.value = h.ok
    const [s, acc] = await Promise.all([
      fetch(`${apiBase}/api/samples`),
      fetch(`${apiBase}/api/access/status`)
    ])
    if (s.ok) {
      const data = await s.json()
      samples.value = data.samples || []
    }
    if (acc.ok) {
      const accData = await acc.json()
      uploadLocked.value = Boolean(accData.upload_locked)
      const saved = sessionStorage.getItem('kh_owner_code')
      if (saved && uploadLocked.value) {
        await handleUnlockOwner(saved, true)
      }
    }
  } catch {
    apiHealthy.value = false
  }
}

async function handleUnlockOwner(code, silent = false) {
  unlocking.value = true
  unlockError.value = ''
  try {
    const resp = await fetch(`${apiBase}/api/access/verify`, {
      method: 'POST',
      headers: { 'X-Owner-Code': code }
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      sessionStorage.removeItem('kh_owner_code')
      if (!silent) unlockError.value = err.detail || 'Invalid owner access code.'
      return
    }
    ownerCode.value = code
    ownerUnlocked.value = true
    sessionStorage.setItem('kh_owner_code', code)
  } catch {
    if (!silent) unlockError.value = 'Could not reach verification endpoint.'
  } finally {
    unlocking.value = false
  }
}

function handleLockOwner() {
  ownerCode.value = ''
  ownerUnlocked.value = false
  uploadedFiles.value = null
  sessionStorage.removeItem('kh_owner_code')
}

async function loadSample(caseId, targetMetric = null, flagCol = null) {
  activeSampleId.value = caseId
  uploadedFiles.value = null
  selectedColumns.value = { targetMetric, flagCol }
  loading.value = true
  errorMsg.value = ''
  try {
    const params = new URLSearchParams({ lang: lang.value })
    if (targetMetric) params.set('target_metric', targetMetric)
    if (flagCol) params.set('flag_col', flagCol)
    const resp = await fetch(`${apiBase}/api/analyze/sample/${caseId}?${params.toString()}`, { method: 'POST' })
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
  selectedColumns.value = { targetMetric, flagCol }
  loading.value = true
  errorMsg.value = ''
  try {
    const form = new FormData()
    form.append('quant_file', quantFile)
    form.append('lang', lang.value)
    if (sentimentFile) form.append('sentiment_file', sentimentFile)
    if (snapshotFile) form.append('snapshot_file', snapshotFile)
    if (targetMetric) form.append('target_metric', targetMetric)
    if (flagCol) form.append('flag_col', flagCol)
    const resp = await fetch(`${apiBase}/api/analyze/upload`, {
      method: 'POST',
      headers: ownerHeaders(),
      body: form
    })
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
    form.append('lang', lang.value)
    if (sliceCol) form.append('slice_col', sliceCol)
    if (sliceVal) form.append('slice_val', sliceVal)
    if (selectedColumns.value.targetMetric) form.append('target_metric', selectedColumns.value.targetMetric)
    if (selectedColumns.value.flagCol) form.append('flag_col', selectedColumns.value.flagCol)

    if (uploadedFiles.value?.quantFile) {
      form.append('quant_file', uploadedFiles.value.quantFile)
      if (uploadedFiles.value.sentimentFile) form.append('sentiment_file', uploadedFiles.value.sentimentFile)
    } else if (activeSampleId.value) {
      form.append('sample_id', activeSampleId.value)
    }

    const resp = await fetch(`${apiBase}/api/reconcile`, {
      method: 'POST',
      headers: uploadedFiles.value?.quantFile ? ownerHeaders() : {},
      body: form
    })
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
