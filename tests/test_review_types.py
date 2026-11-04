"""Review types and general eligibility criteria (spec: docs/superpowers/specs/2026-11-04-review-types-and-criteria-design.md)."""
import shutil
from pathlib import Path

import pytest
import yaml

from review.config import ConfigError, load_project
from review.prompt import build_prompt, prompt_fingerprint

REPO = Path(__file__).resolve().parent.parent

# Fingerprints of the PICOS prompt before review types existed. They must never change: every saved
# AI decision in an existing project (and the demo's reference decisions) is tied to them.
PINNED = {
    'tests/fixtures/project.yaml': '4b205609fa7b',
    'examples/demo/project.yaml': '34980ce16d9a',
    'project.example.yaml': '4b7660935f75',
}


@pytest.mark.parametrize('source', PINNED)
def test_picos_prompt_is_unchanged(source, tmp_path):
    shutil.copy(REPO / source, tmp_path / 'project.yaml')
    assert prompt_fingerprint(load_project(tmp_path)) == PINNED[source]


def write_project(tmp_path, **changes):
    """The fixture project with its picos block replaced by `changes` (None deletes a key)."""
    data = yaml.safe_load((REPO / 'tests/fixtures/project.yaml').read_text(encoding='utf-8'))
    data.pop('picos')
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    (tmp_path / 'project.yaml').write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
    return tmp_path


def problems(tmp_path, **changes):
    with pytest.raises(ConfigError) as err:
        load_project(write_project(tmp_path, **changes))
    return '\n'.join(err.value.problems)


PCC = {'framework': 'PCC', 'elements': {'Population': 'Nursing students', 'Concept': 'Simulation training',
                                        'Context': 'Undergraduate programs'},
       'include': ['Empirical studies of any design'], 'exclude': ['Opinion pieces']}


def test_legacy_picos_reads_as_systematic_picos(tmp_path):
    shutil.copy(REPO / 'tests/fixtures/project.yaml', tmp_path / 'project.yaml')
    project = load_project(tmp_path)
    assert project.review_type == 'systematic' and project.framework == 'PICOS'
    assert project.criteria_elements[0] == ('Population', 'Team sport athletes')
    assert ('Intervention or exposure', 'Wearable tracking (GPS or accelerometer)') in project.criteria_elements


def test_picos_and_criteria_together_is_an_error(tmp_path):
    text = problems(tmp_path, picos={'population': 'x'}, criteria=PCC)
    assert 'both picos and criteria' in text


def test_scoping_pcc_loads_with_type_defaults(tmp_path):
    project = load_project(write_project(tmp_path, review_type='scoping', criteria=PCC))
    assert project.review_noun == 'scoping review' and project.criteria_name == 'PCC'
    assert project.appraisal_tool == 'none'
    assert project.include_rules == ['Empirical studies of any design'] and project.exclude_rules == ['Opinion pieces']
    assert project.flow_title == 'PRISMA-ScR flow diagram'


def test_type_framework_is_the_default(tmp_path):
    project = load_project(write_project(tmp_path, review_type='scoping',
                                         criteria={'elements': PCC['elements']}))
    assert project.framework == 'PCC'


def test_researcher_settings_beat_type_defaults(tmp_path):
    project = load_project(write_project(tmp_path, review_type='collection',
                                         criteria={'framework': 'plain', 'include': ['Any study of X']},
                                         appraisal={'tool': 'AXIS'}, validation=None))
    assert project.appraisal_tool == 'AXIS'
    assert project.validation['sample_percent'] == 5 and project.validation['min_per_tier'] == 3
    project = load_project(write_project(tmp_path, review_type='collection',
                                         criteria={'framework': 'plain', 'include': ['Any study of X']},
                                         validation={'sample_percent': 20}))
    assert project.validation['sample_percent'] == 20 and project.validation['min_per_tier'] == 3


