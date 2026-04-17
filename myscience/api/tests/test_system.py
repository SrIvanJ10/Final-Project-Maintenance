"""
System tests — complete system behaviour verified end-to-end.

These tests exercise the full stack (HTTP → view → service → DB) for
scenarios that involve file I/O, external-API mocking, complex data
pipelines, or cross-cutting concerns such as access control.
"""
import os
from unittest.mock import patch

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
)
from api.tests.helpers import (
    CRITERIA_URL,
    RESULTS_URL,
    ARTICLES_URL,
    PROJECT_URL,
    _make_project,
    _make_ss_criteria,
    _make_scopus_criteria,
    _make_scopus_csv,
    _fake_ss_paper,
)


# ===========================================================================
# BLOCK C — External Results Import (Scopus)
# US-08 (S-DATA-01)
# ===========================================================================

class ScopusImportTestCase(APITestCase):
    """
    US-08 — Scopus CSV import (System).
    Valid files must be processed; invalid formats must be rejected;
    uploading the same file twice must warn the user without adding duplicates.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project  = _make_project(self.owner)
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

        search  = Search.objects.get(criteria=self.criteria)
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

        self.assertEqual(Article.objects.count(), article_count_after_first)
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
        imported_search = Search.objects.get(criteria=self.criteria)
        self.assertEqual(
            SearchResult.objects.filter(search=imported_search).count(), 12
        )


# ===========================================================================
# BLOCK C — Semantic Scholar Search (Keywords)
# US-09 (S-DATA-02)
# ===========================================================================

class SemanticScholarSearchTestCase(APITestCase):
    """
    US-09 — Semantic Scholar keyword search (System).
    Successful searches must store results; failed searches must surface errors.
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


# ===========================================================================
# BLOCK C — List and Filter Articles
# US-10 (I-VIEW-02)
# ===========================================================================

class ArticleFilterTestCase(APITestCase):
    """
    US-10 — Article listing and filtering (System).
    Users can filter by source type, by review status, and by a combination of both.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.client.force_login(self.owner)

        ss_criteria     = _make_ss_criteria(self.project)
        scopus_criteria = _make_scopus_criteria(self.project)
        self.ss_search     = Search.objects.create(criteria=ss_criteria,     status='completed')
        self.scopus_search = Search.objects.create(criteria=scopus_criteria, status='completed')

        self.ss_art_pending = Article.objects.create(
            semantic_scholar_id='ss-pending', title='SS Pending', publication_year=2023,
            article_source='semantic_scholar'
        )
        self.ss_art_included = Article.objects.create(
            semantic_scholar_id='ss-included', title='SS Included', publication_year=2023,
            article_source='semantic_scholar'
        )
        self.scopus_art_pending = Article.objects.create(
            semantic_scholar_id='sc-pending', title='Scopus Pending', publication_year=2023,
            article_source='scopus'
        )

        self.sr_ss_pending = SearchResult.objects.create(
            search=self.ss_search, article=self.ss_art_pending, rank=1, relevance='not_reviewed'
        )
        self.sr_ss_included = SearchResult.objects.create(
            search=self.ss_search, article=self.ss_art_included, rank=2, relevance='highly_relevant'
        )
        self.sr_scopus_pending = SearchResult.objects.create(
            search=self.scopus_search, article=self.scopus_art_pending, rank=1,
            relevance='not_reviewed'
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


# ===========================================================================
# BLOCK E — Export Results (data contract)
# US-11 (S-EXP-01)
# ===========================================================================

class ExportResultsSystemTestCase(APITestCase):
    """
    US-11 — Export results, system-level data contract (System).

    Verifies the backend API contract required by the frontend export function:
    field presence, count accuracy, and deterministic ordering.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = Project.objects.create(
            title='Systematic Review 2024',
            description='Desc',
            owner=self.owner,
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        criteria    = SearchCriteria.objects.create(
            project=self.project, name='C', keywords='ai'
        )
        self.search = Search.objects.create(criteria=criteria, status='completed')
        self.client.force_login(self.owner)

    def _create_rich_article(self, uid):
        return Article.objects.create(
            semantic_scholar_id=f'exp-art-{uid}',
            title=f'Article {uid}: A Study',
            abstract='Some abstract.',
            authors=[{'name': f'Author {uid}'}],
            publication_year=2023,
            publication_venue=f'Journal {uid}',
            source_url=f'https://example.com/{uid}',
            article_source='semantic_scholar',
        )

    def _create_results(self, n):
        results = []
        for i in range(1, n + 1):
            art = self._create_rich_article(i)
            results.append(
                SearchResult.objects.create(
                    search=self.search, article=art, rank=i,
                    relevance='highly_relevant', reviewer_notes=f'Note {i}',
                )
            )
        return results

    def test_e01_api_returns_all_fields_required_by_export_function(self):
        """E-01 (System): With 5 results the API returns exactly 5 rows, each
        containing every field consumed by exportResultsCsv()."""
        self._create_results(5)

        response = self.client.get(RESULTS_URL, {'search': self.search.pk})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 5)

        required_result_fields  = {'rank', 'relevance', 'reviewer_notes', 'article'}
        required_article_fields = {
            'article_source', 'title', 'authors',
            'publication_year', 'publication_venue', 'source_url',
        }
        for item in response.data['results']:
            self.assertTrue(
                required_result_fields.issubset(item.keys()),
                msg=f'Missing result fields: {required_result_fields - set(item.keys())}',
            )
            self.assertTrue(
                required_article_fields.issubset(item['article'].keys()),
                msg=f'Missing article fields: {required_article_fields - set(item["article"].keys())}',
            )

    def test_e02_no_results_means_export_source_is_empty(self):
        """E-02 (System): When the project has no search results the API returns
        count=0, which triggers the 'There are no results to export' message in
        the frontend."""
        response = self.client.get(RESULTS_URL, {'search': self.search.pk})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_e01_result_rank_values_are_sequential_and_match_import_order(self):
        """E-01 (System): rank values in the API response match the order in which
        articles were imported, ensuring the CSV rows are deterministically ordered."""
        self._create_results(5)

        response = self.client.get(RESULTS_URL, {'search': self.search.pk})

        ranks = [item['rank'] for item in response.data['results']]
        self.assertEqual(ranks, sorted(ranks))


# ===========================================================================
# BLOCK I — System Administration
# US-18 (S-ADMIN-01)
# ===========================================================================

class SystemAdminTestCase(APITestCase):
    """
    US-18 — Admin panel access (System).
    I-01: Superusers can access the Django admin panel.
    I-02: Regular users are redirected to login or forbidden when attempting access.
    """

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin_boss', email='admin@test.com', password='pass12345!'
        )
        self.regular_user = User.objects.create_user(
            username='regular', email='reg@test.com', password='pass12345!'
        )
        self.admin_url = '/admin/'

    def test_i01_superuser_can_access_admin_panel(self):
        """I-01 (System): Admin user receives a 200/302 OK when accessing /admin/."""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.admin_url)

        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])

    def test_i02_regular_user_cannot_access_admin_panel(self):
        """I-02 (Security): Regular user accessing /admin/ is redirected to admin login (302)."""
        self.client.force_login(self.regular_user)
        response = self.client.get(self.admin_url)

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn('login', response.url.lower())
