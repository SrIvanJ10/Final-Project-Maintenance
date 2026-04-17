"""
Integration tests — multiple components working together.

These tests verify that API endpoints, the database, and business logic
interact correctly through complete HTTP request/response cycles.
"""
import json
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
    SearchResultAssessment,
)
from workflow.models import ScreeningTask, WorkflowPhase
from api.tests.helpers import (
    PROJECT_URL,
    CRITERIA_URL,
    _make_project,
    _make_search_result,
    _make_ss_criteria,
    _make_pending_results,
    _project_payload,
    _fake_ss_paper,
)


# ===========================================================================
# BLOCK A — Authentication & Collaborators
# US-01 (I-AUTH-01), US-02 (I-AUTH-02), US-05 (I-COLL-01)
# ===========================================================================

class RegistrationTestCase(APITestCase):
    """
    US-01 — New user registration (happy path).
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


class AuthenticationTestCase(APITestCase):
    """
    US-02 — Login and logout (happy path).
    Login must validate credentials and open a session.
    Logout must close the session and block subsequent access.
    """

    LOGIN_URL  = '/api/v1/auth/login/'
    LOGOUT_URL = '/api/v1/auth/logout/'
    ME_URL     = '/api/v1/auth/me/'

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
# BLOCK B — Projects & Inclusion Criteria
# US-03 (I-PROJ-01), US-04 (I-PROJ-02), US-06 (I-VIEW-01)
# ===========================================================================

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


class InclusionCriteriaTestCase(APITestCase):
    """
    US-04 — Inclusion criteria management (happy path).
    Owners can modify criteria freely.
    After a modification, all members can read the updated value.
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


class DashboardIntegrationTestCase(APITestCase):
    """
    US-06 — Project dashboard statistics (Integration).
    The statistics endpoint must correctly reflect accepted, rejected,
    and pending article counts when the project has data.
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


# ===========================================================================
# BLOCK C — Search Source Configuration
# US-07 (I-DATA-01)
# ===========================================================================

class SearchCriteriaTestCase(APITestCase):
    """
    US-07 — Search source configuration (happy path).
    A valid query must be saved and immediately executable.
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


# ===========================================================================
# BLOCK D — Screening Distribution & Queue
# US-12 (U-WORK-01), US-13 (I-VOTE-01)
# ===========================================================================

