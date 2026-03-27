from django.db import migrations, models


def set_article_source(apps, schema_editor):
    Article = apps.get_model('core', 'Article')
    Article.objects.filter(semantic_scholar_id__startswith='scopus:').update(article_source='scopus')
    Article.objects.exclude(semantic_scholar_id__startswith='scopus:').update(article_source='semantic_scholar')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_searchcriteria_source_type_scopus_query_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='article_source',
            field=models.CharField(
                choices=[('semantic_scholar', 'Semantic Scholar'), ('scopus', 'Scopus CSV')],
                db_index=True,
                default='semantic_scholar',
                max_length=30,
                verbose_name='Fuente del artículo',
            ),
        ),
        migrations.RunPython(set_article_source, migrations.RunPython.noop),
    ]
