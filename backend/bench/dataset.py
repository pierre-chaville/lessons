"""Bench datasets: loading, parsing and validation of the lesson folders (see README "Datasets")."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

BENCH_DIR = Path(__file__).resolve().parent

DATASET_KINDS = ("extracts", "full")

REQUIRED_FILES = {
    "extracts": ("meta.yaml", "initial.md", "corrected.md", "edited.md", "edited_ideas.yaml"),
    "full": ("meta.yaml", "corrected.md", "edited.md", "summary.md", "summary_keypoints.yaml"),
}
OPTIONAL_FILES = {
    "extracts": (),
    "full": ("initial.md",),
}

TASK_DATASET = {"correction": "extracts", "edition": "extracts", "summary": "full"}
# Files a task needs (input and references), besides meta.yaml.
TASK_FILES = {
    "correction": ("initial.md", "corrected.md"),
    "edition": ("corrected.md", "edited.md", "edited_ideas.yaml"),
    "summary": ("corrected.md", "edited.md", "summary.md", "summary_keypoints.yaml"),
}


def required_files(kind: str, tasks: Optional[set[str]] = None) -> tuple[str, ...]:
    """Files required in a `kind` lesson: all of REQUIRED_FILES, or only those of `tasks`."""
    if tasks is None:
        return REQUIRED_FILES[kind]
    needed = {"meta.yaml"} | {f for t in tasks if TASK_DATASET.get(t) == kind for f in TASK_FILES[t]}
    return tuple(f for f in (*REQUIRED_FILES[kind], *OPTIONAL_FILES[kind]) if f in needed)

IMPORTANCE_WEIGHTS = {"high": 3, "medium": 2, "low": 1}
AUDIO_QUALITIES = {"good", "medium", "poor"}

# Recommended number of entries (see README annotation guidelines)
IDEAS_RANGE = (10, 25)
KEYPOINTS_RANGE = (8, 22)  # prompts/summary_keypoints: 8-12 high + medium, 6-10 low

MAX_REPORTED_LINES = 5

_SEGMENT_RE = re.compile(r"^- \[(?P<start>[^\]]*?) - (?P<end>[^\]]*?)\](?: (?P<text>.*))?$")
_DURATION_RE = re.compile(r"^(?:(?P<h>\d+)h)? ?(?:(?P<m>\d+)m)? ?(?:(?P<s>\d+)s)?$")
_CITE_RE = re.compile(r"\[cite:[^\]]*\]")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class Segment:
    start: int  # seconds
    end: int
    text: str
    line: int  # 1-based line number in the source file


@dataclass
class Issue:
    level: str  # "error" | "warning"
    message: str
    file: Optional[str] = None
    line: Optional[int] = None

    def format(self) -> str:
        location = ""
        if self.file:
            location = self.file + (f":{self.line}" if self.line else "") + ": "
        return f"{self.level.upper():7} {location}{self.message}"


@dataclass
class LessonItem:
    id: str
    kind: str  # "extracts" | "full"
    path: Path
    meta: dict = field(default_factory=dict)
    initial: Optional[list[Segment]] = None
    corrected: Optional[list[Segment]] = None
    edited: Optional[str] = None
    ideas: Optional[list[dict]] = None
    summary: Optional[str] = None
    keypoints: Optional[list[dict]] = None
    issues: list[Issue] = field(default_factory=list)

    def error(self, message: str, file: Optional[str] = None, line: Optional[int] = None) -> None:
        self.issues.append(Issue("error", message, file, line))

    def warn(self, message: str, file: Optional[str] = None, line: Optional[int] = None) -> None:
        self.issues.append(Issue("warning", message, file, line))

    @property
    def n_errors(self) -> int:
        return sum(1 for i in self.issues if i.level == "error")

    @property
    def n_warnings(self) -> int:
        return sum(1 for i in self.issues if i.level == "warning")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_duration(value: str) -> Optional[int]:
    """Parse `6s`, `1m 05s`, `1h 02m 03s` into seconds. Returns None if invalid."""
    value = value.strip()
    match = _DURATION_RE.match(value)
    if not value or not match or not any(match.groupdict().values()):
        return None
    h, m, s = (int(match.group(k) or 0) for k in ("h", "m", "s"))
    return h * 3600 + m * 60 + s


def parse_transcript(text: str) -> tuple[list[Segment], list[tuple[int, str, str]]]:
    """Parse `- [start - end] text` lines.

    Returns (segments, problems) where problems are (line, kind, content) tuples
    with kind in {"not_a_segment", "bad_timestamp"}. Blank lines are ignored.
    """
    segments: list[Segment] = []
    problems: list[tuple[int, str, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        match = _SEGMENT_RE.match(line)
        if not match:
            problems.append((lineno, "not_a_segment", line))
            continue
        start = parse_duration(match.group("start"))
        end = parse_duration(match.group("end"))
        if start is None or end is None:
            problems.append((lineno, "bad_timestamp", line))
            continue
        segments.append(Segment(start, end, (match.group("text") or "").strip(), lineno))
    return segments, problems


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _shorten(text: str, width: int = 60) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def _format_seconds(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def paragraphs(markdown: str) -> list[str]:
    """Non-empty paragraphs (blocks separated by blank lines) of a markdown text, each on one line.
    Paragraph numbers (1-based) in the gold files refer to this list."""
    blocks = re.split(r"\n\s*\n", markdown.replace("\r\n", "\n"))
    return [" ".join(line.strip() for line in b.splitlines() if line.strip()) for b in blocks if b.strip()]


def format_transcript(segments: list[Segment]) -> str:
    """Inverse of parse_transcript (same format as the app export)."""
    return "".join(f"- [{_format_seconds(s.start)} - {_format_seconds(s.end)}] {s.text}\n" for s in segments)


# --------------------------------------------------------------------------- #
# Loading + validation of one lesson
# --------------------------------------------------------------------------- #


def _load_yaml(item: LessonItem, name: str) -> Any:
    try:
        return yaml.safe_load(_read_text(item.path / name))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        item.error(f"invalid YAML: {getattr(exc, 'problem', exc)}", name, mark.line + 1 if mark else None)
        return None


def _load_meta(item: LessonItem) -> None:
    name = "meta.yaml"
    data = _load_yaml(item, name)
    if data is None:
        if not item.issues or item.issues[-1].file != name:
            item.error("empty file", name)
        return
    if not isinstance(data, dict):
        item.error(f"expected a mapping, got {type(data).__name__}", name)
        return
    item.meta = data
    if not data.get("lesson"):
        item.warn("missing 'lesson' (source lesson name)", name)
    quality = data.get("audio_quality")
    if quality is not None and quality not in AUDIO_QUALITIES:
        item.error(f"audio_quality must be one of {sorted(AUDIO_QUALITIES)}, got {quality!r}", name)


def _load_transcript(item: LessonItem, name: str) -> Optional[list[Segment]]:
    segments, problems = parse_transcript(_read_text(item.path / name))

    for kind, label in (("not_a_segment", "not a `- [start - end] text` line"), ("bad_timestamp", "invalid timestamp")):
        found = [p for p in problems if p[1] == kind]
        for lineno, _, content in found[:MAX_REPORTED_LINES]:
            item.error(f"{label}: {_shorten(content)!r}", name, lineno)
        if len(found) > MAX_REPORTED_LINES:
            item.error(f"... and {len(found) - MAX_REPORTED_LINES} more lines: {label}", name)

    if not segments:
        item.error("no segment found", name)
        return segments

    prev: Optional[Segment] = None
    for seg in segments:
        if seg.end < seg.start:
            item.error(f"end before start ({_format_seconds(seg.start)} > {_format_seconds(seg.end)})", name, seg.line)
        if prev is not None and seg.start < prev.start:
            item.error(
                f"segment out of order: starts at {_format_seconds(seg.start)}, "
                f"previous one at {_format_seconds(prev.start)}",
                name,
                seg.line,
            )
        if not seg.text:
            item.warn("empty segment text", name, seg.line)
        prev = seg

    if name == "corrected.md":
        markdown = [s for s in segments if re.search(r"\*\*|__|^#|`", s.text)]
        for seg in markdown[:MAX_REPORTED_LINES]:
            item.warn(f"markdown formatting in gold transcript (counted as WER errors): {_shorten(seg.text)!r}", name, seg.line)
    return segments


def _compare_segments(item: LessonItem) -> None:
    initial, corrected = item.initial, item.corrected
    if not initial or not corrected:
        return
    if len(initial) != len(corrected):
        item.error(
            f"segment count differs from initial.md ({len(corrected)} vs {len(initial)}); "
            "corrected.md must keep the same segments",
            "corrected.md",
        )
    for a, b in zip(initial, corrected):
        if (a.start, a.end) != (b.start, b.end):
            item.error(
                f"first timestamp mismatch with initial.md:{a.line}: "
                f"[{_format_seconds(b.start)} - {_format_seconds(b.end)}] vs "
                f"[{_format_seconds(a.start)} - {_format_seconds(a.end)}]",
                "corrected.md",
                b.line,
            )
            break


def _load_points(item: LessonItem, name: str, recommended: tuple[int, int],
                 n_paragraphs: Optional[int] = None) -> Optional[list[dict]]:
    """`n_paragraphs`: number of paragraphs of edited.md, to check paragraph_start / paragraph_end."""
    data = _load_yaml(item, name)
    if data is None:
        if not item.issues or item.issues[-1].file != name:
            item.error("empty file", name)
        return None
    if not isinstance(data, list):
        item.error(f"expected a list of entries, got {type(data).__name__}", name)
        return None

    seen_ids: set = set()
    valid: list[dict] = []
    cite_count = 0
    for index, entry in enumerate(data, start=1):
        where = f"entry #{index}"
        if not isinstance(entry, dict):
            item.error(f"{where}: expected a mapping with id/text/importance", name)
            continue
        entry_id = entry.get("id")
        if entry_id is None:
            item.error(f"{where}: missing 'id'", name)
        elif entry_id in seen_ids:
            item.error(f"{where}: duplicate id {entry_id!r}", name)
        else:
            seen_ids.add(entry_id)
            where = f"id {entry_id}"
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            item.error(f"{where}: missing or empty 'text'", name)
        elif _CITE_RE.search(text):
            cite_count += 1
        importance = entry.get("importance")
        if importance not in IMPORTANCE_WEIGHTS:
            item.error(f"{where}: importance must be one of {list(IMPORTANCE_WEIGHTS)}, got {importance!r}", name)
        elements = entry.get("elements")
        if elements is not None and not (isinstance(elements, list) and elements
                                         and all(isinstance(e, str) and e.strip() for e in elements)):
            item.error(f"{where}: 'elements' must be a non-empty list of texts (essential elements)", name)
        timestamp = entry.get("timestamp")
        if timestamp is not None and parse_duration(str(timestamp)) is None:
            item.error(f"{where}: invalid timestamp {timestamp!r} (expected e.g. '4m 04s')", name)
        start, end = entry.get("paragraph_start"), entry.get("paragraph_end")
        if start is not None or end is not None:
            if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end):
                item.error(f"{where}: paragraph_start / paragraph_end must be integers with "
                           f"1 <= start <= end, got {start!r} / {end!r}", name)
            elif n_paragraphs is not None and end > n_paragraphs:
                item.error(f"{where}: paragraph_end {end} > {n_paragraphs} (paragraphs of edited.md)", name)
        unknown = set(entry) - {"id", "text", "importance", "timestamp", "paragraph_start", "paragraph_end"}
        if unknown:
            item.warn(f"{where}: unknown keys {sorted(unknown)}", name)
        valid.append(entry)

    if cite_count:
        item.warn(f"{cite_count} entries contain LLM '[cite: ...]' artifacts", name)
    low, high = recommended
    if not low <= len(data) <= high:
        item.warn(f"{len(data)} entries, {low}-{high} recommended", name)
    return valid


def _load_text(item: LessonItem, name: str) -> Optional[str]:
    text = _read_text(item.path / name)
    if not text.strip():
        item.error("empty file", name)
        return None
    return text


def load_lesson(path: Path, kind: str, tasks: Optional[set[str]] = None) -> LessonItem:
    """`tasks`: only the files of these tasks are required (default: all the files of the dataset);
    the other files are loaded and checked when present."""
    item = LessonItem(id=path.name, kind=kind, path=path)
    if not path.is_dir():
        item.error(f"folder not found: {path}")
        return item

    present = {p.name for p in path.iterdir() if p.is_file()}
    known = set(REQUIRED_FILES[kind]) | set(OPTIONAL_FILES[kind])
    for name in required_files(kind, tasks):
        if name not in present:
            item.error("missing file", name)
    for name in sorted(present - known):
        item.warn(f"unexpected file (expected: {', '.join(REQUIRED_FILES[kind])})", name)

    def has(name: str) -> bool:
        return name in present

    if has("meta.yaml"):
        _load_meta(item)
    if has("initial.md"):
        item.initial = _load_transcript(item, "initial.md")
    if has("corrected.md"):
        item.corrected = _load_transcript(item, "corrected.md")
    _compare_segments(item)
    if has("edited.md"):
        item.edited = _load_text(item, "edited.md")
    if has("edited_ideas.yaml"):
        item.ideas = _load_points(item, "edited_ideas.yaml", IDEAS_RANGE)
    if has("summary.md"):
        item.summary = _load_text(item, "summary.md")
    if has("summary_keypoints.yaml"):
        n_paragraphs = len(paragraphs(item.edited)) if item.edited else None
        item.keypoints = _load_points(item, "summary_keypoints.yaml", KEYPOINTS_RANGE, n_paragraphs)
    return item


# --------------------------------------------------------------------------- #
# Campaign-level loading
# --------------------------------------------------------------------------- #


def load_dataset(config: dict, tasks: Optional[set[str]] = None) -> tuple[list[LessonItem], list[Issue]]:
    """Load every lesson listed in `config['dataset']`. Paths are relative to bench/.
    `tasks`: tasks of the steps to run (only their files are required, see load_lesson)."""
    issues: list[Issue] = []
    items: list[LessonItem] = []
    dataset = config.get("dataset")
    if not isinstance(dataset, dict):
        issues.append(Issue("error", "'dataset' must be a mapping with 'extracts' and/or 'full' lists"))
        return items, issues
    if not config.get("dataset_version"):
        issues.append(Issue("warning", "missing 'dataset_version'"))

    for key in sorted(set(dataset) - set(DATASET_KINDS)):
        issues.append(Issue("error", f"unknown dataset kind {key!r} (expected {list(DATASET_KINDS)})"))

    seen: dict[str, str] = {}
    for kind in DATASET_KINDS:
        entries = dataset.get(kind) or []
        if not isinstance(entries, list):
            issues.append(Issue("error", f"dataset.{kind} must be a list"))
            continue
        expected_parent = (BENCH_DIR / "data" / kind).resolve()
        for entry in entries:
            path = (BENCH_DIR / str(entry)).resolve()
            if path.parent != expected_parent:
                issues.append(Issue("error", f"dataset.{kind}: {entry!r} is not a folder of data/{kind}/"))
            if path.name in seen:
                issues.append(Issue("error", f"lesson {path.name!r} listed twice (in {seen[path.name]} and {kind})"))
                continue
            seen[path.name] = kind
            items.append(load_lesson(path, kind, tasks))
    return items, issues


def describe(item: LessonItem) -> str:
    parts = []
    if item.initial is not None:
        parts.append(f"{len(item.initial)} segments")
    elif item.corrected is not None:
        parts.append(f"{len(item.corrected)} segments")
    if item.corrected:
        parts.append(f"{sum(len(s.text.split()) for s in item.corrected)} words")
    if item.ideas is not None:
        parts.append(f"{len(item.ideas)} ideas")
    if item.keypoints is not None:
        parts.append(f"{len(item.keypoints)} keypoints")
    return ", ".join(parts)
