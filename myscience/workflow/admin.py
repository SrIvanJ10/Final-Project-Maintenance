from django.contrib import admin
from workflow.models import WorkflowPhase, ScreeningTask, DataExtractionTemplate, ExtractedData


@admin.register(WorkflowPhase)
class WorkflowPhaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'phase_type', 'order', 'is_completed')
    list_filter = ('project', 'phase_type', 'is_completed', 'is_active')
    search_fields = ('name', 'project__title')
    fieldsets = (
        ('Información básica', {
            'fields': ('project', 'name', 'description', 'phase_type')
        }),
        ('Secuencia', {
            'fields': ('order',)
        }),
        ('Estado', {
            'fields': ('started_at', 'completed_at', 'is_completed')
        }),
        ('Configuración', {
            'fields': ('is_active',)
        }),
    )


@admin.register(ScreeningTask)
class ScreeningTaskAdmin(admin.ModelAdmin):
    list_display = ('get_search_name', 'reviewer', 'status', 'reviewed_items', 'total_items')
    list_filter = ('phase__project', 'status', 'reviewer', 'assigned_at')
    search_fields = ('search__criteria__name', 'reviewer__username')
    readonly_fields = ('assigned_at',)
    fieldsets = (
        ('Tarea', {
            'fields': ('phase', 'search', 'reviewer')
        }),
        ('Progreso', {
            'fields': ('status', 'total_items', 'reviewed_items', 'included_items')
        }),
        ('Fechas', {
            'fields': ('assigned_at', 'started_at', 'completed_at')
        }),
        ('Notas', {
            'fields': ('notes',)
        }),
    )
    
    def get_search_name(self, obj):
        return obj.search.criteria.name
    get_search_name.short_description = 'Búsqueda'


@admin.register(DataExtractionTemplate)
class DataExtractionTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'is_active', 'created_at')
    list_filter = ('project', 'is_active', 'created_at')
    search_fields = ('name', 'project__title')
    fieldsets = (
        ('Información básica', {
            'fields': ('project', 'name', 'description')
        }),
        ('Campos', {
            'fields': ('fields',)
        }),
        ('Configuración', {
            'fields': ('is_active',)
        }),
    )


@admin.register(ExtractedData)
class ExtractedDataAdmin(admin.ModelAdmin):
    list_display = ('get_article_title', 'template', 'is_verified', 'extracted_by')
    list_filter = ('template__project', 'is_verified', 'extracted_at')
    search_fields = ('search_result__article__title',)
    readonly_fields = ('extracted_at', 'updated_at', 'verified_at')
    fieldsets = (
        ('Información básica', {
            'fields': ('search_result', 'template')
        }),
        ('Datos', {
            'fields': ('data',)
        }),
        ('Extracción', {
            'fields': ('extracted_by', 'extracted_at')
        }),
        ('Verificación', {
            'fields': ('is_verified', 'verified_by', 'verified_at')
        }),
        ('Notas', {
            'fields': ('notes',)
        }),
    )
    
    def get_article_title(self, obj):
        return obj.search_result.article.title[:50]
    get_article_title.short_description = 'Artículo'
