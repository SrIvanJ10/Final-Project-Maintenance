from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_project_inclusion_criteria'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticleAIInteraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('llm_provider', models.CharField(choices=[('deepseek', 'DeepSeek'), ('chatgpt', 'ChatGPT'), ('claude', 'Claude')], max_length=20, verbose_name='Proveedor LLM')),
                ('prompt', models.TextField(blank=True, verbose_name='Prompt enviado')),
                ('response_text', models.TextField(blank=True, verbose_name='Respuesta del LLM')),
                ('recommendation', models.CharField(choices=[('include', 'Incluir'), ('exclude', 'Excluir'), ('uncertain', 'Incierto')], default='uncertain', max_length=20, verbose_name='Sugerencia')),
                ('rationale', models.TextField(blank=True, verbose_name='Justificación')),
                ('status', models.CharField(choices=[('pending', 'Pendiente'), ('completed', 'Completada'), ('failed', 'Fallida')], default='pending', max_length=20, verbose_name='Estado')),
                ('error_message', models.TextField(blank=True, verbose_name='Mensaje de error')),
                ('request_payload', models.JSONField(default=dict, verbose_name='Payload de solicitud')),
                ('response_payload', models.JSONField(default=dict, verbose_name='Payload de respuesta')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='Fecha de finalización')),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_interactions', to='core.article', verbose_name='Artículo')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_interactions', to='core.project', verbose_name='Proyecto')),
                ('requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_interactions', to=settings.AUTH_USER_MODEL, verbose_name='Solicitado por')),
                ('search_result', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_interactions', to='core.searchresult', verbose_name='Resultado de búsqueda')),
            ],
            options={
                'verbose_name': 'Interacción IA de artículo',
                'verbose_name_plural': 'Interacciones IA de artículos',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='articleaiinteraction',
            index=models.Index(fields=['project', 'created_at'], name='core_articl_project_ccf6f0_idx'),
        ),
        migrations.AddIndex(
            model_name='articleaiinteraction',
            index=models.Index(fields=['article', 'created_at'], name='core_articl_article_bf2f9b_idx'),
        ),
        migrations.AddIndex(
            model_name='articleaiinteraction',
            index=models.Index(fields=['llm_provider', 'status'], name='core_articl_llm_pro_99ef78_idx'),
        ),
    ]
