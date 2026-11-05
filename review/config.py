"""Load project.yaml, fill in defaults, validate it, and define every file location."""
from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import PipelineError
KNOWN_SOURCES = ('pubmed', 'wos', 'ebsco', 'ris', 'csv')   # must match importers.PARSERS (tested)
APPRAISAL_TOOLS = ('AXIS', 'CASP', 'CASP-Qual', 'JBI', 'RoB2', 'none')
HOSTING_TARGETS = ('local', 'github_pages', 'openequella')

# Each review type sets the wording used in the prompt, Methods page, and disclosure, and the defaults below.
# A default applies only where the researcher's project.yaml leaves the setting out.
REVIEW_TYPES: dict[str, dict] = {
    'systematic': {'noun': 'systematic review', 'framework': 'PICOS', 'appraisal': 'AXIS',
                   'validation': {'sample_percent': 10, 'min_per_tier': 5}, 'flow_title': 'PRISMA 2020 flow diagram'},
    'scoping': {'noun': 'scoping review', 'framework': 'PCC', 'appraisal': 'none',
                'validation': {'sample_percent': 10, 'min_per_tier': 5}, 'flow_title': 'PRISMA-ScR flow diagram'},
    'qualitative': {'noun': 'qualitative evidence synthesis', 'framework': 'SPIDER', 'appraisal': 'CASP-Qual',
                    'validation': {'sample_percent': 10, 'min_per_tier': 5}, 'flow_title': 'PRISMA 2020 flow diagram'},
    'collection': {'noun': 'literature collection', 'framework': 'plain', 'appraisal': 'none',
                   'validation': {'sample_percent': 5, 'min_per_tier': 3}, 'flow_title': 'Flow of records'},
    'methods': {'noun': 'methods review', 'framework': 'custom', 'appraisal': 'none',
                'validation': {'sample_percent': 5, 'min_per_tier': 3}, 'flow_title': 'Flow of records'},
}
# elements: the framework's labels in order (None: the researcher names their own); required: labels that must be filled.
FRAMEWORKS: dict[str, dict] = {
    'PICOS': {'elements': ('Population', 'Intervention or exposure', 'Comparison', 'Outcomes', 'Study design'),
              'required': ()},
    'PCC': {'elements': ('Population', 'Concept', 'Context'), 'required': ('Population', 'Concept', 'Context')},
    'SPIDER': {'elements': ('Sample', 'Phenomenon of interest', 'Design', 'Evaluation', 'Research type'),
               'required': ('Sample', 'Phenomenon of interest')},
    'plain': {'elements': (), 'required': ()},
    'custom': {'elements': None, 'required': ()},
}
NAMED_FRAMEWORKS = ('PICOS', 'PCC', 'SPIDER')
# The original `picos:` block, still accepted: its keys map onto the PICOS labels.
LEGACY_PICOS = {'population': 'Population', 'intervention_or_exposure': 'Intervention or exposure',
                'comparison': 'Comparison', 'outcomes': 'Outcomes', 'study_design': 'Study design'}

DEFAULTS: dict = {
    'project': {'title': '', 'short_name': 'review', 'researcher': '', 'institution': '', 'ai_operator': ''},
    'question': '',
    'review_type': 'systematic',
    'criteria': {'framework': None, 'elements': {}, 'include': [], 'exclude': []},
    'sources': list(KNOWN_SOURCES),
    'prescreen': {
        'keyword_groups': [],
        'threshold': 1,
        'exclude': {'retracted': True, 'editorials': True, 'conference_abstracts': True,
                    'non_english': True, 'no_abstract': True},
    },
    'tiers': [],
    'validation': {'sample_percent': 10, 'min_per_tier': 5, 'seed': 42},
    'extraction_columns': [],
    'concept_axes': [],
    'appraisal': {'tool': 'AXIS'},
    'outputs': {'prisma': False, 'figures': True, 'knowledge_graph': True},
    'pdfs': {'libkey': True, 'unpaywall': True},
    'site': {'title': '', 'targets': ['local']},
    'classify': {'batch_size': 50},
    'screening': {'method': 'assistant', 'model': 'jev-1.14.0',
                  'thresholds': {'yes_at_least': 0.7, 'no_at_most': 0.3}, 'questions': {}},
    'wiki': {'deep_tiers': None},   # None: the first included tier gets the deep, researcher-confirmed pages
}


