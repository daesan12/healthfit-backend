from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gender', models.CharField(max_length=20)),
                ('age', models.PositiveIntegerField()),
                ('height', models.FloatField()),
                ('weight', models.FloatField()),
                ('body_type', models.CharField(max_length=50)),
                ('activity_level', models.CharField(max_length=20)),
                ('workout_goal', models.CharField(max_length=30)),
                ('workout_experience', models.CharField(max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='profile',
                    to='accounts.user',
                )),
            ],
        ),
    ]
