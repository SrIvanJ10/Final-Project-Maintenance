from rest_framework import serializers
from core.models import (
    Project,
    SearchCriteria,
    Search,
    Article,
    SearchResult,
    SearchResultAssessment,
    ArticleAIInteraction,
    ArticleDiscussionMessage,
    ProjectMembership,
)
from workflow.models import WorkflowPhase, ScreeningTask, DataExtractionTemplate, ExtractedData
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class ProjectSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    collaborators = serializers.SerializerMethodField()
    
    class Meta:
        model = Project
        fields = [
            'id', 'title', 'description', 'owner', 'status',
            'research_question', 'objectives', 'scope', 'inclusion_criteria',
            'created_at', 'updated_at', 'start_date', 'end_date',
            'collaborators'
        ]

    def get_collaborators(self, obj):
        memberships = obj.get_memberships()
        return [
            {
                'id': membership.user.id,
                'username': membership.user.username,
                'email': membership.user.email,
                'first_name': membership.user.first_name,
                'last_name': membership.user.last_name,
                'role': membership.role,
                'membership_id': membership.id,
            }
            for membership in memberships
        ]


class SearchCriteriaSerializer(serializers.ModelSerializer):
    keywords_list = serializers.SerializerMethodField()
    
    class Meta:
        model = SearchCriteria
        fields = [
            'id', 'project', 'name', 'description', 'source_type', 'scopus_query', 'keywords',
            'keywords_list', 'publication_year_from', 'publication_year_to',
            'inclusion_criteria', 'exclusion_criteria', 'is_active',
            'created_at', 'updated_at'
        ]
    
    def get_keywords_list(self, obj):
        return obj.get_keywords_list()


class SearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Search
        fields = [
            'id', 'criteria', 'status', 'executed_at', 'completed_at',
            'total_results', 'processed_results', 'error_message',
            'search_params'
        ]
        read_only_fields = ['executed_at', 'completed_at', 'total_results', 'processed_results']


class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = [
            'id', 'semantic_scholar_id', 'article_source', 'title', 'abstract',
            'authors', 'publication_date', 'publication_year',
            'publication_venue', 'pdf_url', 'source_url',
            'citation_count', 'influence_score', 'fields_of_study',
            'imported_at', 'updated_at'
        ]
        read_only_fields = ['imported_at', 'updated_at']


class SearchResultSerializer(serializers.ModelSerializer):
    article = ArticleSerializer(read_only=True)
    article_id = serializers.PrimaryKeyRelatedField(
        queryset=Article.objects.all(),
        write_only=True,
        source='article'
    )
    assessed_by = UserSerializer(read_only=True)
    assessments = serializers.SerializerMethodField()
    current_user_assessment = serializers.SerializerMethodField()
    required_reviewers = serializers.SerializerMethodField()
    pending_reviewers = serializers.SerializerMethodField()
    
    class Meta:
        model = SearchResult
        fields = [
            'id', 'search', 'article', 'article_id', 'rank',
            'relevance_score', 'relevance', 'reviewer_notes',
            'assessed_by', 'assessed_at', 'created_at',
            'assessments', 'current_user_assessment', 'required_reviewers', 'pending_reviewers',
        ]
        read_only_fields = ['assessed_at']

    def get_assessments(self, obj):
        assessments = getattr(obj, 'prefetched_assessments', None)
        if assessments is None:
            assessments = obj.assessments.select_related('reviewer').all()
        return [
            {
                'id': assessment.id,
                'reviewer': UserSerializer(assessment.reviewer).data,
                'relevance': assessment.relevance,
                'notes': assessment.notes,
                'assessed_at': assessment.assessed_at,
            }
            for assessment in assessments
        ]

    def get_current_user_assessment(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None

        assessments = getattr(obj, 'prefetched_assessments', None)
        if assessments is None:
            assessment = obj.assessments.select_related('reviewer').filter(reviewer=request.user).first()
        else:
            assessment = next((item for item in assessments if item.reviewer_id == request.user.id), None)

        if not assessment:
            return None

        return {
            'id': assessment.id,
            'relevance': assessment.relevance,
            'notes': assessment.notes,
            'assessed_at': assessment.assessed_at,
        }

    def get_required_reviewers(self, obj):
        reviewers = obj.search.criteria.project.get_reviewers()
        return UserSerializer(reviewers, many=True).data

    def get_pending_reviewers(self, obj):
        assessments = getattr(obj, 'prefetched_assessments', None)
        if assessments is None:
            reviewer_ids_with_vote = set(obj.assessments.values_list('reviewer_id', flat=True))
        else:
            reviewer_ids_with_vote = {assessment.reviewer_id for assessment in assessments}
        pending = obj.search.criteria.project.get_reviewers().exclude(id__in=reviewer_ids_with_vote)
        return UserSerializer(pending, many=True).data


class ArticleAIInteractionSerializer(serializers.ModelSerializer):
    requested_by = UserSerializer(read_only=True)

    class Meta:
        model = ArticleAIInteraction
        fields = [
            'id', 'project', 'article', 'search_result', 'requested_by',
            'llm_provider', 'prompt', 'response_text', 'recommendation',
            'rationale', 'status', 'error_message', 'request_payload',
            'response_payload', 'created_at', 'completed_at',
        ]
        read_only_fields = [
            'prompt', 'response_text', 'recommendation', 'rationale',
            'status', 'error_message', 'request_payload', 'response_payload',
            'created_at', 'completed_at',
        ]


class ArticleDiscussionMessageSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = ArticleDiscussionMessage
        fields = [
            'id', 'project', 'article', 'author', 'message',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['author', 'created_at', 'updated_at']

    def validate(self, attrs):
        request = self.context.get('request')
        project = attrs.get('project')
        article = attrs.get('article')

        if not project or not article:
            return attrs

        try:
            ArticleDiscussionMessage.validate_project_article_pair(
                project=project,
                article=article,
                user=request.user if request else None,
            )
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

        return attrs


class WorkflowPhaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowPhase
        fields = [
            'id', 'project', 'phase_type', 'name', 'description',
            'order', 'is_completed', 'started_at', 'completed_at',
            'is_active', 'created_at', 'updated_at'
        ]


class ScreeningTaskSerializer(serializers.ModelSerializer):
    reviewer = UserSerializer(read_only=True)
    reviewer_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True,
        source='reviewer',
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = ScreeningTask
        fields = [
            'id', 'phase', 'search', 'reviewer', 'reviewer_id',
            'status', 'total_items', 'reviewed_items', 'included_items',
            'assigned_at', 'started_at', 'completed_at', 'notes'
        ]
        read_only_fields = ['assigned_at']


class DataExtractionTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataExtractionTemplate
        fields = [
            'id', 'project', 'name', 'description', 'fields',
            'is_active', 'created_at', 'updated_at'
        ]


class ExtractedDataSerializer(serializers.ModelSerializer):
    extracted_by = UserSerializer(read_only=True)
    verified_by = UserSerializer(read_only=True)
    
    class Meta:
        model = ExtractedData
        fields = [
            'id', 'search_result', 'template', 'data',
            'extracted_by', 'extracted_at', 'updated_at',
            'is_verified', 'verified_by', 'verified_at', 'notes'
        ]
        read_only_fields = ['extracted_at', 'updated_at', 'verified_at']