class ConfigError(PipelineError):
    def __init__(self, problems: list[str]):
        super().__init__('project.yaml needs attention:', problems)


class Paths:
    """Every file the pipeline reads or writes, relative to one project root."""

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.project_yaml = self.root / 'project.yaml'
        self.data = self.root / 'data'
        self.exports = self.data / 'exports'
        self.records = self.data / 'records.json'
        self.stats = self.data / 'stats.json'
        self.prefilter_excluded = self.data / 'prefilter_excluded.json'
        self.prescreen_excluded = self.data / 'prescreen_excluded.json'
        self.candidates = self.data / 'candidates.json'
        self.checkpoint = self.data / 'checkpoint.json'
        self.classify_batch = self.data / 'classify_batch.json'
        self.classify_results = self.data / 'classify_results.json'
        self.jev_answers = self.data / 'jev_answers.json'
        self.validation_xlsx = self.data / 'validation.xlsx'
        self.validation_sample = self.data / 'validation_sample.json'
        self.validation_results = self.data / 'validation_results.json'
        self.ai_disclosure = self.data / 'ai_disclosure.md'
        self.results_xlsx = self.data / 'Results.xlsx'
        self.included_csv = self.data / 'included.csv'
        self.excluded_csv = self.data / 'excluded.csv'
        self.prisma_png = self.data / 'prisma.png'
        self.state = self.data / 'state.json'
        self.env = self.root / '.env'
        self.pdf_log = self.data / 'pdf_log.json'
        self.manual_downloads = self.data / 'manual_downloads.csv'
        self.paper_numbers = self.data / 'paper_numbers.json'
        self.wiki_task = self.data / 'wiki_paper.json'
        self.wiki_parts = self.data / 'wiki_paper'
        self.extraction_xlsx = self.data / 'extraction.xlsx'
        self.extraction_csv = self.data / 'extraction.csv'
        self.wiki = self.root / 'wiki'
        self.raw = self.wiki / 'raw'
        self.inbox = self.raw / 'inbox'

    def show(self, path: Path, folder: bool = False) -> str:
        """Name a project file the way the researcher would type it: from the folder they are in
        (demo-workspace/data/validation.xlsx when they work from the template folder), otherwise in full."""
        try:
            text, sep = Path(path).relative_to(Path.cwd().resolve()).as_posix(), '/'
        except (ValueError, OSError):   # outside the current folder, or the current folder is gone
            text, sep = str(path), os.sep
        if text == '.':   # the current folder itself: "./" says nothing, so name it
            text, sep = str(path), os.sep
        return text + sep if folder else text


@dataclass(frozen=True)
class Tier:
    id: int
    label: str
    included: bool
    definition: str


@dataclass(frozen=True)
class KeywordGroup:
    name: str
    weight: int
    terms: tuple[str, ...]


