import shutil

import yaml

from review import figures, wiki
from review.config import load_project
from review.papers import included_papers

DOE = 'doi:10.1000/example.001'


def test_count_values():
    counts = figures.count_values(['PCA; FA', 'pca', None, 'NR', ' Factor analysis ;', ''])
    assert counts == {'pca': 2, 'fa': 1, 'factor analysis': 1}


def test_build_figures(classified):
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['extraction_columns'] = [{'name': 'Method', 'hint': ''}, {'name': 'Software', 'hint': ''}]
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    project = load_project(paths.root)
    wiki.scaffold(paths, project)
    doe = {p.id: p for p in included_papers(paths, project)}[DOE]
    page = paths.wiki / doe.page_rel
    meta, body = wiki.read_page(page)
    meta.update(status='confirmed', extraction={'Method': 'PCA; FA', 'Software': 'NR'})
    wiki.write_page(page, meta, body)

    written = {p.name for p in figures.build_figures(paths, project)}
    assert {'papers-per-tier.png', 'papers-per-year.png', 'papers-per-source.png', 'top-method.png'} <= written
    assert 'top-software.png' not in written and 'prisma.png' not in written
    assert all((paths.wiki / 'figures' / name).stat().st_size > 1000 for name in written)
    page_text = (paths.wiki / 'tables/figures.md').read_text(encoding='utf-8')
    assert '](../figures/top-method.png)' in page_text and 'prisma' not in page_text

    shutil.copy(paths.wiki / 'figures/papers-per-tier.png', paths.prisma_png)   # stands in for a PRISMA chart
    assert 'prisma.png' in {p.name for p in figures.build_figures(paths, project)}
    assert '](../figures/prisma.png)' in (paths.wiki / 'tables/figures.md').read_text(encoding='utf-8')
