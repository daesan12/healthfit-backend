from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('ai_services', '0001_initial'),
        ('diets', '0003_savedmeal_savedmealitem'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='meal',
            name='meal_label',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='meal',
            name='meal_order',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.CreateModel(
            name='FoodSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('ai_food_key', models.CharField(blank=True, max_length=100)),
                ('source_type', models.CharField(choices=[('db', 'DB'), ('free', 'Free')], max_length=10)),
                ('nutrition_per_100g', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('original_food', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='snapshots', to='diets.food')),
            ],
        ),
        migrations.AlterField(
            model_name='mealitem',
            name='food',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='diets.food'),
        ),
        migrations.AlterField(
            model_name='savedmealitem',
            name='food',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='diets.food'),
        ),
        migrations.AddField(
            model_name='mealitem',
            name='food_snapshot',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='meal_items', to='diets.foodsnapshot'),
        ),
        migrations.AddField(
            model_name='savedmealitem',
            name='food_snapshot',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='saved_meal_items', to='diets.foodsnapshot'),
        ),
        migrations.CreateModel(
            name='SavedMealPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('target_calories', models.FloatField(blank=True, null=True)),
                ('target_carbohydrate', models.FloatField(blank=True, null=True)),
                ('target_protein', models.FloatField(blank=True, null=True)),
                ('target_fat', models.FloatField(blank=True, null=True)),
                ('total_calories', models.FloatField(default=0)),
                ('total_carbohydrate', models.FloatField(default=0)),
                ('total_protein', models.FloatField(default=0)),
                ('total_fat', models.FloatField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source_recommendation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='saved_meal_plans', to='ai_services.airecommendation')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='SavedMealPlanMeal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('meal_order', models.PositiveSmallIntegerField()),
                ('meal_label', models.CharField(max_length=50)),
                ('target_calories', models.FloatField(blank=True, null=True)),
                ('total_calories', models.FloatField(default=0)),
                ('total_carbohydrate', models.FloatField(default=0)),
                ('total_protein', models.FloatField(default=0)),
                ('total_fat', models.FloatField(default=0)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meals', to='diets.savedmealplan')),
            ],
            options={'ordering': ['meal_order', 'id']},
        ),
        migrations.CreateModel(
            name='SavedMealPlanItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.FloatField()),
                ('calories', models.FloatField()),
                ('carbohydrate', models.FloatField()),
                ('protein', models.FloatField()),
                ('fat', models.FloatField()),
                ('food', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='diets.food')),
                ('food_snapshot', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='saved_meal_plan_items', to='diets.foodsnapshot')),
                ('plan_meal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='diets.savedmealplanmeal')),
            ],
        ),
    ]