@dataclass(frozen=True)
class Project:
    raw: dict
    tiers: tuple[Tier, ...]
    keyword_groups: tuple[KeywordGroup, ...]

    @property
    def title(self) -> str:
        return self.raw['project']['title']

    @property
    def question(self) -> str:
        return self.raw['question']

    @property
    def review_type(self) -> str:
        return self.raw['review_type']

    @property
    def review_noun(self) -> str:
        return REVIEW_TYPES[self.review_type]['noun']

    @property
    def flow_title(self) -> str:
        return REVIEW_TYPES[self.review_type]['flow_title']

    @property
    def framework(self) -> str:
        return self.raw['criteria']['framework']

    @property
    def criteria_name(self) -> str:
        """'PICOS', 'PCC' or 'SPIDER'; 'eligibility' for plain and custom criteria."""
        return self.framework if self.framework in NAMED_FRAMEWORKS else 'eligibility'

    @property
    def criteria_elements(self) -> list[tuple[str, str]]:
        return list(self.raw['criteria']['elements'])

    @property
    def include_rules(self) -> list[str]:
        return list(self.raw['criteria']['include'])

    @property
    def exclude_rules(self) -> list[str]:
        return list(self.raw['criteria']['exclude'])

    @property
    def sources(self) -> list[str]:
        return list(self.raw['sources'])

    @property
    def threshold(self) -> int:
        return self.raw['prescreen']['threshold']

    @property
    def exclude(self) -> dict:
        return self.raw['prescreen']['exclude']

    @property
    def validation(self) -> dict:
        return self.raw['validation']

    @property
    def outputs(self) -> dict:
        return self.raw['outputs']

    @property
    def screening(self) -> dict:
        return self.raw['screening']

    @property
    def thresholds(self) -> dict:
        t = self.raw['screening']['thresholds']
        return {'yes': t['yes_at_least'], 'no': t['no_at_most']}

    @property
    def tier_rules(self) -> list[tuple[int, list[list[str]] | None]]:
        """(tier id, alternatives or None for the catch-all), highest tier first."""
        by_id = {t['id']: t for t in self.raw['tiers']}
        return [(t.id, by_id[t.id].get('when')) for t in self.tiers]

    @property
    def batch_size(self) -> int:
        return self.raw['classify']['batch_size']

    @property
    def tier_ids(self) -> list[int]:
        return [t.id for t in self.tiers]

    @property
    def included_tier_ids(self) -> list[int]:
        return [t.id for t in self.tiers if t.included]

    @property
    def deep_tiers(self) -> list[int]:
        chosen = self.raw['wiki'].get('deep_tiers')
        return list(chosen) if chosen is not None else self.included_tier_ids[:1]

    @property
    def extraction_columns(self) -> list[dict]:
        return [{'name': str(c['name']), 'hint': str(c.get('hint') or '')} for c in self.raw['extraction_columns']]

    @property
    def concept_axes(self) -> list[str]:
        return [str(a) for a in self.raw['concept_axes']]

    @property
    def appraisal_tool(self) -> str:
        return self.raw['appraisal']['tool']

    def tier(self, tier_id: int) -> Tier:
        for t in self.tiers:
            if t.id == tier_id:
                return t
        raise KeyError(tier_id)


_WHOLE = re.compile(r'[+-]?[0-9]+(?:[.]0*)?')


def whole_number(value) -> int | None:
    """A whole number from YAML, JSON, or an Excel cell; None for booleans, fractions, and non-numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):   # digits only, optionally "2.0": no exponents, underscores, nan, or inf
        text = value.strip()
        return int(text.split('.')[0]) if _WHOLE.fullmatch(text) else None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _merge(base: dict, override: dict, problems: list[str], prefix: str = '') -> dict:
    """Overlay the user's settings on the defaults. A value of the wrong shape is reported and the default kept."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        default = out.get(key)
        if value is None and key in out:   # `section:` with nothing under it keeps the defaults
            continue
        if isinstance(default, dict):
            if isinstance(value, dict):
                out[key] = _merge(default, value, problems, f'{prefix}{key}.')
            else:
                problems.append(f'{prefix}{key} should be a section of "name: value" settings')
        elif isinstance(default, list) and not isinstance(value, list):
            problems.append(f'{prefix}{key} should be a list, for example: {key}: [a, b]')
        else:
            out[key] = value
    return out


def _terms(group: dict) -> list[str]:
    """Lower-cased search terms; blanks are dropped. Spaces are kept so ' pca ' matches whole words."""
    terms = group.get('terms')
    if not isinstance(terms, list) or any(not isinstance(t, str) or not t.strip() for t in terms):
        return []
    return [t.lower() for t in terms]


def _at_least_one(value) -> bool:
    n = whole_number(value)
    return n is not None and n >= 1


def _label_key(label) -> str:
    return str(label).strip().lower().replace('_', ' ')


def _framework(value) -> str | None:
    """The canonical framework name for a loosely typed one ('pcc' -> 'PCC'); None if unknown."""
    return next((name for name in FRAMEWORKS if isinstance(value, str) and value.strip().lower() == name.lower()), None)


def _review_type(data: dict) -> str:
    kind = data.get('review_type')
    return kind if isinstance(kind, str) and kind in REVIEW_TYPES else 'systematic'


