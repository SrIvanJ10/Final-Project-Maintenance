from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchcriteria',
            name='scopus_query',
            field=models.TextField(blank=True, verbose_name='Consulta Scopus'),
        ),
        migrations.AddField(
            model_name='searchcriteria',
            name='source_type',
            field=models.CharField(
                choices=[('semantic_scholar', 'Semantic Scholar'), ('scopus', 'Scopus')],
                default='semantic_scholar',
                max_length=30,
                verbose_name='Fuente de búsqueda',
            ),
        ),
        migrations.AlterField(
            model_name='searchcriteria',
            name='keywords',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Palabras clave separadas por comas',
                verbose_name='Palabras clave',
            ),
        ),
    ]
