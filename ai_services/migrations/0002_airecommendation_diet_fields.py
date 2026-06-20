import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai_services', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='airecommendation',
            name='content',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='airecommendation',
            name='food_source',
            field=models.CharField(
                choices=[('all', 'All'), ('my_fridge', 'My fridge'), ('free', 'Free')],
                default='all',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='airecommendation',
            name='parent_recommendation',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='derived_recommendations',
                to='ai_services.airecommendation',
            ),
        ),
        migrations.AddField(
            model_name='airecommendation',
            name='recommendation_scope',
            field=models.CharField(
                choices=[
                    ('meal', 'Meal'), ('day', 'Day'), ('remaining', 'Remaining'),
                    ('replacement', 'Replacement'), ('reroll', 'Reroll'),
                ],
                default='meal',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='airecommendation',
            name='target_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
