import io
import json as _json
import os
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import (
    Article,
    Project,
    ProjectMembership,
    Search,
    SearchCriteria,
    SearchResult,
    SearchResultAssessment,
)


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


# ===========================================================================
# BLOCK C — Search Sources, Import & Filtering
# US-07 (I-DATA-01), US-08 (S-DATA-01), US-09 (S-DATA-02), US-10 (I-VIEW-02)
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CRITERIA_URL = '/api/v1/search-criteria/'
RESULTS_URL  = '/api/v1/search-results/'
ARTICLES_URL = '/api/v1/articles/'

# Minimal Scopus CSV that matches the real export format the import parser expects.
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


def _make_scopus_criteria(project):
    return SearchCriteria.objects.create(
        project=project,
        name='Scopus Criteria',
        source_type='scopus',
        keywords='',
    )


def _make_ss_criteria(project, keywords='machine learning'):
    return SearchCriteria.objects.create(
        project=project,
        name='SS Criteria',
        source_type='semantic_scholar',
        keywords=keywords,
    )


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


# ---------------------------------------------------------------------------
# US-07 — Search Source Configuration
# ---------------------------------------------------------------------------

class SearchCriteriaTestCase(APITestCase):
    """
    US-07 — Search source configuration.
    A valid query must be saved and immediately executable.
    An empty query must be rejected before saving.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.client.force_login(self.owner)

    def test_c01_valid_semantic_scholar_query_is_saved(self):
        """C-01: POST with valid keywords creates criteria and persists it."""
        payload = {
            'project': self.project.pk,
            'name': 'ML Search',
            'source_type': 'semantic_scholar',
            'keywords': 'machine learning, neural networks',
        }
        response = self.client.post(CRITERIA_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            SearchCriteria.objects.filter(
                project=self.project, keywords='machine learning, neural networks'
            ).exists()
        )

    @patch('api.views.SemanticScholarAPI')
    def test_c01_saved_criteria_can_trigger_execute_search(self, mock_api_class):
        """C-01: Once criteria is saved, execute_search can be called successfully."""
        mock_instance = mock_api_class.return_value
        mock_instance.search_papers.return_value = {
            'data': [_fake_ss_paper('p1'), _fake_ss_paper('p2')]
        }
        criteria = _make_ss_criteria(self.project, keywords='deep learning')
        url = f'{CRITERIA_URL}{criteria.pk}/execute_search/'

        response = self.client.post(url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Search.objects.filter(criteria=criteria).count(), 1)

    def test_c02_empty_keywords_are_rejected_on_execute(self):
        """C-02: Executing a search with no keywords returns 400 and creates no Search."""
        criteria = _make_ss_criteria(self.project, keywords='')
        url = f'{CRITERIA_URL}{criteria.pk}/execute_search/'

        response = self.client.post(url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(Search.objects.filter(criteria=criteria).count(), 0)


# ---------------------------------------------------------------------------
# US-08 — External Results Import (Scopus)
# ---------------------------------------------------------------------------

class ScopusImportTestCase(APITestCase):
    """
    US-08 — Scopus CSV import.
    Valid files must be processed; invalid formats must be rejected;
    uploading the same file twice must warn the user without adding duplicates.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.criteria = _make_scopus_criteria(self.project)
        self.import_url = f'{CRITERIA_URL}{self.criteria.pk}/import_scopus_results/'
        self.client.force_login(self.owner)

    def test_c03_valid_scopus_csv_imports_all_articles(self):
        """C-03 (System): Uploading a valid Scopus CSV creates one SearchResult per row."""
        csv_file = SimpleUploadedFile(
            'scopus_export.csv', _make_scopus_csv(n_articles=5), content_type='text/csv'
        )
        response = self.client.post(self.import_url, {'file': csv_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        imported_search = Search.objects.get(criteria=self.criteria)
        self.assertEqual(
            SearchResult.objects.filter(search=imported_search).count(), 5
        )

    def test_c03_imported_articles_have_pending_relevance(self):
        """C-03 (System): All imported articles start with relevance 'not_reviewed'."""
        csv_file = SimpleUploadedFile(
            'scopus_export.csv', _make_scopus_csv(n_articles=3), content_type='text/csv'
        )
        self.client.post(self.import_url, {'file': csv_file}, format='multipart')

        search = Search.objects.get(criteria=self.criteria)
        pending = SearchResult.objects.filter(
            search=search, relevance='not_reviewed'
        ).count()
        self.assertEqual(pending, 3)

    def test_c04_invalid_file_format_is_rejected(self):
        """C-04 (System): A non-CSV/JSON file is rejected, no articles are added."""
        bad_file = SimpleUploadedFile(
            'document.pdf', b'%PDF-1.4 fake pdf content', content_type='application/pdf'
        )
        response = self.client.post(self.import_url, {'file': bad_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(Article.objects.count(), 0)

    def test_c05_uploading_same_csv_twice_warns_and_does_not_duplicate_articles(self):
        """C-05 (System): Re-uploading the same CSV must warn the user and not create duplicate articles."""
        csv_content = _make_scopus_csv(n_articles=3)

        self.client.post(
            self.import_url,
            {'file': SimpleUploadedFile('scopus.csv', csv_content, content_type='text/csv')},
            format='multipart',
        )
        article_count_after_first = Article.objects.count()

        response = self.client.post(
            self.import_url,
            {'file': SimpleUploadedFile('scopus.csv', csv_content, content_type='text/csv')},
            format='multipart',
        )

        # No new Article rows must be created.
        self.assertEqual(Article.objects.count(), article_count_after_first)
        # The response must signal the duplicate situation to the caller.
        self.assertIn('warning', response.data)

    def test_c03_real_scopus_csv_file_is_imported_correctly(self):
        """C-03 (System): The real project Scopus CSV (12 articles) is fully processed."""
        csv_path = os.path.join(
            os.path.dirname(__file__),
            '../../../../..',
            'scopus_export_Mar 19-2026_0de5d4a2-1a27-4bba-ad13-4f53b7d8c836.csv',
        )
        if not os.path.exists(csv_path):
            self.skipTest('Real Scopus CSV not found at expected path.')

        with open(csv_path, 'rb') as f:
            csv_file = SimpleUploadedFile('real_scopus.csv', f.read(), content_type='text/csv')

        response = self.client.post(self.import_url, {'file': csv_file}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # The 12-article file has 1 header row, so 12 data rows.
        imported_search = Search.objects.get(criteria=self.criteria)
        self.assertEqual(
            SearchResult.objects.filter(search=imported_search).count(), 12
        )


# ---------------------------------------------------------------------------
# US-09 — Semantic Scholar Search (Keywords)
# ---------------------------------------------------------------------------

class SemanticScholarSearchTestCase(APITestCase):
    """
    US-09 — Semantic Scholar keyword search.
    Successful searches must store results; failed searches must surface errors;
    empty keyword fields must be caught before any external call.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.client.force_login(self.owner)

    @patch('api.views.SemanticScholarAPI')
    def test_c06_successful_keyword_search_stores_results(self, mock_api_class):
        """C-06 (System): A valid keyword search retrieves papers and creates SearchResult rows."""
        mock_instance = mock_api_class.return_value
        mock_instance.search_papers.return_value = {
            'data': [_fake_ss_paper('ss-001', 'Deep Learning Survey'),
                     _fake_ss_paper('ss-002', 'Transformer Models')]
        }
        criteria = _make_ss_criteria(self.project, keywords='deep learning')
        url = f'{CRITERIA_URL}{criteria.pk}/execute_search/'

        response = self.client.post(url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        search = Search.objects.get(criteria=criteria)
        self.assertEqual(search.status, 'completed')
        self.assertEqual(SearchResult.objects.filter(search=search).count(), 2)

    @patch('api.views.SemanticScholarAPI')
    def test_c07_search_with_no_results_returns_error(self, mock_api_class):
        """C-07 (System): When the API returns no papers the response must signal an error."""
        mock_instance = mock_api_class.return_value
        mock_instance.search_papers.side_effect = Exception(
            'No papers found for the given query'
        )
        criteria = _make_ss_criteria(self.project, keywords='xyzzy_nonexistent_term_999')
        url = f'{CRITERIA_URL}{criteria.pk}/execute_search/'

        response = self.client.post(url, {}, format='json')

        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_429_TOO_MANY_REQUESTS,
        ])
        self.assertIn('error', response.data)
        self.assertEqual(SearchResult.objects.filter(search__criteria=criteria).count(), 0)

    def test_c08_empty_keywords_field_returns_validation_error(self):
        """C-08: execute_search with empty keywords returns 400 without making any external call."""
        criteria = _make_ss_criteria(self.project, keywords='')
        url = f'{CRITERIA_URL}{criteria.pk}/execute_search/'

        with patch('api.views.SemanticScholarAPI') as mock_api_class:
            response = self.client.post(url, {}, format='json')
            mock_api_class.assert_not_called()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)


# ---------------------------------------------------------------------------
# US-10 — List and Filter Articles
# ---------------------------------------------------------------------------

class ArticleFilterTestCase(APITestCase):
    """
    US-10 — Article listing and filtering.
    Users can filter by source type, by review status, and by a combination of both.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.client.force_login(self.owner)

        # Two searches: one SS, one Scopus.
        ss_criteria = _make_ss_criteria(self.project)
        scopus_criteria = _make_scopus_criteria(self.project)
        self.ss_search = Search.objects.create(criteria=ss_criteria, status='completed')
        self.scopus_search = Search.objects.create(criteria=scopus_criteria, status='completed')

        # SS articles: 1 pending, 1 included.
        self.ss_art_pending  = Article.objects.create(
            semantic_scholar_id='ss-pending', title='SS Pending', publication_year=2023,
            article_source='semantic_scholar'
        )
        self.ss_art_included = Article.objects.create(
            semantic_scholar_id='ss-included', title='SS Included', publication_year=2023,
            article_source='semantic_scholar'
        )
        # Scopus article: 1 pending.
        self.scopus_art_pending = Article.objects.create(
            semantic_scholar_id='sc-pending', title='Scopus Pending', publication_year=2023,
            article_source='scopus'
        )

        self.sr_ss_pending  = SearchResult.objects.create(
            search=self.ss_search, article=self.ss_art_pending,  rank=1, relevance='not_reviewed'
        )
        self.sr_ss_included = SearchResult.objects.create(
            search=self.ss_search, article=self.ss_art_included, rank=2, relevance='highly_relevant'
        )
        self.sr_scopus_pending = SearchResult.objects.create(
            search=self.scopus_search, article=self.scopus_art_pending, rank=1, relevance='not_reviewed'
        )

    def test_c09_no_filter_returns_all_results(self):
        """C-09: GET /search-results/ with no filter returns all 3 results."""
        response = self.client.get(RESULTS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)

    def test_c10_filter_by_source_returns_only_semantic_scholar_articles(self):
        """C-10: GET /articles/?article_source=semantic_scholar returns only SS articles."""
        response = self.client.get(ARTICLES_URL, {'article_source': 'semantic_scholar'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sources = {item['article_source'] for item in response.data['results']}
        self.assertEqual(sources, {'semantic_scholar'})
        self.assertEqual(response.data['count'], 2)

    def test_c11_filter_by_pending_status_returns_only_not_reviewed(self):
        """C-11: GET /search-results/?relevance=not_reviewed returns only pending results."""
        response = self.client.get(RESULTS_URL, {'relevance': 'not_reviewed'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        relevances = {item['relevance'] for item in response.data['results']}
        self.assertEqual(relevances, {'not_reviewed'})
        self.assertEqual(response.data['count'], 2)

    def test_c12_combined_source_and_status_filter_returns_correct_intersection(self):
        """C-12: Filtering by SS search + pending returns exactly the 1 SS pending article."""
        response = self.client.get(RESULTS_URL, {
            'search': self.ss_search.pk,
            'relevance': 'not_reviewed',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        result = response.data['results'][0]
        self.assertEqual(result['relevance'], 'not_reviewed')
        self.assertEqual(result['article']['article_source'], 'semantic_scholar')
