from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AIRecommendation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recommendation_type', models.CharField(choices=[('diet', 'Diet'), ('workout', 'Workout')], max_length=20)),
                ('input_data', models.JSONField(default=dict)),
                ('result_data', models.JSONField(default=dict)),
                ('source', models.CharField(max_length=20)),
                ('is_saved', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_recommendations', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='DietFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_date', models.DateField()),
                ('score', models.IntegerField()),
                ('summary', models.TextField()),
                ('good_points', models.JSONField(default=list)),
                ('improvement_points', models.JSONField(default=list)),
                ('recommendation', models.TextField()),
                ('result_data', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='diet_feedbacks', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
