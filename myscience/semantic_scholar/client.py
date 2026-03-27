"""
Semantic Scholar API Client
"""
import random
import time
import requests
import logging
from typing import List, Dict, Optional
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class SemanticScholarRateLimitError(Exception):
    """Raised when Semantic Scholar keeps returning 429 after retries."""


class SemanticScholarRequestError(Exception):
    """Raised for Semantic Scholar non-429 request failures with details."""


class SemanticScholarAPI:
    """Client for Semantic Scholar API"""
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    DEFAULT_SEARCH_FIELDS = [
        'paperId',
        'title',
        'authors',
        'abstract',
        'publicationDate',
        'publicationVenue',
        'year',
        'citationCount',
        'fieldsOfStudy',
        'url',
    ]
    
    def __init__(self, api_key: Optional[str] = None, timeout: Optional[int] = None):
        self.api_key = api_key or settings.SEMANTIC_SCHOLAR_API_KEY
        self.timeout = timeout or settings.SEMANTIC_SCHOLAR_API_TIMEOUT
        self.max_retries = int(getattr(settings, 'SEMANTIC_SCHOLAR_API_MAX_RETRIES', 5))
        self.backoff_factor = float(getattr(settings, 'SEMANTIC_SCHOLAR_API_BACKOFF_FACTOR', 1.5))
        self.min_request_interval = float(getattr(settings, 'SEMANTIC_SCHOLAR_API_MIN_REQUEST_INTERVAL', 1.05))
        self.use_bulk_search = bool(getattr(settings, 'SEMANTIC_SCHOLAR_USE_BULK_SEARCH', True))
        self._last_request_ts = 0.0
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy"""
        session = requests.Session()
        
        # Retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session

    def _respect_min_interval(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> Optional[float]:
        raw = response.headers.get('Retry-After')
        if not raw:
            return None
        try:
            return max(float(raw), 0.0)
        except (TypeError, ValueError):
            return None
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a request to the Semantic Scholar API"""
        url = f"{self.BASE_URL}{endpoint}"
        
        headers = {
            'User-Agent': 'MyScience (https://github.com/user/myscience)'
        }
        
        if self.api_key:
            headers['x-api-key'] = self.api_key
        
        for attempt in range(self.max_retries + 1):
            self._respect_min_interval()
            self._last_request_ts = time.monotonic()

            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
            except requests.exceptions.RequestException as e:
                if attempt >= self.max_retries:
                    logger.error(f"Error making request to Semantic Scholar API: {str(e)}")
                    raise
                sleep_for = (self.backoff_factor ** attempt) + random.uniform(0.1, 0.7)
                logger.warning(
                    "Network error calling Semantic Scholar (%s). Retrying in %.2fs (%s/%s).",
                    str(e),
                    sleep_for,
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(sleep_for)
                continue

            if response.status_code == 429:
                if attempt >= self.max_retries:
                    msg = (
                        "Semantic Scholar API rate limit reached after retries. "
                        "Try again in a few minutes, reduce keywords, or configure an API key."
                    )
                    logger.error(msg)
                    raise SemanticScholarRateLimitError(msg)

                retry_after = self._retry_after_seconds(response)
                backoff = (self.backoff_factor ** attempt) + random.uniform(0.1, 0.7)
                sleep_for = max(retry_after or 0.0, backoff)
                logger.warning(
                    "Semantic Scholar returned 429. Retrying in %.2fs (%s/%s).",
                    sleep_for,
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(sleep_for)
                continue

            if 400 <= response.status_code < 500:
                details = ''
                try:
                    payload = response.json()
                    details = payload.get('error') or payload.get('message') or str(payload)
                except ValueError:
                    details = response.text.strip()

                if response.status_code == 429:
                    # Already handled above; keep defensive fallback.
                    details = details or 'Rate limit exceeded'
                    raise SemanticScholarRateLimitError(details)

                msg = f"Semantic Scholar API {response.status_code}: {details or 'Bad request'}"
                logger.error(msg)
                raise SemanticScholarRequestError(msg)

            try:
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error making request to Semantic Scholar API: {str(e)}")
                raise

        raise RuntimeError("Unreachable request retry loop end")
    
    def search_papers(
        self, 
        query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
        fields: Optional[List[str]] = None,
        use_bulk: Optional[bool] = None,
    ) -> Dict:
        """
        Search for papers using a query string
        
        Args:
            query: Search query string
            year_from: Minimum publication year
            year_to: Maximum publication year
            limit: Number of results to return (max 100)
            offset: Offset for pagination
            fields: List of fields to include in response
        
        Returns:
            Dictionary with search results
        """
        
        # Default fields to retrieve
        if fields is None:
            fields = self.DEFAULT_SEARCH_FIELDS
        
        use_bulk_search = self.use_bulk_search if use_bulk is None else use_bulk
        params = {
            'query': query,
            'limit': min(limit, 100),
            'fields': ','.join(fields)
        }

        endpoint = '/paper/search'
        if use_bulk_search:
            endpoint = '/paper/search/bulk'
            if year_from and year_to:
                params['year'] = f'{year_from}-{year_to}'
            elif year_from:
                params['year'] = f'{year_from}-'
            elif year_to:
                params['year'] = f'-{year_to}'
        else:
            params['offset'] = offset
            if year_from:
                params['minYear'] = year_from
            if year_to:
                params['maxYear'] = year_to

        try:
            return self._make_request(endpoint, params)
        except SemanticScholarRateLimitError:
            raise
        except SemanticScholarRequestError as e:
            if use_bulk_search:
                logger.warning(
                    "Bulk endpoint failed for query '%s' (%s). Falling back to /paper/search.",
                    query,
                    str(e),
                )
                fallback_params = {
                    'query': query,
                    'limit': min(limit, 100),
                    'offset': offset,
                    'fields': ','.join(fields),
                }
                if year_from:
                    fallback_params['minYear'] = year_from
                if year_to:
                    fallback_params['maxYear'] = year_to
                return self._make_request('/paper/search', fallback_params)
            raise
        except Exception as e:
            if use_bulk_search:
                logger.warning(
                    "Bulk endpoint failed for query '%s' (%s). Falling back to /paper/search.",
                    query,
                    str(e),
                )
                fallback_params = {
                    'query': query,
                    'limit': min(limit, 100),
                    'offset': offset,
                    'fields': ','.join(fields),
                }
                if year_from:
                    fallback_params['minYear'] = year_from
                if year_to:
                    fallback_params['maxYear'] = year_to
                try:
                    return self._make_request('/paper/search', fallback_params)
                except Exception as fallback_error:
                    logger.error(f"Error searching papers: {str(fallback_error)}")
                    raise

            logger.error(f"Error searching papers: {str(e)}")
            raise
    
    def get_paper(self, paper_id: str, fields: Optional[List[str]] = None) -> Dict:
        """
        Get details of a specific paper
        
        Args:
            paper_id: The paper ID from Semantic Scholar
            fields: List of fields to include in response
        
        Returns:
            Dictionary with paper details
        """
        
        if fields is None:
            fields = [
                'paperId',
                'title',
                'authors',
                'abstract',
                'publicationDate',
                'publicationVenue',
                'year',
                'citationCount',
                'influenceScore',
                'fieldsOfStudy',
                'externalIds',
                'url',
                'references',
                'citations',
                's2FieldsOfStudy'
            ]
        
        endpoint = f'/paper/{paper_id}'
        params = {'fields': ','.join(fields)}
        
        try:
            return self._make_request(endpoint, params)
        except Exception as e:
            logger.error(f"Error getting paper {paper_id}: {str(e)}")
            raise
    
    def get_paper_references(
        self, 
        paper_id: str,
        limit: int = 100,
        offset: int = 0,
        fields: Optional[List[str]] = None
    ) -> Dict:
        """
        Get references of a specific paper
        
        Args:
            paper_id: The paper ID from Semantic Scholar
            limit: Number of results to return
            offset: Offset for pagination
            fields: List of fields to include in response
        
        Returns:
            Dictionary with paper references
        """
        
        if fields is None:
            fields = [
                'paperId',
                'title',
                'authors',
                'year',
                'citationCount',
                'url'
            ]
        
        endpoint = f'/paper/{paper_id}/references'
        params = {
            'limit': min(limit, 100),
            'offset': offset,
            'fields': ','.join(fields)
        }
        
        try:
            return self._make_request(endpoint, params)
        except Exception as e:
            logger.error(f"Error getting paper references for {paper_id}: {str(e)}")
            raise
    
    def get_paper_citations(
        self, 
        paper_id: str,
        limit: int = 100,
        offset: int = 0,
        fields: Optional[List[str]] = None
    ) -> Dict:
        """
        Get citations of a specific paper
        
        Args:
            paper_id: The paper ID from Semantic Scholar
            limit: Number of results to return
            offset: Offset for pagination
            fields: List of fields to include in response
        
        Returns:
            Dictionary with paper citations
        """
        
        if fields is None:
            fields = [
                'paperId',
                'title',
                'authors',
                'year',
                'citationCount',
                'url'
            ]
        
        endpoint = f'/paper/{paper_id}/citations'
        params = {
            'limit': min(limit, 100),
            'offset': offset,
            'fields': ','.join(fields)
        }
        
        try:
            return self._make_request(endpoint, params)
        except Exception as e:
            logger.error(f"Error getting paper citations for {paper_id}: {str(e)}")
            raise
    
    def batch_search(self, queries: List[str], **kwargs) -> List[Dict]:
        """
        Perform multiple searches
        
        Args:
            queries: List of search queries
            **kwargs: Additional arguments to pass to search_papers
        
        Returns:
            List of search results
        """
        results = []
        for query in queries:
            try:
                result = self.search_papers(query, **kwargs)
                results.append({'query': query, 'result': result})
            except Exception as e:
                logger.error(f"Error searching for query '{query}': {str(e)}")
                results.append({'query': query, 'error': str(e)})
        
        return results
