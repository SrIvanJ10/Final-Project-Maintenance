"""
Shared helper functions and constants for all test modules.
"""
import os

from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import (
    Article,
    Project,
    Search,
    SearchCriteria,
    SearchResult,
)

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

PROJECT_URL  = '/api/v1/projects/'
CRITERIA_URL = '/api/v1/search-criteria/'
RESULTS_URL  = '/api/v1/search-results/'
ARTICLES_URL = '/api/v1/articles/'

# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def _project_payload(**overrides):
    """Minimal valid payload for project creation."""
    base = {
        'title': 'Test SLR',
        'description': 'A systematic literature review for testing.',
        'research_question': 'What is the impact of X on Y?',
        'objectives': 'Identify primary studies on X.',
        'scope': 'Peer-reviewed articles from 2010 to 2024.',
    }
    base.update(overrides)
    return base


def _make_project(owner):
    """Create a project directly in the DB (no LLM call)."""
    return Project.objects.create(
        title='Base Project',
        description='Description',
        owner=owner,
        research_question='RQ',
        objectives='OBJ',
        scope='Scope',
        inclusion_criteria='Initial PRISMA criteria.',
    )


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def _make_ss_criteria(project, keywords='machine learning'):
    return SearchCriteria.objects.create(
        project=project,
        name='SS Criteria',
        source_type='semantic_scholar',
        keywords=keywords,
    )


def _make_scopus_criteria(project):
    return SearchCriteria.objects.create(
        project=project,
        name='Scopus Criteria',
        source_type='scopus',
        keywords='',
    )


def _make_search_result(search, rank, relevance='not_reviewed'):
    article = Article.objects.create(
        semantic_scholar_id=f'art-{search.id}-{rank}',
        title=f'Article {rank}',
        publication_year=2023,
    )
    return SearchResult.objects.create(
        search=search, article=article, rank=rank, relevance=relevance
    )


def _make_pending_results(search, n, prefix='d'):
    """Create n pending SearchResult rows for the given search."""
    results = []
    for i in range(1, n + 1):
        art = Article.objects.create(
            semantic_scholar_id=f'{prefix}-art-{search.pk}-{i}',
            title=f'Article {i}',
            publication_year=2024,
        )
        results.append(SearchResult.objects.create(search=search, article=art, rank=i))
    return results


# ---------------------------------------------------------------------------
# Scopus CSV helpers
# ---------------------------------------------------------------------------

_SCOPUS_CSV_HEADER = (
    '"Authors","Author full names","Author(s) ID","Title","Year","Source title",'
    '"Volume","Issue","Art. No.","Page start","Page end","Cited by","DOI","Link",'
    '"Abstract","Document Type","Publication Stage","Open Access","Source","EID"'
)


def _scopus_csv_row(n):
    return (
        f'"Author {n}","Author {n} (100{n})","100{n}",'
        f'"Article title {n}","2023","Journal {n}",'
        f'"1","1","","1","10","5","10.000/{n}",'
        f'"https://scopus.com/{n}",'
        f'"Abstract {n}","Article","Final","","Scopus","2-s2.0-{n}"'
    )


def _make_scopus_csv(n_articles=5):
    """Return bytes of a valid Scopus CSV with n_articles data rows."""
    rows = [_SCOPUS_CSV_HEADER] + [_scopus_csv_row(i) for i in range(1, n_articles + 1)]
    return '\n'.join(rows).encode('utf-8')


# ---------------------------------------------------------------------------
# Semantic Scholar helpers
# ---------------------------------------------------------------------------

def _fake_ss_paper(paper_id, title='A Paper'):
    """Minimal dict that mimics a Semantic Scholar API paper record."""
    return {
        'paperId': paper_id,
        'title': title,
        'abstract': 'Some abstract.',
        'authors': [{'authorId': '1', 'name': 'Author One'}],
        'year': 2023,
        'publicationDate': '2023-01-01',
        'publicationVenue': 'Journal X',
        'url': f'https://semanticscholar.org/paper/{paper_id}',
        'citationCount': 10,
        'influenceScore': 5.0,
        'fieldsOfStudy': ['Computer Science'],
    }
