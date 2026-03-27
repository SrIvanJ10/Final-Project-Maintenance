from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_memberships_from_existing_collaborators(apps, schema_editor):
    Project = apps.get_model('core', 'Project')
    ProjectMembership = apps.get_model('core', 'ProjectMembership')

    for project in Project.objects.all():
        collaborator_ids = project.collaborators.values_list('id', flat=True)
        for collaborator_id in collaborator_ids:
            ProjectMembership.objects.get_or_create(
                project_id=project.id,
                user_id=collaborator_id,
                defaults={'role': 'reviewer'},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_articlediscussionmessage'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('owner', 'Owner'), ('reviewer', 'Reviewer'), ('viewer', 'Viewer'), ('advisor', 'Advisor')], default='reviewer', max_length=20, verbose_name='Rol')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='core.project', verbose_name='Proyecto')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_memberships', to=settings.AUTH_USER_MODEL, verbose_name='Usuario')),
            ],
            options={
                'verbose_name': 'Membresia de proyecto',
                'verbose_name_plural': 'Membresias de proyectos',
                'ordering': ['project', 'user__username'],
                'unique_together': {('project', 'user')},
            },
        ),
        migrations.AddIndex(
            model_name='projectmembership',
            index=models.Index(fields=['project', 'role'], name='core_projec_project_6c270f_idx'),
        ),
        migrations.AddIndex(
            model_name='projectmembership',
            index=models.Index(fields=['user', 'role'], name='core_projec_user_id_c87f9c_idx'),
        ),
        migrations.RunPython(create_memberships_from_existing_collaborators, migrations.RunPython.noop),
    ]
