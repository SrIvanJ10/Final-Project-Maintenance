from django.contrib import admin
from core.models import (
    Project,
    ProjectMembership,
    SearchCriteria,
    Search,
    Article,
    SearchResult,
    SearchResultAssessment,
    ArticleAIInteraction,
    ArticleDiscussionMessage,
)


class ProjectMembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0
    autocomplete_fields = ('user',)
    fields = ('user', 'role', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at', 'updated_at')
    search_fields = ('title', 'description', 'research_question')
    inlines = (ProjectMembershipInline,)
    fieldsets = (
        ('Informacion basica', {
            'fields': ('title', 'description', 'owner')
        }),
        ('Investigacion', {
            'fields': ('research_question', 'objectives', 'scope', 'inclusion_criteria', 'status')
        }),
        ('Documentos', {
            'fields': ('protocol_file',)
        }),
        ('Fechas', {
            'fields': ('start_date', 'end_date')
        }),
    )


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ('project', 'user', 'role', 'created_at')
    list_filter = ('role', 'project', 'created_at')
    search_fields = ('project__title', 'user__username', 'user__email')
    autocomplete_fields = ('project', 'user')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SearchCriteria)
class SearchCriteriaAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'is_active', 'created_at')
    list_filter = ('project', 'is_active', 'created_at')
    search_fields = ('name', 'keywords')
    fieldsets = (
        ('Informacion basica', {
            'fields': ('project', 'name', 'description', 'keywords')
        }),
        ('Filtros', {
            'fields': ('publication_year_from', 'publication_year_to')
        }),
        ('Criterios', {
            'fields': ('inclusion_criteria', 'exclusion_criteria')
        }),
        ('Configuracion', {
            'fields': ('is_active',)
        }),
    )


@admin.register(Search)
class SearchAdmin(admin.ModelAdmin):
    list_display = ('get_criteria_name', 'status', 'executed_at', 'total_results')
    list_filter = ('status', 'criteria__project', 'executed_at')
    search_fields = ('criteria__name',)
    readonly_fields = ('executed_at', 'completed_at', 'total_results', 'processed_results', 'search_params')

    def get_criteria_name(self, obj):
        return obj.criteria.name

    get_criteria_name.short_description = 'Criterios'


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'article_source', 'publication_year', 'citation_count', 'imported_at')
    list_filter = ('article_source', 'publication_year', 'imported_at')
    search_fields = ('title', 'abstract')
    readonly_fields = ('semantic_scholar_id', 'imported_at', 'updated_at', 'raw_data')


@admin.register(SearchResult)
class SearchResultAdmin(admin.ModelAdmin):
    list_display = ('get_article_title', 'rank', 'relevance', 'assessed_by', 'assessed_at')
    list_filter = ('search__criteria__project', 'relevance', 'assessed_at')
    search_fields = ('article__title',)
    readonly_fields = ('created_at',)

    def get_article_title(self, obj):
        return obj.article.title[:50]

    get_article_title.short_description = 'Articulo'


@admin.register(ArticleAIInteraction)
class ArticleAIInteractionAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'article', 'recommendation', 'status', 'created_at')
    list_filter = ('status', 'recommendation', 'created_at')
    search_fields = ('article__title', 'project__title', 'rationale', 'error_message')
    readonly_fields = ('created_at', 'completed_at', 'request_payload', 'response_payload', 'prompt', 'response_text')


@admin.register(SearchResultAssessment)
class SearchResultAssessmentAdmin(admin.ModelAdmin):
    list_display = ('search_result', 'reviewer', 'relevance', 'assessed_at')
    list_filter = ('relevance', 'reviewer', 'assessed_at')
    search_fields = ('search_result__article__title', 'reviewer__username')


@admin.register(ArticleDiscussionMessage)
class ArticleDiscussionMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'project', 'article', 'author', 'short_message', 'created_at')
    list_filter = ('project', 'author', 'created_at')
    search_fields = ('article__title', 'project__title', 'author__username', 'message')
    readonly_fields = ('created_at', 'updated_at')

    def short_message(self, obj):
        return obj.message[:80]

    short_message.short_description = 'Mensaje'
