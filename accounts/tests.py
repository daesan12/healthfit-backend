from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from ai_services.models import DietFeedback
from diets.models import Meal
from workouts.models import Exercise, WorkoutLog

from .models import BodyRecord


class BodyRecordPaginationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='body-pagination',
            email='body-pagination@example.com',
            password='password123!',
        )
        self.client.force_authenticate(user=self.user)
        start = date(2026, 1, 1)
        BodyRecord.objects.bulk_create([
            BodyRecord(user=self.user, record_date=start + timedelta(days=index), weight=70 + index)
            for index in range(25)
        ])

    def test_body_records_are_paginated_after_date_filter(self):
        response = self.client.get(
            '/api/v1/body-records/?start_date=2026-01-10&end_date=2026-01-20&page_size=5'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['count'], 11)
        self.assertEqual(data['page_size'], 5)
        self.assertEqual(len(data['results']), 5)
        self.assertTrue(data['has_next'])


class ProgressApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='progress-user',
            email='progress@example.com',
            password='password123!',
        )
        self.client.force_authenticate(self.user)
        BodyRecord.objects.create(
            user=self.user, record_date='2026-06-20', weight=70
        )
        BodyRecord.objects.create(
            user=self.user, record_date='2026-06-21', weight=72
        )
        Meal.objects.create(
            user=self.user,
            meal_type='breakfast',
            intake_date='2026-06-20',
            total_calories=1800,
        )
        Meal.objects.create(
            user=self.user,
            meal_type='breakfast',
            intake_date='2026-06-21',
            total_calories=2200,
        )
        DietFeedback.objects.create(
            user=self.user,
            target_date='2026-06-20',
            score=80,
            summary='좋습니다.',
            recommendation='유지하세요.',
        )
        DietFeedback.objects.create(
            user=self.user,
            target_date='2026-06-21',
            score=90,
            summary='아주 좋습니다.',
            recommendation='유지하세요.',
        )
        exercise = Exercise.objects.create(
            exercise_id='progress-exercise',
            name='Squat',
            body_parts=['legs'],
            equipments=['barbell'],
            target_muscles=['quadriceps'],
            secondary_muscles=['glutes'],
            instructions=['Squat.'],
        )
        WorkoutLog.objects.create(
            user=self.user, exercise=exercise, workout_date='2026-06-20'
        )
        WorkoutLog.objects.create(
            user=self.user, exercise=exercise, workout_date='2026-06-21'
        )

    def test_progress_returns_averages_scores_workout_count_and_chart(self):
        response = self.client.get(
            '/api/v1/progress/?start_date=2026-06-20&end_date=2026-06-21'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['body_summary']['average_weight'], 71)
        self.assertEqual(data['meal_summary']['average_intake_calories'], 2000)
        self.assertEqual(data['meal_summary']['average_meal_score'], 85)
        self.assertEqual(data['workout_summary']['workout_count'], 2)
        self.assertEqual(len(data['chart_data']), 2)
        self.assertEqual(data['chart_data'][0]['meal_score'], 80)
        self.assertEqual(data['chart_data'][1]['workout_count'], 1)
