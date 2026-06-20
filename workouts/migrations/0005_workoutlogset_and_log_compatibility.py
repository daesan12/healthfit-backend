from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('workouts', '0004_workoutlog')]

    operations = [
        migrations.AlterField(
            model_name='workoutlog',
            name='repetition',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='workoutlog',
            name='set_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='workoutlog',
            name='workout_time',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workoutlog',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='WorkoutLogSet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('set_order', models.PositiveIntegerField()),
                ('weight_kg', models.FloatField(blank=True, null=True)),
                ('repetition', models.PositiveIntegerField(blank=True, null=True)),
                ('duration_seconds', models.PositiveIntegerField(blank=True, null=True)),
                ('rpe', models.FloatField(blank=True, null=True)),
                ('is_warmup', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('workout_log', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sets', to='workouts.workoutlog')),
            ],
            options={
                'ordering': ['set_order', 'id'],
                'constraints': [models.UniqueConstraint(fields=('workout_log', 'set_order'), name='unique_workout_log_set_order')],
            },
        ),
    ]
