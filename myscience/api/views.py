from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.decorators import api_view, permission_classes
from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie

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
from api.serializers import (
    ProjectSerializer, SearchCriteriaSerializer, SearchSerializer,
    ArticleSerializer, SearchResultSerializer, WorkflowPhaseSerializer,
    ScreeningTaskSerializer, DataExtractionTemplateSerializer, ExtractedDataSerializer,
    UserSerializer, ArticleAIInteractionSerializer, ArticleDiscussionMessageSerializer
)
from api.llm import request_article_suggestion, generate_project_inclusion_criteria, LLMServiceError
from semantic_scholar.client import SemanticScholarAPI, SemanticScholarRateLimitError
from django.utils import timezone
import logging
import csv
import io
import json
import hashlib

logger = logging.getLogger(__name__)


def accessible_projects_for(user):
    return Project.objects.filter(
        Q(owner=user) |
        Q(memberships__user=user)
    ).distinct()

def _to_int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_text(record, *keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ''):
            return str(value).strip()
    return ''


def _parse_scopus_payload(request):
    """
    Parse Scopus results from:
    - multipart file (csv/json)
    - json body with `results` list
    - json body with `csv_content` text
    """
    if request.FILES.get('file'):
        upload = request.FILES['file']
        raw = upload.read().decode('utf-8-sig', errors='ignore')
        file_name = upload.name.lower()
        if file_name.endswith('.json'):
            payload = json.loads(raw)
            if not isinstance(payload, list):
                raise ValueError('JSON file must contain a list of records')
            return payload
        if file_name.endswith('.csv'):
            return list(csv.DictReader(io.StringIO(raw)))
        raise ValueError('Unsupported file format. Use .csv or .json')

    if isinstance(request.data.get('results'), list):
        return request.data.get('results')

    csv_content = request.data.get('csv_content')
    if csv_content:
        return list(csv.DictReader(io.StringIO(csv_content)))

    raise ValueError('Provide Scopus results using file, results list, or csv_content')


def _scopus_record_to_article_defaults(record):
    authors_text = _safe_text(record, 'Authors', 'authors', 'Author(s)')
    authors = []
    if authors_text:
        authors = [{'name': item.strip()} for item in authors_text.split(',') if item.strip()]

    fields_text = _safe_text(record, 'Author Keywords', 'Index Keywords', 'Keywords')
    fields = [item.strip() for item in fields_text.replace(';', ',').split(',') if item.strip()]

    return {
        'article_source': 'scopus',
        'title': _safe_text(record, 'Title', 'title', 'Document Title'),
        'abstract': _safe_text(record, 'Abstract', 'abstract', 'Abstract Note'),
        'authors': authors,
        'publication_year': _to_int(_safe_text(record, 'Year', 'year', 'Publication Year'), None),
        'publication_venue': _safe_text(record, 'Source title', 'source_title', 'Journal', 'Publication Name'),
        'source_url': _safe_text(record, 'Link', 'link', 'URL', 'url'),
        'citation_count': _to_int(_safe_text(record, 'Cited by', 'cited_by', 'Citations'), 0),
        'fields_of_study': fields,
        'raw_data': record,
    }


