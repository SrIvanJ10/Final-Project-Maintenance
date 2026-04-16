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

# ===========================================================================
# BLOCK A — Authentication & Collaborators
# US-01 (I-AUTH-01), US-02 (I-AUTH-02), US-05 (I-COLL-01)
# ===========================================================================

class RegistrationTestCase(APITestCase):
    """
    US-01 — New user registration.
    Registration must create the account with the provided data,
    return 201, and leave the user authenticated immediately.
    """

    URL = '/api/v1/auth/register/'

    def test_a01_successful_registration_returns_201_and_user_data(self):
        """A-01: Valid registration creates the account and returns 201."""
        payload = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
        }
        response = self.client.post(self.URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['username'], 'newuser')
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_a01_user_is_authenticated_after_registration(self):
        """A-01: After registering, /auth/me/ returns the user without a separate login step."""
        payload = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
        }
        self.client.post(self.URL, payload, format='json')

        me_response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data['user']['username'], 'newuser')

    def test_a01_registration_fails_when_required_fields_are_missing(self):
        """A-01 edge: Incomplete payload returns 400."""
        response = self.client.post(self.URL, {'username': 'incomplete'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a01_registration_fails_with_duplicate_username(self):
        """A-01 edge: Already-taken username returns 400."""
        User.objects.create_user(
            username='taken', email='taken@example.com', password='pass12345'
        )
        payload = {
            'username': 'taken',
            'email': 'other@example.com',
            'password': 'pass12345',
        }
        response = self.client.post(self.URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data.get('error', ''))

    def test_a01_registration_fails_with_duplicate_email(self):
        """A-01 edge: Already-registered email returns 400."""
        User.objects.create_user(
            username='user1', email='dup@example.com', password='pass12345'
        )
        payload = {
            'username': 'user2',
            'email': 'dup@example.com',
            'password': 'pass12345',
        }
        response = self.client.post(self.URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data.get('error', ''))


class AuthenticationTestCase(APITestCase):
    """
    US-02 — Login and logout.
    Login must validate credentials and open a session.
    Logout must close the session and block subsequent access.
    """

    LOGIN_URL = '/api/v1/auth/login/'
    LOGOUT_URL = '/api/v1/auth/logout/'
    ME_URL = '/api/v1/auth/me/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='correctpass123',
        )

    def test_a02_login_with_correct_credentials_returns_200(self):
        """A-02: Correct credentials return 200 and user data."""
        payload = {'username': 'testuser', 'password': 'correctpass123'}
        response = self.client.post(self.LOGIN_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['username'], 'testuser')

    def test_a03_login_with_wrong_password_returns_401(self):
        """A-03: Wrong password returns 401 with an error message."""
        payload = {'username': 'testuser', 'password': 'wrongpass'}
        response = self.client.post(self.LOGIN_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('error', response.data)

    def test_a03_login_with_nonexistent_user_returns_401(self):
        """A-03 edge: Unknown username returns 401."""
        payload = {'username': 'nobody', 'password': 'whatever123'}
        response = self.client.post(self.LOGIN_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a04_logout_of_authenticated_user_returns_200(self):
        """A-04: Successful logout returns 200 with confirmation."""
        self.client.force_login(self.user)

        response = self.client.post(self.LOGOUT_URL, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('detail'), 'logged out')

    def test_a04_me_endpoint_is_inaccessible_after_logout(self):
        """A-04: After logout, /auth/me/ returns 403."""
        self.client.force_login(self.user)
        self.client.post(self.LOGOUT_URL, format='json')

        me_response = self.client.get(self.ME_URL)

        self.assertEqual(me_response.status_code, status.HTTP_403_FORBIDDEN)


class CollaboratorManagementTestCase(APITestCase):
    """
    US-05 — Adding collaborators and role assignment.
    The owner can add members with a role.
    Trying to add someone already in the project warns without duplicating.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='ownerpass123'
        )
        self.collaborator = User.objects.create_user(
            username='collab', email='collab@example.com', password='collabpass123'
        )
        self.project = Project.objects.create(
            title='Test Project',
            description='A test project',
            owner=self.owner,
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        self.add_url = f'/api/v1/projects/{self.project.pk}/add_collaborator/'
        self.client.force_login(self.owner)

    def test_a05_owner_adds_collaborator_with_role(self):
        """A-05: Owner adds a new collaborator with role 'reviewer'."""
        payload = {'username': 'collab', 'role': 'reviewer'}
        response = self.client.post(self.add_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'collaborator added')
        self.assertEqual(response.data['collaborator']['role'], 'reviewer')
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.collaborator,
                role='reviewer',
            ).exists()
        )

    def test_a06_adding_existing_member_warns_and_does_not_duplicate(self):
        """A-06: Re-adding an existing member returns a warning and no duplicate membership is created."""
        ProjectMembership.objects.create(
            project=self.project, user=self.collaborator, role='reviewer')
        self.project.collaborators.add(self.collaborator)

        payload = {'username': 'collab', 'role': 'viewer'}
        response = self.client.post(self.add_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'collaborator updated')
        membership_count = ProjectMembership.objects.filter(
            project=self.project, user=self.collaborator
        ).count()
        self.assertEqual(membership_count, 1)

# ===========================================================================
# BLOCK C — Search Sources, Import & Filtering
# US-07 (I-DATA-01), US-08 (S-DATA-01), US-09 (S-DATA-02), US-10 (I-VIEW-02)
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

        ss_criteria = _make_ss_criteria(self.project)
        scopus_criteria = _make_scopus_criteria(self.project)
        self.ss_search = Search.objects.create(criteria=ss_criteria, status='completed')
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
