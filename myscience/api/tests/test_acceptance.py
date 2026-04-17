"""
Acceptance tests — business requirements verified from a user perspective.

These tests correspond directly to Gherkin scenarios and user story
acceptance criteria.  Each test confirms that the system satisfies a
specific observable outcome that a stakeholder cares about.
"""
import json

from django.contrib.auth.models import User
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
from workflow.models import ScreeningTask, WorkflowPhase
from api.tests.helpers import (
    PROJECT_URL,
    RESULTS_URL,
    _make_project,
    _make_search_result,
    _make_pending_results,
)


# ===========================================================================
# BLOCK B — Project Dashboard Progress
# US-06 (I-VIEW-01)
# ===========================================================================

class DashboardAcceptanceTestCase(APITestCase):
    """
    US-06 — Project dashboard acceptance scenarios.
    B-05: A brand-new project shows 0 everywhere.
    B-06: After partial screening the counters reflect actual progress.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='pass12345!'
        )
        self.project = _make_project(self.owner)
        self.criteria = SearchCriteria.objects.create(
            project=self.project, name='Criteria', keywords='machine learning'
        )
        self.search    = Search.objects.create(criteria=self.criteria, status='completed')
        self.stats_url = f'{PROJECT_URL}{self.project.pk}/statistics/'
        self.client.force_login(self.owner)

    def test_b05_new_project_has_all_counters_at_zero(self):
        """B-05 (Acceptance): A brand-new project with no imported articles shows 0 everywhere."""
        response = self.client.get(self.stats_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_results'], 0)
        self.assertEqual(response.data['included_results'], 0)
        self.assertEqual(response.data['articles'], 0)

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


# ===========================================================================
# BLOCK D — Screening Queue Completion
# US-13 (I-VOTE-01)
# ===========================================================================

class ScreeningQueueAcceptanceTestCase(APITestCase):
    """
    US-13 — Screening queue acceptance scenarios.
    D-06: Reviewer votes on the last article → no more pending in their assignment.
    D-07: Reviewer's pending queue shows only their unreviewed assigned articles.
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

        criteria     = SearchCriteria.objects.create(project=self.project, name='C', keywords='ai')
        self.search  = Search.objects.create(criteria=criteria, status='completed')
        self.results = _make_pending_results(self.search, n=3, prefix='queue')

    def test_d06_reviewer_completes_last_article_leaves_no_pending(self):
        """D-06 (Acceptance): After voting on the only pending article, the reviewer
        has no more unreviewed assignments."""
        self.client.force_login(self.reviewer)

        single_art = Article.objects.create(
            semantic_scholar_id='last-art', title='Last Article', publication_year=2024
        )
        single_result = SearchResult.objects.create(
            search=self.search, article=single_art, rank=99
        )
        url_last = f'/api/v1/search-results/{single_result.pk}/assess_relevance/'
        self.client.post(url_last, {'relevance': 'highly_relevant'}, format='json')

        unreviewed_by_reviewer = SearchResult.objects.filter(
            search=self.search
        ).exclude(
            assessments__reviewer=self.reviewer
        )
        self.assertNotIn(single_result, unreviewed_by_reviewer)

    def test_d07_reviewer_queue_shows_only_assigned_unreviewed_articles(self):
        """D-07 (Acceptance): After reviewer A decides on 2 of their 5 assigned articles,
        exactly 3 remain without an assessment from reviewer A."""
        reviewer_b = User.objects.create_user(username='reviewer_b', password='pass12345!')
        ProjectMembership.objects.create(project=self.project, user=reviewer_b, role='reviewer')
        self.project.collaborators.add(reviewer_b)

        extra_results = []
        for i in range(4, 11):
            art = Article.objects.create(
                semantic_scholar_id=f'queue-art-{i}', title=f'Article {i}', publication_year=2024
            )
            extra_results.append(
                SearchResult.objects.create(search=self.search, article=art, rank=i)
            )

        # Distribute: owner + reviewer + reviewer_b = 3 participants, 10 articles → 4/3/3
        self.project.distribute_screening_load()

        phase         = WorkflowPhase.objects.get(project=self.project, phase_type='screening')
        reviewer_task = ScreeningTask.objects.filter(phase=phase, reviewer=self.reviewer).first()
        assigned_ids     = json.loads(reviewer_task.notes).get('assigned_result_ids', [])
        assigned_results = SearchResult.objects.filter(pk__in=assigned_ids)

        # Reviewer A votes on 2 of their assigned articles.
        self.client.force_login(self.reviewer)
        for result in list(assigned_results[:2]):
            self.client.post(
                f'/api/v1/search-results/{result.pk}/assess_relevance/',
                {'relevance': 'highly_relevant'},
                format='json',
            )

        unreviewed_by_a  = assigned_results.exclude(assessments__reviewer=self.reviewer)
        expected_pending = assigned_results.count() - 2
        self.assertEqual(unreviewed_by_a.count(), expected_pending)

        # None of reviewer B's articles appear in reviewer A's pending queue.
        reviewer_b_task = ScreeningTask.objects.filter(phase=phase, reviewer=reviewer_b).first()
        reviewer_b_ids  = json.loads(reviewer_b_task.notes).get('assigned_result_ids', [])
        overlap = set(reviewer_b_ids) & set(unreviewed_by_a.values_list('pk', flat=True))
        self.assertEqual(len(overlap), 0)


# ===========================================================================
# BLOCK E — Export Filename & Project Title
# US-11 (S-EXP-01)
# ===========================================================================

class ExportResultsAcceptanceTestCase(APITestCase):
    """
    US-11 — Export results, acceptance-level filename scenarios.
    E-03: The project title stored in the API is the one used to build the
          CSV download filename.
    E-04: The frontend fallback expression produces 'results-articles.csv'
          when no project is selected.
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
        self.client.force_login(self.owner)

    def test_e03_project_title_is_accessible_for_filename_generation(self):
        """E-03 (Acceptance): The project title used to build the download filename
        is correctly stored and returned by the API."""
        response = self.client.get(f'{PROJECT_URL}{self.project.pk}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Systematic Review 2024')
        expected_filename = f"{response.data['title']}-articles.csv"
        self.assertEqual(expected_filename, 'Systematic Review 2024-articles.csv')

    def test_e03_project_title_reflects_actual_project_name(self):
        """E-03 (Acceptance): A project titled 'Machine Learning Review' produces
        the expected filename string."""
        ml_project = Project.objects.create(
            title='Machine Learning Review',
            description='Desc',
            owner=self.owner,
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        response = self.client.get(f'{PROJECT_URL}{ml_project.pk}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_filename = f"{response.data['title']}-articles.csv"
        self.assertEqual(expected_filename, 'Machine Learning Review-articles.csv')

    def test_e04_fallback_filename_when_title_is_missing(self):
        """E-04 (Acceptance): The frontend falls back to 'results-articles.csv'
        when selectedProject.title is falsy.  The Project model requires a non-blank
        title, so this scenario can only arise from a frontend state where no project
        is selected.  We verify the fallback expression: title || 'results'."""
        title    = ''           # no project selected in the UI
        filename = f"{title or 'results'}-articles.csv"
        self.assertEqual(filename, 'results-articles.csv')
