"""
Tests para workflow module
"""

from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Project, SearchCriteria, Search, Article, SearchResult
from workflow.models import WorkflowPhase, ScreeningTask, DataExtractionTemplate

