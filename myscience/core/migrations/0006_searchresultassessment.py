from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_existing_assessments(apps, schema_editor):
    SearchResult = apps.get_model('core', 'SearchResult')
    SearchResultAssessment = apps.get_model('core', 'SearchResultAssessment')

    for result in SearchResult.objects.exclude(assessed_by=None):
        SearchResultAssessment.objects.update_or_create(
            search_result_id=result.id,
            reviewer_id=result.assessed_by_id,
            defaults={
                'relevance': result.relevance,
                'notes': result.reviewer_notes or '',
                'assessed_at': result.assessed_at,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_articleaiinteraction'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SearchResultAssessment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('relevance', models.CharField(choices=[('not_reviewed', 'No revisado'), ('highly_relevant', 'Muy relevante'), ('relevant', 'Relevante'), ('somewhat_relevant', 'Moderadamente relevante'), ('not_relevant', 'No relevante'), ('duplicate', 'Duplicado')], max_length=20, verbose_name='Decision')),
                ('notes', models.TextField(blank=True, verbose_name='Notas')),
                ('assessed_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de evaluacion')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('reviewer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='search_result_assessments', to=settings.AUTH_USER_MODEL, verbose_name='Revisor')),
                ('search_result', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assessments', to='core.searchresult', verbose_name='Resultado de busqueda')),
            ],
            options={
                'verbose_name': 'Evaluacion de resultado',
                'verbose_name_plural': 'Evaluaciones de resultados',
                'ordering': ['reviewer__username'],
                'unique_together': {('search_result', 'reviewer')},
            },
        ),
        migrations.AddIndex(
            model_name='searchresultassessment',
            index=models.Index(fields=['search_result', 'reviewer'], name='core_search_search__fa1497_idx'),
        ),
        migrations.AddIndex(
            model_name='searchresultassessment',
            index=models.Index(fields=['reviewer', 'assessed_at'], name='core_search_reviewe_6cb4cf_idx'),
        ),
        migrations.RunPython(backfill_existing_assessments, migrations.RunPython.noop),
    ]
