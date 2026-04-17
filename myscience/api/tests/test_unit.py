"""
Unit tests — input validation, edge cases, and isolated logic.

These tests verify that individual components correctly reject invalid
inputs or boundary conditions.  Each test exercises a single rule in
isolation, with minimal or no dependency on external services.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import (
    Article,
    ArticleAIInteraction,
    ArticleDiscussionMessage,
    Project,
    ProjectMembership,
    Search,
    SearchCriteria,
    SearchResult,
)
from api.llm import LLMServiceError
from api.tests.helpers import (
    PROJECT_URL,
    CRITERIA_URL,
    _make_project,
    _make_ss_criteria,
)


# ===========================================================================
# BLOCK A — Authentication Validation
# US-01 (I-AUTH-01), US-02 (I-AUTH-02)
# ===========================================================================

class RegistrationValidationTestCase(APITestCase):
    """
    US-01 — Registration edge cases.
    Incomplete or duplicate data must be rejected with 400.
    """

    URL = '/api/v1/auth/register/'

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


class AuthenticationValidationTestCase(APITestCase):
    """
    US-02 — Login edge cases.
    Wrong or non-existent credentials must be rejected with 401.
    """

    LOGIN_URL = '/api/v1/auth/login/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='correctpass123',
        )

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


# ===========================================================================
# BLOCK B — Inclusion Criteria Validation
# US-04 (I-PROJ-02)
# ===========================================================================

class InclusionCriteriaValidationTestCase(APITestCase):
    """
    US-04 — Inclusion criteria validation.
    Submitting empty criteria must be rejected with 400 and leave the
    original value unchanged.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.reviewer = User.objects.create_user(
            username='reviewer', email='reviewer@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        ProjectMembership.objects.create(
            project=self.project, user=self.reviewer, role='reviewer'
        )
        self.project.collaborators.add(self.reviewer)
        self.detail_url = f'{PROJECT_URL}{self.project.pk}/'

    def test_b03_deleting_inclusion_criteria_is_rejected(self):
        """B-03: PATCH with empty inclusion_criteria must return 400 and leave the field unchanged."""
        self.client.force_login(self.reviewer)
        original_criteria = self.project.inclusion_criteria

        response = self.client.patch(
            self.detail_url, {'inclusion_criteria': ''}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.project.refresh_from_db()
        self.assertEqual(self.project.inclusion_criteria, original_criteria)


# ===========================================================================
# BLOCK C — Search Validation
# US-07 (I-DATA-01), US-09 (S-DATA-02)
# ===========================================================================

class SearchCriteriaValidationTestCase(APITestCase):
    """
    US-07 — Search source configuration edge cases.
    An empty keyword field must be caught before creating any Search.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.client.force_login(self.owner)

    def test_c02_empty_keywords_are_rejected_on_execute(self):
        """C-02: Executing a search with no keywords returns 400 and creates no Search."""
        criteria = _make_ss_criteria(self.project, keywords='')
        url = f'{CRITERIA_URL}{criteria.pk}/execute_search/'

        response = self.client.post(url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertEqual(Search.objects.filter(criteria=criteria).count(), 0)


class SearchKeywordsValidationTestCase(APITestCase):
    """
    US-09 — Keyword search edge cases.
    An empty keyword field must return 400 without making any external call.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.client.force_login(self.owner)

    def test_c08_empty_keywords_field_returns_validation_error(self):
        """C-08: execute_search with empty keywords returns 400 without making any external call."""
        criteria = _make_ss_criteria(self.project, keywords='')
        url = f'{CRITERIA_URL}{criteria.pk}/execute_search/'

        with patch('api.views.SemanticScholarAPI') as mock_api_class:
            response = self.client.post(url, {}, format='json')
            mock_api_class.assert_not_called()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)


# ===========================================================================
# BLOCK G — AI Support Edge Cases
# US-15 (I-AI-01)
# ===========================================================================

class AISuggestionsValidationTestCase(APITestCase):
    """
    US-15 — AI suggestions edge and failure cases.
    G-02: Empty inclusion criteria returns 400.
    G-03: LLM provider failure is caught, logged in DB, and returns 400.
    """

    def setUp(self):
        self.reviewer = User.objects.create_user(username='ai_rev', password='pass12345!')
        self.project = Project.objects.create(
            title='AI Project', owner=self.reviewer, inclusion_criteria='Must include Machine Learning.'
        )
        self.criteria = SearchCriteria.objects.create(project=self.project)
        self.search = Search.objects.create(criteria=self.criteria, status='completed')
        self.article = Article.objects.create(title='AI Article')
        self.result = SearchResult.objects.create(search=self.search, article=self.article, rank=1)

        self.client.force_login(self.reviewer)
        self.url = f'/api/v1/search-results/{self.result.pk}/suggest_with_ai/'

    def test_g02_ai_request_fails_if_inclusion_criteria_is_empty(self):
        """G-02 (Edge): Missing project inclusion criteria returns 400 Bad Request."""
        self.project.inclusion_criteria = ''
        self.project.save()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Project inclusion_criteria is empty', response.data.get('error', ''))
        self.assertFalse(ArticleAIInteraction.objects.filter(search_result=self.result).exists())

    @patch('api.views.request_article_suggestion')
    def test_g03_llm_service_error_is_caught_and_saved_in_db(self, mock_ai):
        """G-03 (Edge): LLM API downtime returns 400 and saves 'failed' state in DB."""
        mock_ai.side_effect = LLMServiceError("OpenAI API is down")

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        interaction = ArticleAIInteraction.objects.get(search_result=self.result)
        self.assertEqual(interaction.status, 'failed')
        self.assertEqual(interaction.error_message, "OpenAI API is down")


# ===========================================================================
# BLOCK H — Discussion Thread Security
# US-16 (I-COMM-01)
# ===========================================================================

class DiscussionThreadSecurityTestCase(APITestCase):
    """
    US-16 — Discussion thread immutability.
    Deletion and editing of comments are strictly forbidden (405) to
    maintain the audit trail.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='chatter', password='pass12345!')
        self.project = Project.objects.create(title='Chat Project', owner=self.user)
        self.article = Article.objects.create(title='Chat Article')

        ProjectMembership.objects.create(project=self.project, user=self.user, role='reviewer')

        criteria = SearchCriteria.objects.create(project=self.project, keywords='test')
        search = Search.objects.create(criteria=criteria, status='completed')
        SearchResult.objects.create(search=search, article=self.article, rank=1)

        self.client.force_login(self.user)
        self.list_url = '/api/v1/article-discussions/'

    def test_h02_comment_deletion_is_prevented(self):
        """H-02 (Security/Edge): DELETE method is blocked to maintain audit trail."""
        message = ArticleDiscussionMessage.objects.create(
            project=self.project, article=self.article, author=self.user, message='To be deleted'
        )
        detail_url = f'{self.list_url}{message.pk}/'

        response = self.client.delete(detail_url)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(ArticleDiscussionMessage.objects.filter(pk=message.pk).exists())

    def test_h03_comment_editing_is_prevented(self):
        """H-03 (Security/Edge): PATCH/PUT methods are blocked to maintain audit trail."""
        message = ArticleDiscussionMessage.objects.create(
            project=self.project, article=self.article, author=self.user, message='Original'
        )
        detail_url = f'{self.list_url}{message.pk}/'

        response = self.client.patch(detail_url, {'message': 'Edited secretly'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        message.refresh_from_db()
        self.assertEqual(message.message, 'Original')
