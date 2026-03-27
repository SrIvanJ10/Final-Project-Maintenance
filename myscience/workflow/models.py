from django.db import models
from django.contrib.auth.models import User
from core.models import Project, Search


class WorkflowPhase(models.Model):
    """Model for workflow phases in systematic review process"""
    
    PHASE_TYPES = (
        ('planning', 'Planificación'),
        ('search', 'Búsqueda'),
        ('screening', 'Cribado'),
        ('eligibility', 'Evaluación de elegibilidad'),
        ('data_extraction', 'Extracción de datos'),
        ('quality_assessment', 'Evaluación de calidad'),
        ('synthesis', 'Síntesis'),
        ('dissemination', 'Diseminación'),
    )
    
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='workflow_phases',
        verbose_name='Proyecto'
    )
    
    phase_type = models.CharField(
        max_length=50, 
        choices=PHASE_TYPES,
        verbose_name='Tipo de fase'
    )
    
    name = models.CharField(max_length=255, verbose_name='Nombre')
    description = models.TextField(blank=True, verbose_name='Descripción')
    
    # Sequence
    order = models.IntegerField(verbose_name='Orden')
    
    # Status
    is_completed = models.BooleanField(default=False, verbose_name='Completada')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de inicio')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de finalización')
    
    # Settings
    is_active = models.BooleanField(default=True, verbose_name='Está activa')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Fase de flujo de trabajo'
        verbose_name_plural = 'Fases de flujo de trabajo'
        unique_together = ['project', 'order']
        indexes = [
            models.Index(fields=['project', 'is_active']),
        ]
    
    def __str__(self):
        return f'{self.get_phase_type_display()} - {self.project.title}'


class ScreeningTask(models.Model):
    """Model for screening tasks assigned to reviewers"""
    
    STATUS_CHOICES = (
        ('pending', 'Pendiente'),
        ('in_progress', 'En progreso'),
        ('completed', 'Completado'),
        ('rejected', 'Rechazado'),
    )
    
    phase = models.ForeignKey(
        WorkflowPhase, 
        on_delete=models.CASCADE, 
        related_name='screening_tasks',
        verbose_name='Fase'
    )
    
    search = models.ForeignKey(
        Search, 
        on_delete=models.CASCADE, 
        related_name='screening_tasks',
        verbose_name='Búsqueda'
    )
    
    reviewer = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='screening_tasks',
        verbose_name='Revisor'
    )
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        verbose_name='Estado'
    )
    
    # Screening details
    total_items = models.IntegerField(default=0, verbose_name='Total de elementos')
    reviewed_items = models.IntegerField(default=0, verbose_name='Elementos revisados')
    included_items = models.IntegerField(default=0, verbose_name='Elementos incluidos')
    
    # Dates
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name='Asignado en')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Iniciado en')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Completado en')
    
    # Notes
    notes = models.TextField(blank=True, verbose_name='Notas')
    
    class Meta:
        ordering = ['-assigned_at']
        verbose_name = 'Tarea de cribado'
        verbose_name_plural = 'Tareas de cribado'
        indexes = [
            models.Index(fields=['reviewer', 'status']),
        ]
    
    def __str__(self):
        return f'Cribado: {self.search.criteria.name} - {self.reviewer}'


class DataExtractionTemplate(models.Model):
    """Model for data extraction templates"""
    
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='extraction_templates',
        verbose_name='Proyecto'
    )
    
    name = models.CharField(max_length=255, verbose_name='Nombre')
    description = models.TextField(blank=True, verbose_name='Descripción')
    
    # Template fields (stored as JSON)
    fields = models.JSONField(
        default=list,
        help_text='Lista de campos para extraer datos',
        verbose_name='Campos'
    )
    
    # Version control
    is_active = models.BooleanField(default=True, verbose_name='Está activa')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')
    
    class Meta:
        verbose_name = 'Plantilla de extracción de datos'
        verbose_name_plural = 'Plantillas de extracción de datos'
        indexes = [
            models.Index(fields=['project', 'is_active']),
        ]
    
    def __str__(self):
        return f'{self.name} ({self.project.title})'


class ExtractedData(models.Model):
    """Model for storing extracted data from articles"""
    
    from core.models import SearchResult
    
    search_result = models.OneToOneField(
        SearchResult, 
        on_delete=models.CASCADE, 
        related_name='extracted_data',
        verbose_name='Resultado de búsqueda'
    )
    
    template = models.ForeignKey(
        DataExtractionTemplate, 
        on_delete=models.PROTECT,
        verbose_name='Plantilla'
    )
    
    # Extracted data stored as JSON
    data = models.JSONField(default=dict, verbose_name='Datos extraídos')
    
    # Quality control
    extracted_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='extracted_data',
        verbose_name='Extraído por'
    )
    
    extracted_at = models.DateTimeField(auto_now_add=True, verbose_name='Extraído en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')
    
    is_verified = models.BooleanField(default=False, verbose_name='Verificado')
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='verified_extractions',
        verbose_name='Verificado por'
    )
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name='Verificado en')
    
    # Notes
    notes = models.TextField(blank=True, verbose_name='Notas')
    
    class Meta:
        verbose_name = 'Datos extraídos'
        verbose_name_plural = 'Datos extraídos'
        indexes = [
            models.Index(fields=['template', 'is_verified']),
        ]
    
    def __str__(self):
        return f'Datos extraídos: {self.search_result.article.title[:50]}'
