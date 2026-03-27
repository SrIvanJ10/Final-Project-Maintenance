from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import json
from django.utils import timezone

class Project(models.Model):
    """Model for systematic literature review projects"""
    PRISMA_2020_INCLUSION_TEMPLATE = (
        "PRISMA 2020 inclusion criteria:\n"
        "- Population/Problem: define target participants or domain.\n"
        "- Intervention/Exposure: define intervention or exposure of interest.\n"
        "- Comparator: define comparison condition when applicable.\n"
        "- Outcomes: define primary and secondary outcomes.\n"
        "- Study design: define eligible study designs.\n"
        "- Context and time window: define setting, language, and publication years."
    )
    
    STATUS_CHOICES = (
        ('draft', 'Borrador'),
        ('active', 'Activo'),
        ('on_hold', 'En pausa'),
        ('completed', 'Completado'),
    )
    
    title = models.CharField(max_length=255, verbose_name='Título')
    description = models.TextField(verbose_name='Descripción')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='draft',
        verbose_name='Estado'
    )
    
    # Research details
    research_question = models.TextField(verbose_name='Pregunta de investigación')
    objectives = models.TextField(verbose_name='Objetivos')
    scope = models.TextField(verbose_name='Alcance')
    inclusion_criteria = models.TextField(
        default=PRISMA_2020_INCLUSION_TEMPLATE,
        verbose_name='Criterios de inclusion (PRISMA 2020)',
    )
    
    # Protocol
    protocol_file = models.FileField(
        upload_to='protocols/', 
        null=True, 
        blank=True,
        verbose_name='Archivo de protocolo'
    )
    
    # Dates
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')
    start_date = models.DateField(null=True, blank=True, verbose_name='Fecha de inicio')
    end_date = models.DateField(null=True, blank=True, verbose_name='Fecha de finalización')
    
    # Collaboration
    collaborators = models.ManyToManyField(
        User, 
        related_name='collaborated_projects',
        blank=True,
        verbose_name='Colaboradores'
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Proyecto'
        verbose_name_plural = 'Proyectos'
        indexes = [
            models.Index(fields=['owner', 'status']),
        ]
    
    def __str__(self):
        return self.title

    def get_memberships(self):
        return self.memberships.select_related('user').order_by('user__username')

    def get_member_role(self, user):
        if not user or not getattr(user, 'is_authenticated', False):
            return None
        if user.id == self.owner_id:
            return 'owner'
        membership = self.memberships.filter(user=user).values_list('role', flat=True).first()
        return membership

    def has_access(self, user):
        return self.get_member_role(user) is not None

    def can_review(self, user):
        # Intentionally permissive for the testing assignment:
        # any project member can perform review actions.
        return self.has_access(user)

    def can_discuss(self, user):
        # Intentionally permissive for the testing assignment:
        # any project member can participate in discussions.
        return self.has_access(user)

    def get_reviewers(self):
        """Return all users whose vote is required for screening consensus."""
        return User.objects.filter(
            models.Q(id=self.owner_id) |
            models.Q(project_memberships__project=self, project_memberships__role='reviewer')
        ).distinct()

    def get_pending_search_results(self):
        return SearchResult.objects.filter(
            search__criteria__project=self,
            relevance='not_reviewed',
        ).select_related('search').order_by('search_id', 'rank', 'id')

    def get_screening_participants(self):
        """
        Return users that will receive screening load.

        Intentionally permissive for the testing assignment:
        any project member with access can be assigned work, not only real reviewers.
        """
        return User.objects.filter(
            models.Q(id=self.owner_id) |
            models.Q(project_memberships__project=self)
        ).distinct().order_by('id')

    def get_or_create_screening_phase(self):
        from workflow.models import WorkflowPhase

        phase = self.workflow_phases.filter(
            phase_type='screening',
        ).order_by('order').first()
        if phase:
            return phase

        next_order = (self.workflow_phases.aggregate(max_order=models.Max('order')).get('max_order') or 0) + 1
        return WorkflowPhase.objects.create(
            project=self,
            phase_type='screening',
            name='Screening',
            description='Distribucion automatica de carga de screening.',
            order=next_order,
            started_at=timezone.now(),
        )

    def distribute_screening_load(self):
        from workflow.models import ScreeningTask

        pending_results = list(self.get_pending_search_results())
        if not pending_results:
            raise ValueError('There are no pending articles to distribute')

        participants = list(self.get_screening_participants())
        if not participants:
            raise ValueError('No project members available for screening')

        phase = self.get_or_create_screening_phase()
        phase.started_at = phase.started_at or timezone.now()
        phase.is_active = True
        phase.is_completed = False
        phase.save(update_fields=['started_at', 'is_active', 'is_completed', 'updated_at'])

        ScreeningTask.objects.filter(phase=phase).delete()

        total_results = len(pending_results)
        participant_count = len(participants)
        base_load = total_results // participant_count
        extra = total_results % participant_count

        created_tasks = []
        assignments = []
        offset = 0

        for index, participant in enumerate(participants):
            load = base_load + (1 if index < extra else 0)
            assigned_slice = pending_results[offset:offset + load]
            offset += load

            grouped_by_search = {}
            for result in assigned_slice:
                grouped_by_search.setdefault(result.search_id, []).append(result)

            for search_id, search_results in grouped_by_search.items():
                created_tasks.append(
                    ScreeningTask.objects.create(
                        phase=phase,
                        search_id=search_id,
                        reviewer=participant,
                        status='pending',
                        total_items=len(search_results),
                        reviewed_items=0,
                        included_items=0,
                        notes=json.dumps({
                            'assignment_source': 'automatic_start_review',
                            'assigned_result_ids': [item.id for item in search_results],
                        }),
                    )
                )

            assignments.append({
                'user': participant,
                'assigned_results': len(assigned_slice),
            })

        self.status = 'active'
        self.save(update_fields=['status', 'updated_at'])

        return {
            'phase': phase,
            'pending_results': pending_results,
            'participants': participants,
            'created_tasks': created_tasks,
            'assignments': assignments,
        }


class ProjectMembership(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_REVIEWER = 'reviewer'
    ROLE_VIEWER = 'viewer'
    ROLE_ADVISOR = 'advisor'

    ROLE_CHOICES = (
        (ROLE_OWNER, 'Owner'),
        (ROLE_REVIEWER, 'Reviewer'),
        (ROLE_VIEWER, 'Viewer'),
        (ROLE_ADVISOR, 'Advisor'),
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='memberships',
        verbose_name='Proyecto',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='project_memberships',
        verbose_name='Usuario',
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_REVIEWER,
        verbose_name='Rol',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')

    class Meta:
        ordering = ['project', 'user__username']
        verbose_name = 'Membresia de proyecto'
        verbose_name_plural = 'Membresias de proyectos'
        unique_together = ['project', 'user']
        indexes = [
            models.Index(fields=['project', 'role']),
            models.Index(fields=['user', 'role']),
        ]

    def __str__(self):
        return f'{self.project.title} - {self.user.username} ({self.role})'


class SearchCriteria(models.Model):
    """Model for defining search criteria"""
    SOURCE_CHOICES = (
        ('semantic_scholar', 'Semantic Scholar'),
        ('scopus', 'Scopus'),
    )
    
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='search_criteria',
        verbose_name='Proyecto'
    )
    
    name = models.CharField(max_length=255, verbose_name='Nombre del criterio')
    description = models.TextField(blank=True, verbose_name='Descripción')
    source_type = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default='semantic_scholar',
        verbose_name='Fuente de búsqueda',
    )
    scopus_query = models.TextField(
        blank=True,
        verbose_name='Consulta Scopus',
    )
    
    # Search parameters
    keywords = models.TextField(
        blank=True,
        default='',
        help_text='Palabras clave separadas por comas',
        verbose_name='Palabras clave'
    )
    
    # Filters
    publication_year_from = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2100)],
        verbose_name='Año de publicación desde'
    )
    publication_year_to = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2100)],
        verbose_name='Año de publicación hasta'
    )
    
    # Inclusion/Exclusion criteria
    inclusion_criteria = models.TextField(
        blank=True,
        verbose_name='Criterios de inclusión'
    )
    exclusion_criteria = models.TextField(
        blank=True,
        verbose_name='Criterios de exclusión'
    )
    
    # Settings
    is_active = models.BooleanField(default=True, verbose_name='Está activo')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Criterio de búsqueda'
        verbose_name_plural = 'Criterios de búsqueda'
        indexes = [
            models.Index(fields=['project', 'is_active']),
        ]
    
    def __str__(self):
        return f'{self.name} ({self.project.title})'
    
    def get_keywords_list(self):
        """Return keywords as a list"""
        if not self.keywords:
            return []
        return [k.strip() for k in self.keywords.split(',') if k.strip()]