def test_qualitative_defaults_to_casp_qual(tmp_path):
    project = load_project(write_project(tmp_path, review_type='qualitative', criteria={
        'elements': {'Sample': 'Nurses', 'Phenomenon of interest': 'Burnout'}}))
    assert project.framework == 'SPIDER' and project.appraisal_tool == 'CASP-Qual'


def test_unknown_type_and_framework(tmp_path):
    assert 'review_type must be one of systematic, scoping, qualitative, collection, methods' in \
        problems(tmp_path, review_type='meta', criteria=PCC)
    assert 'criteria.framework must be one of PICOS, PCC, SPIDER, plain, custom' in \
        problems(tmp_path, criteria={**PCC, 'framework': 'SPICE'})


def test_framework_requirements(tmp_path):
    text = problems(tmp_path, criteria={'framework': 'PCC', 'elements': {'Population': 'x', 'Concept': 'y'}})
    assert 'PCC needs Population, Concept and Context (missing: Context)' in text
    text = problems(tmp_path, criteria={**PCC, 'elements': {**PCC['elements'], 'Outcome': 'z'}})
    assert 'criteria.elements has "Outcome", which is not part of PCC; use custom to name your own elements' in text
    assert 'plain criteria need at least one include rule' in problems(tmp_path, criteria={'framework': 'plain'})
    assert 'custom criteria need at least one element' in problems(tmp_path, criteria={'framework': 'custom'})


def test_labels_match_loosely_and_come_out_canonical(tmp_path):
    project = load_project(write_project(tmp_path, criteria={'framework': 'pcc', 'elements': {
        'context': 'Undergraduate programs', 'population': 'Nursing students', 'CONCEPT': 'Simulation'}}))
    assert project.framework == 'PCC'
    assert [k for k, _ in project.criteria_elements] == ['Population', 'Concept', 'Context']


def test_custom_keeps_its_own_labels_in_order(tmp_path):
    project = load_project(write_project(tmp_path, review_type='methods', criteria={
        'elements': {'Method': 'Principal component analysis', 'Data': 'Wearable sensor data'}}))
    assert project.framework == 'custom' and project.criteria_name == 'eligibility'
    assert project.criteria_elements == [('Method', 'Principal component analysis'), ('Data', 'Wearable sensor data')]


def test_scoping_prompt_uses_type_and_framework(tmp_path):
    prompt = build_prompt(load_project(write_project(tmp_path, review_type='scoping', criteria=PCC)))
    assert 'screening papers for a scoping review.' in prompt
    assert 'Apply the research question, PCC criteria, and tier definitions below exactly.' in prompt
    assert 'PCC CRITERIA:\n  Population                : Nursing students\n' in prompt
    assert '  Include:\n    - Empirical studies of any design\n  Exclude:\n    - Opinion pieces\n\nTIERS:' in prompt


def test_plain_prompt_has_rules_only(tmp_path):
    prompt = build_prompt(load_project(write_project(tmp_path, review_type='collection',
                                                     criteria={'framework': 'plain', 'include': ['About X']})))
    assert 'eligibility criteria, and tier definitions' in prompt
    assert 'ELIGIBILITY CRITERIA:\n  Include:\n    - About X\n\nTIERS:' in prompt


def test_methods_page_shows_framework_and_rules(tmp_path):
    from review import vault_text
    project = load_project(write_project(tmp_path, review_type='scoping', criteria=PCC))
    text = vault_text.search_and_screening(project, {}, {}, [], [], None)
    assert '## Eligibility criteria (PCC)' in text and '| Concept | Simulation training |' in text
    assert '**Include:**\n\n- Empirical studies of any design\n' in text and '- Opinion pieces' in text
    assert 'the PCC criteria' in text


def test_casp_qual_checklist():
    from review.appraisal import checklist
    from review.config import APPRAISAL_TOOLS
    tool = checklist('CASP-Qual')
    assert 'CASP-Qual' in APPRAISAL_TOOLS and len(tool['items']) == 10
    assert tool['answers'] == ['yes', 'no', "can't tell"]


