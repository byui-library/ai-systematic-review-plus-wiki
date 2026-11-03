"""Built-in quality-appraisal checklists. Item wording is paraphrased; cite the official instrument."""
from __future__ import annotations

CHECKLISTS: dict[str, dict] = {
    'AXIS': {
        'name': 'AXIS: appraisal tool for cross-sectional studies (Downes et al., 2016, BMJ Open)',
        'answers': ['yes', 'no', 'unclear'],
        'overall': ['high', 'moderate', 'low'],
        'note': 'For q13 (response rate and non-response bias) and q19 (funding or conflicts of interest), "yes" signals '
                'a concern; for every other item "yes" is favourable.',
        'items': [
            ('q1', 'Were the aims or objectives of the study clear?'),
            ('q2', 'Was the study design appropriate for the stated aims?'),
            ('q3', 'Was the sample size justified?'),
            ('q4', 'Was the target or reference population clearly defined?'),
            ('q5', 'Was the sample frame taken from an appropriate population base?'),
            ('q6', 'Was the selection process likely to select participants representative of the target population?'),
            ('q7', 'Were measures taken to address and categorise non-responders?'),
            ('q8', 'Were the risk factor and outcome variables appropriate to the aims?'),
            ('q9', 'Were the variables measured with instruments that had been trialled, piloted, or published?'),
            ('q10', 'Is it clear what was used to determine statistical significance or precision?'),
            ('q11', 'Were the methods, including statistical methods, described well enough to be repeated?'),
            ('q12', 'Were the basic data adequately described?'),
            ('q13', 'Does the response rate raise concerns about non-response bias?'),
            ('q14', 'If appropriate, was information about non-responders described?'),
            ('q15', 'Were the results internally consistent?'),
            ('q16', 'Were the results of all analyses described in the methods presented?'),
            ('q17', "Were the authors' discussion and conclusions justified by the results?"),
            ('q18', 'Were the limitations of the study discussed?'),
            ('q19', "Were there funding sources or conflicts of interest that may affect the authors' interpretation?"),
            ('q20', 'Was ethical approval or participant consent obtained?'),
        ],
    },
    'JBI': {
        'name': 'JBI critical appraisal checklist for analytical cross-sectional studies',
        'answers': ['yes', 'no', 'unclear', 'not applicable'],
        'overall': ['include', 'exclude', 'seek further info'],
        'note': 'JBI publishes separate checklists for other designs; switch tools in project.yaml if most studies are not cross-sectional.',
        'items': [
            ('q1', 'Were the criteria for inclusion in the sample clearly defined?'),
            ('q2', 'Were the study subjects and the setting described in detail?'),
            ('q3', 'Was the exposure measured in a valid and reliable way?'),
            ('q4', 'Were objective, standard criteria used to measure the condition?'),
            ('q5', 'Were confounding factors identified?'),
            ('q6', 'Were strategies to deal with confounding factors stated?'),
            ('q7', 'Were the outcomes measured in a valid and reliable way?'),
            ('q8', 'Was appropriate statistical analysis used?'),
        ],
    },
    'CASP': {
        'name': 'CASP checklist for cohort studies',
        'answers': ['yes', 'no', "can't tell"],
        'overall': ['high', 'moderate', 'low'],
        'note': 'CASP questions 7, 8, and 12 are open in the original; here they are phrased as yes/no and the '
                'explanation goes in the page text.',
        'items': [
            ('q1', 'Did the study address a clearly focused issue?'),
            ('q2', 'Was the cohort recruited in an acceptable way?'),
            ('q3', 'Was the exposure accurately measured to minimise bias?'),
            ('q4', 'Was the outcome accurately measured to minimise bias?'),
            ('q5', 'Did the authors identify and account for important confounding factors?'),
            ('q6', 'Was follow-up of participants complete enough and long enough?'),
            ('q7', 'Are the results clearly reported?'),
            ('q8', 'Are the results precise (for example, narrow confidence intervals)?'),
            ('q9', 'Are the results believable?'),
            ('q10', 'Can the results be applied to the population of interest?'),
            ('q11', 'Do the results fit with other available evidence?'),
            ('q12', 'Does the study have clear implications for practice?'),
        ],
    },
    'RoB2': {
        'name': 'Cochrane RoB 2: risk of bias in randomised trials',
        'answers': ['low', 'some concerns', 'high'],
        'overall': ['low', 'some concerns', 'high'],
        'note': 'Judge each domain with the official RoB 2 signalling questions and algorithm.',
        'items': [
            ('d1', 'Bias arising from the randomisation process'),
            ('d2', 'Bias due to deviations from intended interventions'),
            ('d3', 'Bias due to missing outcome data'),
            ('d4', 'Bias in measurement of the outcome'),
            ('d5', 'Bias in selection of the reported result'),
        ],
    },
}


def checklist(tool: str) -> dict | None:
    return CHECKLISTS.get(tool)
