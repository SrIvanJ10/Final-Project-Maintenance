from django.db import migrations, models


PRISMA_2020_INCLUSION_TEMPLATE = (
    "PRISMA 2020 inclusion criteria:\n"
    "- Population/Problem: define target participants or domain.\n"
    "- Intervention/Exposure: define intervention or exposure of interest.\n"
    "- Comparator: define comparison condition when applicable.\n"
    "- Outcomes: define primary and secondary outcomes.\n"
    "- Study design: define eligible study designs.\n"
    "- Context and time window: define setting, language, and publication years."
)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_article_article_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='inclusion_criteria',
            field=models.TextField(
                default=PRISMA_2020_INCLUSION_TEMPLATE,
                verbose_name='Criterios de inclusion (PRISMA 2020)',
            ),
        ),
    ]
