# BENCH – evaluating the quality of the lesson workflow steps

## Context

Several steps of the lesson workflow rely on LLMs: transcript correction, edited version and summary.
The "right" output is partly subjective and LLM calls are non-deterministic, so choosing a model or
a prompt by eye is unreliable. This bench runs these steps **locally** (never on Render) on a fixed
sample of annotated lessons, for several models and prompt versions, and compares the outputs with
deterministic metrics, an LLM judge and blind human review.

Typical questions it answers:
- Is model A better than model B on a given step, and is the difference larger than the noise?
- Did prompt V2 improve on V1?
- What does each option cost (USD, latency) for the quality it gives?

## Folder structure

```
backend/bench/
  README.md
  configs/                 # one YAML file per campaign
  data/
    extracts/<lesson_id>/  # 10-15 min extracts  -> correction, edition
    full/<lesson_id>/      # full lessons (1h-1h30) -> summary
  prompts/<step>/          # prompt versions, e.g. prompts/correction/standard_V1.md
  rubrics/                 # grading rubrics for the LLM judge
  metrics/                 # one module per metric
  dataset.py               # loading + validation of the lesson folders
  db.py                    # SQLite storage (results/bench.sqlite)
  steps.py                 # adapters between the bench and the app code
  run.py                   # validation, generation with cache, budget (+ scoring + report)
  score.py                 # metrics computation
  report.py                # HTML report
  review_app/              # local FastAPI + Vue.js UI
  results/                 # SQLite database + HTML reports (git-ignored)
```

`data/`, `prompts/`, `rubrics/` and `configs/` are versioned in git; `results/` is not.

## Datasets

Each lesson is stored in its own sub-folder of `data/extracts` (extract of 10 to 15 min) or
`data/full` (full lesson of 1h to 1h30). **The folder name is the lesson id** used everywhere
(database, reports, UI), e.g. `Midrash.Lekh_Lekha.44-22`.

Extracts are enough for correction and edition; the summary needs full lessons, because the main
idea of a lesson is built over its whole length.

### Files of a lesson folder

| File | Role | Needed in |
|---|---|---|
| `meta.yaml` | Metadata: source lesson, speaker, topic, start/end in the audio, audio quality, notes | all |
| `initial.md` | Raw transcript = **input** of the correction step | extracts (and full, optional) |
| `corrected.md` | Hand-corrected transcript = **gold** of the correction, and **input** of edition and summary in `gold` mode | all |
| `edited.md` | Reference edited version, used in A/B comparison | extracts |
| `edited_ideas.yaml` | Ideas expected in the edited version (for `idea_coverage`) | extracts |
| `summary.md` | Reference summary, used in A/B comparison | full |
| `summary_keypoints.yaml` | Key points expected in the summary (for `keypoint_coverage`) | full |

Transcript format (`initial.md`, `corrected.md`): one line per segment, `- [start - end] text`, e.g.

```
- [6s - 8s] le texte, on l'a fini, je pense, mais
```

`meta.yaml` example:

```yaml
lesson: Midrash 44-22
lesson_id: RtFRdTY
speaker: X
course: Midrash
duration: "01:12:30"
audio_quality: good        # good | medium | poor
notes: "many Hebrew quotations"
```

`edited_ideas.yaml` / `summary_keypoints.yaml` format:

```yaml
- id: 1
  text: "The Name of Hashem does not appear in the Megila: Providence acts in a hidden way"
  importance: high          # high | medium | low  (weights 3 / 2 / 1)
- id: 2
  text: "..."
  importance: medium
```

### Annotation guidelines

- **corrected.md**: keep exactly the same segments and timestamps as `initial.md`; fix recognition
  errors (words, names, Hebrew terms, punctuation), never rephrase. Plain text, no markdown
  formatting (bold, titles), otherwise WER counts it as errors.
