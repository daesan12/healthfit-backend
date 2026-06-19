from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Exercise',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exercise_id', models.CharField(max_length=20, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('gif_url', models.URLField()),
                ('body_parts', models.JSONField(default=list)),
                ('equipments', models.JSONField(default=list)),
                ('target_muscles', models.JSONField(default=list)),
                ('secondary_muscles', models.JSONField(default=list)),
                ('instructions', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
    ]
