import json
import re

from review import graph, wiki


def test_parse_links():
    text = 'See [[a/b]], [[a/b|Label]], [[c.md]], and in a table [[d/e\\|L]].'
    assert graph.parse_links(text) == ['a/b', 'a/b', 'c', 'd/e']


def test_build_graph(classified):
    paths, project = classified
    wiki.scaffold(paths, project)
    w = paths.wiki
    (w / 'concepts/methods/pca.md').write_text(
        '# PCA\n\nUsed by [[papers/tier1/01-doe-2021]] and [[01-kim-2023]]; see [[debates/structure|debate]].\n',
        encoding='utf-8')
    (w / 'debates/structure.md').write_text('# Debate: structure\n\n[[pca]] vs [[missing-page]]\n', encoding='utf-8')
    (w / 'concepts/metrics/pca.md').write_text('# Another PCA\n', encoding='utf-8')   # makes the stem "pca" ambiguous
    wiki.write_page(w / 'concepts/methods/xss.md', {'title': 'XSS test'},
                    '# </script><script>alert(1)</script>\n')

    out = graph.build_graph(paths)
    html = (w / 'tables/knowledge-graph.html').read_text(encoding='utf-8')
    assert 'https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js' in html
    data = json.loads(re.search(r'const GRAPH = (\{.*?\});', html, re.S).group(1))
    ids = {n['id'] for n in data['nodes']}
    assert {'concepts/methods/pca', 'papers/tier1/01-doe-2021', 'debates/structure'} <= ids
    assert not any(i.startswith(('raw/', 'tables/')) or i in ('index', 'log') for i in ids)
    groups = {n['id']: n['group'] for n in data['nodes']}
    assert groups['concepts/methods/pca'] == 'concepts' and groups['debates/structure'] == 'debates'
    edges = {(e['from'], e['to']) for e in data['edges']}
    assert ('concepts/methods/pca', 'papers/tier2/01-kim-2023') in edges        # bare stem resolved
    xss = next(n for n in data['nodes'] if n['id'] == 'concepts/methods/xss')
    assert xss['title'] == '</script><script>alert(1)</script>'
    assert xss['url'] == '../concepts/methods/xss.html'
    assert '</script><script>alert(1)</script>' not in html
    assert out['unresolved'] == 2                                                # ambiguous [[pca]] + missing page
    summary = (w / 'tables/knowledge-graph.md').read_text(encoding='utf-8')
    assert '[Open the interactive graph](knowledge-graph.html)' in summary and 'PCA' in summary