- **edited_ideas.yaml**: one atomic, self-contained, checkable idea per entry, coming from the speaker
  (not from general knowledge). Typically 10 to 25 ideas per extract.
- **summary_keypoints.yaml**: only what a good summary must contain, 5 to 10 points per lesson.
- To save time, ideas and key points can be drafted by an LLM and then reviewed by hand. Use a model
  that is **not** among the compared candidates, otherwise the gold inherits its wording and favours it.
- Any change to the gold files requires bumping `dataset_version` in the campaign.

### Adding a lesson

1. Create `data/extracts/<lesson_id>/` (or `data/full/`).
2. Add `meta.yaml` and `initial.md`, then `corrected.md`.
3. Add the step-specific gold files (see table above).
4. Add the lesson to the `dataset` of the campaign(s) and bump `dataset_version`.
5. Run `python -m bench.run <config> --check` to validate the folder (missing files, format errors).

## Steps

The steps evaluated are part of the app workflow:

| Step | Dataset | Input (`gold` mode) | References | Metrics |
|---|---|---|---|---|
| `correction` | extracts | `initial.md` | `corrected.md` | wer, cer, edit_precision_recall, overcorrection_rate |
| `edition` | extracts | `corrected.md` | `edited_ideas.yaml`, `edited.md` | idea_coverage, faithfulness, length_ratio, hebrew_quotes_preserved, judge_rubric, judge_pairwise |
| `summary` | full | `corrected.md` | `summary_keypoints.yaml`, `summary.md` | keypoint_coverage, faithfulness, length_words, judge_pairwise |

### Calling the app code

Steps run **the same code as the app**. `steps.py` contains thin adapters that call the app
functions while injecting the model and the prompt of the campaign. Every adapter follows the same
contract:

```python
def correction(text: str, *, item: LessonItem, provider: str, model: str, prompt: str, params: dict,
               timeout: float) -> dict:
    # returns {"output": str | dict, "tokens_in": int, "tokens_out": int, "cost_usd": float | None, "meta": dict}
```

- `params` = model params of the campaign + step-specific params; unknown keys are rejected.
- `timeout` applies to each LLM call.
- `cost_usd` is `None` when the provider does not report it (the runner computes it from `price`).
- `meta` holds step diagnostics stored with the generation.
- An adapter raises `StepError` when the generation must be recorded as failed (LLM error, timeout,
  truncated output). App functions often fall back to their input on error; the adapters wrap the
  LLM to detect it, so that a fallback is never scored as a real output.

The app calls LLMs through LangChain (`services.llm_utils.get_llm_model`), so candidate models are
limited to the providers it supports: `openai`, `anthropic` and `openrouter` (any model available
on OpenRouter, e.g. Gemini).

`correction` runs `services.correction.correct_segment_group` with the app grouping. Step params:
`segments_per_group` (default 10), `max_concurrency` (default 10), `glossary` (default `false`:
apply the glossary of the app DB after the LLM; its content is not in the cache key, so bump the
step `version` when it changes). `meta`: number of LLM calls, segments changed,
`unparsed_output_lines` (lines of the model output that the app parser ignored) and glossary
replacements.

By convention, step `correction` calls `steps.correction`. A step can override this with
`function:` (e.g. to point directly to an app function) and declare a `version:` that must be bumped
whenever the code of the step changes (see Cache).

To compare two **implementations** of the same step (e.g. one-shot vs chunked correction), declare
two steps with different names and the same `task:` – they share the dataset, input and metrics:

```yaml
correction_chunked:
  task: correction
  function: steps.correction_chunked
```

### Input source

- `raw`: the step starts from `initial.md` (correction).
- `gold` (default): the step starts from the hand-corrected `corrected.md`. Each step is then
  evaluated **independently**, without errors propagating from the previous step.
- `pipeline`: the step starts from the output of the previous step of the campaign, or of the
  step named in `from_step:` (same lesson and model, first prompt, first repeat). Used for
  end-to-end evaluation, after the step-by-step evaluation. Steps run in campaign order; a call
  whose input was not generated (failed call) is skipped.

