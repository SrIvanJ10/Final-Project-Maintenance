import json
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import (
    Project,
    ProjectMembership,
    SearchCriteria,
    Search,
    Article,
    SearchResult,
)

# ===========================================================================
# BLOCK B — Projects, Inclusion Criteria & Dashboard
# US-03 (I-PROJ-01), US-04 (I-PROJ-02), US-06 (I-VIEW-01)
# ===========================================================================

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

PROJECT_URL = '/api/v1/projects/'

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


def _make_search_result(search, rank, relevance='not_reviewed'):
    article = Article.objects.create(
        semantic_scholar_id=f'art-{search.id}-{rank}',
        title=f'Article {rank}',
        publication_year=2023,
    )
    return SearchResult.objects.create(
        search=search, article=article, rank=rank, relevance=relevance
    )


# ---------------------------------------------------------------------------
# US-03 — Systematic Review Creation
# ---------------------------------------------------------------------------

class ProjectCreationTestCase(APITestCase):
    """
    US-03 — Creating a systematic review.
    When a project is created without explicit inclusion criteria the system
    calls the LLM to generate a PRISMA 2020 proposal automatically.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.client.force_login(self.user)

    @patch('api.views.generate_project_inclusion_criteria')
    def test_b01_project_creation_triggers_llm_for_inclusion_criteria(self, mock_llm):
        """B-01: Creating a project without criteria calls the LLM and stores the result."""
        mock_llm.return_value = {'text': 'LLM-generated PRISMA criteria.'}

        response = self.client.post(PROJECT_URL, _project_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_llm.assert_called_once()
        project = Project.objects.get(pk=response.data['id'])
        self.assertEqual(project.inclusion_criteria, 'LLM-generated PRISMA criteria.')

    @patch('api.views.generate_project_inclusion_criteria')
    def test_b01_project_creation_falls_back_to_template_when_llm_fails(self, mock_llm):
        """B-01: When the LLM raises an exception the system falls back to the default PRISMA template."""
        mock_llm.side_effect = Exception('LLM service unavailable')

        response = self.client.post(PROJECT_URL, _project_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(pk=response.data['id'])
        self.assertEqual(project.inclusion_criteria, Project.PRISMA_2020_INCLUSION_TEMPLATE)

    @patch('api.views.generate_project_inclusion_criteria')
    def test_b01_project_creation_skips_llm_when_criteria_provided(self, mock_llm):
        """B-01: When the caller already supplies criteria the LLM is never called."""
        payload = _project_payload(inclusion_criteria='Pre-written criteria.')
        response = self.client.post(PROJECT_URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_llm.assert_not_called()
        project = Project.objects.get(pk=response.data['id'])
        self.assertEqual(project.inclusion_criteria, 'Pre-written criteria.')


# ---------------------------------------------------------------------------
# US-04 — Inclusion Criteria Management
# ---------------------------------------------------------------------------

class InclusionCriteriaTestCase(APITestCase):
    """
    US-04 — Inclusion criteria management.
    Owners can modify criteria freely.
    Submitting empty criteria must be rejected with a warning.
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

    def test_b02_owner_can_modify_inclusion_criteria(self):
        """B-02: PATCH with new criteria updates the field and persists."""
        self.client.force_login(self.owner)
        new_criteria = 'Updated PRISMA criteria — version 2.'

        response = self.client.patch(
            self.detail_url, {'inclusion_criteria': new_criteria}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.inclusion_criteria, new_criteria)

    def test_b02_modified_criteria_are_visible_to_members(self):
        """B-02: After the owner updates criteria, a member can read the new value."""
        self.client.force_login(self.owner)
        new_criteria = 'Updated criteria visible to all.'
        self.client.patch(
            self.detail_url, {'inclusion_criteria': new_criteria}, format='json'
        )

        self.client.force_login(self.reviewer)
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['inclusion_criteria'], new_criteria)

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


# ---------------------------------------------------------------------------
# US-06 — Project Dashboard & Status
# ---------------------------------------------------------------------------

class DashboardTestCase(APITestCase):
    """
    US-06 — Project dashboard and status.
    The statistics endpoint must reflect the real state of articles:
    accepted, rejected, and pending counts.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.criteria = SearchCriteria.objects.create(
            project=self.project, name='Criteria', keywords='machine learning'
        )
        self.search = Search.objects.create(criteria=self.criteria, status='completed')
        self.stats_url = f'{PROJECT_URL}{self.project.pk}/statistics/'
        self.client.force_login(self.owner)

    def test_b05_new_project_has_all_counters_at_zero(self):
        """B-05 (Acceptance): A brand-new project with no imported articles shows 0 everywhere."""
        response = self.client.get(self.stats_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_results'], 0)
        self.assertEqual(response.data['included_results'], 0)
        self.assertEqual(response.data['articles'], 0)

    def test_b04_dashboard_shows_correct_counts_by_relevance(self):
        """B-04 (Integration): Statistics reflect accepted, rejected, and pending articles correctly."""
        _make_search_result(self.search, rank=1, relevance='highly_relevant')
        _make_search_result(self.search, rank=2, relevance='highly_relevant')
        _make_search_result(self.search, rank=3, relevance='not_relevant')
        _make_search_result(self.search, rank=4, relevance='not_reviewed')
        _make_search_result(self.search, rank=5, relevance='not_reviewed')

        response = self.client.get(self.stats_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_results'], 5)
        self.assertEqual(response.data['included_results'], 2)
        self.assertEqual(response.data['articles'], 5)

    def test_b06_dashboard_reflects_progress_after_partial_screening(self):
        """B-06 (Acceptance): With 100 articles and 25 voted on, totals match the Gherkin scenario."""
        for i in range(1, 26):
            _make_search_result(self.search, rank=i, relevance='highly_relevant')
        for i in range(26, 101):
            _make_search_result(self.search, rank=i, relevance='not_reviewed')

        response = self.client.get(self.stats_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_results'], 100)
        self.assertEqual(response.data['included_results'], 25)