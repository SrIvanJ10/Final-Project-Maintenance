"""
Tests para MyScience
"""

from django.test import TestCase
from django.contrib.auth.models import User
from core.models import (
    Project,
    ProjectMembership,
    SearchCriteria,
    Search,
    Article,
    SearchResult,
    SearchResultAssessment,
    ArticleDiscussionMessage,
)
from workflow.models import WorkflowPhase, ScreeningTask


class ProjectDomainLogicTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='testpass123')
        self.reviewer = User.objects.create_user(username='reviewer', password='testpass123')
        self.viewer = User.objects.create_user(username='viewer', password='testpass123')
        self.project = Project.objects.create(
            title='Domain Project',
            description='Desc',
            owner=self.owner,
            status='draft',
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        ProjectMembership.objects.create(project=self.project, user=self.reviewer, role='reviewer')
        ProjectMembership.objects.create(project=self.project, user=self.viewer, role='viewer')
        self.project.collaborators.add(self.reviewer, self.viewer)
        self.criteria = SearchCriteria.objects.create(project=self.project, name='Criteria', keywords='ai')
        self.search = Search.objects.create(criteria=self.criteria, status='completed')

        for rank in range(1, 6):
            article = Article.objects.create(
                semantic_scholar_id=f'article-{rank}',
                title=f'Article {rank}',
                publication_year=2024,
            )
            SearchResult.objects.create(
                search=self.search,
                article=article,
                rank=rank,
            )

    def test_distribute_screening_load_uses_all_project_members_with_access(self):
        distribution = self.project.distribute_screening_load()

        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'active')
        self.assertEqual(distribution['phase'].phase_type, 'screening')
        self.assertEqual(len(distribution['pending_results']), 5)
        self.assertEqual(
            {assignment['user'].username for assignment in distribution['assignments']},
            {'owner', 'reviewer', 'viewer'},
        )
        self.assertEqual(
            ScreeningTask.objects.filter(phase=distribution['phase']).count(),
            3,
        )

    def test_record_assessment_persists_vote_and_updates_result(self):
        result = SearchResult.objects.filter(search=self.search).first()

        assessment = result.record_assessment(
            reviewer=self.viewer,
            relevance='highly_relevant',
            notes='Looks good',
        )

        result.refresh_from_db()
        self.assertEqual(assessment.reviewer, self.viewer)
        self.assertEqual(
            SearchResultAssessment.objects.get(search_result=result, reviewer=self.viewer).relevance,
            'highly_relevant',
        )
        self.assertEqual(result.relevance, 'not_reviewed')

    def test_validate_project_article_pair_rejects_articles_outside_project(self):
        outsider_article = Article.objects.create(
            semantic_scholar_id='outside-article',
            title='Outside article',
            publication_year=2024,
        )

        with self.assertRaisesMessage(ValueError, 'This article does not belong to the selected project'):
            ArticleDiscussionMessage.validate_project_article_pair(
                project=self.project,
                article=outsider_article,
                user=self.owner,
            )