Step-specific parameters (e.g. `segments_per_group` for correction) go in the step `params:`;
they are merged over the model `params`.

## Campaigns

A campaign is a YAML file in `configs/` defining:
- the dataset (list of lesson folders) and its version;
- the candidate models (short alias → model id + provider + parameters + price);
- for each step: prompts, models, input source, repeats and metrics;
- the judge (model + provider + parameters), the cost budget and the report options.

`provider` is one of the providers of the app: `openai`, `anthropic` or `openrouter`. The model id
is sent as is to that provider: `gpt-5.4` with `openai`, `openai/gpt-5.4` with `openrouter`.

```yaml
models:
  gpt-5.4:
    id: openai/gpt-5.4
    provider: openrouter
    params: { temperature: 0.2, max_tokens: 8000 }
    price: [2.5, 15]
```

Each model must have a unique alias, and steps, baselines and pairwise comparisons always refer
to **aliases**.

One campaign = one file, kept in git (e.g. `campaign-2026-11_models.yaml`,
`campaign-2026-12_summary_prompts.yaml`), so that every result can be traced back to its exact
configuration.

## Prompts

Prompts are stored in `prompts/<step>/<name>_V<n>.md`. A campaign can test several prompts for the
same step. Never edit a prompt that has already been used in a campaign: create a new version.
(The cache relies on the prompt content, so an edited prompt is re-run anyway, but the history
becomes unreadable.)

## Metrics

### Deterministic metrics

- **wer** – word error rate between the model output and `corrected.md`. Texts are normalized first
  (timestamps removed, lowercase, punctuation and apostrophes normalized, whitespace collapsed).
  Computed on the whole extract, and also per segment when the output keeps the same segments
  (timestamps are used for the alignment). Aggregated as total errors / total words, not as a mean
  of segment WERs.
- **cer** – same at character level (less sensitive to word splitting, useful for Hebrew terms).
- **edit_precision_recall** – compares the edits made by the model (word diff `initial → output`)
  with the expected edits (diff `initial → corrected`). Precision = share of the model edits that are
  correct; recall = share of the expected edits made by the model; F1.
- **overcorrection_rate** – share of words that were already correct (unchanged between `initial`
  and `corrected`) but modified by the model.

Details of the correction metrics (`metrics/wer.py`, `cer.py`, `edit_precision_recall.py`,
`overcorrection_rate.py`):
- Normalization: speaker tags (`[audience]`) removed, lowercase, apostrophes unified, punctuation
  removed; apostrophes and hyphens inside words are kept (`l'a`, `ha-Nahar`, `'Hazal`), Hebrew
  keeps its vowel points. Option `strict: true` compares raw words (case and punctuation count).
- An **edit** is a maximal run of changed words in the word diff; a model edit is correct only if
  the gold has the same edit (same words replaced by the same words). F1 = 2 × correct /
  (model edits + expected edits); precision / recall are `None` when there is no model / expected
  edit. Words inserted by the model lower the edit precision but not the overcorrection rate.
- The diffs are done segment by segment when the transcripts keep the same timestamps, otherwise
  on the whole text (`segment_aligned` in the details).
- Each result has a `value` and `details` (error counts, worst segments, missed / wrong edits...).

Tests: `python -m pytest bench/tests` (hand-made examples with known results).
- **length_ratio** – number of words of the output / number of words of the input, checked against
  a `[min, max]` range.
- **length_words** – number of words of the output versus a `target` with a `tolerance`.
- **hebrew_quotes_preserved** – share of the Hebrew quotations of the input (Hebrew-script spans and
  transliterated terms from the glossary) found in the output (fuzzy match).
- **format_valid** – the output respects the expected format (segments/timestamps for correction).

### LLM-based metrics

