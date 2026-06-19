from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('workouts', '0002_exercise_user_alter_exercise_gif_url'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkoutRoutine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='workout_routines',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.CreateModel(
            name='RoutineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField()),
                ('sets', models.PositiveIntegerField()),
                ('reps', models.PositiveIntegerField()),
                ('weight', models.FloatField()),
                ('rest_seconds', models.PositiveIntegerField()),
                ('exercise', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='workouts.exercise',
                )),
                ('routine', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='workouts.workoutroutine',
                )),
            ],
            options={
                'ordering': ['order', 'id'],
            },
        ),
    ]
