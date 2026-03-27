from django.db import migrations, models


def normalize_ai_interaction_provider(apps, schema_editor):
    ArticleAIInteraction = apps.get_model('core', 'ArticleAIInteraction')
    ArticleAIInteraction.objects.exclude(llm_provider='openai').update(llm_provider='openai')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_projectmembership'),
    ]

    operations = [
        migrations.RunPython(normalize_ai_interaction_provider, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='articleaiinteraction',
            name='llm_provider',
            field=models.CharField(
                choices=[('openai', 'OpenAI')],
                default='openai',
                max_length=20,
                verbose_name='Proveedor LLM',
            ),
        ),
    ]