The judge is an LLM, configured in the campaign (`judge`). Rules: temperature 0, structured JSON
output, a model from a different family than the candidates when possible.

- **idea_coverage** (edition) – for each idea of `edited_ideas.yaml`, the judge answers
  `present` / `partial` / `absent` and must quote the passage of the output that contains it.
  Score = Σ(weight × value) / Σ(weight), with present = 1, partial = 0.5, absent = 0 and weights
  high = 3, medium = 2, low = 1. Missed high-importance ideas are also reported.
- **keypoint_coverage** (summary) – same principle with `summary_keypoints.yaml`.
- **faithfulness** (edition, summary) – checks that what is written comes from the lesson:
  1. the judge splits the output into atomic claims (always the same judge model, so that all
     candidates are split the same way);
  2. each claim is checked against the step input (`corrected.md`), with a quote as evidence:
     `supported`, `external_addition` (possibly true but not said in the lesson), `extrapolation`,
     `misattribution` (e.g. Rashi instead of Ramban), `contradicted`.

  Score = supported claims / total claims. The numbers of `contradicted` and `misattribution` are
  reported separately, as they are the most serious errors.
- **judge_rubric** – the judge grades the output from 1 to 5 on each criterion of a rubric file
  (`rubrics/*.yaml`: clarity, structure, register, respect of the speaker's voice...), with a short
  justification per criterion.
- **judge_pairwise** – the judge compares two outputs of the same lesson (candidate vs `baseline`
  model, and optionally vs the reference `edited.md` / `summary.md`) and returns A, B or tie. Each
  pair is judged in both orders (`swap_order`) to cancel the position bias. Results are aggregated
  as win rates and a Bradley-Terry ranking.

**Evidence check**: every quote given by the judge (`present`, `supported`) is verified by code
(fuzzy match) against the text it refers to. A verdict whose evidence cannot be found is rejected.

**Judge calibration**: `data/human_labels_v1.jsonl` contains ~50 judgments made by hand (coverage,
claims, pairwise). The agreement between the judge and the human labels is computed and reported;
below ~80 % the rubric or the definitions must be clarified before trusting the judge.

### Cost and operational metrics

For every call: input/output tokens, cost (USD), latency, errors (timeouts, invalid output,
truncation).

## Repeats

LLM outputs vary between two identical calls, even at temperature 0. `repeats` (campaign default or
per step) runs each combination several times in order to:
- check that a difference between models is larger than the variation of a model with itself;
- measure the stability of each model (a stable model is preferable at equal mean score);
- detect intermittent failures (invalid output, truncation, invented content).

Scores are averaged over repeats, then over lessons; the spread between repeats is reported as the
instability. Start with 2 repeats; switch to 1 for steps that prove stable. With a fixed budget,
more lessons is usually better than more repeats.

## Cache

Every call is identified by a key: lesson id + step + function + step `version` + provider + model id +
parameters + **prompt content** + **input content** + repeat index. A call whose key already has a
successful result in the database is never re-run; failed calls are retried at the next launch.

Consequences:
- adding a model or a prompt to a campaign only runs the new combinations;
- an interrupted campaign resumes where it stopped;
- metrics can be added or fixed and re-computed on existing outputs without any new LLM call;
- **changing the code of a step does not invalidate the cache by itself: bump its `version`.**

## Runs and database

A run is one launch of a campaign. Everything is stored in `results/bench.sqlite` (SQLite in WAL
mode, so that the review UI can stay open during a run):

| Table | Content |
|---|---|
| `runs` | one row per launch: campaign, config hash, dataset version, git commit, date |
| `generations` | one row per LLM call of a step: lesson, step, model, prompt, repeat, output, tokens, cost, latency, error |
| `scores` | one row per (generation, metric): value + details (JSON) + judge model |
| `human_votes` | blind A/B votes and comments from the review UI |

For analysis, DuckDB can read the SQLite file directly (`ATTACH 'bench.sqlite' (TYPE sqlite)`).

## Usage

Run from `backend/` so that the app modules can be imported:

```bash
cd backend
pip install -r bench/requirements.txt                                      # bench-only dependencies
python -m bench.run bench/configs/campaign-2026-11_models.yaml --check     # validate config + dataset
python -m bench.run bench/configs/campaign-2026-11_models.yaml --dry-run   # number of calls + estimated cost
python -m bench.run bench/configs/campaign-2026-11_models.yaml --limit 1   # quick test on 1 lesson
python -m bench.run bench/configs/campaign-2026-11_models.yaml             # generation + scoring + report
python -m bench.run bench/configs/... --only score                         # re-compute metrics only
python -m bench.run bench/configs/... --steps edition --models gpt-5.4     # subset
python -m bench.review_app                                                 # local UI
```

A launch runs **generate → score → report**. Scoring computes the metrics of each step on the
successful generations of the campaign (cached ones included) and stores them in `scores`;
deterministic metrics are always re-computed (cheap), metrics not implemented yet are skipped.
`--only generate|score|report` runs a single phase.

Other options: `--workers N` (parallel calls, default `defaults.workers` or 1), `--yes` (no
confirmation), `--verbose` (show the logs of the app code). Each call is retried
`defaults.max_retries` times within a run (except non-retryable errors such as a truncated output),
then recorded as failed and retried at the next launch.

API keys are read from `backend/.env` (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`...).
Set `LITELLM_LOCAL_MODEL_COST_MAP=True` to prevent LiteLLM from downloading its price table.

## Budget

Each model declares its price (`price: {input_per_mtok, output_per_mtok}`). Before running, the
estimated cost of the calls that are not cached is displayed; the run does not start if it exceeds
`budget.max_usd`, and asks for confirmation if `budget.dry_run_estimate` is true. During the run, no
new call is started once the actual cost of the run + the estimate of the running calls and of the
next call would exceed `budget.max_usd` (the run is then marked `budget_exceeded`). The budget
applies per run; tokens of failed calls are counted when the adapter reports them.

Token estimates are rough (~3.5 characters per token, see `estimate_<step>` in `steps.py`) and do
not include the reasoning tokens of thinking models: compare with the actual cost of a first
`--limit 1` run. Judge calls count
too: for edition and summary they cost about as much as the generation itself (the judge reads the
whole input for faithfulness).

## Reports

At the end of a run, an HTML report is generated (`report.export`, default
`results/report_<campaign>.html`). Currently implemented (minimal version): one table per step,
one row per model × prompt, with for each metric the mean over lessons of the mean over repeats
± the spread between repeats, the best value per column highlighted, calls OK / planned, cost and
latency per call, the list of calls without output, and for correction an "input, unchanged" row
(scores of the raw transcript, i.e. the level to beat).

For correction steps, a second report `<report>_<step>_errors.html` (linked from the main one)
lists, per lesson (chosen in a dropdown), the segments where the initial transcript or a model differs from
`corrected.md`: timestamps, initial, corrected, then one column per model (first successful
repeat), empty when the model matches the gold, red with the differing words highlighted
otherwise. Comparison ignores punctuation and spacing; case counts unless
`report.correction_errors.case_sensitive: false`.

Planned:
- matrix model × step: mean score with confidence interval (bootstrap), cost per lesson, latency;
- coverage vs faithfulness chart for edition and summary;
- per-lesson details and the lessons where a candidate is worse than the baseline;
- judge calibration (agreement with the human labels).

The local review UI (FastAPI + Vue.js) is used to investigate the details:
- **dashboard** of runs and scores;
- **lesson explorer**: input, gold and outputs side by side, diff view for correction, missed ideas
  and unsupported claims highlighted;
- **blind review**: two anonymized outputs in random order, A / B / tie (keyboard shortcuts);
- **judge calibration**: human votes vs judge verdicts, with the disagreements to review.
