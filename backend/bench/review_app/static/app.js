import { createApp, reactive, computed, watch, ref, onMounted } from "/vendor/vue.js";
import { marked } from "/vendor/marked.js";

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //

async function api(path, method = "GET", body = undefined) {
  const options = { method };
  if (body !== undefined) Object.assign(options, { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(`${response.status} ${detail}`);
  }
  return response.json();
}

const enc = encodeURIComponent;

function fmt(value, column) {
  if (value === null || value === undefined) return "–";
  if (column && column.percent) return `${(value * 100).toFixed(column.digits <= 1 ? 1 : 2)} %`;
  const digits = column ? column.digits : 3;
  return Number.isInteger(value) && digits <= 1 ? String(value) : value.toFixed(digits);
}
const usd = (v) => (v === null || v === undefined ? "–" : `$${v.toFixed(v < 0.1 ? 4 : 2)}`);
const arrow = (c) => (c.higher_is_better === true ? " ↑" : c.higher_is_better === false ? " ↓" : "");
const title = (c) => (c.higher_is_better === true ? "higher is better" : c.higher_is_better === false ? "lower is better" : "no better direction");

/** Index of the best value per column (null when fewer than 2 values or no direction). */
function bestValues(columns, rows) {
  return columns.map((c, i) => {
    const values = rows.map((r) => r[i]).filter((v) => v !== null && v !== undefined);
    if (values.length < 2 || c.higher_is_better === null) return null;
    return c.higher_is_better ? Math.max(...values) : Math.min(...values);
  });
}

function markdown(text) {
  return marked.parse(text || "", { gfm: true, breaks: false });
}

// --------------------------------------------------------------------------- //
// Router (hash): #/  #/c/<campaign>  #/c/<campaign>/s/<step>  #/c/<campaign>/s/<step>/l/<lesson>?m=a,b&r=0
// --------------------------------------------------------------------------- //

const route = reactive({ name: "list", params: {}, query: {} });

function parseHash() {
  const [path, search] = location.hash.replace(/^#/, "").split("?");
  const parts = (path || "/").split("/").filter(Boolean).map(decodeURIComponent);
  const query = Object.fromEntries(new URLSearchParams(search || ""));
  const params = {};
  for (let i = 0; i + 1 < parts.length; i += 2) params[parts[i]] = parts[i + 1];
  route.params = params;
  route.query = query;
  route.name = params.l ? "lesson" : params.s ? "step" : params.c ? "campaign" : "list";
}
window.addEventListener("hashchange", parseHash);
parseHash();

function go(params, query) {
  let hash = "#/";
  for (const key of ["c", "s", "l"]) if (params[key]) hash += `${key}/${enc(params[key])}/`;
  const search = new URLSearchParams(Object.entries(query || {}).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString();
  location.hash = hash.replace(/\/$/, "") + (search ? `?${search}` : "");
}

// Selected candidates per campaign/step, kept between views and sessions.
function storedSelection(stem, step) {
  try { return JSON.parse(localStorage.getItem(`bench:${stem}:${step}`)); } catch { return null; }
}
function storeSelection(stem, step, keys) {
  localStorage.setItem(`bench:${stem}:${step}`, JSON.stringify(keys));
}

// --------------------------------------------------------------------------- //
// Components
// --------------------------------------------------------------------------- //

/** Short definition of a report column (metric or detail), for its tooltip. */
const metricTooltip = (c) => [c.summary, c.unit ? "Unit: " + c.unit : null, title(c) + (c.judge ? " – LLM judge" : ""),
  "Click for how it is measured."].filter(Boolean).join("\n");

/** Modal with the definition of a report column: summary, unit, direction, options, how it is measured (metric docstring). */
const MetricInfo = {
  props: ["column"],
  emits: ["close"],
  setup(props, { emit }) {
    const box = ref(null);
    onMounted(() => box.value?.focus());
    const options = computed(() => {
      const parsed = JSON.parse(props.column.options || "{}");
      return Object.keys(parsed).length ? JSON.stringify(parsed) : null;
    });
    return { box, options, title, close: () => emit("close") };
  },
  template: `
  <div class="modal-backdrop" @mousedown.self="close" @keydown.esc="close">
    <div class="modal metric-info" role="dialog" aria-modal="true" tabindex="-1" ref="box">
      <header>
        <span class="name">{{ column.detail ? column.metric + ' › ' + column.label : column.metric }}</span>
        <span v-if="column.judge" class="muted small"> · LLM judge</span>
      </header>
      <p v-if="column.summary">{{ column.summary }}</p>
      <dl>
        <dt>Unit</dt><dd>{{ column.unit || (column.percent ? '%' : 'number') }}</dd>
        <dt>Direction</dt><dd>{{ title(column) }}</dd>
        <dt v-if="options">Options</dt><dd v-if="options"><code>{{ options }}</code></dd>
        <dt v-if="column.detail">Detail of</dt><dd v-if="column.detail"><code>{{ column.metric }}</code> (described below)</dd>
      </dl>
      <h4>How it is measured</h4>
      <pre class="metric-doc">{{ column.doc || 'No description.' }}</pre>
      <p class="small muted">Scores are averaged over the lessons (each lesson: mean over its repeats). From <code>bench/metrics/{{ column.metric }}.py</code>.</p>
      <div style="text-align:right"><button @click="close">Close</button></div>
    </div>
  </div>`,
};

/** Metrics as rows, models (candidates) as columns: there are many more metrics than models. */
const SummaryTable = {
  components: { MetricInfo },
  props: ["step", "selectable", "selected"],
  emits: ["toggle"],
  setup(props) {
    const best = computed(() => bestValues(props.step.columns, props.step.rows.map((r) => r.cells.map((c) => c.value))));
    const severalPrompts = computed(() => new Set(props.step.rows.map((r) => r.prompt)).size > 1);
    const costRows = [
      { label: "calls ok", value: (r) => `${r.calls_ok}/${r.calls}` },
      { label: "lessons", value: (r) => r.lessons },
      { label: "USD / call", value: (r) => usd(r.cost_per_call) },
      { label: "s / call", value: (r) => (r.latency === null ? "–" : r.latency.toFixed(1)) },
      { label: "total USD", value: (r) => usd(r.cost) },
      { label: "judge USD", value: (r) => (r.judge_cost ? usd(r.judge_cost) : "–") },
    ];
    const info = ref(null);  // column whose definition is shown
    return { best, severalPrompts, costRows, fmt, usd, arrow, title, info, metricTooltip };
  },
  template: `
  <div class="scroll"><table class="summary">
    <thead><tr>
      <th class="l">metric</th>
      <th v-for="row in step.rows" :key="row.key">
        <label v-if="selectable" class="pick"><input type="checkbox" :checked="selected.includes(row.key)" @change="$emit('toggle', row.key)"> {{ row.model }}</label>
        <template v-else>{{ row.model }}</template>
        <div v-if="severalPrompts" class="muted small">{{ row.prompt }}</div>
      </th>
      <th v-if="step.baseline" class="baseline-col">{{ step.baseline.label }}</th>
    </tr></thead>
    <tbody>
      <tr v-for="(c, i) in step.columns" :class="{ detail: c.detail, 'metric-start': !c.detail && i > 0 }">
        <td class="l metric-name" :title="metricTooltip(c)" @click="info = c">
          <template v-if="c.detail">› {{ c.label }}</template><b v-else>{{ c.metric }}</b>{{ c.percent ? ' %' : '' }}{{ arrow(c) }}</td>
        <td v-for="row in step.rows" :key="row.key" :class="{ best: row.cells[i].value !== null && row.cells[i].value === best[i] }">
          {{ fmt(row.cells[i].value, c) }}<span v-if="row.cells[i].spread !== null" class="spread">± {{ fmt(row.cells[i].spread, c) }}</span>
        </td>
        <td v-if="step.baseline" class="baseline-col">{{ fmt(step.baseline.cells[i].value, c) }}</td>
      </tr>
      <tr v-for="(r, k) in costRows" class="cost" :class="{ 'metric-start': k === 0 }">
        <td class="l">{{ r.label }}</td>
        <td v-for="row in step.rows" :key="row.key">{{ r.value(row) }}</td>
        <td v-if="step.baseline" class="baseline-col"></td>
      </tr>
    </tbody>
  </table></div>
  <MetricInfo v-if="info" :column="info" @close="info = null" />
  <p v-for="w in step.warnings || []" class="warning small">⚠ {{ w }}</p>
  <details v-if="step.failures.length" class="small" style="margin-top:.5rem">
    <summary>{{ step.failures.length }} call(s) without output</summary>
    <ul><li v-for="f in step.failures"><code>{{ f.label }}</code>: <span class="muted">{{ f.error }}</span></li></ul>
  </details>`,
};

const CampaignList = {
  setup() {
    const state = reactive({ campaigns: null, error: null });
    api("/campaigns").then((c) => (state.campaigns = c)).catch((e) => (state.error = e.message));
    return { state, go, usd };
  },
  template: `
  <div v-if="state.error" class="error">{{ state.error }}</div>
  <div v-else-if="!state.campaigns" class="loading">Loading…</div>
  <template v-else>
    <h1>Campaigns</h1>
    <p class="muted">Campaign files of <code>bench/configs</code>, most recently modified first.</p>
    <div class="cards">
      <div v-for="c in state.campaigns" class="card" @click="go({ c: c.stem })">
        <h2>{{ c.name }}</h2>
        <div class="muted small"><code>{{ c.stem }}</code> – dataset {{ c.dataset_version || '?' }} – {{ c.lessons }} lesson(s)</div>
        <p class="small">{{ c.description }}</p>
        <div><span v-for="s in c.steps" class="tag">{{ s.name }} · {{ s.models }} models</span></div>
        <div class="small muted" style="margin-top:.4rem">
          <template v-if="c.last_run">last run #{{ c.last_run.id }} <span :class="'tag status-' + c.last_run.status">{{ c.last_run.status }}</span>
            {{ c.last_run.started_at?.slice(0, 16).replace('T', ' ') }} – {{ usd(c.last_run.actual_usd) }}</template>
          <template v-else>never run</template>
        </div>
      </div>
    </div>
  </template>`,
};

const CampaignDashboard = {
  components: { SummaryTable },
  setup() {
    const state = reactive({ data: null, error: null });
    const load = () => {
      state.data = null; state.error = null;
      api(`/campaigns/${enc(route.params.c)}`).then((d) => (state.data = d)).catch((e) => (state.error = e.message));
    };
    watch(() => route.params.c, load, { immediate: true });
    return { state, go, usd, route };
  },
  template: `
  <div v-if="state.error" class="error">{{ state.error }}</div>
  <div v-else-if="!state.data" class="loading">Loading campaign…</div>
  <template v-else>
    <h1>{{ state.data.name }}</h1>
    <div class="muted">{{ state.data.description }}</div>
    <div class="muted small"><code>{{ state.data.file }}</code> – dataset {{ state.data.dataset_version || '?' }}
      <template v-if="state.data.judge"> – judge {{ state.data.judge.model }} ({{ state.data.judge.provider }})</template></div>
    <div class="kpis">
      <div class="kpi"><div class="v">{{ state.data.lessons.length }}</div><div class="l">lessons</div></div>
      <div class="kpi"><div class="v">{{ Object.keys(state.data.models).length }}</div><div class="l">models</div></div>
      <div class="kpi"><div class="v">{{ state.data.steps.length }}</div><div class="l">steps</div></div>
      <div class="kpi"><div class="v">{{ usd(state.data.cost) }}</div><div class="l">generation cost</div></div>
      <div class="kpi"><div class="v">{{ usd(state.data.judge_cost) }}</div><div class="l">judge cost</div></div>
      <div class="kpi"><div class="v">{{ state.data.runs.length }}</div><div class="l">runs</div></div>
    </div>
    <div v-for="step in state.data.steps" class="panel">
      <h2><a @click="go({ c: route.params.c, s: step.name })">{{ step.name }}</a> <span class="muted small">({{ step.task }})</span>
        <button style="float:right" @click="go({ c: route.params.c, s: step.name })">Details by lesson →</button></h2>
      <SummaryTable :step="step" />
    </div>
    <div class="panel">
      <h2>Lessons</h2>
      <span v-for="l in state.data.lessons" class="tag">{{ l.id }} <span class="muted">({{ l.kind }})</span></span>
    </div>
    <div class="panel">
      <h2>Models</h2>
      <table><thead><tr><th class="l">alias</th><th class="l">id</th><th class="l">provider</th><th class="l">params</th></tr></thead>
        <tbody><tr v-for="(m, alias) in state.data.models"><td class="l">{{ alias }}</td><td class="l">{{ m.id }}</td>
          <td class="l">{{ m.provider }}</td><td class="l"><code>{{ JSON.stringify(m.params) }}</code></td></tr></tbody></table>
    </div>
    <div class="panel" v-if="state.data.runs.length">
      <h2>Runs</h2>
      <table><thead><tr><th>#</th><th class="l">status</th><th class="l">started</th><th class="l">dataset</th><th class="l">commit</th><th>estimated</th><th>actual</th></tr></thead>
        <tbody><tr v-for="r in state.data.runs"><td>{{ r.id }}</td><td class="l"><span :class="'tag status-' + r.status">{{ r.status }}</span></td>
          <td class="l">{{ r.started_at?.slice(0, 19).replace('T', ' ') }}</td><td class="l">{{ r.dataset_version }}</td>
          <td class="l"><code>{{ (r.git_commit || '').slice(0, 8) }}</code></td><td>{{ usd(r.estimated_usd) }}</td><td>{{ usd(r.actual_usd) }}</td></tr></tbody></table>
    </div>
  </template>`,
};

const StepView = {
  components: { SummaryTable },
  setup() {
    const state = reactive({ data: null, error: null, selected: [], metric: 0 });
    const load = () => {
      state.data = null; state.error = null;
      api(`/campaigns/${enc(route.params.c)}/steps/${enc(route.params.s)}`).then((d) => {
        const keys = d.candidates.map((c) => c.key);
        const stored = (storedSelection(route.params.c, route.params.s) || []).filter((k) => keys.includes(k));
        state.selected = stored.length ? stored : keys;
        state.metric = Math.max(0, d.columns.findIndex((c) => !c.detail));
        state.data = d;
      }).catch((e) => (state.error = e.message));
    };
    watch(() => [route.params.c, route.params.s], load, { immediate: true });
    const toggle = (key) => {
      state.selected = state.selected.includes(key) ? state.selected.filter((k) => k !== key) : [...state.selected, key];
      storeSelection(route.params.c, route.params.s, state.selected);
    };
    const shown = computed(() => (state.data ? state.data.candidates.filter((c) => state.selected.includes(c.key)) : []));
    const column = computed(() => state.data?.columns[state.metric]);
    const lessonBest = (lesson) => {
      const values = shown.value.map((c) => lesson.values[c.key]?.cells[state.metric]).filter((v) => v !== null && v !== undefined);
      if (values.length < 2 || !column.value || column.value.higher_is_better === null) return null;
      return column.value.higher_is_better ? Math.max(...values) : Math.min(...values);
    };
    const open = (lesson) => go({ c: route.params.c, s: route.params.s, l: lesson }, { m: state.selected.join(",") });
    return { state, toggle, shown, column, lessonBest, open, fmt, arrow, route, go };
  },
  template: `
  <div v-if="state.error" class="error">{{ state.error }}</div>
  <div v-else-if="!state.data" class="loading">Loading step…</div>
  <template v-else>
    <h1>{{ state.data.name }} <span class="muted small">({{ state.data.task }}) – {{ state.data.campaign }}</span></h1>
    <div class="panel">
      <h2>Summary</h2>
      <p class="muted small">Mean over lessons of the mean over repeats; ± = spread between repeats. Tick the models to compare below.</p>
      <SummaryTable :step="state.data" selectable="1" :selected="state.selected" @toggle="toggle" />
    </div>
    <div class="panel">
      <div class="toolbar">
        <h2 style="margin:0">By lesson</h2>
        <label>metric <select v-model.number="state.metric">
          <option v-for="(c, i) in state.data.columns" :value="i">{{ c.detail ? '  ' + c.metric + ' › ' : '' }}{{ c.label }}{{ arrow(c) }}</option>
        </select></label>
        <div class="chips"><span v-for="c in state.data.candidates" class="chip" :class="{ on: state.selected.includes(c.key) }" @click="toggle(c.key)">{{ c.model }}<span v-if="new Set(state.data.candidates.map(x => x.prompt)).size > 1"> / {{ c.prompt }}</span></span></div>
      </div>
      <div class="tablewrap"><table>
        <thead><tr><th class="l">lesson</th><th v-for="c in shown">{{ c.model }}<div class="muted small">{{ c.prompt }}</div></th></tr></thead>
        <tbody>
          <tr v-for="lesson in state.data.lessons" class="clickable" @click="open(lesson.id)" title="Open gold vs outputs">
            <td class="l"><a>{{ lesson.id }}</a></td>
            <td v-for="c in shown" :class="{ best: lesson.values[c.key]?.cells[state.metric] != null && lesson.values[c.key]?.cells[state.metric] === lessonBest(lesson) }">
              <template v-if="!lesson.values[c.key]">–</template>
              <template v-else-if="!lesson.values[c.key].ok"><span class="error small">no output</span></template>
              <template v-else>{{ fmt(lesson.values[c.key].cells[state.metric], column) }}</template>
            </td>
          </tr>
        </tbody>
      </table></div>
    </div>
  </template>`,
};

const ScoresTable = {
  props: ["data"],
  setup(props) {
    const outputs = computed(() => props.data.outputs.filter((o) => o.output !== null));
    const value = (o, c) => {
      const score = o.scores.find((s) => s.metric === c.metric && JSON.stringify(sortKeys(s.options)) === JSON.stringify(sortKeys(JSON.parse(c.options))));
      if (!score) return null;
      return c.detail ? score.details[c.label] : score.value;
    };
    const best = computed(() => bestValues(
      props.data.columns,
      outputs.value.map((o) => props.data.columns.map((c) => (typeof value(o, c) === "number" ? value(o, c) : null))),
    ));
    return { outputs, value, best, fmt, arrow, usd };
  },
  template: `
  <div class="scroll"><table>
    <thead><tr><th class="l">metric</th><th v-for="o in outputs">{{ o.model }}<div class="muted small">{{ o.prompt }} · r{{ o.repeat }}</div></th></tr></thead>
    <tbody>
      <tr v-for="(c, i) in data.columns" :class="{ muted: c.detail }">
        <td class="l">{{ c.detail ? '› ' + c.label : c.metric }}{{ arrow(c) }}</td>
        <td v-for="o in outputs" :class="{ best: value(o, c) !== null && value(o, c) === best[i] }">{{ typeof value(o, c) === 'number' ? fmt(value(o, c), c) : (value(o, c) ?? '–') }}</td>
      </tr>
      <tr class="baseline"><td class="l">cost / tokens in·out / s</td>
        <td v-for="o in outputs">{{ usd(o.cost_usd) }} · {{ o.tokens_in }}/{{ o.tokens_out }} · {{ o.latency_s?.toFixed(1) }}</td></tr>
    </tbody>
  </table></div>
  <h3>Details</h3>
  <details v-for="o in outputs"><summary>{{ o.model }} / {{ o.prompt }} · r{{ o.repeat }}</summary>
    <details v-for="s in o.scores" style="margin-left:1rem"><summary>{{ s.metric }} = {{ s.value }}</summary>
      <pre class="json">{{ JSON.stringify(s.details, null, 2) }}</pre></details>
  </details>`,
};

function sortKeys(obj) {
  if (Array.isArray(obj)) return obj.map(sortKeys);
  if (obj && typeof obj === "object") return Object.fromEntries(Object.keys(obj).sort().map((k) => [k, sortKeys(obj[k])]));
  return obj;
}

/** One piece of a segment text (backend review_app/segment_view.py): a category maps to CSS classes.
 * `judged`: colors after the judge (level `p.j`; a red / purple difference without verdict keeps its color). */
const Piece = {
  props: ["p", "judged"],
  setup(props) {
    const classes = computed(() => {
      const p = props.p;
      const afterJudge = props.judged && p.j && p.j !== "unjudged";
      return ["tok", "tok--" + p.c, afterJudge ? "jl--" + p.j : "sev--" + p.s,
        { "tok--gap": p.gap, "tok--unjudged": props.judged && p.j === "unjudged", "tok--suspect": props.judged && p.gs }];
    });
    const title = computed(() => (props.judged && props.p.jh ? props.p.h + "\n\n" + props.p.jh : props.p.h));
    return { classes, title };
  },
  template: `<span v-if="p.c" :class="classes" :title="title">{{ p.t }}</span><template v-else>{{ p.t }}</template>`,
};

/** Pieces of a segment text; each Hebrew passage is isolated in <bdi dir="rtl"> (punctuation around it stays outside). */
const Pieces = {
  components: { Piece },
  props: ["items", "judged"],
  template: `<template v-for="(it, i) in items" :key="i"><bdi v-if="it.rtl" dir="rtl"><Piece v-for="(p, j) in it.rtl" :key="j" :p="p" :judged="judged" /></bdi><Piece v-else :p="it" :judged="judged" /></template>`,
};

/** Modal to edit the gold text of one segment, with the texts of the initial transcript and of the models to copy from. */
const GoldEditor = {
  components: { Pieces },
  props: ["data", "row"],
  emits: ["close", "saved"],
  setup(props, { emit }) {
    const draft = ref(props.row.gold_raw);  // as written: doubt tags are kept
    const box = ref(null);
    onMounted(() => box.value?.focus());
    const state = reactive({ saving: false, error: null });
    const sources = computed(() => [
      { key: "initial", name: "initial", detail: "initial.md", text: props.row.initial.text, raw: props.row.initial.raw, html: props.row.initial.html,
        severity: props.row.initial.severity, pieces: props.row.initial.pieces, same: props.row.initial.changed === 0 },
      ...props.data.outputs.map((o) => {
        const cell = props.row.cells[o.key];
        const missing = !cell || cell.missing;
        return { key: o.key, name: o.model, detail: `${o.prompt} · r${o.repeat}`, text: missing ? null : cell.text, raw: missing ? null : cell.raw,
                 html: cell?.html ?? null, severity: cell?.severity ?? null, pieces: cell?.pieces ?? null, worst: cell?.worst ?? null,
                 same: cell?.pieces ? !cell.worst : !cell?.severity };
      }),
    ]);
    const changed = computed(() => draft.value.split(/\s+/).join(" ").trim() !== props.row.gold_raw);
    const save = async () => {
      if (!changed.value || state.saving) return;
      state.saving = true; state.error = null;
      try {
        await api(`/campaigns/${enc(route.params.c)}/steps/${enc(route.params.s)}/lessons/${enc(props.data.lesson)}/gold-segment`, "PUT",
                  { start: props.row.start, end: props.row.end, previous: props.row.gold_raw, text: draft.value });
        emit("saved");
      } catch (e) {
        state.error = e.message;
      } finally {
        state.saving = false;
      }
    };
    const close = () => {
      if (!changed.value || confirm("Discard the changes of this segment?")) emit("close");
    };
    return { draft, box, state, sources, changed, save, close };
  },
  template: `
  <div class="modal-backdrop" @mousedown.self="close" @keydown.esc="close">
    <div class="modal" role="dialog" aria-modal="true">
      <header><span class="name">corrected (gold)</span> <span class="muted small">{{ row.time }} · {{ data.gold_file }}</span></header>
      <textarea ref="box" v-model="draft" rows="4" @keydown.ctrl.enter="save" @keydown.meta.enter="save"></textarea>
      <div class="toolbar" style="margin:.4rem 0 .8rem">
        <button class="primary" :disabled="!changed || state.saving" @click="save">{{ state.saving ? "Saving…" : "Save" }}</button>
        <button @click="close">Cancel</button>
        <button :disabled="!changed" @click="draft = row.gold_raw">Reset</button>
        <span class="muted small">Ctrl+Enter to save · Esc to cancel</span>
        <span v-if="state.error" class="error small">{{ state.error }}</span>
      </div>
      <div class="muted small" style="margin-bottom:.3rem">Copy the text of another transcript into the gold, doubt tags included (marks: differences with the saved gold, tags ignored):</div>
      <div class="sources">
        <div v-for="src in sources" :key="src.key" class="source" :class="src.text === null ? 'na' : (src.worst ? 'worst--' + src.worst : (src.severity ? 'sev-' + src.severity : ''))">
          <button :disabled="src.text === null" @click="draft = src.raw" :title="'Copy into the gold'">{{ src.name }}</button>
          <span class="muted small">{{ src.detail }}</span>
          <div class="text">
            <em v-if="src.text === null" class="muted">no segment</em>
            <span v-else-if="src.pieces" class="seg-text"><Pieces :items="src.pieces" /><span v-if="src.same" class="muted small"> (= gold)</span></span>
            <span v-else-if="src.html" v-html="src.html"></span>
            <span v-else>{{ src.text }} <span class="muted small">(= gold)</span></span>
          </div>
        </div>
      </div>
    </div>
  </div>`,
};

const CorrectionSegments = {
  components: { GoldEditor },
  props: ["data"],
  emits: ["changed"],
  setup(props, { emit }) {
    const onlyDiff = ref(true);
    const editing = ref(null);
    const saved = () => { editing.value = null; emit("changed"); };
    const outputs = computed(() => props.data.outputs);
    const rows = computed(() => props.data.segments.filter((r) => !onlyDiff.value || r.initial.severity || Object.values(r.cells).some((c) => c.severity)));
    const counts = computed(() => {
      const result = { initial: { fold: 0, norm: 0, minor: 0 } };
      for (const o of outputs.value) result[o.key] = { fold: 0, norm: 0, minor: 0 };
      for (const r of props.data.segments) {
        if (r.initial.severity) result.initial[r.initial.severity]++;
        for (const [key, cell] of Object.entries(r.cells)) if (cell.severity) result[key][cell.severity]++;
      }
      return result;
    });
    const total = (c) => c.fold + c.norm + c.minor;
    return { onlyDiff, rows, outputs, counts, total, editing, saved };
  },
  template: `
  <div class="toolbar">
    <label><input type="checkbox" v-model="onlyDiff"> only segments with a difference</label>
    <span class="small muted">{{ rows.length }} / {{ data.segments.length }} segments</span>
    <span class="small"><mark class="fold">real error</mark> (wer_fold) · <mark class="norm">transliteration variant</mark> (wer_norm only) · <mark class="minor">minor</mark> (case, accents, apostrophes, hyphens) · ‸ missing words</span>
  </div>
  <table style="margin-bottom:1rem">
    <thead><tr><th class="l">segments different from corrected</th><th>initial</th><th v-for="o in outputs">{{ o.model }}</th></tr></thead>
    <tbody><tr><td class="l">count <span class="n fold">fold</span><span class="n norm">norm</span><span class="n minor">minor</span></td>
      <td>{{ total(counts.initial) }}<span class="n fold">{{ counts.initial.fold }}</span><span class="n norm">{{ counts.initial.norm }}</span><span class="n minor">{{ counts.initial.minor }}</span></td>
      <td v-for="o in outputs"><template v-if="o.output === null">–</template><template v-else>{{ total(counts[o.key]) }}<span class="n fold">{{ counts[o.key].fold }}</span><span class="n norm">{{ counts[o.key].norm }}</span><span class="n minor">{{ counts[o.key].minor }}</span></template></td>
    </tr></tbody>
  </table>
  <div class="tablewrap"><table class="segments">
    <thead><tr><th class="l">time</th><th class="l">initial</th><th class="l">corrected (gold)</th><th class="l" v-for="o in outputs">{{ o.model }}<div class="muted small">{{ o.prompt }} · r{{ o.repeat }}</div></th></tr></thead>
    <tbody>
      <tr v-for="r in rows" :key="r.start">
        <td class="ts">{{ r.time }}</td>
        <td :class="r.initial.severity ? 'sev-' + r.initial.severity : ''"><span v-if="r.initial.html" v-html="r.initial.html"></span><span v-else>{{ r.initial.text }}</span></td>
        <td class="gold editable" title="Click to edit the gold" @click="editing = r">{{ r.gold }}</td>
        <td v-for="o in outputs" :class="o.output === null ? 'na' : (r.cells[o.key]?.severity ? 'sev-' + r.cells[o.key].severity : '')">
          <template v-if="o.output !== null && r.cells[o.key]?.severity"><span v-html="r.cells[o.key].html"></span></template>
        </td>
      </tr>
    </tbody>
  </table></div>
  <p class="small muted">Model cells: empty = same words as corrected.md; grey = no output. Click a gold cell to edit corrected.md.</p>
  <GoldEditor v-if="editing" :data="data" :row="editing" @close="editing = null" @saved="saved" />`,
};

/** Segments of a correction in Hebrew script: colors and counters from the categories of the metrics
 * (backend metrics/hebrew.py compare_unit), so they match hebrew_identification / wer_french. */
const HebrewSegments = {
  components: { GoldEditor, Pieces },
  props: ["data"],
  emits: ["changed"],
  setup(props, { emit }) {
    const minimum = ref("any");
    const editing = ref(null);
    const saved = () => { editing.value = null; emit("changed"); };
    const outputs = computed(() => props.data.outputs);
    const judge = computed(() => props.data.judge || null);
    // "after": colors and counters after the judge (critical / significant / minor / none).
    const view = ref(props.data.judge && Object.values(props.data.judge.judged).some(Boolean) ? "after" : "before");
    const judged = computed(() => view.value === "after" && judge.value !== null);
    watch(view, () => { minimum.value = "any"; });
    // Levels of the current view, from the most to the least serious: {key, label, parts: [{key, label}]}.
    const levels = computed(() => (judged.value
      ? judge.value.legend.map((l) => ({ key: l.level, label: l.label, parts: l.parts, css: l.level === "unjudged" ? "sev--error tok--unjudged" : "jl--" + l.level }))
      : props.data.segment_legend.map((s) => ({ key: s.severity, label: s.label, css: "sev--" + s.severity,
        parts: s.categories.map((c) => ({ key: c.category, label: c.label })) }))));
    const rank = (level) => { const i = levels.value.findIndex((l) => l.key === level); return i < 0 ? Infinity : i; };
    const cellWorst = (cell) => (judged.value ? cell.judge_worst : cell.worst);
    const cellClass = (cell) => {
      const worst = cellWorst(cell);
      if (!worst) return "seg-text";
      if (!judged.value) return "seg-text worst--" + worst;
      return "seg-text " + (worst === "unjudged" ? "worst--" + cell.worst : "jworst--" + worst);
    };
    const rows = computed(() => props.data.segments.filter((r) => {
      const worst = Math.min(...Object.values(r.cells).map((c) => (c.missing ? 0 : rank(cellWorst(c)))));
      if (minimum.value === "all") return true;
      if (minimum.value === "any") return worst < Infinity || r.initial.changed > 0 || r.doubts > 0;
      return worst <= rank(minimum.value);
    }));
    const totals = props.data.segment_totals;
    const countsOf = (key) => (judged.value ? judge.value.totals[key] : totals.models[key]) || {};
    const count = (key, level) => level.parts.reduce((n, p) => n + (countsOf(key)[p.key] || 0), 0);
    const breakdown = (key, level) => level.parts.map((p) => `${p.label}: ${countsOf(key)[p.key] || 0}`).join("\n");
    const partsOf = (level) => level.parts.map((p) => p.label).join(", ");
    const visibleLevels = computed(() => levels.value.filter((l) => l.key !== "unjudged" || outputs.value.some((o) => count(o.key, l) > 0)));
    const suspects = (key) => countsOf(key).gold_suspect || 0;
    const acceptable = (key) => countsOf(key).both_acceptable || 0;
    const notJudged = computed(() => (judge.value ? outputs.value.filter((o) => o.output !== null && !judge.value.judged[o.key]).map((o) => o.model) : []));
    return { minimum, editing, saved, outputs, judge, view, judged, levels, visibleLevels, rows, totals, count, breakdown,
      partsOf, cellClass, cellWorst, suspects, acceptable, notJudged };
  },
  template: `
  <div class="toolbar">
    <span v-if="judge" class="seg-toggle" title="Colors and counters before / after the judge (correction_judge)">
      <button :class="{ on: view === 'before' }" @click="view = 'before'">before judge</button><button :class="{ on: view === 'after' }" @click="view = 'after'">after judge</button>
    </span>
    <label>show <select v-model="minimum">
      <option value="any">segments with a difference</option>
      <option v-for="l in visibleLevels" :value="l.key">{{ l.label }} or worse</option>
      <option value="all">all segments</option>
    </select></label>
    <span class="small muted">{{ rows.length }} / {{ data.segments.length }} segments</span>
    <span class="small"><span class="tok tok--gold_doubt sev--doubt">questionable gold (&lt;d&gt;)</span>: {{ totals.gold_doubts }}</span>
    <span class="small"><span class="tok tok--gold_changed sev--cosmetic">changed by the gold</span> (initial): {{ totals.initial_changes }}</span>
    <span class="small muted">glossary: {{ totals.glossary_entries }} entries</span>
  </div>
  <p v-if="judged && notJudged.length" class="small muted">Not judged yet: {{ notJudged.join(", ") }} (run the scoring with the judge: <code>python -m bench.run &lt;campaign&gt; --only score</code>).</p>
  <table style="margin-bottom:1rem">
    <thead><tr><th class="l">{{ judged ? 'impact after the judge' : 'differences with corrected.md' }}</th><th v-for="o in outputs">{{ o.model }}</th></tr></thead>
    <tbody>
      <tr v-for="l in visibleLevels" :key="l.key">
        <td class="l" :title="partsOf(l)"><span :class="['tok', l.css]">{{ l.label }}</span> <span class="muted small">{{ partsOf(l) }}</span></td>
        <td v-for="o in outputs" :title="breakdown(o.key, l)"><template v-if="o.output === null">–</template><template v-else>{{ count(o.key, l) }}</template></td>
      </tr>
      <tr v-if="judged">
        <td class="l"><span class="tok tok--suspect jl--none">gold suspects</span> <span class="muted small">the judge says the output is right, not the gold (review corrected.md)</span></td>
        <td v-for="o in outputs" :title="'both acceptable: ' + acceptable(o.key)"><template v-if="o.output === null">–</template><template v-else>{{ suspects(o.key) }}</template></td>
      </tr>
    </tbody>
  </table>
  <div class="tablewrap"><table class="segments">
    <thead><tr><th class="l">time</th><th class="l">initial</th><th class="l">corrected (gold)</th><th class="l" v-for="o in outputs">{{ o.model }}<div class="muted small">{{ o.prompt }} · r{{ o.repeat }}</div></th></tr></thead>
    <tbody>
      <tr v-for="r in rows" :key="r.start">
        <td class="ts">{{ r.time }}</td>
        <td class="seg-text"><Pieces :items="r.initial.pieces" /></td>
        <td class="gold editable seg-text" title="Click to edit the gold" @click="editing = r"><Pieces :items="r.gold_pieces" /></td>
        <td v-for="o in outputs" :class="o.output === null || !r.cells[o.key] ? 'na' : (r.cells[o.key].missing ? 'worst--error' : cellClass(r.cells[o.key]))">
          <em v-if="r.cells[o.key]?.missing" class="muted">missing segment</em>
          <Pieces v-else-if="r.cells[o.key]?.worst" :items="r.cells[o.key].pieces" :judged="judged" />
        </td>
      </tr>
    </tbody>
  </table></div>
  <p class="small muted">Model cells: empty = same words as corrected.md; grey = no output. Hover a marked word for its category, the gold form and the rendering of both forms<template v-if="judged">, and the verdict of the judge (blue outline: gold suspect; red / purple with a "?" : not judged)</template>. Click a gold cell to edit corrected.md.</p>
  <GoldEditor v-if="editing" :data="data" :row="editing" @close="editing = null" @saved="saved" />`,
};

const SideBySide = {
  props: ["data"],
  setup(props) {
    const raw = ref(false);
    const showInput = ref(false);
    const columns = computed(() => {
      const cols = [];
      if (showInput.value) cols.push({ key: "input", name: `input (${props.data.input_file})`, text: props.data.input, css: "" });
      cols.push({ key: "gold", name: `gold (${props.data.gold_file})`, text: props.data.gold, css: "gold" });
      for (const o of props.data.outputs) {
        cols.push({ key: o.key, name: o.model, sub: `${o.prompt} · r${o.repeat}`, text: o.output, error: o.error, css: "", output: o });
      }
      return cols;
    });
    const words = (t) => (t || "").split(/\s+/).filter(Boolean).length;
    return { raw, showInput, columns, markdown, words };
  },
  template: `
  <div class="toolbar">
    <label><input type="checkbox" v-model="raw"> raw markdown</label>
    <label><input type="checkbox" v-model="showInput"> show the input ({{ data.input_file }})</label>
  </div>
  <div class="columns" :style="{ gridTemplateColumns: 'repeat(' + columns.length + ', minmax(320px, 1fr))' }">
    <div v-for="c in columns" class="textcol" :class="c.css">
      <header><span class="name">{{ c.name }}</span> <span class="muted small">{{ c.sub }} · {{ words(c.text) }} words</span></header>
      <div v-if="c.error" class="body error">{{ c.error }}</div>
      <div v-else-if="raw || c.key === 'input'" class="body raw">{{ c.text }}</div>
      <div v-else class="body markdown" v-html="markdown(c.text)"></div>
    </div>
  </div>`,
};

const ELEMENT_MARKS = { present: "●", implicit: "◐", distorted: "◇", missing: "○" };

const IdeasMatrix = {
  props: ["data"],
  setup(props) {
    const open = ref(new Set());
    const onlyNotPresent = ref(false);
    const outputs = computed(() => props.data.outputs.filter((o) => o.output !== null));
    const score = (o) => o.scores.find((s) => s.metric === "idea_coverage");
    const verdict = (o, id) => score(o)?.details?.verdicts?.find((v) => v.id === id) || null;
    const ideas = computed(() => (props.data.ideas || []).filter((idea) =>
      !onlyNotPresent.value || outputs.value.some((o) => verdict(o, idea.id) && verdict(o, idea.id).verdict !== "present")));
    const toggle = (id) => {
      const next = new Set(open.value);
      next.has(id) ? next.delete(id) : next.add(id);
      open.value = next;
    };
    const note = (v) => (v.judge_verdict && v.judge_verdict !== v.verdict
      ? (v.verdict === "absent" ? "judge: " + v.judge_verdict + ", no quote found in the output" : "judge: present, but not every element is")
      : "");
    const pct = (d, key) => (d && d[key] != null ? Math.round(d[key] * 100) : 0);
    return { open, onlyNotPresent, outputs, score, verdict, ideas, toggle, note, pct, ELEMENT_MARKS };
  },
  template: `
  <p class="small muted">Rule given to the judge: <b>present</b> = all essential elements explicitly stated; <b>partial</b> = at least one essential element missing, only implied or distorted;
    <b>absent</b> = the idea is no longer recognizable. Applied again by code: a present verdict with an element that is not present counts as partial (↓), a verdict without any quote found in the output counts as absent (✗).
    Elements: ● present ◐ implicit ◇ distorted ○ missing. Click an idea for the elements and the quotes.</p>
  <div class="toolbar"><label><input type="checkbox" v-model="onlyNotPresent"> only ideas not present for some model</label></div>
  <div class="tablewrap"><table class="ideas">
    <thead><tr><th>#</th><th class="l">idea</th><th class="l">importance</th>
      <th v-for="o in outputs" class="l">{{ o.model }}
        <div v-if="score(o)" class="small muted">{{ (score(o).value * 100).toFixed(1) }} %</div>
        <div v-if="score(o) && score(o).details.present_rate != null" class="distribution" :title="score(o).details.present + ' present, ' + score(o).details.partial + ' partial, ' + score(o).details.absent + ' absent'">
          <span class="v-present" :style="{ width: pct(score(o).details, 'present_rate') + '%' }"></span><span class="v-partial" :style="{ width: pct(score(o).details, 'partial_rate') + '%' }"></span><span class="v-absent" :style="{ width: pct(score(o).details, 'absent_rate') + '%' }"></span>
        </div>
        <div v-if="score(o) && score(o).details.present_rate != null" class="small muted">{{ score(o).details.present }} / {{ score(o).details.partial }} / {{ score(o).details.absent }}</div>
        <div v-else-if="!score(o)" class="small muted">not judged</div></th></tr></thead>
    <tbody>
      <template v-for="idea in ideas" :key="idea.id">
        <tr class="clickable" @click="toggle(idea.id)">
          <td>{{ idea.id }}</td><td class="idea">{{ idea.text }}</td><td class="l">{{ idea.importance }}</td>
          <td v-for="o in outputs" class="cellv">
            <template v-if="verdict(o, idea.id)">
              <span class="verdict" :class="'v-' + verdict(o, idea.id).verdict" :title="note(verdict(o, idea.id))">{{ verdict(o, idea.id).verdict }}<template v-if="note(verdict(o, idea.id))"> {{ verdict(o, idea.id).verdict === 'absent' ? '✗' : '↓' }}</template></span>
              <span class="elements" :title="(verdict(o, idea.id).elements || []).map(e => e.status + ': ' + e.element).join('\\n')"><span v-for="e in verdict(o, idea.id).elements || []" :class="'e-' + e.status">{{ ELEMENT_MARKS[e.status] }}</span></span>
              <div v-if="verdict(o, idea.id).missing" class="small muted">{{ verdict(o, idea.id).missing }}</div>
            </template>
            <span v-else class="muted">–</span>
          </td>
        </tr>
        <tr v-if="open.has(idea.id)" class="expanded">
          <td></td><td colspan="2" class="small muted">elements: {{ verdict(outputs[0], idea.id)?.elements_source === 'dataset' ? 'from edited_ideas.yaml' : 'broken down by the judge' }}</td>
          <td v-for="o in outputs" class="small">
            <template v-if="verdict(o, idea.id)">
              <div v-for="e in verdict(o, idea.id).elements || []"><span :class="'e-' + e.status">{{ ELEMENT_MARKS[e.status] }}</span> {{ e.element }} <span class="muted">({{ e.status }})</span></div>
              <div v-for="q in verdict(o, idea.id).quotes || []" class="quote"><em>« {{ q.text }} »</em> <span :title="q.found ? 'found in the output' : 'not found in the output'">{{ q.found ? '✓' : '✗' }}</span></div>
            </template>
          </td>
        </tr>
      </template>
    </tbody>
  </table></div>`,
};

const CATEGORIES = ["wrong_reference", "contradicted", "model_error", "content_added", "extrapolation", "unverified",
  "speaker_corrected", "quote_added", "reference_added", "missing"];

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Output text with quotes highlighted, sorted by start (overlapping quotes: the first one wins).
 * A highlight is a claim ({id, category, penalized}) or carries its own {id, cls, title}. */
function highlightOutput(text, highlights, prefix) {
  let html = "", position = 0;
  for (const h of highlights || []) {
    if (h.start < position) continue;
    const cls = h.cls || `claim c-${h.category}${h.penalized ? " penalized" : ""}`;
    const title = h.title || `#${h.id} ${h.category}`;
    html += escapeHtml(text.slice(position, h.start));
    html += `<mark id="${prefix}-${h.id}" class="${cls}" title="${escapeHtml(title)}">${escapeHtml(text.slice(h.start, h.end))}</mark>`;
    position = h.end;
  }
  return html + escapeHtml(text.slice(position));
}

const ClaimsView = {
  props: ["data"],
  setup(props) {
    const onlyPenalized = ref(false);
    const showText = ref(true);
    const outputs = computed(() => props.data.outputs.filter((o) => o.output !== null));
    const score = (o) => o.scores.find((s) => s.metric === "faithfulness");
    const issues = (o) => (score(o)?.details.issues || []).filter((i) => !onlyPenalized.value || i.penalized);
    const prefix = (o) => `claim-${o.key.replace(/[^\w-]/g, "_")}`;
    const reveal = (o, issue) => {
      const mark = document.getElementById(`${prefix(o)}-${issue.id}`);
      if (!mark) return;
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
      mark.classList.add("flash");
      setTimeout(() => mark.classList.remove("flash"), 1200);
    };
    const sefariaUrl = (r) => (r?.slug ? `https://www.sefaria.org/${encodeURIComponent(r.slug)}` : null);
    const refStatus = (r) => (!r ? "" : !r.found ? "not found on Sefaria" : r.match ? r.match : "not checked");
    return { onlyPenalized, showText, outputs, score, issues, prefix, reveal, sefariaUrl, refStatus, highlightOutput, CATEGORIES };
  },
  template: `
  <p class="small muted">Claims of each output checked against the lesson ({{ data.input_file }}); supported claims are not listed.
    <b>Penalized</b> categories (campaign <code>penalize</code>) lower the score, the others are only reported.
    Click a claim to show its passage in the output. Source quote ✗ = not found in the transcript (the judge may have invented it).</p>
  <div class="toolbar">
    <label><input type="checkbox" v-model="onlyPenalized"> only penalized claims</label>
    <label><input type="checkbox" v-model="showText"> show the output with the claims highlighted</label>
  </div>
  <div v-for="o in outputs" class="panel">
    <h3 style="margin-top:0">{{ o.model }} <span class="muted small">{{ o.prompt }} · r{{ o.repeat }}</span>
      <template v-if="score(o)"> – {{ (score(o).value * 100).toFixed(1) }} % ({{ score(o).details.claims }} claims,
        {{ score(o).details.penalized ?? '?' }} penalized, {{ score(o).details.reported ?? '?' }} reported, {{ score(o).details.major ?? '?' }} major)</template></h3>
    <div v-if="!score(o)" class="muted">Not judged.</div>
    <template v-else>
      <div style="margin-bottom:.5rem"><span v-for="k in CATEGORIES" v-show="score(o).details[k]" class="verdict" :class="'c-' + k" style="margin-right:.3rem">{{ k }}: {{ score(o).details[k] }}</span></div>
      <div :style="{ display: 'grid', gridTemplateColumns: showText ? 'minmax(0, 3fr) minmax(0, 2fr)' : '1fr', gap: '.75rem', alignItems: 'start' }">
        <div class="tablewrap">
          <table class="ideas claims">
            <thead><tr><th>#</th><th class="l">category</th><th class="l">claim / explanation</th><th class="l">output</th><th class="l">source</th><th class="l">reference</th></tr></thead>
            <tbody>
              <tr v-for="i in issues(o)" class="clickable" @click="reveal(o, i)">
                <td>{{ i.id }}</td>
                <td class="l"><span class="verdict" :class="'c-' + (i.category || i.verdict)">{{ i.category || i.verdict }}</span>
                  <div class="small muted">{{ i.severity }}{{ i.penalized ? ' · penalized' : '' }}</div>
                  <div v-if="i.believes" class="small muted" title="who the judge believes is right">believes: {{ i.believes }}</div></td>
                <td class="idea">{{ i.claim }}<div v-if="i.explanation" class="small" style="margin-top:.25rem">{{ i.explanation }}</div></td>
                <td class="idea small"><em>{{ i.output_quote }}</em> <span :title="i.output_found ? 'found in the output' : 'not found in the output'">{{ i.output_found ? '✓' : '✗' }}</span></td>
                <td class="idea small">
                  <template v-if="i.source_quote"><span v-if="i.source_time" class="tag">{{ i.source_time }}</span>
                    <em>{{ i.source_quote }}</em> <span :title="i.source_found ? 'found in the transcript' : 'not found in the transcript'">{{ i.source_found ? '✓' : '✗' }}</span></template>
                  <span v-else-if="i.quote !== undefined"><em>{{ i.quote }}</em></span>
                  <span v-else class="muted">nothing related in the lesson</span></td>
                <td class="idea small"><template v-if="i.reference">
                  <a v-if="sefariaUrl(i.reference)" :href="sefariaUrl(i.reference)" target="_blank" @click.stop>{{ i.reference.sefaria_ref || i.reference.reference }}</a>
                  <span v-else>{{ i.reference.reference }}</span>
                  <div><span class="verdict" :class="i.reference.found && i.reference.match !== 'differs' ? 'c-speaker_corrected' : 'c-wrong_reference'">{{ refStatus(i.reference) }}</span></div>
                  <div v-if="i.reference.explanation" class="muted">{{ i.reference.explanation }}</div></template></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="showText" class="textcol"><header><span class="name">output</span> <span class="muted small">quotes highlighted by category</span></header>
          <div class="body raw" v-html="highlightOutput(o.output, score(o).details.highlights, prefix(o))"></div></div>
      </div>
    </template>
  </div>`,
};

const IdeasView = {
  props: ["data"],
  setup(props) {
    const onlyNotPresent = ref(true);
    const showText = ref(true);
    const outputs = computed(() => props.data.outputs.filter((o) => o.output !== null));
    const score = (o) => o.scores.find((s) => s.metric === "idea_coverage");
    const verdicts = (o) => (score(o)?.details.verdicts || []).filter((v) => !onlyNotPresent.value || v.verdict !== "present");
    const prefix = (o) => `idea-${o.key.replace(/[^\w-]/g, "_")}`;
    const highlights = (o) => (score(o)?.details.verdicts || [])
      .flatMap((v) => (v.quotes || []).map((q, k) => ({ ...q, v, k })))
      .filter((q) => q.found && q.start != null)
      .sort((a, b) => a.start - b.start)
      .map((q) => ({ id: `${q.v.id}-${q.k}`, start: q.start, end: q.end, cls: `claim v-${q.v.verdict}`,
                     title: `idea ${q.v.id} (${q.v.verdict}): ${q.v.idea}` }));
    const reveal = (o, v, k) => {
      const index = k ?? (v.quotes || []).findIndex((q) => q.found);
      const mark = index >= 0 && document.getElementById(`${prefix(o)}-${v.id}-${index}`);
      if (!mark) return;
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
      mark.classList.add("flash");
      setTimeout(() => mark.classList.remove("flash"), 1200);
    };
    const note = (v) => (!v.judge_verdict ? "no verdict from the judge"
      : v.judge_verdict === v.verdict ? ""
      : v.verdict === "absent" ? `judge: ${v.judge_verdict}, but no quote found in the output`
      : "judge: present, but not every element is present");
    const pct = (x) => (x != null ? (x * 100).toFixed(0) + " %" : "?");
    return { onlyNotPresent, showText, outputs, score, verdicts, prefix, highlights, reveal, note, pct, highlightOutput, ELEMENT_MARKS };
  },
  template: `
  <p class="small muted">Verdicts of the judge per output. <b>present</b> = all essential elements explicitly stated; <b>partial</b> = at least one essential element missing, only implied or distorted;
    <b>absent</b> = the idea is no longer recognizable. Click an idea (or a quote) to show its passage in the output. Quote ✗ = not found in the output (the judge may have invented it).</p>
  <div class="toolbar">
    <label><input type="checkbox" v-model="onlyNotPresent"> only ideas not present</label>
    <label><input type="checkbox" v-model="showText"> show the output with the quotes highlighted</label>
  </div>
  <div v-for="o in outputs" class="panel">
    <h3 style="margin-top:0">{{ o.model }} <span class="muted small">{{ o.prompt }} · r{{ o.repeat }}</span>
      <template v-if="score(o)"> – {{ (score(o).value * 100).toFixed(1) }} % ({{ score(o).details.ideas }} ideas)</template></h3>
    <div v-if="!score(o)" class="muted">Not judged.</div>
    <template v-else>
      <div style="margin-bottom:.5rem">
        <span class="verdict v-present" style="margin-right:.3rem">present: {{ score(o).details.present }} ({{ pct(score(o).details.present_rate) }})</span>
        <span class="verdict v-partial" style="margin-right:.3rem">partial: {{ score(o).details.partial }} ({{ pct(score(o).details.partial_rate) }})</span>
        <span class="verdict v-absent" style="margin-right:.3rem">absent: {{ score(o).details.absent }} ({{ pct(score(o).details.absent_rate) }})</span>
        <span v-if="score(o).details.elements" class="small muted">elements:
          <template v-for="(n, s) in score(o).details.elements"><span :class="'e-' + s">{{ ELEMENT_MARKS[s] }}</span> {{ s }} {{ n }}&nbsp; </template></span>
        <span v-if="score(o).details.missed_high" class="verdict v-absent">{{ score(o).details.missed_high }} high-importance idea(s) missed</span>
      </div>
      <div :style="{ display: 'grid', gridTemplateColumns: showText ? 'minmax(0, 3fr) minmax(0, 2fr)' : '1fr', gap: '.75rem', alignItems: 'start' }">
        <div class="tablewrap">
          <table class="ideas claims">
            <thead><tr><th>#</th><th class="l">verdict</th><th class="l">idea / what is missing</th><th class="l">essential elements</th><th class="l">quotes of the output</th></tr></thead>
            <tbody>
              <tr v-if="!verdicts(o).length"><td colspan="5" class="muted">Every idea is present.</td></tr>
              <tr v-for="v in verdicts(o)" class="clickable" @click="reveal(o, v)">
                <td>{{ v.id }}</td>
                <td class="l"><span class="verdict" :class="'v-' + v.verdict">{{ v.verdict }}</span>
                  <div class="small muted">{{ v.importance }}</div>
                  <div v-if="note(v)" class="small warning" style="margin:0">{{ note(v) }}</div></td>
                <td class="idea">{{ v.idea }}<div v-if="v.missing" class="small" style="margin-top:.25rem">{{ v.missing }}</div></td>
                <td class="idea small">
                  <div v-for="e in v.elements || []"><span :class="'e-' + e.status">{{ ELEMENT_MARKS[e.status] }}</span> {{ e.element }}
                    <span v-if="e.status !== 'present'" class="muted">({{ e.status }})</span></div>
                  <div class="muted" style="margin-top:.2rem">{{ v.elements_source === 'dataset' ? 'from edited_ideas.yaml' : 'broken down by the judge' }}</div></td>
                <td class="idea small">
                  <div v-for="(q, k) in v.quotes || []" class="quote" @click.stop="reveal(o, v, k)"><em>« {{ q.text }} »</em>
                    <span :title="q.found ? 'found in the output' : 'not found in the output'">{{ q.found ? '✓' : '✗' }}</span></div>
                  <span v-if="!(v.quotes || []).length" class="muted">no quote</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="showText" class="textcol"><header><span class="name">output</span> <span class="muted small">quotes highlighted by verdict</span></header>
          <div class="body raw" v-html="highlightOutput(o.output, highlights(o), prefix(o))"></div></div>
      </div>
    </template>
  </div>`,
};

const HebrewExpressionsView = {
  props: ["data"],
  setup(props) {
    const onlyProblems = ref(true);
    const showText = ref(true);
    const outputs = computed(() => props.data.outputs.filter((o) => o.output !== null));
    const score = (o) => o.scores.find((s) => s.metric === "hebrew_expression_format");
    const items = (o) => (score(o)?.details.items || []).map((item, index) => ({ ...item, index }))
      .filter((item) => !onlyProblems.value || !item.compliant);
    const prefix = (o) => `hebexpr-${o.key.replace(/[^\w-]/g, "_")}`;
    const verdictOf = (item, form) => (form === "full" ? "present" : item.compliant ? "present" : form === "no_translation" ? "partial" : "absent");
    const highlights = (o) => (score(o)?.details.items || [])
      .flatMap((item, index) => (item.spans || []).map((s, k) => ({ ...s, item, index, k })))
      .sort((a, b) => a.start - b.start)
      .map((s) => ({ id: `${s.index}-${s.k}`, start: s.start, end: s.end, cls: `claim v-${verdictOf(s.item, s.form)}`,
                     title: `${s.item.expression}: ${s.form === "full" ? "full form" : s.item.problem || "introduced in full form elsewhere"}` }));
    const reveal = (o, item) => {
      const mark = document.getElementById(`${prefix(o)}-${item.index}-0`);
      if (!mark) return;
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
      mark.classList.add("flash");
      setTimeout(() => mark.classList.remove("flash"), 1200);
    };
    const pct = (x) => (x != null ? (x * 100).toFixed(0) + " %" : "?");
    return { onlyProblems, showText, outputs, score, items, prefix, highlights, reveal, pct, highlightOutput };
  },
  template: `
  <p class="small muted">Rule 2: a Hebrew expression of several words is written at least once (normally at its first occurrence) as Hebrew + transliteration + translation,
    e.g. וְאָהַבְתָּ לְרֵעֲךָ כָּמוֹךָ (<em>Ve'ahavta lere'akha kamokha</em>, "tu aimeras ton prochain comme toi-même"), then transliteration only.
    Expressions are runs of words not in the French dictionary, italic transliterations and Hebrew script. Highlights: green = full form or compliant expression, orange = no translation, red = other problems. Click an expression to show its first occurrence.</p>
  <div class="toolbar">
    <label><input type="checkbox" v-model="onlyProblems"> only non-compliant expressions</label>
    <label><input type="checkbox" v-model="showText"> show the output with the expressions highlighted</label>
  </div>
  <div v-for="o in outputs" class="panel">
    <h3 style="margin-top:0">{{ o.model }} <span class="muted small">{{ o.prompt }} · r{{ o.repeat }}</span>
      <template v-if="score(o) && score(o).value != null"> – {{ (score(o).value * 100).toFixed(1) }} % ({{ score(o).details.compliant }} / {{ score(o).details.expressions }} expressions)</template></h3>
    <div v-if="!score(o)" class="muted">Not scored.</div>
    <div v-else-if="!score(o).details.expressions" class="muted">No Hebrew expression found.</div>
    <template v-else>
      <div style="margin-bottom:.5rem">
        <span class="verdict v-present" style="margin-right:.3rem">compliant: {{ score(o).details.compliant }}</span>
        <span class="verdict v-partial" style="margin-right:.3rem">no translation: {{ score(o).details.no_translation }}</span>
        <span class="verdict v-absent" style="margin-right:.3rem">no Hebrew: {{ score(o).details.no_hebrew }}</span>
        <span class="verdict v-absent" style="margin-right:.3rem">no transliteration: {{ score(o).details.no_transliteration }}</span>
        <span class="small muted">full form at the first occurrence: {{ pct(score(o).details.first_occurrence_rate) }}<template v-if="score(o).details.translation_after">
          · {{ score(o).details.translation_after }} translation(s) given just after the parenthesis</template></span>
      </div>
      <div :style="{ display: 'grid', gridTemplateColumns: showText ? 'minmax(0, 2fr) minmax(0, 3fr)' : '1fr', gap: '.75rem', alignItems: 'start' }">
        <div class="tablewrap">
          <table class="ideas claims">
            <thead><tr><th class="l">expression (first occurrence)</th><th class="l">status</th><th>occurrences</th><th title="full form at the first occurrence">first</th></tr></thead>
            <tbody>
              <tr v-if="!items(o).length"><td colspan="4" class="muted">Every expression complies.</td></tr>
              <tr v-for="item in items(o)" class="clickable" @click="reveal(o, item)">
                <td class="idea"><em>{{ item.expression }}</em></td>
                <td class="l"><span class="verdict" :class="item.compliant ? 'v-present' : item.problem === 'no translation' ? 'v-partial' : 'v-absent'">{{ item.compliant ? 'compliant' : item.problem }}</span></td>
                <td>{{ item.occurrences }}</td>
                <td>{{ item.first_occurrence ? '✓' : '✗' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="showText" class="textcol"><header><span class="name">output</span> <span class="muted small">expressions highlighted</span></header>
          <div class="body raw" v-html="highlightOutput(o.output, highlights(o), prefix(o))"></div></div>
      </div>
    </template>
  </div>`,
};

const RubricView = {
  props: ["data"],
  setup(props) {
    const outputs = computed(() => props.data.outputs.filter((o) => o.output !== null));
    const scoresOf = (o) => o.scores.filter((s) => s.metric === "judge_rubric");
    const rubrics = computed(() => {
      const byName = new Map();
      for (const o of outputs.value) for (const s of scoresOf(o)) {
        const name = s.details.rubric || "rubric";
        if (!byName.has(name)) byName.set(name, { name, version: s.details.rubric_version, scale: s.details.scale, criteria: s.details.criteria || [] });
      }
      return [...byName.values()];
    });
    const score = (o, rubric) => scoresOf(o).find((s) => (s.details.rubric || "rubric") === rubric.name);
    const cell = (o, rubric, cid) => score(o, rubric)?.details.criteria?.find((c) => c.criterion === cid) || null;
    const best = (rubric, cid) => {
      const values = outputs.value.map((o) => cell(o, rubric, cid)?.score).filter((v) => v != null);
      return values.length >= 2 ? Math.max(...values) : null;
    };
    const num = (v, digits = 1) => (v == null ? "–" : Number.isInteger(v) ? String(v) : v.toFixed(digits));
    return { outputs, rubrics, score, cell, best, num };
  },
  template: `
  <p class="small muted">Style grades of the LLM judge. Anchored criteria: score given by the judge after its justification; checklist criteria: score computed from the yes/no checks passed.
    The judge is warned against generous grades and against preferring longer texts: compare with <b>length ratio</b> (words of the output / words of the input).</p>
  <div v-for="rubric in rubrics" class="panel">
    <h3 style="margin-top:0">{{ rubric.name }} <span class="muted small">v{{ rubric.version }} · scale {{ rubric.scale?.join('–') }}</span></h3>
    <div class="tablewrap"><table class="ideas rubric">
      <thead><tr><th class="l">criterion</th>
        <th v-for="o in outputs" class="l">{{ o.model }}<div class="muted small">{{ o.prompt }} · r{{ o.repeat }}</div></th></tr></thead>
      <tbody>
        <tr class="total"><td class="l"><b>weighted grade</b></td>
          <td v-for="o in outputs"><b>{{ num(score(o, rubric)?.value, 2) }}</b>
            <span class="muted small"> · length ratio {{ num(score(o, rubric)?.details.length_ratio, 2) }} · {{ score(o, rubric)?.details.words ?? '–' }} words</span></td></tr>
        <tr v-for="c in rubric.criteria">
          <td class="idea"><b>{{ c.criterion }}</b> <span class="muted small">× {{ c.weight }} · {{ c.source === 'checks' ? 'checklist' : 'anchors' }}</span>
            <div class="small muted">{{ c.definition }}</div></td>
          <td v-for="o in outputs" class="cellv" :class="{ best: cell(o, rubric, c.criterion)?.score != null && cell(o, rubric, c.criterion)?.score === best(rubric, c.criterion) }">
            <template v-if="cell(o, rubric, c.criterion)">
              <span class="grade">{{ num(cell(o, rubric, c.criterion).score) }}</span>
              <div v-if="cell(o, rubric, c.criterion).justification" class="small">{{ cell(o, rubric, c.criterion).justification }}</div>
              <div v-for="k in cell(o, rubric, c.criterion).checks || []" class="small" :title="k.evidence || ''">
                <span :class="k.passed ? 'e-present' : 'e-missing'">{{ k.passed === null ? '?' : k.passed ? '✓' : '✗' }}</span> {{ k.question }}
                <em v-if="k.evidence && !k.passed" class="muted">« {{ k.evidence }} »</em></div>
            </template>
            <span v-else class="muted">not judged</span>
          </td>
        </tr>
      </tbody>
    </table></div>
  </div>`,
};

const LessonView = {
  components: { CorrectionSegments, HebrewSegments, SideBySide, IdeasMatrix, IdeasView, ClaimsView, HebrewExpressionsView, RubricView, ScoresTable },
  setup() {
    const state = reactive({ data: null, error: null, loading: false, tab: null });
    const selected = computed(() => (route.query.m ? route.query.m.split(",").filter(Boolean) : null));
    const load = () => {
      state.error = null; state.loading = true;
      const params = new URLSearchParams();
      const keys = selected.value || storedSelection(route.params.c, route.params.s);
      if (keys && keys.length) params.set("candidates", keys.join(","));
      if (route.query.r !== undefined && route.query.r !== "") params.set("repeat", route.query.r);
      api(`/campaigns/${enc(route.params.c)}/steps/${enc(route.params.s)}/lessons/${enc(route.params.l)}?${params}`)
        .then((d) => {
          state.data = d;
          const tabs = tabsOf(d).map((t) => t.id);
          if (!tabs.includes(state.tab)) state.tab = tabs[0];
        })
        .catch((e) => (state.error = e.message))
        .finally(() => (state.loading = false));
    };
    watch(() => [route.params.c, route.params.s, route.params.l, route.query.m, route.query.r], load, { immediate: true });

    const tabsOf = (d) => {
      const has = (metric) => d.outputs.some((o) => o.scores.some((s) => s.metric === metric)) || d.columns.some((c) => c.metric === metric);
      if (d.task === "correction") return [{ id: "segments", label: "Segments" }, { id: "texts", label: "Full texts" }, { id: "scores", label: "Scores" }];
      const tabs = [{ id: "texts", label: "Gold vs outputs" }];
      if (d.ideas?.length && has("idea_coverage")) {
        tabs.push({ id: "ideas", label: "Ideas (matrix)" }, { id: "idea_details", label: "Ideas (details)" });
      }
      if (has("faithfulness")) tabs.push({ id: "claims", label: "Claims" });
      if (has("hebrew_expression_format")) tabs.push({ id: "hebrew", label: "Hebrew expressions" });
      if (has("judge_rubric")) tabs.push({ id: "rubric", label: "Style" });
      tabs.push({ id: "scores", label: "Scores" });
      return tabs;
    };
    const tabs = computed(() => (state.data ? tabsOf(state.data) : []));
    const navigate = (changes) => {
      const query = { m: route.query.m, r: route.query.r, ...(changes.query || {}) };
      go({ c: route.params.c, s: route.params.s, l: changes.lesson || route.params.l }, query);
    };
    const toggle = (key) => {
      const current = state.data.selected;
      const next = current.includes(key) ? current.filter((k) => k !== key) : [...state.data.candidates.map((c) => c.key).filter((k) => current.includes(k) || k === key)];
      storeSelection(route.params.c, route.params.s, next);
      navigate({ query: { m: next.join(",") } });
    };
    const shift = (delta) => {
      const lessons = state.data.lessons;
      const index = lessons.indexOf(state.data.lesson);
      navigate({ lesson: lessons[(index + delta + lessons.length) % lessons.length] });
    };
    return { state, tabs, navigate, toggle, shift, route, go, load };
  },
  template: `
  <div v-if="state.error" class="error">{{ state.error }}</div>
  <div v-else-if="!state.data" class="loading">Loading lesson…</div>
  <template v-else>
    <div class="toolbar">
      <h1 style="margin:0">{{ state.data.lesson }}</h1>
      <span class="muted">{{ state.data.step }} ({{ state.data.task }})</span>
      <button @click="shift(-1)" title="previous lesson">‹</button>
      <select :value="state.data.lesson" @change="navigate({ lesson: $event.target.value })">
        <option v-for="l in state.data.lessons" :value="l">{{ l }}</option>
      </select>
      <button @click="shift(1)" title="next lesson">›</button>
      <label v-if="state.data.repeats.length > 1">repeat
        <select :value="route.query.r ?? ''" @change="navigate({ query: { r: $event.target.value } })">
          <option value="">first OK</option><option v-for="r in state.data.repeats" :value="r">r{{ r }}</option>
        </select></label>
      <span v-if="state.loading" class="muted small">loading…</span>
    </div>
    <div class="toolbar">
      <span class="muted small">models</span>
      <div class="chips"><span v-for="c in state.data.candidates" class="chip" :class="{ on: state.data.selected.includes(c.key) }" @click="toggle(c.key)">{{ c.model }}<span v-if="new Set(state.data.candidates.map(x => x.prompt)).size > 1"> / {{ c.prompt }}</span></span></div>
    </div>
    <div v-if="state.data.meta" class="muted small" style="margin-bottom:.6rem">
      <template v-for="k in ['lesson', 'speaker', 'topic', 'audio_quality']"><span v-if="state.data.meta[k]" class="tag">{{ k }}: {{ state.data.meta[k] }}</span></template>
    </div>
    <nav class="tabs" role="tablist"><a v-for="t in tabs" role="tab" tabindex="0" :class="{ on: state.tab === t.id }" @click="state.tab = t.id" @keydown.enter="state.tab = t.id">{{ t.label }}</a></nav>
    <HebrewSegments v-if="state.tab === 'segments' && state.data.segment_view === 'hebrew'" :data="state.data" @changed="load" />
    <CorrectionSegments v-else-if="state.tab === 'segments'" :data="state.data" @changed="load" />
    <SideBySide v-else-if="state.tab === 'texts'" :data="state.data" />
    <IdeasMatrix v-else-if="state.tab === 'ideas'" :data="state.data" />
    <IdeasView v-else-if="state.tab === 'idea_details'" :data="state.data" />
    <ClaimsView v-else-if="state.tab === 'claims'" :data="state.data" />
    <HebrewExpressionsView v-else-if="state.tab === 'hebrew'" :data="state.data" />
    <RubricView v-else-if="state.tab === 'rubric'" :data="state.data" />
    <ScoresTable v-else-if="state.tab === 'scores'" :data="state.data" />
  </template>`,
};

// --------------------------------------------------------------------------- //
// App shell
// --------------------------------------------------------------------------- //

const App = {
  components: { CampaignList, CampaignDashboard, StepView, LessonView },
  setup() {
    const campaigns = ref([]);
    api("/campaigns").then((c) => (campaigns.value = c)).catch(() => {});
    const steps = computed(() => campaigns.value.find((c) => c.stem === route.params.c)?.steps || []);
    return { route, go, campaigns, steps };
  },
  template: `
  <header class="top">
    <a class="brand" @click="go({})">Bench review</a>
    <div class="crumbs">
      <select :value="route.params.c || ''" @change="go({ c: $event.target.value })">
        <option value="" disabled>Select a campaign…</option>
        <option v-for="c in campaigns" :value="c.stem">{{ c.name }} ({{ c.stem }})</option>
      </select>
      <template v-if="route.params.c">
        <span class="sep">›</span><a @click="go({ c: route.params.c })">dashboard</a>
        <template v-for="s in steps"><span class="sep">·</span>
          <a @click="go({ c: route.params.c, s: s.name })" :style="{ fontWeight: route.params.s === s.name ? 700 : 400 }">{{ s.name }}</a></template>
      </template>
      <template v-if="route.params.l"><span class="sep">›</span><span>{{ route.params.l }}</span></template>
    </div>
  </header>
  <main>
    <CampaignList v-if="route.name === 'list'" />
    <CampaignDashboard v-else-if="route.name === 'campaign'" />
    <StepView v-else-if="route.name === 'step'" />
    <LessonView v-else-if="route.name === 'lesson'" />
  </main>`,
};

createApp(App).mount("#app");