def _legacy_picos(data: dict, problems: list[str]) -> tuple[dict, list[tuple[str, str]] | None]:
    """Read an old `picos:` block as `criteria` with framework PICOS.

    Also returns its rows exactly as the old prompt printed them: the five standard keys first, then any
    other key in file order, nothing merged or reordered. Two keys that differ only in case (`population`
    and `Population`) stay two rows, and `Outcomes:` stays an extra row. Changing either would change the
    prompt fingerprint and retire the project's saved decisions. None when there is no legacy block."""
    if 'picos' not in data:
        return data, None
    data = dict(data)
    picos = data.pop('picos')
    if not picos:   # an empty `picos:` left behind is harmless
        return data, None
    if data.get('criteria'):   # an empty `criteria:` line next to it is harmless too
        problems.append('project.yaml has both picos and criteria: keep criteria and delete the picos section')
        return data, None
    if not isinstance(picos, dict):
        problems.append('picos should be a section of "name: value" settings')
        return data, None
    # Extra keys (for example `setting:`) were always accepted and screened on, so they stay as extra PICOS rows.
    order = [k for k in LEGACY_PICOS if k in picos] + [k for k in picos if k not in LEGACY_PICOS]
    # Other keys keep their own spelling (only `_` becomes a space): the prompt title-cases labels, which then
    # gives exactly the old `key.replace('_', ' ').title()`, even for non-ASCII keys.
    rows = [(LEGACY_PICOS.get(k, str(k).replace('_', ' ')), str(picos[k]))
            for k in order if str(picos[k] or '').strip()]
    # PICOS validation checks only the shape, so a collapsed copy is enough; the rows themselves are kept.
    data['criteria'] = {'framework': 'PICOS', 'elements': dict(rows)}
    return data, rows


def _type_defaults(data: dict) -> dict:
    """DEFAULTS with the review type's own defaults on top; the researcher's settings go on top of this."""
    t = REVIEW_TYPES[_review_type(data)]
    return _merge(DEFAULTS, {'appraisal': {'tool': t['appraisal']}, 'validation': t['validation'],
                             'criteria': {'framework': t['framework']}}, [])


def _filled(elements: dict) -> dict:
    """Elements with text. Values are kept exactly as written (only the blank test strips them): the prompt
    has always printed them unstripped, so stripping would change existing PICOS fingerprints."""
    return {str(k).strip(): str(v) for k, v in elements.items() if str(v or '').strip()}


CRITERIA_KEYS = ('framework', 'elements', 'include', 'exclude')


def _criteria_problems(c: dict) -> list[str]:
    name = _framework(c.get('framework'))
    if name is None:
        return [f'criteria.framework must be one of {", ".join(FRAMEWORKS)}']
    elements = c.get('elements') or {}
    if not isinstance(elements, dict):
        return ['criteria.elements should be a section of "label: text" settings']
    p: list[str] = [f'criteria has an unknown setting "{k}"; use {", ".join(CRITERIA_KEYS)}'
                    for k in c if k not in CRITERIA_KEYS]
    for key in ('include', 'exclude'):
        if any(not isinstance(r, str) or not r.strip() for r in c.get(key) or []):
            p.append(f'criteria.{key} must be a list of rules, for example: {key}: [Peer-reviewed studies]')
    labels = FRAMEWORKS[name]['elements']
    filled = {_label_key(k) for k in _filled(elements)}
    if labels is not None and name != 'PICOS':   # PICOS may carry extra rows, such as Setting
        known = {_label_key(label) for label in labels}
        for k in elements:
            if _label_key(k) in known:
                continue
            if labels:
                p.append(f'criteria.elements has "{k}", which is not part of {name}; use custom to name your own '
                         'elements')
            else:
                p.append(f'plain criteria have no elements: move "{k}" into include or exclude, or use custom')
        required = FRAMEWORKS[name]['required']
        missing = [r for r in required if _label_key(r) not in filled]
        if missing:
            p.append(f'{name} needs {", ".join(required[:-1])} and {required[-1]} (missing: {", ".join(missing)})')
    include = c.get('include') or []
    if name == 'plain' and isinstance(include, list) and not any(isinstance(r, str) and r.strip() for r in include):
        p.append('plain criteria need at least one include rule')
    if name == 'custom' and not filled:   # PICOS may be empty: older projects with no picos section still load
        p.append('custom criteria need at least one element filled in')
    return p


