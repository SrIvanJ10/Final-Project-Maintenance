"""
Celery app and tasks for MyScience project.
"""
import os
import logging

from celery import Celery, shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myscience.settings')

app = Celery('myscience')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

logger = logging.getLogger(__name__)


@shared_task
def execute_search_task(search_id):
    """
    Execute a search asynchronously
    
    Args:
        search_id: ID of the Search object to execute
    """
    try:
        from core.models import Search, Article, SearchResult
        from semantic_scholar.client import SemanticScholarAPI, SemanticScholarRateLimitError

        search = Search.objects.get(id=search_id)
        search.status = 'running'
        search.executed_at = timezone.now()
        search.save()
        
        criteria = search.criteria
        api_client = SemanticScholarAPI()
        
        keywords = criteria.get_keywords_list()
        all_results = []
        keyword_errors = []
        per_keyword_limit = max(1, min(int(getattr(settings, 'SEMANTIC_SCHOLAR_RESULTS_PER_KEYWORD', 40)), 100))
        
        # Perform searches for all keywords
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

        deduplicated_results = []
        seen_ids = set()
        for paper_data in all_results:
            paper_id = paper_data.get('paperId')
            if not paper_id or paper_id in seen_ids:
                continue
            seen_ids.add(paper_id)
            deduplicated_results.append(paper_data)

        if not deduplicated_results and keyword_errors:
            search.status = 'failed'
            search.error_message = keyword_errors[0]['error']
            search.completed_at = timezone.now()
            search.search_params = {
                **(search.search_params or {}),
                'keyword_errors': keyword_errors,
                'partial_success': False,
            }
            search.save()
            return {
                'search_id': search_id,
                'status': 'failed',
                'errors': keyword_errors,
            }
        
        # Store results
        search.total_results = len(deduplicated_results)
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
        
        search.status = 'completed'
        search.completed_at = timezone.now()
        search.save()
        
        return {
            'search_id': search_id,
            'status': 'completed',
            'total_results': search.total_results,
            'processed_results': search.processed_results
        }
    
    except ObjectDoesNotExist:
        logger.error(f"Search with id {search_id} not found")
        return {'error': f'Search with id {search_id} not found'}
    except Exception as e:
        logger.error(f"Error executing search: {str(e)}")
        try:
            search = Search.objects.get(id=search_id)
            search.status = 'failed'
            search.error_message = str(e)
            search.completed_at = timezone.now()
            search.save()
        except:
            pass
        return {'error': str(e)}


@shared_task
def update_paper_citations(paper_id):
    """
    Update citation count and other metadata for a paper
    
    Args:
        paper_id: ID of the Article object to update
    """
    try:
        from core.models import Article
        from semantic_scholar.client import SemanticScholarAPI

        article = Article.objects.get(id=paper_id)
        api_client = SemanticScholarAPI()
        
        paper_data = api_client.get_paper(article.semantic_scholar_id)
        
        article.citation_count = paper_data.get('citationCount', article.citation_count)
        article.influence_score = paper_data.get('influenceScore', article.influence_score)
        article.raw_data = paper_data
        article.save()
        
        return {'article_id': paper_id, 'status': 'updated'}
    
    except ObjectDoesNotExist:
        logger.error(f"Article with id {paper_id} not found")
        return {'error': f'Article with id {paper_id} not found'}
    except Exception as e:
        logger.error(f"Error updating paper: {str(e)}")
        return {'error': str(e)}


@shared_task
def batch_update_citations():
    """
    Batch update citations for all articles
    """
    from core.models import Article

    articles = Article.objects.all()
    updated_count = 0
    
    for article in articles:
        try:
            update_paper_citations.delay(article.id)
            updated_count += 1
        except Exception as e:
            logger.error(f"Error scheduling update for article {article.id}: {str(e)}")
    
    return {'updated_count': updated_count}
