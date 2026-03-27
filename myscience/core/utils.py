"""
Utility functions for MyScience
"""

from core.models import Project, SearchCriteria, Search, Article, SearchResult
from workflow.models import WorkflowPhase
from django.utils import timezone


def create_project_with_workflow(
    title,
    owner,
    research_question="",
    objectives="",
    scope="",
    inclusion_criteria=Project.PRISMA_2020_INCLUSION_TEMPLATE,
):
    """
    Create a project with default workflow phases
    
    Args:
        title: Project title
        owner: User object
        research_question: Research question
        objectives: Project objectives
        scope: Project scope
        inclusion_criteria: Project inclusion criteria (PRISMA 2020)
    
    Returns:
        Project object
    """
    project = Project.objects.create(
        title=title,
        owner=owner,
        research_question=research_question,
        objectives=objectives,
        scope=scope,
        inclusion_criteria=inclusion_criteria,
        status='active'
    )
    
    # Create default workflow phases
    phases = [
        ('planning', 'Planificación', 'Planificación del estudio'),
        ('search', 'Búsqueda', 'Búsqueda de artículos'),
        ('screening', 'Cribado', 'Cribado de títulos y resúmenes'),
        ('eligibility', 'Elegibilidad', 'Evaluación de criterios de elegibilidad'),
        ('data_extraction', 'Extracción de datos', 'Extracción de datos de artículos'),
        ('quality_assessment', 'Evaluación de calidad', 'Evaluación de calidad metodológica'),
        ('synthesis', 'Síntesis', 'Síntesis de resultados'),
        ('dissemination', 'Diseminación', 'Diseminación de resultados'),
    ]
    
    for order, (phase_type, name, description) in enumerate(phases, 1):
        WorkflowPhase.objects.create(
            project=project,
            phase_type=phase_type,
            name=name,
            description=description,
            order=order,
            is_active=True
        )
    
    return project


def get_project_statistics(project):
    """
    Get comprehensive statistics for a project
    
    Args:
        project: Project object
    
    Returns:
        Dictionary with statistics
    """
    searches = Search.objects.filter(criteria__project=project)
    completed_searches = searches.filter(status='completed')
    results = SearchResult.objects.filter(search__criteria__project=project)
    
    return {
        'total_searches': searches.count(),
        'completed_searches': completed_searches.count(),
        'total_results': results.count(),
        'highly_relevant': results.filter(relevance='highly_relevant').count(),
        'relevant': results.filter(relevance='relevant').count(),
        'somewhat_relevant': results.filter(relevance='somewhat_relevant').count(),
        'not_relevant': results.filter(relevance='not_relevant').count(),
        'not_reviewed': results.filter(relevance='not_reviewed').count(),
        'unique_articles': Article.objects.filter(
            search_results__search__criteria__project=project
        ).distinct().count(),
        'average_citation_count': Article.objects.filter(
            search_results__search__criteria__project=project
        ).values_list('citation_count', flat=True).aggregate(avg=__import__('django.db.models', fromlist=['Avg']).Avg('citation_count'))['avg'] or 0,
    }


def bulk_create_search_results(search, articles_data):
    """
    Create multiple SearchResult objects efficiently
    
    Args:
        search: Search object
        articles_data: List of article data dictionaries
    
    Returns:
        List of created SearchResult objects
    """
    search_results = []
    
    for rank, article_data in enumerate(articles_data, 1):
        # Get or create article
        article, created = Article.objects.get_or_create(
            semantic_scholar_id=article_data.get('paperId', ''),
            defaults={
                'title': article_data.get('title', ''),
                'abstract': article_data.get('abstract', ''),
                'authors': article_data.get('authors', []),
                'publication_year': article_data.get('year'),
                'publication_venue': article_data.get('publicationVenue', ''),
                'citation_count': article_data.get('citationCount', 0),
                'influence_score': article_data.get('influenceScore'),
                'fields_of_study': article_data.get('fieldsOfStudy', []),
                'raw_data': article_data,
            }
        )
        
        # Create search result
        search_result = SearchResult.objects.create(
            search=search,
            article=article,
            rank=rank,
            relevance_score=article_data.get('influenceScore', 0),
        )
        
        search_results.append(search_result)
    
    return search_results


def update_search_completion(search, articles_count):
    """
    Update search completion status
    
    Args:
        search: Search object
        articles_count: Number of articles to mark as processed
    """
    search.processed_results += articles_count
    search.completed_at = timezone.now()
    
    if search.total_results <= search.processed_results:
        search.status = 'completed'
    
    search.save()


def get_included_articles(project):
    """
    Get all articles marked as highly relevant
    
    Args:
        project: Project object
    
    Returns:
        QuerySet of Article objects
    """
    return Article.objects.filter(
        search_results__search__criteria__project=project,
        search_results__relevance='highly_relevant'
    ).distinct()


def export_results_to_json(project):
    """
    Export project results to JSON format
    
    Args:
        project: Project object
    
    Returns:
        JSON-serializable dictionary
    """
    import json
    from api.serializers import (
        ProjectSerializer, SearchResultSerializer, ArticleSerializer
    )
    
    results = SearchResult.objects.filter(
        search__criteria__project=project
    ).select_related('article', 'search', 'assessed_by')
    
    data = {
        'project': ProjectSerializer(project).data,
        'total_results': results.count(),
        'results': SearchResultSerializer(results, many=True).data,
    }
    
    return json.dumps(data, indent=2, default=str)


def get_workflow_progress(project):
    """
    Get workflow phase progress
    
    Args:
        project: Project object
    
    Returns:
        List of phases with completion data
    """
    phases = WorkflowPhase.objects.filter(project=project).order_by('order')
    
    progress = []
    for phase in phases:
        progress.append({
            'name': phase.name,
            'type': phase.get_phase_type_display(),
            'order': phase.order,
            'is_completed': phase.is_completed,
            'started_at': phase.started_at,
            'completed_at': phase.completed_at,
        })
    
    return progress