def _normalise_criteria(c: dict, legacy_rows: list[tuple[str, str]] | None = None) -> dict:
    """Canonical framework name and labels, framework order, blanks dropped (call after validation).

    `elements` becomes an ordered list of (label, text) rows. An old picos block supplies its own rows,
    which are kept exactly as written (see _legacy_picos)."""
    name = _framework(c['framework'])
    filled = _filled(c.get('elements') or {})
    labels = FRAMEWORKS[name]['elements']
    if labels is not None:
        by_key = {_label_key(k): v for k, v in filled.items()}
        known = {_label_key(label) for label in labels}
        extras = {k: v for k, v in filled.items() if _label_key(k) not in known}   # PICOS only (validated)
        filled = {label: by_key[_label_key(label)] for label in labels if _label_key(label) in by_key} | extras
    rows = list(legacy_rows) if legacy_rows is not None else list(filled.items())
    return {'framework': name, 'elements': rows,
            'include': [r.strip() for r in c.get('include') or []],
            'exclude': [r.strip() for r in c.get('exclude') or []]}


QUESTION_ID = re.compile(r'^[a-z][a-z0-9_]*$')
RESERVED_WORDS = "'yes', 'no', 'on', 'off', 'true' and 'false' can't be question ids in YAML; choose another, such as is_on"


def _word(value) -> str:
    """How a YAML value reads back to the researcher (True shows as yes, False as no)."""
    return ('yes' if value else 'no') if isinstance(value, bool) else str(value)


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _threshold_problems(t) -> list[str]:
    if not isinstance(t, dict):
        return ['screening.thresholds should be a section, for example: yes_at_least: 0.7 and no_at_most: 0.3']
    extra = [_word(k) for k in t if k not in ('yes_at_least', 'no_at_most')]
    if extra:
        return [f"screening.thresholds accepts only yes_at_least and no_at_most (found: {', '.join(extra)}). "
                'Write them as yes_at_least: 0.7 and no_at_most: 0.3.']
    lo, hi = t.get('no_at_most'), t.get('yes_at_least')
    if not (_number(lo) and _number(hi) and 0 < lo < hi < 1):
        return ['screening.thresholds: no_at_most must be below yes_at_least, and both between 0 and 1 '
                '(for example yes_at_least: 0.7, no_at_most: 0.3)']
    return []


def _screening_problems(raw: dict) -> list[str]:
    s, p = raw['screening'], []
    method = s.get('method')
    if method not in ('assistant', 'jev'):
        p.append(f'screening.method must be assistant or jev (found: {_word(method)})')
    tiers = sorted((t for t in raw.get('tiers') or [] if isinstance(t, dict) and whole_number(t.get('id')) is not None),
                   key=lambda t: whole_number(t['id']))
    jev = method == 'jev'
    questions = s.get('questions')
    if jev:
        if not isinstance(questions, dict) or not questions:
            p.append('screening.questions must list at least one question, for example: team_sport: Is it a team sport?')
            questions = {}
        for k, v in questions.items():
            if isinstance(k, bool):
                p.append(RESERVED_WORDS)
            elif not isinstance(k, str) or not QUESTION_ID.match(k) or k == 'not':
                p.append(f"screening question ids must be lowercase words joined by _, for example: team_sport "
                         f"('not' is reserved); fix '{_word(k)}'")
            elif not isinstance(v, str) or not v.strip():
                p.append(f"screening question '{k}' needs its text")
        model = s.get('model')
        if not isinstance(model, str) or not model.strip() or model.strip().endswith(('-latest', '-preview')):
            p.append('screening.model must name an exact Jev version such as jev-1.14.0, '
                     'so the methods section can report it')
    p += _threshold_problems(s.get('thresholds'))
    used = set()
    for i, tier in enumerate(tiers):
        when, last = tier.get('when'), i == len(tiers) - 1
        if jev and last and when is not None:
            p.append(f"the last tier ({tier['id']}) catches everything else, so it must not have when:")
        if jev and not last and when is None:
            p.append(f"tier {tier['id']} needs when: (only the last tier catches everything else)")
        if when is None:
            continue
        if not isinstance(when, list) or not when or any(not isinstance(a, list) or not a for a in when):
            p.append(f"tier {tier['id']} when: must be a list of lists, for example: [[team_sport, wearable]]")
            continue
        if not jev:
            continue
        for cond in (c for a in when for c in a):
            if isinstance(cond, bool):
                p.append(RESERVED_WORDS)
                continue
            cond = str(cond).strip()
            if cond[:4].lower() == 'not ' and cond[:4] != 'not ':
                p.append(f"tier {tier['id']}: write 'not {cond[4:].strip()}' in lowercase")
                continue
            qid = cond[4:].strip() if cond.startswith('not ') else cond
            used.add(qid)
            if qid not in questions:
                p.append(f"tier {tier['id']} uses unknown question '{qid}'")
    if jev:
        p += [f"question '{q}' is not used by any tier's when: (remove it or use it in a rule)"
              for q in questions if isinstance(q, str) and q not in used]
    return p


