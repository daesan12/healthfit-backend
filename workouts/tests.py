from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Exercise, WorkoutLog, WorkoutLogSet, WorkoutRoutine


class WorkoutLogSetApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='workout-user', email='workout@example.com', password='password123!'
        )
        self.other_user = User.objects.create_user(
            username='other-workout-user', email='other-workout@example.com', password='password123!'
        )
        self.exercise = Exercise.objects.create(
            exercise_id='bench-press-test',
            name='Bench Press',
            body_parts=['chest'],
            equipments=['barbell'],
            target_muscles=['pectorals'],
            secondary_muscles=['triceps', 'delts'],
            instructions=['Press the bar.'],
        )
        self.routine = WorkoutRoutine.objects.create(user=self.user, name='Push routine')
        self.client.force_authenticate(self.user)

    def set_payload(self):
        return {
            'workout_id': self.exercise.id,
            'routine_id': self.routine.id,
            'workout_date': '2026-06-21',
            'workout_time': 25,
            'memo': '사용자에게만 보이는 메모',
            'sets': [
                {'set_order': 1, 'weight_kg': 60, 'repetition': 10, 'rpe': 8},
                {'set_order': 2, 'weight_kg': 60, 'repetition': 10, 'rpe': 8.5},
                {'set_order': 3, 'weight_kg': 60, 'repetition': 8, 'rpe': 9},
            ],
        }

    def test_create_log_with_multiple_sets_and_summary(self):
        response = self.client.post('/api/v1/workout-logs/', self.set_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        log = WorkoutLog.objects.get(user=self.user)
        self.assertEqual(log.sets.count(), 3)
        self.assertEqual(log.set_count, 3)
        self.assertEqual(log.repetition, 10)
        self.assertEqual(response.data['data']['workout_id'], self.exercise.id)
        self.assertEqual(len(response.data['data']['sets']), 3)

    def test_list_filters_by_workout_id_and_returns_sets(self):
        self.client.post('/api/v1/workout-logs/', self.set_payload(), format='json')
        other_exercise = Exercise.objects.create(
            exercise_id='squat-test', name='Squat', body_parts=['legs'],
            equipments=['barbell'], target_muscles=['quadriceps'],
            secondary_muscles=['glutes'], instructions=['Squat.'],
        )
        payload = self.set_payload()
        payload['workout_id'] = other_exercise.id
        self.client.post('/api/v1/workout-logs/', payload, format='json')

        response = self.client.get(f'/api/v1/workout-logs/?workout_id={self.exercise.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['count'], 1)
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(response.data['data']['results'][0]['workout_id'], self.exercise.id)

    def test_patch_replaces_sets(self):
        created = self.client.post('/api/v1/workout-logs/', self.set_payload(), format='json')
        log_id = created.data['data']['id']

        response = self.client.patch(
            f'/api/v1/workout-logs/{log_id}/',
            {
                'sets': [
                    {'set_order': 1, 'weight_kg': 62.5, 'repetition': 8, 'rpe': 8},
                    {'set_order': 2, 'weight_kg': 62.5, 'repetition': 8, 'rpe': 8.5},
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = WorkoutLog.objects.get(pk=log_id)
        self.assertEqual(log.sets.count(), 2)
        self.assertEqual(log.set_count, 2)
        self.assertEqual(log.repetition, 8)

    def test_delete_log_cascades_sets(self):
        created = self.client.post('/api/v1/workout-logs/', self.set_payload(), format='json')
        log_id = created.data['data']['id']

        response = self.client.delete(f'/api/v1/workout-logs/{log_id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(WorkoutLog.objects.filter(pk=log_id).exists())
        self.assertFalse(WorkoutLogSet.objects.filter(workout_log_id=log_id).exists())

    def test_other_user_cannot_access_log(self):
        created = self.client.post('/api/v1/workout-logs/', self.set_payload(), format='json')
        log_id = created.data['data']['id']
        self.client.force_authenticate(self.other_user)

        response = self.client.get(f'/api/v1/workout-logs/{log_id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_legacy_summary_fields_create_compatible_sets(self):
        response = self.client.post(
            '/api/v1/workout-logs/',
            {
                'exercise_id': self.exercise.id,
                'workout_date': '2026-06-21',
                'workout_time': 20,
                'set_count': 3,
                'repetition': 12,
                'memo': 'legacy request',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WorkoutLogSet.objects.count(), 3)
        self.assertEqual(
            list(WorkoutLogSet.objects.values_list('repetition', flat=True)),
            [12, 12, 12],
        )


class WorkoutPaginationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='workout-pagination',
            email='workout-pagination@example.com',
            password='password123!',
        )
        self.client.force_authenticate(user=self.user)
        Exercise.objects.bulk_create([
            Exercise(
                exercise_id=f'pagination-exercise-{index}',
                name=f'Chest Press {index:02d}',
                body_parts=['chest'],
                equipments=['barbell'],
                target_muscles=['pectorals'],
                secondary_muscles=['triceps'],
                instructions=['Press.'],
            )
            for index in range(25)
        ])
        self.exercise = Exercise.objects.order_by('id').first()

    def assert_paginated(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data['data']['results'], list)
        self.assertIn('total_pages', response.data['data'])
        self.assertIn('has_next', response.data['data'])

    def test_exercises_are_paginated_after_filters(self):
        response = self.client.get(
            '/api/v1/exercises/?body_part=chest&equipment=barbell&target_muscle=pect&page_size=8'
        )

        self.assert_paginated(response)
        data = response.data['data']
        self.assertEqual(data['count'], 25)
        self.assertEqual(len(data['results']), 8)
        self.assertTrue(all(isinstance(item['id'], int) for item in data['results']))

    def test_exercise_source_my_returns_only_custom_exercises(self):
        custom = Exercise.objects.create(
            user=self.user,
            exercise_id='pagination-custom-exercise',
            name='My Press',
            body_parts=['chest'],
            equipments=['dumbbell'],
            target_muscles=['pectorals'],
            secondary_muscles=[],
            instructions=['Press.'],
        )

        response = self.client.get('/api/v1/exercises/?source=my')

        self.assert_paginated(response)
        self.assertEqual(response.data['data']['count'], 1)
        self.assertEqual(response.data['data']['results'][0]['id'], custom.id)

    def test_workout_routines_are_paginated_and_searchable(self):
        WorkoutRoutine.objects.bulk_create([
            WorkoutRoutine(user=self.user, name=f'가슴 루틴 {index}', description='push')
            for index in range(24)
        ])
        WorkoutRoutine.objects.create(user=self.user, name='하체 루틴', description='legs')

        response = self.client.get('/api/v1/workout-routines/?search=가슴&page_size=9')

        self.assert_paginated(response)
        self.assertEqual(response.data['data']['count'], 24)
        self.assertEqual(len(response.data['data']['results']), 9)

    def test_workout_logs_paginate_after_date_and_workout_filters(self):
        start = date(2026, 3, 1)
        WorkoutLog.objects.bulk_create([
            WorkoutLog(
                user=self.user,
                exercise=self.exercise,
                workout_date=start + timedelta(days=index % 3),
                workout_time=30,
            )
            for index in range(15)
        ])

        response = self.client.get(
            f'/api/v1/workout-logs/?start_date=2026-03-01&end_date=2026-03-02'
            f'&workout_id={self.exercise.id}&page_size=6'
        )

        self.assert_paginated(response)
        data = response.data['data']
        self.assertEqual(data['count'], 10)
        self.assertEqual(len(data['results']), 6)
        self.assertTrue(all(item['workout_id'] == self.exercise.id for item in data['results']))