@api_view(['GET'])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf_token_view(request):
    """Ensure a CSRF cookie exists and return the token value."""
    return Response({'csrfToken': get_token(request)})


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """Authenticate with username/password and create a session."""
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '')

    if not username or not password:
        return Response(
            {'error': 'username and password are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {'error': 'invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    login(request, user)
    return Response({'user': UserSerializer(user).data})


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    """Create a new user account and open a session immediately."""
    username = (request.data.get('username') or '').strip()
    email = (request.data.get('email') or '').strip().lower()
    password = request.data.get('password') or ''

    if not username or not email or not password:
        return Response(
            {'error': 'username, email and password are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(username__iexact=username).exists():
        return Response(
            {'error': 'username is already taken'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(email__iexact=email).exists():
        return Response(
            {'error': 'email is already registered'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_email(email)
    except ValidationError:
        return Response(
            {'error': 'email is not valid'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(password) < 8:
        return Response(
            {'error': 'password must contain at least 8 characters'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
    )
    login(request, user)
    return Response({'user': UserSerializer(user).data}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """Close current session."""
    logout(request)
    return Response({'detail': 'logged out'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    """Return current authenticated user."""
    return Response({'user': UserSerializer(request.user).data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_lookup_view(request):
    """Search users by username or email to add them as project collaborators."""
    query = (request.query_params.get('q') or '').strip()
    if len(query) < 2:
        return Response({'results': []})

    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(email__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).order_by('username')[:10]
    return Response({'results': UserSerializer(users, many=True).data})


class ProjectViewSet(viewsets.ModelViewSet):
    """ViewSet for managing projects"""
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['title', 'description', 'research_question', 'inclusion_criteria']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Return projects owned by or collaborated with current user"""
        return accessible_projects_for(self.request.user)
    
    def perform_create(self, serializer):
        """Set the owner to the current user"""
        inclusion_criteria = (serializer.validated_data.get('inclusion_criteria') or '').strip()

        if not inclusion_criteria:
            title = (serializer.validated_data.get('title') or '').strip()
            description = (serializer.validated_data.get('description') or '').strip()
            try:
                llm_result = generate_project_inclusion_criteria(
                    title=title,
                    description=description,
                )
                inclusion_criteria = llm_result['text']
            except Exception as exc:
                logger.warning(
                    "Could not generate inclusion criteria automatically for project '%s': %s",
                    title,
                    str(exc),
                )
                inclusion_criteria = Project.PRISMA_2020_INCLUSION_TEMPLATE

        serializer.save(owner=self.request.user, inclusion_criteria=inclusion_criteria)
    
    @action(detail=True, methods=['post'])
    def add_collaborator(self, request, pk=None):
        """Add a collaborator to the project"""
        project = self.get_object()
        if request.user != project.owner:
            return Response({'error': 'Only the project owner can add collaborators'}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get('user_id')
        username = (request.data.get('username') or '').strip()
        role = (request.data.get('role') or ProjectMembership.ROLE_REVIEWER).strip().lower()

        if role not in {
            ProjectMembership.ROLE_REVIEWER,
            ProjectMembership.ROLE_VIEWER,
            ProjectMembership.ROLE_ADVISOR,
        }:
            return Response({'error': 'role must be one of: reviewer, viewer, advisor'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if user_id:
                user = User.objects.get(id=user_id)
            elif username:
                user = User.objects.get(username=username)
            else:
                return Response({'error': 'user_id or username is required'}, status=status.HTTP_400_BAD_REQUEST)

            if user == project.owner:
                return Response({'error': 'Project owner already has the owner role'}, status=status.HTTP_400_BAD_REQUEST)

            membership, created = ProjectMembership.objects.update_or_create(
                project=project,
                user=user,
                defaults={'role': role},
            )
            project.collaborators.add(user)
            if created or role == ProjectMembership.ROLE_REVIEWER:
                for result in SearchResult.objects.filter(search__criteria__project=project):
                    result.sync_consensus_decision()
            return Response({
                'status': 'collaborator added' if created else 'collaborator updated',
                'collaborator': {
                    **UserSerializer(user).data,
                    'role': membership.role,
                    'membership_id': membership.id,
                },
            })
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Get project statistics"""
        project = self.get_object()
        
        searches = Search.objects.filter(criteria__project=project)
        completed_searches = searches.filter(status='completed')
        results = SearchResult.objects.filter(search__criteria__project=project)
        
        return Response({
            'total_searches': searches.count(),
            'completed_searches': completed_searches.count(),
            'total_results': results.count(),
            'included_results': results.filter(relevance='highly_relevant').count(),
            'articles': Article.objects.filter(search_results__search__criteria__project=project).distinct().count(),
        })

    @action(detail=True, methods=['post'])
    def start_review(self, request, pk=None):
        """Distribute pending screening work across the project team."""
        project = self.get_object()
        if request.user != project.owner:
            return Response(
                {'error': 'Only the project owner can start the review'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            distribution = project.distribute_screening_load()
        except ValueError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'status': 'review_started',
            'phase_id': distribution['phase'].id,
            'assigned_results': len(distribution['pending_results']),
            'created_tasks': len(distribution['created_tasks']),
            'distributed_to': [
                {
                    'user': UserSerializer(item['user']).data,
                    'assigned_results': item['assigned_results'],
                }
                for item in distribution['assignments']
            ],
        })


class SearchCriteriaViewSet(viewsets.ModelViewSet):
    """ViewSet for managing search criteria"""
    serializer_class = SearchCriteriaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'is_active', 'source_type']
    search_fields = ['name', 'keywords', 'scopus_query']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Return criteria from projects the user owns or collaborates with"""
        user_projects = accessible_projects_for(self.request.user)
        return SearchCriteria.objects.filter(project__in=user_projects)

    def _import_scopus_records(self, criteria, records, query_text=''):
        search = Search.objects.create(
            criteria=criteria,
            status='running',
            executed_at=timezone.now(),
            search_params={
                'source_type': 'scopus',
                'scopus_query': query_text or criteria.scopus_query,
                'records_received': len(records),
            },
        )

        search.total_results = len(records)
        search.save()

        for rank, record in enumerate(records, 1):
            try:
                eid = _safe_text(record, 'EID', 'eid', 'Scopus ID', 'scopus_id')
                doi = _safe_text(record, 'DOI', 'doi')
                title = _safe_text(record, 'Title', 'title', 'Document Title')
                stable_key = eid or doi or title or f'row-{rank}'
                normalized_id = f"scopus:{hashlib.sha1(stable_key.encode('utf-8')).hexdigest()[:20]}"

                article_defaults = _scopus_record_to_article_defaults(record)
                article, _ = Article.objects.get_or_create(
                    semantic_scholar_id=normalized_id,
                    defaults=article_defaults,
                )

                SearchResult.objects.get_or_create(
                    search=search,
                    article=article,
                    defaults={
                        'rank': rank,
                        'relevance_score': article_defaults.get('influence_score'),
                    },
                )
                search.processed_results += 1
            except Exception as exc:
                logger.error(f"Error processing Scopus record #{rank}: {str(exc)}")
                continue

        search.status = 'completed'
        search.completed_at = timezone.now()
        search.save()
        return search
    
    @action(detail=True, methods=['post'])
    def execute_search(self, request, pk=None):
        """Execute a search based on these criteria"""
        criteria = self.get_object()
        
        try:
            if criteria.source_type == 'scopus':
                records = _parse_scopus_payload(request)
                query_text = request.data.get('scopus_query', criteria.scopus_query)
                search = self._import_scopus_records(criteria, records, query_text=query_text)
                return Response(SearchSerializer(search).data, status=status.HTTP_201_CREATED)

            keywords = criteria.get_keywords_list()
            if not keywords:
                return Response(
                    {'error': 'No keywords configured for Semantic Scholar search'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create a new Search object
            search = Search.objects.create(
                criteria=criteria,
                status='running',
                executed_at=timezone.now(),
                search_params={
                    'source_type': 'semantic_scholar',
                    'keywords': criteria.get_keywords_list(),
                    'year_from': criteria.publication_year_from,
                    'year_to': criteria.publication_year_to,
                }
            )
            
            # Initialize Semantic Scholar API client
            api_client = SemanticScholarAPI()
            
            # Perform search
            all_results = []
            keyword_errors = []
            per_keyword_limit = max(1, min(int(getattr(settings, 'SEMANTIC_SCHOLAR_RESULTS_PER_KEYWORD', 40)), 100))
            
            for keyword in keywords:
                try:
                    result = api_client.search_papers(
                        query=keyword,
                        year_from=criteria.publication_year_from,
                        year_to=criteria.publication_year_to,
                        limit=per_keyword_limit
                    )
                    all_results.extend(result.get('data', []))
                except SemanticScholarRateLimitError as e:
                    logger.error(f"Semantic Scholar rate limit for keyword '{keyword}': {str(e)}")
                    keyword_errors.append({'keyword': keyword, 'error': str(e), 'type': 'rate_limit'})
                    break
                except Exception as e:
                    logger.error(f"Error searching for keyword '{keyword}': {str(e)}")
                    keyword_errors.append({'keyword': keyword, 'error': str(e), 'type': 'request_error'})
                    continue

            # Remove duplicates by paperId before persisting.
            deduplicated_results = []
            seen_ids = set()
            for paper_data in all_results:
                paper_id = paper_data.get('paperId')
                if not paper_id or paper_id in seen_ids:
                    continue
                seen_ids.add(paper_id)
                deduplicated_results.append(paper_data)

            if not deduplicated_results and keyword_errors:
                first_error = keyword_errors[0]
                search.error_message = first_error['error']
                search.status = 'failed'
                search.completed_at = timezone.now()
                search.search_params = {
                    **(search.search_params or {}),
                    'keyword_errors': keyword_errors,
                    'partial_success': False,
                }
                search.save()
                status_code = status.HTTP_429_TOO_MANY_REQUESTS if first_error.get('type') == 'rate_limit' else status.HTTP_400_BAD_REQUEST
                return Response(
                    {
                        'error': first_error['error'],
                        'details': keyword_errors,
                    },
                    status=status_code,
                )
            
            # Store results
            search.total_results = len(deduplicated_results)
            search.status = 'completed'
            search.completed_at = timezone.now()
            search.search_params = {
                **(search.search_params or {}),
                'keyword_errors': keyword_errors,
                'partial_success': bool(keyword_errors),
            }
            search.save()
            
            # Create Article and SearchResult objects
            for rank, paper_data in enumerate(deduplicated_results, 1):
                try:
                    # Get or create article
                    article, created = Article.objects.get_or_create(
                        semantic_scholar_id=paper_data.get('paperId', ''),
                        defaults={
                            'article_source': 'semantic_scholar',
                            'title': paper_data.get('title', ''),
                            'abstract': paper_data.get('abstract', ''),
                            'authors': paper_data.get('authors', []),
                            'publication_date': paper_data.get('publicationDate'),
                            'publication_year': paper_data.get('year'),
                            'publication_venue': paper_data.get('publicationVenue', ''),
                            'source_url': paper_data.get('url', ''),
                            'citation_count': paper_data.get('citationCount', 0),
                            'influence_score': paper_data.get('influenceScore'),
                            'fields_of_study': paper_data.get('fieldsOfStudy', []),
                            'raw_data': paper_data,
                        }
                    )
                    
                    # Create search result
                    SearchResult.objects.create(
                        search=search,
                        article=article,
                        rank=rank,
                        relevance_score=paper_data.get('influenceScore', 0),
                    )
                    
                    search.processed_results += 1
                except Exception as e:
                    logger.error(f"Error processing paper: {str(e)}")
                    continue
            
            search.save()
            
            return Response(
                SearchSerializer(search).data,
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error executing search: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def import_scopus_results(self, request, pk=None):
        """Import Scopus exported results (csv/json) for this criteria."""
        criteria = self.get_object()
        if criteria.source_type != 'scopus':
            return Response(
                {'error': 'This criteria is not configured as source_type=scopus'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            records = _parse_scopus_payload(request)
            query_text = request.data.get('scopus_query', criteria.scopus_query)
            search = self._import_scopus_records(criteria, records, query_text=query_text)
            return Response(SearchSerializer(search).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.error(f"Error importing Scopus results: {str(exc)}")
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class SearchViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing searches"""
    serializer_class = SearchSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['criteria', 'status']
    ordering_fields = ['executed_at', 'completed_at']
    ordering = ['-executed_at']
    
    def get_queryset(self):
        """Return searches from criteria in projects the user accesses"""
        user_projects = accessible_projects_for(self.request.user)
        return Search.objects.filter(criteria__project__in=user_projects)


class ArticleViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing articles"""
    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['publication_year', 'article_source']
    search_fields = ['title', 'authors', 'abstract']
    ordering_fields = ['publication_year', 'citation_count']
    ordering = ['-publication_year']
    
    def get_queryset(self):
        return Article.objects.all()


class ArticleDiscussionMessageViewSet(viewsets.ModelViewSet):
    """Chat-style discussion messages for a paper within a project."""

    serializer_class = ArticleDiscussionMessageSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post']
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['project', 'article']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['created_at']

    def get_queryset(self):
        user_projects = accessible_projects_for(self.request.user)
        return ArticleDiscussionMessage.objects.filter(
            project__in=user_projects
        ).select_related('author', 'article', 'project')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(author=request.user)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class SearchResultViewSet(viewsets.ModelViewSet):
    """ViewSet for managing search results"""
    serializer_class = SearchResultSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['search', 'relevance']
    ordering_fields = ['rank', 'relevance_score', 'assessed_at']
    ordering = ['rank']
    
    def get_queryset(self):
        """Return results from searches in projects the user accesses"""
        user_projects = accessible_projects_for(self.request.user)
        return SearchResult.objects.filter(
            search__criteria__project__in=user_projects
        ).select_related(
            'article', 'assessed_by', 'search__criteria__project'
        ).prefetch_related(
            'search__criteria__project__memberships__user',
            models.Prefetch(
                'assessments',
                queryset=SearchResultAssessment.objects.select_related('reviewer'),
                to_attr='prefetched_assessments',
            ),
        )
    
    @action(detail=True, methods=['post'])
    def assess_relevance(self, request, pk=None):
        """Assess the relevance of a search result"""
        result = self.get_object()
        
        relevance = request.data.get('relevance')
        notes = request.data.get('notes', '')
        
        try:
            result.record_assessment(
                reviewer=request.user,
                relevance=relevance,
                notes=notes,
            )
        except PermissionError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_403_FORBIDDEN,
            )
        except ValueError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SearchResultSerializer(result, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def suggest_with_ai(self, request, pk=None):
        """Generate include/exclude suggestion using selected LLM on demand."""
        result = self.get_object()
        project = result.search.criteria.project
        article = result.article
        criteria_text = (project.inclusion_criteria or '').strip()
        if not criteria_text:
            return Response(
                {'error': 'Project inclusion_criteria is empty'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        article_context = {
            'title': article.title,
            'abstract': article.abstract,
            'authors': article.authors,
            'publication_year': article.publication_year,
            'publication_venue': article.publication_venue,
            'source_url': article.source_url,
            'citation_count': article.citation_count,
            'fields_of_study': article.fields_of_study,
            'article_source': article.article_source,
            'current_relevance': result.relevance,
            'reviewer_notes': result.reviewer_notes,
        }

        interaction = ArticleAIInteraction.objects.create(
            project=project,
            article=article,
            search_result=result,
            requested_by=request.user,
            llm_provider='openai',
            status='pending',
            request_payload={
                'project_inclusion_criteria': criteria_text,
                'article_context': article_context,
            },
        )

        try:
            llm_result = request_article_suggestion(
                criteria_text=criteria_text,
                article_context=article_context,
            )

            interaction.prompt = llm_result.get('prompt', '')
            interaction.response_text = llm_result.get('raw_text', '')
            interaction.response_payload = llm_result.get('payload', {})
            interaction.recommendation = llm_result.get('parsed', {}).get('recommendation', 'uncertain')
            interaction.rationale = llm_result.get('parsed', {}).get('rationale', '')
            interaction.status = 'completed'
            interaction.completed_at = timezone.now()
            interaction.save()
            return Response(ArticleAIInteractionSerializer(interaction).data, status=status.HTTP_201_CREATED)
        except LLMServiceError as exc:
            interaction.status = 'failed'
            interaction.error_message = str(exc)
            interaction.completed_at = timezone.now()
            interaction.save()
            return Response(
                {
                    'error': str(exc),
                    'interaction': ArticleAIInteractionSerializer(interaction).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.error(f"Error running AI suggestion for result {result.id}: {str(exc)}")
            interaction.status = 'failed'
            interaction.error_message = str(exc)
            interaction.completed_at = timezone.now()
            interaction.save()
            return Response(
                {
                    'error': 'Unexpected error during AI suggestion',
                    'interaction': ArticleAIInteractionSerializer(interaction).data,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkflowPhaseViewSet(viewsets.ModelViewSet):
    """ViewSet for managing workflow phases"""
    serializer_class = WorkflowPhaseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['project', 'phase_type', 'is_active']
    ordering_fields = ['order', 'created_at']
    ordering = ['order']
    
    def get_queryset(self):
        """Return phases from projects the user owns or collaborates with"""
        user_projects = accessible_projects_for(self.request.user)
        return WorkflowPhase.objects.filter(project__in=user_projects)


class ScreeningTaskViewSet(viewsets.ModelViewSet):
    """ViewSet for managing screening tasks"""
    serializer_class = ScreeningTaskSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['phase', 'reviewer', 'status']
    
    def get_queryset(self):
        """Return tasks the user is assigned to or owns"""
        user_projects = accessible_projects_for(self.request.user)
        return ScreeningTask.objects.filter(
            Q(phase__project__in=user_projects) |
            Q(reviewer=self.request.user)
        )


class DataExtractionTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing data extraction templates"""
    serializer_class = DataExtractionTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['project', 'is_active']
    search_fields = ['name', 'description']
    
    def get_queryset(self):
        """Return templates from projects the user owns or collaborates with"""
        user_projects = accessible_projects_for(self.request.user)
        return DataExtractionTemplate.objects.filter(project__in=user_projects)


class ExtractedDataViewSet(viewsets.ModelViewSet):
    """ViewSet for managing extracted data"""
    serializer_class = ExtractedDataSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['template', 'is_verified']
    
    def get_queryset(self):
        """Return extracted data from search results in projects the user accesses"""
        user_projects = accessible_projects_for(self.request.user)
        return ExtractedData.objects.filter(
            search_result__search__criteria__project__in=user_projects
        )