def _problems(raw: dict) -> list[str]:
    p: list[str] = []
    if not str(raw['project'].get('title') or '').strip():
        p.append('project.title is empty')
    if not str(raw.get('question') or '').strip():
        p.append('question is empty: write your research question')
    kind = raw.get('review_type')
    if not isinstance(kind, str) or kind not in REVIEW_TYPES:
        p.append(f'review_type must be one of {", ".join(REVIEW_TYPES)}')
    p += _criteria_problems(raw['criteria'])

    sources = raw.get('sources') or []
    if not sources:
        p.append('sources is empty: list the databases you exported from')
    unknown = [s for s in sources if s not in KNOWN_SOURCES]
    if unknown:
        p.append(f'sources contains unknown entries {unknown}; choose from {list(KNOWN_SOURCES)}')

    groups = raw['prescreen'].get('keyword_groups') or []
    if not groups:
        p.append('prescreen.keyword_groups is empty: add at least one group of search terms')
    for i, g in enumerate(groups):
        if not isinstance(g, dict) or not g.get('name'):
            p.append(f'prescreen.keyword_groups[{i}] needs a name')
            continue
        if not _at_least_one(g.get('weight', 1)):
            p.append(f"keyword group '{g['name']}' weight must be a whole number of 1 or more")
        if not _terms(g):
            p.append(f"keyword group '{g['name']}' terms must be a list of words or phrases, "
                     'for example: terms: [gps, accelerometer]')

    tiers = raw.get('tiers') or []
    if not 2 <= len(tiers) <= 6:
        p.append(f'tiers must have between 2 and 6 entries (found {len(tiers)})')
    ids = []
    for i, t in enumerate(tiers):
        if not isinstance(t, dict) or whole_number(t.get('id')) is None:
            p.append(f'tiers[{i}] needs a whole-number id')
            continue
        ids.append(whole_number(t['id']))
        if not str(t.get('label') or '').strip():
            p.append(f"tier {t['id']} needs a label")
        if not str(t.get('definition') or '').strip():
            p.append(f"tier {t['id']} needs a definition")
        if 'included' in t and not isinstance(t['included'], bool):
            p.append(f"tier {t['id']} included must be true or false")
    if len(ids) != len(set(ids)):
        p.append('tier ids must be unique')
    if tiers and not any(isinstance(t, dict) and t.get('included') is True for t in tiers):
        p.append('at least one tier must have included: true')

    deep = raw['wiki'].get('deep_tiers')
    included = {whole_number(t.get('id')) for t in tiers if isinstance(t, dict) and t.get('included') is True}
    if deep is not None and (not isinstance(deep, list) or any(whole_number(d) not in included for d in deep)):
        p.append(f'wiki.deep_tiers must list included tier ids (choose from {sorted(included)})')
    columns = raw.get('extraction_columns') or []
    if any(not isinstance(c, dict) or not str(c.get('name') or '').strip() for c in columns):
        p.append('every extraction_columns entry needs a name, for example: {name: Sample, hint: "n, level"}')
    axes = raw.get('concept_axes') or []
    if axes and not 2 <= len(axes) <= 4:
        p.append(f'concept_axes should list 2 to 4 axes (found {len(axes)})')
    if raw['appraisal'].get('tool') not in APPRAISAL_TOOLS:
        p.append(f'appraisal.tool must be one of {list(APPRAISAL_TOOLS)}')
    bad_targets = [t for t in raw['site'].get('targets') or [] if t not in HOSTING_TARGETS]
    if bad_targets:
        p.append(f'site.targets contains unknown entries {bad_targets}; choose from {list(HOSTING_TARGETS)}')
    for label, value, minimum in (('classify.batch_size', raw['classify'].get('batch_size'), 1),
                                  ('prescreen.threshold', raw['prescreen'].get('threshold'), 0),
                                  ('validation.min_per_tier', raw['validation'].get('min_per_tier'), 0),
                                  ('validation.seed', raw['validation'].get('seed'), None)):
        n = whole_number(value)
        if n is None or (minimum is not None and n < minimum):
            p.append(f'{label} must be a whole number' + (f' of {minimum} or more' if minimum is not None else ''))
    pct = raw['validation'].get('sample_percent')
    if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 < pct <= 100:
        p.append('validation.sample_percent must be a number between 1 and 100')
    p += _screening_problems(raw)
    return p


