from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api import views

router = DefaultRouter()
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'search-criteria', views.SearchCriteriaViewSet, basename='search-criteria')
router.register(r'searches', views.SearchViewSet, basename='search')
router.register(r'articles', views.ArticleViewSet, basename='article')
router.register(r'article-discussions', views.ArticleDiscussionMessageViewSet, basename='article-discussion')
router.register(r'search-results', views.SearchResultViewSet, basename='search-result')
router.register(r'workflow-phases', views.WorkflowPhaseViewSet, basename='workflow-phase')
router.register(r'screening-tasks', views.ScreeningTaskViewSet, basename='screening-task')
router.register(r'extraction-templates', views.DataExtractionTemplateViewSet, basename='extraction-template')
router.register(r'extracted-data', views.ExtractedDataViewSet, basename='extracted-data')

app_name = 'api'

urlpatterns = [
    path('auth/csrf/', views.csrf_token_view, name='auth-csrf'),
    path('auth/login/', views.login_view, name='auth-login'),
    path('auth/register/', views.register_view, name='auth-register'),
    path('auth/logout/', views.logout_view, name='auth-logout'),
    path('auth/me/', views.me_view, name='auth-me'),
    path('users/lookup/', views.user_lookup_view, name='user-lookup'),
    path('', include(router.urls)),
]
