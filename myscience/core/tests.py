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


# ===========================================================================
# BLOCK D (Unit) — Workload Distribution & Consensus Logic
# US-12 (U-WORK-01), US-14 (U-CONS-01)
# ===========================================================================

def _make_article(uid):
    return Article.objects.create(
        semantic_scholar_id=f'art-{uid}',
        title=f'Article {uid}',
        publication_year=2024,
    )


class DistributionAlgorithmTestCase(TestCase):
    """
    US-12 — D-04: Workload distribution algorithm.
    7 articles across 3 participants must be split 3 / 2 / 2 (remainder to first).
    Participants are ordered by DB id, so the owner (created first) gets the extra article.
    """

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pass12345!')
        self.bob   = User.objects.create_user(username='bob',   password='pass12345!')
        self.carol = User.objects.create_user(username='carol', password='pass12345!')

        self.project = Project.objects.create(
            title='Distribution Test',
            description='Desc',
            owner=self.alice,
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        ProjectMembership.objects.create(project=self.project, user=self.bob,   role='reviewer')
        ProjectMembership.objects.create(project=self.project, user=self.carol, role='reviewer')
        self.project.collaborators.add(self.bob, self.carol)

        criteria = SearchCriteria.objects.create(project=self.project, name='C', keywords='ai')
        search   = Search.objects.create(criteria=criteria, status='completed')
        for i in range(1, 8):
            SearchResult.objects.create(search=search, article=_make_article(i), rank=i)

    def test_d04_seven_articles_are_split_3_2_2_across_three_participants(self):
        """D-04 (Unit): 7 articles / 3 participants → alice:3, bob:2, carol:2."""
        distribution = self.project.distribute_screening_load()

        by_user = {a['user'].username: a['assigned_results'] for a in distribution['assignments']}
        self.assertEqual(by_user['alice'], 3)
        self.assertEqual(by_user['bob'],   2)
        self.assertEqual(by_user['carol'], 2)
        self.assertEqual(sum(by_user.values()), 7)


class ConsensusLogicTestCase(TestCase):
    """
    US-14 — Consensus engine unit tests.
    D-08: Partial votes keep status pending.
    D-09: All required reviewers vote to include → unanimous inclusion.
    D-11: Adding a new reviewer reverts a finished consensus back to pending.
    """

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pass12345!')
        self.bob   = User.objects.create_user(username='bob',   password='pass12345!')

        self.project = Project.objects.create(
            title='Consensus Test',
            description='Desc',
            owner=self.alice,
            research_question='RQ',
            objectives='OBJ',
            scope='Scope',
        )
        ProjectMembership.objects.create(project=self.project, user=self.bob, role='reviewer')
        self.project.collaborators.add(self.bob)

        criteria = SearchCriteria.objects.create(project=self.project, name='C', keywords='ai')
        search   = Search.objects.create(criteria=criteria, status='completed')
        self.result = SearchResult.objects.create(
            search=search, article=_make_article('p001'), rank=1
        )

    def test_d08_consensus_is_pending_when_not_all_reviewers_have_voted(self):
        """D-08 (Unit): Alice votes but Bob has not → consensus stays 'not_reviewed'."""
        self.result.record_assessment(reviewer=self.alice, relevance='highly_relevant')

        self.result.refresh_from_db()
        self.assertEqual(self.result.relevance, 'not_reviewed')

        pending = self.result.search.criteria.project.get_reviewers().exclude(
            id__in=SearchResultAssessment.objects.filter(
                search_result=self.result
            ).values_list('reviewer_id', flat=True)
        )
        self.assertIn(self.bob, pending)

    def test_d09_unanimous_inclusion_when_all_reviewers_vote_to_include(self):
        """D-09 (Unit): Alice votes 'highly_relevant', Bob votes 'relevant' → consensus 'highly_relevant'."""
        self.result.record_assessment(reviewer=self.alice, relevance='highly_relevant')
        self.result.record_assessment(reviewer=self.bob,   relevance='relevant')

        self.result.refresh_from_db()
        self.assertEqual(self.result.relevance, 'highly_relevant')

        pending = self.result.search.criteria.project.get_reviewers().exclude(
            id__in=SearchResultAssessment.objects.filter(
                search_result=self.result
            ).values_list('reviewer_id', flat=True)
        )
        self.assertEqual(pending.count(), 0)

    def test_d11_adding_new_reviewer_reverts_consensus_to_pending(self):
        """D-11 (Unit): After unanimous inclusion, adding Carol as reviewer reverts consensus to 'not_reviewed'."""
        self.result.record_assessment(reviewer=self.alice, relevance='highly_relevant')
        self.result.record_assessment(reviewer=self.bob,   relevance='highly_relevant')
        self.result.refresh_from_db()
        self.assertEqual(self.result.relevance, 'highly_relevant')

        carol = User.objects.create_user(username='carol', password='pass12345!')
        ProjectMembership.objects.create(project=self.project, user=carol, role='reviewer')
        self.project.collaborators.add(carol)

        # Simulate what add_collaborator does: resync all project results.
        for sr in SearchResult.objects.filter(search__criteria__project=self.project):
            sr.sync_consensus_decision()

        self.result.refresh_from_db()
        self.assertEqual(self.result.relevance, 'not_reviewed')

        pending = self.result.search.criteria.project.get_reviewers().exclude(
            id__in=SearchResultAssessment.objects.filter(
                search_result=self.result
            ).values_list('reviewer_id', flat=True)
        )
        self.assertIn(carol, pending)