def load_project(root: Path | str) -> Project:
    paths = Paths(root)
    if not paths.project_yaml.exists():
        raise ConfigError([
            f'No project.yaml found in {paths.root}. Ask your AI assistant to "set up my review", '
            'or copy project.example.yaml to project.yaml and edit it.'
        ])
    try:
        data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as exc:
        raise ConfigError([f'project.yaml is not valid YAML: {exc}']) from exc
    if not isinstance(data, dict):
        raise ConfigError(['project.yaml must be a set of "name: value" settings'])

    problems: list[str] = []
    data, legacy_rows = _legacy_picos(data, problems)
    raw = _merge(_type_defaults(data), data, problems)
    shape_problem = any(q.startswith('criteria.include ') for q in problems)   # the default [] was kept
    problems += [q for q in _problems(raw) if not (shape_problem and q.startswith('plain criteria need'))]
    if problems:
        raise ConfigError(problems)

    # Validated: store numbers as ints so every reader of `raw` sees the same values as Tier/KeywordGroup.
    for section, key in (('classify', 'batch_size'), ('prescreen', 'threshold'),
                         ('validation', 'min_per_tier'), ('validation', 'seed')):
        raw[section][key] = whole_number(raw[section][key])
    for t in raw['tiers']:
        t['id'] = whole_number(t['id'])
    for g in raw['prescreen']['keyword_groups']:
        g['weight'] = whole_number(g.get('weight', 1))
    if raw['wiki'].get('deep_tiers') is not None:
        raw['wiki']['deep_tiers'] = [whole_number(d) for d in raw['wiki']['deep_tiers']]
    raw['criteria'] = _normalise_criteria(raw['criteria'], legacy_rows)

    tiers = tuple(sorted(
        (Tier(t['id'], str(t['label']).strip(), bool(t.get('included', False)), str(t['definition']).strip())
         for t in raw['tiers']),
        key=lambda t: t.id,
    ))
    groups = tuple(KeywordGroup(str(g['name']), g['weight'], tuple(_terms(g)))
                   for g in raw['prescreen']['keyword_groups'])
    return Project(raw=raw, tiers=tiers, keyword_groups=groups)


def _count(n: int, noun: str) -> str:
    return f'{n} {noun}' + ('' if n == 1 else 's')


def summary(project: Project) -> str:
    v = project.validation
    lines = [
        f'Project: {project.title}',
        f'Question: {project.question}',
        f'Review type: {project.review_noun}',
        f'Criteria: {project.criteria_name} ({_count(len(project.criteria_elements), "element")}, '
        f'{_count(len(project.include_rules), "include rule")}, {_count(len(project.exclude_rules), "exclude rule")})',
        '',
        'Sources: ' + ', '.join(project.sources),
        '',
        f'Keyword groups (papers need a score of {project.threshold} or more):',
    ]
    for g in project.keyword_groups:
        lines.append(f'  - {g.name} (weight {g.weight}): {len(g.terms)} terms')
    lines += ['', 'Tiers:']
    for t in project.tiers:
        lines.append(f"  {t.id}. {t.label} ({'included' if t.included else 'excluded'})")
    lines += [
        '',
        f"Validation sample: {v['sample_percent']}% of each tier (at least {v['min_per_tier']})",
        f"PRISMA flowchart: {'on' if project.outputs.get('prisma') else 'off'}",
    ]
    return '\n'.join(lines)
