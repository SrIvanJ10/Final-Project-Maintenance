from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_searchresultassessment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticleDiscussionMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField(verbose_name='Mensaje')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='discussion_messages', to='core.article', verbose_name='Articulo')),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='article_discussion_messages', to=settings.AUTH_USER_MODEL, verbose_name='Autor')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='article_discussion_messages', to='core.project', verbose_name='Proyecto')),
            ],
            options={
                'verbose_name': 'Mensaje de discusion de articulo',
                'verbose_name_plural': 'Mensajes de discusion de articulos',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='articlediscussionmessage',
            index=models.Index(fields=['project', 'article', 'created_at'], name='core_articl_project_bd0c24_idx'),
        ),
        migrations.AddIndex(
            model_name='articlediscussionmessage',
            index=models.Index(fields=['author', 'created_at'], name='core_articl_author_8fdb01_idx'),
        ),
    ]
