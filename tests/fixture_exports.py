"""Synthetic exports in every supported format. 10 raw records -> 8 unique."""
from __future__ import annotations

import csv
from pathlib import Path

NBIB = """PMID- 10000001
TI  - Principal component analysis of workload metrics in collegiate
      soccer players.
AB  - We applied principal component analysis to GPS-derived workload metrics
      in 40 collegiate soccer players.
AU  - Doe J
AU  - Roe R
JT  - Journal of Example Science
DP  - 2021 Mar
LA  - eng
PT  - Journal Article
MH  - *Principal Component Analysis
OT  - workload
AID - 10.1000/example.001 [doi]

PMID- 10000002
TI  - An editorial on wearables.
AB  - Opinion piece about wearables.
AU  - Smith A
JT  - Journal of Example Science
DP  - 2020
LA  - eng
PT  - Editorial

PMID- 10000003
TI  - Effects of diet on cardiac outcomes in older adults.
AB  - Randomized trial of a dietary intervention in older adults.
AU  - Lee K
JT  - Clinical Example
DP  - 2019
LA  - eng
PT  - Journal Article
AID - 10.1000/example.003 [doi]
"""

WOS_HEADER = ['PT', 'AU', 'TI', 'SO', 'LA', 'DT', 'DE', 'ID', 'AB', 'PY', 'DI', 'PM', 'UT']
WOS_ROWS = [
    ['J', 'Doe, J; Roe, R',
     'Principal component analysis of workload metrics in collegiate soccer players.',
     'JOURNAL OF EXAMPLE SCIENCE', 'English', 'Article', 'workload', '',
     'We applied principal component analysis to GPS-derived workload metrics.',
     '2021', '10.1000/EXAMPLE.001', '10000001', 'WOS:0001'],
    ['J', 'Park, S', 'Factor analysis of external load in rugby union',
     'EXAMPLE SPORTS JOURNAL', 'English', 'Article', 'external load', '',
     'Factor analysis of external load variables in 30 rugby union players.',
     '2022', '10.1000/example.004', '', 'WOS:0002'],
]

EBSCO_HEADER = ['an', 'title', 'abstract', 'contributors', 'source', 'doi', 'publicationDate',
                'docTypes', 'isiType', 'pubTypes', 'language', 'subjects']
EBSCO_ROWS = [
    ['E1', 'Factor Analysis of External Load in Rugby Union',
     'Factor analysis of external load variables.', 'Park, S', 'Example Sports Journal', '',
     '20220115', 'Article', 'JOUR', 'Academic Journal', 'English', 'external load'],
    ['E2', 'Conference abstract on futsal load', 'Abstract of a talk on futsal GPS load.',
     'Ng, T', 'Proceedings', '', '20230601', 'Abstract', 'ABST', '', 'English', ''],
]

RIS = """TY  - JOUR
AU  - Kim, H
TI  - Redundancy in GPS workload variables: a correlation matrix approach
AB  - Correlation matrix analysis of 12 GPS workload variables
  in basketball.
PY  - 2023
DO  - 10.1000/example.005
JO  - Example Sports Journal
LA  - English
KW  - workload
KW  - correlation
ER  -
TY  - JOUR
TI  - Teaching statistics with games
AB  - A classroom report.
PY  - 2018
ER  -
"""

SCOPUS_HEADER = ['Authors', 'Title', 'Year', 'Source title', 'DOI', 'Abstract', 'Author Keywords',
                 'Language of Original Document', 'Document Type', 'EID']
SCOPUS_ROWS = [
    ['Ito, M', 'Dimensionality of training load in field hockey', '2024', 'Example Hockey Review',
     '10.1000/example.006',
     'We examined the dimensionality of accelerometer-derived training load in field hockey.',
     'training load; accelerometer', 'English', 'Article', '2-s2.0-1'],
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def write_exports(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'pubmed.nbib').write_text(NBIB, encoding='utf-8')
    wos = '\n'.join('\t'.join(row) for row in [WOS_HEADER, *WOS_ROWS]) + '\n'
    (directory / 'wos.txt').write_text(wos, encoding='utf-8')
    _write_csv(directory / 'ebsco.csv', EBSCO_HEADER, EBSCO_ROWS)
    (directory / 'export.ris').write_text(RIS, encoding='utf-8')
    _write_csv(directory / 'scopus.csv', SCOPUS_HEADER, SCOPUS_ROWS)