def test_casp_qual_runs_through_the_wiki(classified):
    """Stubs get the CASP-Qual items, the checklist page renders, and the tables build."""
    from review import tables, wiki
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['appraisal'] = {'tool': 'CASP-Qual'}
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    project = load_project(paths.root)
    wiki.scaffold(paths, project)
    assert 'qualitative studies' in (paths.wiki / 'methods-review/appraisal-checklist.md').read_text(encoding='utf-8')
    page = next((paths.wiki / 'papers').rglob('*.md'))
    meta, _ = wiki.read_page(page)
    assert list(meta['appraisal']['items']) == [f'q{i}' for i in range(1, 11)]
    tables.build_tables(paths, project)
    assert 'CASP-Qual' in (paths.wiki / 'tables/appraisal.md').read_text(encoding='utf-8')


def test_setup_interview_covers_types_and_frameworks():
    from review.config import FRAMEWORKS, REVIEW_TYPES
    text = (REPO / 'prompts/01-setup-interview.md').read_text(encoding='utf-8')
    for name in [*REVIEW_TYPES, *FRAMEWORKS, 'CASP-Qual']:
        assert f'`{name}`' in text, name
    assert 'Sets `picos`' not in text


def test_setup_doc_shows_every_type_and_framework():
    from review.config import FRAMEWORKS, REVIEW_TYPES
    text = (REPO / 'docs/03-setup.md').read_text(encoding='utf-8')
    for name in [*REVIEW_TYPES, *FRAMEWORKS]:
        assert f'framework: {name}' in text or f'review_type: {name}' in text, name


def _legacy_prompt(picos: dict | None) -> str:
    """The criteria block exactly as build_prompt wrote it before review types (from the git history)."""
    order = list(LEGACY_KEYS) + [k for k in (picos or {}) if k not in LEGACY_KEYS]
    values = {**dict.fromkeys(LEGACY_KEYS, ''), **(picos or {})}
    return 'PICOS CRITERIA:\n' + '\n'.join(f"  {k.replace('_', ' ').title():<26}: {values[k]}"
                                           for k in order if str(values[k] or '').strip()) + '\n\n'


LEGACY_KEYS = ('population', 'intervention_or_exposure', 'comparison', 'outcomes', 'study_design')


@pytest.mark.parametrize('picos', [
    {'population': 'Athletes\n', 'outcomes': 'Load  '},                  # block scalars and trailing spaces
    {'population': 'Athletes', 'setting': 'Elite clubs', 'time_frame': '2000 onward'},   # extra rows
    {},                                                                  # an empty picos section
    None,                                                                # no picos section at all
])
def test_legacy_picos_prompt_is_unchanged(tmp_path, picos):
    data = yaml.safe_load((REPO / 'tests/fixtures/project.yaml').read_text(encoding='utf-8'))
    if picos is None:
        data.pop('picos')
    else:
        data['picos'] = picos
    (tmp_path / 'project.yaml').write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
    assert _legacy_prompt(picos) + 'TIERS:' in build_prompt(load_project(tmp_path))


def test_empty_picos_next_to_criteria_is_fine(tmp_path):
    assert load_project(write_project(tmp_path, picos={}, criteria=PCC)).framework == 'PCC'


def test_a_string_include_gets_one_clear_message(tmp_path):
    text = problems(tmp_path, criteria={'framework': 'plain', 'include': 'About X'})
    assert 'criteria.include should be a list' in text and 'need at least one include rule' not in text


def test_misspelt_criteria_settings_are_reported(tmp_path):
    assert 'criteria has an unknown setting "includes"' in problems(tmp_path, criteria={**PCC, 'includes': ['x']})


def test_summary_names_type_and_criteria(tmp_path):
    from review.config import summary
    text = summary(load_project(write_project(tmp_path, review_type='scoping', criteria=PCC)))
    assert 'Review type: scoping review' in text and 'Criteria: PCC (3 elements, 1 include rule, 1 exclude rule)' in text