class Search(models.Model):
    """Model for executed searches"""
    
    STATUS_CHOICES = (
        ('pending', 'Pendiente'),
        ('running', 'En ejecución'),
        ('completed', 'Completado'),
        ('failed', 'Falló'),
        ('cancelled', 'Cancelado'),
    )
    
    criteria = models.ForeignKey(
        SearchCriteria, 
        on_delete=models.CASCADE, 
        related_name='searches',
        verbose_name='Criterios'
    )
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        verbose_name='Estado'
    )
    
    executed_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de ejecución')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de finalización')
    
    total_results = models.IntegerField(default=0, verbose_name='Total de resultados')
    processed_results = models.IntegerField(default=0, verbose_name='Resultados procesados')
    
    error_message = models.TextField(blank=True, verbose_name='Mensaje de error')
    
    # Metadata
    search_params = models.JSONField(default=dict, verbose_name='Parámetros de búsqueda')
    
    class Meta:
        ordering = ['-executed_at']
        verbose_name = 'Búsqueda'
        verbose_name_plural = 'Búsquedas'
        indexes = [
            models.Index(fields=['criteria', 'status']),
            models.Index(fields=['-executed_at']),
        ]
    
    def __str__(self):
        return f'Búsqueda: {self.criteria.name} ({self.status})'


