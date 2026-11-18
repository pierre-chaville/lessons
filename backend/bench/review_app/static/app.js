import { createApp, reactive, computed, watch, ref } from "/vendor/vue.js";
import { marked } from "/vendor/marked.js";

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //

async function api(path) {
  const response = await fetch(`/api${path}`);
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

const SummaryTable = {
  props: ["step", "selectable", "selected"],
  emits: ["toggle"],
  setup(props) {
    const best = computed(() => bestValues(props.step.columns, props.step.rows.map((r) => r.cells.map((c) => c.value))));
    return { best, fmt, usd, arrow, title };
  },
  template: `
  <div class="scroll"><table>
    <thead><tr>
      <th v-if="selectable"></th><th class="l">model</th><th class="l">prompt</th>
      <th v-for="c in step.columns" :title="title(c) + (c.judge ? ' – LLM judge' : '')">{{ c.label }}{{ c.percent ? ' %' : '' }}{{ arrow(c) }}</th>
      <th>calls ok</th><th>lessons</th><th>USD / call</th><th>s / call</th><th>total USD</th><th>judge USD</th>
    </tr></thead>
    <tbody>
      <tr v-for="row in step.rows" :key="row.key">
        <td v-if="selectable"><input type="checkbox" :checked="selected.includes(row.key)" @change="$emit('toggle', row.key)"></td>
        <td class="l">{{ row.model }}</td><td class="l">{{ row.prompt }}</td>
        <td v-for="(cell, i) in row.cells" :class="{ best: cell.value !== null && cell.value === best[i] }">
          {{ fmt(cell.value, step.columns[i]) }}<span v-if="cell.spread !== null" class="spread">± {{ fmt(cell.spread, step.columns[i]) }}</span>
        </td>
        <td>{{ row.calls_ok }}/{{ row.calls }}</td><td>{{ row.lessons }}</td>
        <td>{{ usd(row.cost_per_call) }}</td><td>{{ row.latency === null ? '–' : row.latency.toFixed(1) }}</td>
        <td>{{ usd(row.cost) }}</td><td>{{ row.judge_cost ? usd(row.judge_cost) : '–' }}</td>
      </tr>
      <tr v-if="step.baseline" class="baseline">
        <td v-if="selectable"></td><td class="l">{{ step.baseline.label }}</td><td></td>
        <td v-for="(cell, i) in step.baseline.cells">{{ fmt(cell.value, step.columns[i]) }}</td>
        <td colspan="6"></td>
      </tr>
    </tbody>
  </table></div>
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

const CorrectionSegments = {
  props: ["data"],
  setup(props) {
    const onlyDiff = ref(true);
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
    return { onlyDiff, rows, outputs, counts, total };
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
        <td class="gold">{{ r.gold }}</td>
        <td v-for="o in outputs" :class="o.output === null ? 'na' : (r.cells[o.key]?.severity ? 'sev-' + r.cells[o.key].severity : '')">
          <template v-if="o.output !== null && r.cells[o.key]?.severity"><span v-html="r.cells[o.key].html"></span></template>
        </td>
      </tr>
    </tbody>
  </table></div>
  <p class="small muted">Model cells: empty = same words as corrected.md; grey = no output.</p>`,
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

const IdeasMatrix = {
  props: ["data"],
  setup(props) {
    const outputs = computed(() => props.data.outputs.filter((o) => o.output !== null));
    const verdict = (o, id) => {
      const score = o.scores.find((s) => s.metric === "idea_coverage");
      return score?.details?.verdicts?.find((v) => v.id === id) || null;
    };
    const coverage = (o) => o.scores.find((s) => s.metric === "idea_coverage")?.value;
    return { outputs, verdict, coverage };
  },
  template: `
  <p class="small muted">Verdicts of the judge (hover a verdict for the quote of the output). A present / partial verdict whose quote is not found in the output is counted as absent.</p>
  <div class="tablewrap"><table class="ideas">
    <thead><tr><th>#</th><th class="l">idea</th><th class="l">importance</th>
      <th v-for="o in outputs">{{ o.model }}<div class="muted small">{{ coverage(o) != null ? (coverage(o) * 100).toFixed(1) + ' %' : 'not judged' }}</div></th></tr></thead>
    <tbody>
      <tr v-for="idea in data.ideas">
        <td>{{ idea.id }}</td><td class="idea">{{ idea.text }}</td><td class="l">{{ idea.importance }}</td>
        <td v-for="o in outputs">
          <span v-if="verdict(o, idea.id)" class="verdict" :class="'v-' + verdict(o, idea.id).verdict" :title="verdict(o, idea.id).quote">{{ verdict(o, idea.id).verdict }}</span>
          <span v-else class="muted">–</span>
        </td>
      </tr>
    </tbody>
  </table></div>`,
};

const ClaimsView = {
  props: ["data"],
  setup(props) {
    const outputs = computed(() => props.data.outputs.filter((o) => o.output !== null));
    const score = (o) => o.scores.find((s) => s.metric === "faithfulness");
    const KINDS = ["supported", "contradicted", "misattribution", "extrapolation", "external_addition", "unverified", "missing"];
    return { outputs, score, KINDS };
  },
  template: `
  <p class="small muted">Claims of each output checked against the lesson ({{ data.input_file }}). Only the claims that are not supported are listed; "unverified" = said supported, but the quote is not in the source.</p>
  <div v-for="o in outputs" class="panel">
    <h3 style="margin-top:0">{{ o.model }} <span class="muted small">{{ o.prompt }} · r{{ o.repeat }}</span>
      <template v-if="score(o)"> – {{ (score(o).value * 100).toFixed(1) }} % supported ({{ score(o).details.claims }} claims)</template></h3>
    <div v-if="!score(o)" class="muted">Not judged.</div>
    <template v-else>
      <div><span v-for="k in KINDS" v-show="score(o).details[k]" class="verdict" :class="'v-' + k" style="margin-right:.3rem">{{ k }}: {{ score(o).details[k] }}</span></div>
      <table class="ideas" style="margin-top:.6rem" v-if="score(o).details.issues?.length">
        <thead><tr><th class="l">verdict</th><th class="l">claim</th><th class="l">quote of the source</th></tr></thead>
        <tbody><tr v-for="i in score(o).details.issues"><td class="l"><span class="verdict" :class="'v-' + i.verdict">{{ i.verdict }}</span></td>
          <td class="idea">{{ i.claim }}</td><td class="idea muted"><em>{{ i.quote }}</em></td></tr></tbody>
      </table>
    </template>
  </div>`,
};

const LessonView = {
  components: { CorrectionSegments, SideBySide, IdeasMatrix, ClaimsView, ScoresTable },
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
      if (d.ideas?.length && has("idea_coverage")) tabs.push({ id: "ideas", label: "Ideas" });
      if (has("faithfulness")) tabs.push({ id: "claims", label: "Claims" });
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
    return { state, tabs, navigate, toggle, shift, route, go };
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
    <CorrectionSegments v-if="state.tab === 'segments'" :data="state.data" />
    <SideBySide v-else-if="state.tab === 'texts'" :data="state.data" />
    <IdeasMatrix v-else-if="state.tab === 'ideas'" :data="state.data" />
    <ClaimsView v-else-if="state.tab === 'claims'" :data="state.data" />
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