class StartReviewTestCase(APITestCase):
    """
    US-12 — start_review endpoint.
    D-01: Owner starts review → 200, tasks created, phase active.
    D-02: Non-owner → 403.
    D-03: No pending articles → 400.
    """

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pass12345!')
        self.bob   = User.objects.create_user(username='bob',   password='pass12345!')
        self.carol = User.objects.create_user(username='carol', password='pass12345!')

        self.project = Project.objects.create(
            title='Review Project',
            description='Desc',
            owner=self.alice,
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        ProjectMembership.objects.create(project=self.project, user=self.bob,   role='reviewer')
        ProjectMembership.objects.create(project=self.project, user=self.carol, role='reviewer')
        self.project.collaborators.add(self.bob, self.carol)

        criteria     = SearchCriteria.objects.create(project=self.project, name='C', keywords='ai')
        self.search  = Search.objects.create(criteria=criteria, status='completed')
        self.results = _make_pending_results(self.search, n=5, prefix='rev')
        self.start_url = f'/api/v1/projects/{self.project.pk}/start_review/'

    def test_d01_owner_starts_review_returns_200_and_distributes_tasks(self):
        """D-01 (Integration): Owner triggers start_review → 200, status review_started,
        3 entries in distributed_to, ScreeningPhase is_active=True, ScreeningTasks created."""
        self.client.force_login(self.alice)

        response = self.client.post(self.start_url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'review_started')
        self.assertEqual(len(response.data['distributed_to']), 3)

        phase = WorkflowPhase.objects.get(project=self.project, phase_type='screening')
        self.assertTrue(phase.is_active)
        self.assertGreaterEqual(ScreeningTask.objects.filter(phase=phase).count(), 1)

    def test_d02_non_owner_cannot_start_review(self):
        """D-02 (Integration): Reviewer calls start_review → 403, no tasks created."""
        self.client.force_login(self.bob)

        response = self.client.post(self.start_url, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Only the project owner can start the review', response.data.get('error', ''))
        self.assertEqual(ScreeningTask.objects.count(), 0)

    def test_d03_start_review_fails_when_no_pending_articles(self):
        """D-03 (Integration): No not_reviewed results → 400, no ScreeningPhase activated."""
        for result in self.results:
            result.relevance = 'highly_relevant'
            result.save(update_fields=['relevance'])

        self.client.force_login(self.alice)
        response = self.client.post(self.start_url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('There are no pending articles to distribute', response.data.get('error', ''))
        self.assertFalse(
            WorkflowPhase.objects.filter(project=self.project, is_active=True).exists()
        )


class ScreeningQueueIntegrationTestCase(APITestCase):
    """
    US-13 — Individual assessment (Integration).
    D-05: Reviewer votes on an article → assessment recorded,
          next article still pending.
    """

    def setUp(self):
        self.owner    = User.objects.create_user(username='owner',    password='pass12345!')
        self.reviewer = User.objects.create_user(username='reviewer', password='pass12345!')

        self.project = Project.objects.create(
            title='Queue Project',
            description='Desc',
            owner=self.owner,
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        ProjectMembership.objects.create(project=self.project, user=self.reviewer, role='reviewer')
        self.project.collaborators.add(self.reviewer)

        criteria    = SearchCriteria.objects.create(project=self.project, name='C', keywords='ai')
        self.search = Search.objects.create(criteria=criteria, status='completed')
        self.results = _make_pending_results(self.search, n=3, prefix='queue')

    def test_d05_reviewer_votes_include_and_assessment_is_recorded(self):
        """D-05 (Integration): POST assess_relevance records the vote and the remaining
        articles are still pending."""
        self.client.force_login(self.reviewer)
        url = f'/api/v1/search-results/{self.results[0].pk}/assess_relevance/'

        response = self.client.post(url, {'relevance': 'highly_relevant'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(
            SearchResultAssessment.objects.filter(
                search_result=self.results[0],
                reviewer=self.reviewer,
                relevance='highly_relevant',
            ).exists()
        )
        pending = SearchResult.objects.filter(
            search=self.search,
        ).exclude(
            assessments__reviewer=self.reviewer,
        ).count()
        self.assertEqual(pending, 2)


# ===========================================================================
# BLOCK F — Team Consensus
# US-14 (U-CONS-01)
# ===========================================================================

class ConsensusTestCase(APITestCase):
    """
    US-14 — Team Consensus Logic.
    F-01: A single 'not_relevant' vote automatically rejects the article.
    """

    def setUp(self):
        self.owner    = User.objects.create_user(username='owner_cons', password='pass12345!')
        self.reviewer = User.objects.create_user(username='rev_cons',   password='pass12345!')

        self.project = Project.objects.create(
            title='Consensus Project', owner=self.owner,
        )
        ProjectMembership.objects.create(project=self.project, user=self.reviewer, role='reviewer')
        self.project.collaborators.add(self.reviewer)

        self.criteria = SearchCriteria.objects.create(project=self.project, name='C')
        self.search   = Search.objects.create(criteria=self.criteria, status='completed')
        self.article  = Article.objects.create(title='Test Article', publication_year=2024)
        self.result   = SearchResult.objects.create(
            search=self.search, article=self.article, rank=1, relevance='pending'
        )
        self.url = f'/api/v1/search-results/{self.result.pk}/assess_relevance/'

    def test_f01_single_negative_vote_rejects_article_immediately(self):
        """F-01 (Integration): A single 'not_relevant' assessment automatically updates
        the SearchResult relevance to rejected."""
        self.client.force_login(self.reviewer)

        response = self.client.post(
            self.url,
            {'relevance': 'not_relevant', 'notes': 'Bad methodology'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.result.refresh_from_db()
        self.assertEqual(self.result.relevance, 'not_relevant')


# ===========================================================================
# BLOCK G — AI Support (happy path)
# US-15 (I-AI-01)
# ===========================================================================

class AISuggestionsIntegrationTestCase(APITestCase):
    """
    US-15 — AI Suggestions for Screening (Integration).
    G-01: Explicit request generates a suggestion and saves interaction in DB.
    """

    def setUp(self):
        self.reviewer = User.objects.create_user(username='ai_rev', password='pass12345!')
        self.project  = Project.objects.create(
            title='AI Project', owner=self.reviewer,
            inclusion_criteria='Must include Machine Learning.',
        )
        self.criteria = SearchCriteria.objects.create(project=self.project)
        self.search   = Search.objects.create(criteria=self.criteria, status='completed')
        self.article  = Article.objects.create(title='AI Article')
        self.result   = SearchResult.objects.create(
            search=self.search, article=self.article, rank=1
        )

        self.client.force_login(self.reviewer)
        self.url = f'/api/v1/search-results/{self.result.pk}/suggest_with_ai/'

    @patch('api.views.request_article_suggestion')
    def test_g01_successful_ai_request_saves_interaction(self, mock_ai):
        """G-01 (Integration): AI returns suggestion, DB records interaction as completed."""
        mock_ai.return_value = {
            "prompt": "Test prompt",
            "raw_text": "Include this.",
            "payload": {},
            "parsed": {"recommendation": "include", "rationale": "Matches ML criteria."},
        }

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['recommendation'], "include")

        interaction = ArticleAIInteraction.objects.get(search_result=self.result)
        self.assertEqual(interaction.status, 'completed')
        self.assertEqual(interaction.rationale, "Matches ML criteria.")
        self.assertEqual(interaction.requested_by, self.reviewer)


# ===========================================================================
# BLOCK H — Discussion Threads (happy path)
# US-16 (I-COMM-01)
# ===========================================================================

class DiscussionThreadIntegrationTestCase(APITestCase):
    """
    US-16 — Chat-style discussion thread (Integration).
    H-01: Valid user can add a comment to the thread.
    """

    def setUp(self):
        self.user    = User.objects.create_user(username='chatter', password='pass12345!')
        self.project = Project.objects.create(title='Chat Project', owner=self.user)
        self.article = Article.objects.create(title='Chat Article')

        ProjectMembership.objects.create(project=self.project, user=self.user, role='reviewer')

        criteria = SearchCriteria.objects.create(project=self.project, keywords='test')
        search   = Search.objects.create(criteria=criteria, status='completed')
        SearchResult.objects.create(search=search, article=self.article, rank=1)

        self.client.force_login(self.user)
        self.list_url = '/api/v1/article-discussions/'

    def test_h01_user_can_post_comment_to_thread(self):
        """H-01 (Integration): Valid comment returns 201 and creates object in DB."""
        payload = {
            'project': self.project.pk,
            'article': self.article.pk,
            'message': 'This methodology is flawed.',
        }

        response = self.client.post(self.list_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['message'], 'This methodology is flawed.')

        self.assertTrue(
            ArticleDiscussionMessage.objects.filter(
                project=self.project, article=self.article, author=self.user
            ).exists()
        )