class Article(models.Model):
    """Model for scientific articles/papers"""
    ARTICLE_SOURCE_CHOICES = (
        ('semantic_scholar', 'Semantic Scholar'),
        ('scopus', 'Scopus CSV'),
    )
    
    # These will be sourced from Semantic Scholar API
    semantic_scholar_id = models.CharField(
        max_length=255, 
        unique=True, 
        db_index=True,
        verbose_name='ID de Semantic Scholar'
    )
    
    title = models.CharField(max_length=500, verbose_name='Título')
    abstract = models.TextField(blank=True, verbose_name='Resumen')
    
    # Authors
    authors = models.JSONField(default=list, verbose_name='Autores')
    
    # Publication details
    publication_date = models.DateField(null=True, blank=True, verbose_name='Fecha de publicación')
    publication_year = models.IntegerField(null=True, blank=True, verbose_name='Año de publicación')
    publication_venue = models.CharField(
        max_length=500, 
        blank=True,
        verbose_name='Publicación'
    )
    
    # URLs
    pdf_url = models.URLField(blank=True, verbose_name='URL del PDF')
    source_url = models.URLField(blank=True, verbose_name='URL de origen')
    
    # Metrics
    citation_count = models.IntegerField(default=0, verbose_name='Número de citas')
    influence_score = models.FloatField(null=True, blank=True, verbose_name='Puntuación de influencia')
    
    # Fields of study
    fields_of_study = models.JSONField(default=list, verbose_name='Campos de estudio')
    article_source = models.CharField(
        max_length=30,
        choices=ARTICLE_SOURCE_CHOICES,
        default='semantic_scholar',
        db_index=True,
        verbose_name='Fuente del artículo',
    )
    
    # Metadata
    imported_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de importación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')
    
    # Raw API response (for reference)
    raw_data = models.JSONField(default=dict, verbose_name='Datos crudos de API')
    
    class Meta:
        ordering = ['-publication_year', '-publication_date']
        verbose_name = 'Artículo'
        verbose_name_plural = 'Artículos'
        indexes = [
            models.Index(fields=['semantic_scholar_id']),
            models.Index(fields=['article_source']),
            models.Index(fields=['publication_year']),
            models.Index(fields=['citation_count']),
        ]
    
    def __str__(self):
        return self.title[:100]


