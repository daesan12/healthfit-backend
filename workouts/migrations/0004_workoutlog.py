from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('workouts', '0003_workoutroutine_routineitem'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkoutLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('workout_date', models.DateField()),
                ('workout_time', models.PositiveIntegerField()),
                ('set_count', models.PositiveIntegerField()),
                ('repetition', models.PositiveIntegerField()),
                ('memo', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('exercise', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='workouts.exercise',
                )),
                ('routine', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='workouts.workoutroutine',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='workout_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
    ]