class SearchResult(models.Model):
    """Model for linking articles found in searches"""
    
    RELEVANCE_CHOICES = (
        ('not_reviewed', 'No revisado'),
        ('highly_relevant', 'Muy relevante'),
        ('relevant', 'Relevante'),
        ('somewhat_relevant', 'Moderadamente relevante'),
        ('not_relevant', 'No relevante'),
        ('duplicate', 'Duplicado'),
    )
    
    search = models.ForeignKey(
        Search, 
        on_delete=models.CASCADE, 
        related_name='results',
        verbose_name='Búsqueda'
    )
    
    article = models.ForeignKey(
        Article, 
        on_delete=models.CASCADE, 
        related_name='search_results',
        verbose_name='Artículo'
    )
    
    # Ranking in search results
    rank = models.IntegerField(verbose_name='Posición en resultados')
    relevance_score = models.FloatField(null=True, blank=True, verbose_name='Puntuación de relevancia')
    
    # Assessment
    relevance = models.CharField(
        max_length=20, 
        choices=RELEVANCE_CHOICES, 
        default='not_reviewed',
        verbose_name='Relevancia'
    )
    reviewer_notes = models.TextField(blank=True, verbose_name='Notas del revisor')
    assessed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assessed_results',
        verbose_name='Evaluado por'
    )
    assessed_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de evaluación')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    
    class Meta:
        ordering = ['rank']
        verbose_name = 'Resultado de búsqueda'
        verbose_name_plural = 'Resultados de búsqueda'
        unique_together = ['search', 'article']
        indexes = [
            models.Index(fields=['search', 'relevance']),
        ]
    
    def __str__(self):
        return f'{self.article.title[:50]} - {self.search.criteria.name}'

    def sync_consensus_decision(self, save=True):
        """
        Compute the aggregate decision from individual reviewer assessments.

        Inclusion requires a positive vote from every project reviewer.
        Any explicit exclusion makes the result excluded immediately.
        Otherwise the result remains pending until unanimity is reached.
        """
        project = self.search.criteria.project
        required_reviewer_ids = set(project.get_reviewers().values_list('id', flat=True))
        assessments = list(self.assessments.select_related('reviewer'))
        assessment_by_reviewer = {assessment.reviewer_id: assessment for assessment in assessments}

        excluded_values = {'not_relevant', 'duplicate'}
        included_values = {'highly_relevant', 'relevant', 'somewhat_relevant'}

        if any(assessment.relevance in excluded_values for assessment in assessments):
            self.relevance = 'not_relevant'
        elif required_reviewer_ids and required_reviewer_ids.issubset(assessment_by_reviewer.keys()):
            if all(assessment_by_reviewer[reviewer_id].relevance in included_values for reviewer_id in required_reviewer_ids):
                self.relevance = 'highly_relevant'
            else:
                self.relevance = 'not_reviewed'
        else:
            self.relevance = 'not_reviewed'

        latest_assessment = max(
            assessments,
            key=lambda assessment: assessment.assessed_at or assessment.created_at,
            default=None,
        )
        if latest_assessment:
            self.assessed_by = latest_assessment.reviewer
            self.assessed_at = latest_assessment.assessed_at
        else:
            self.assessed_by = None
            self.assessed_at = None

        self.reviewer_notes = '\n\n'.join(
            f'{assessment.reviewer.username}: {assessment.notes}'
            for assessment in assessments
            if assessment.notes
        )

        if save:
            self.save(update_fields=['relevance', 'assessed_by', 'assessed_at', 'reviewer_notes'])
        return self.relevance

    def record_assessment(self, reviewer, relevance, notes=''):
        if relevance not in dict(self.RELEVANCE_CHOICES):
            raise ValueError('Invalid relevance value')

        if relevance == 'not_reviewed':
            raise ValueError('Use an inclusion or exclusion decision, not not_reviewed')

        assessment, _ = SearchResultAssessment.objects.update_or_create(
            search_result=self,
            reviewer=reviewer,
            defaults={
                'relevance': relevance,
                'notes': notes,
            },
        )
        self.sync_consensus_decision()
        return assessment


class SearchResultAssessment(models.Model):
    """Individual screening decision for a specific reviewer."""

    search_result = models.ForeignKey(
        SearchResult,
        on_delete=models.CASCADE,
        related_name='assessments',
        verbose_name='Resultado de busqueda',
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='search_result_assessments',
        verbose_name='Revisor',
    )
    relevance = models.CharField(
        max_length=20,
        choices=SearchResult.RELEVANCE_CHOICES,
        verbose_name='Decision',
    )
    notes = models.TextField(blank=True, verbose_name='Notas')
    assessed_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de evaluacion')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')

    class Meta:
        ordering = ['reviewer__username']
        verbose_name = 'Evaluacion de resultado'
        verbose_name_plural = 'Evaluaciones de resultados'
        unique_together = ['search_result', 'reviewer']
        indexes = [
            models.Index(fields=['search_result', 'reviewer']),
            models.Index(fields=['reviewer', 'assessed_at']),
        ]

    def __str__(self):
        return f'{self.reviewer.username} - {self.search_result_id} - {self.relevance}'


class ArticleAIInteraction(models.Model):
    """LLM interactions linked to article review decisions."""

    LLM_PROVIDER_CHOICES = (
        ('openai', 'OpenAI'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pendiente'),
        ('completed', 'Completada'),
        ('failed', 'Fallida'),
    )

    RECOMMENDATION_CHOICES = (
        ('include', 'Incluir'),
        ('exclude', 'Excluir'),
        ('uncertain', 'Incierto'),
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='ai_interactions',
        verbose_name='Proyecto',
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='ai_interactions',
        verbose_name='Artículo',
    )
    search_result = models.ForeignKey(
        SearchResult,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_interactions',
        verbose_name='Resultado de búsqueda',
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_interactions',
        verbose_name='Solicitado por',
    )

    llm_provider = models.CharField(
        max_length=20,
        choices=LLM_PROVIDER_CHOICES,
        default='openai',
        verbose_name='Proveedor LLM',
    )
    prompt = models.TextField(blank=True, verbose_name='Prompt enviado')
    response_text = models.TextField(blank=True, verbose_name='Respuesta del LLM')
    recommendation = models.CharField(
        max_length=20,
        choices=RECOMMENDATION_CHOICES,
        default='uncertain',
        verbose_name='Sugerencia',
    )
    rationale = models.TextField(blank=True, verbose_name='Justificación')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Estado',
    )
    error_message = models.TextField(blank=True, verbose_name='Mensaje de error')

    # Keep both prompt context and raw provider payload for traceability/auditing.
    request_payload = models.JSONField(default=dict, verbose_name='Payload de solicitud')
    response_payload = models.JSONField(default=dict, verbose_name='Payload de respuesta')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de finalización')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Interacción IA de artículo'
        verbose_name_plural = 'Interacciones IA de artículos'
        indexes = [
            models.Index(fields=['project', 'created_at']),
            models.Index(fields=['article', 'created_at']),
            models.Index(fields=['llm_provider', 'status']),
        ]

    def __str__(self):
        return f'{self.get_llm_provider_display()} - {self.article.title[:40]}'


class ArticleDiscussionMessage(models.Model):
    """Chat-style discussion messages about a paper within a project."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='article_discussion_messages',
        verbose_name='Proyecto',
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name='discussion_messages',
        verbose_name='Articulo',
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='article_discussion_messages',
        verbose_name='Autor',
    )
    message = models.TextField(verbose_name='Mensaje')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Mensaje de discusion de articulo'
        verbose_name_plural = 'Mensajes de discusion de articulos'
        indexes = [
            models.Index(fields=['project', 'article', 'created_at']),
            models.Index(fields=['author', 'created_at']),
        ]

    def __str__(self):
        return f'{self.author.username} - {self.article.title[:40]}'

    @classmethod
    def validate_project_article_pair(cls, project, article, user):
        if not user or not getattr(user, 'is_authenticated', False):
            raise ValueError('Authentication is required')

        if not project.can_discuss(user):
            raise ValueError('You do not have permission to participate in this discussion')

        article_in_project = SearchResult.objects.filter(
            search__criteria__project=project,
            article=article,
        ).exists()
        if not article_in_project:
            raise ValueError('This article does not belong to the selected project')

        return True
