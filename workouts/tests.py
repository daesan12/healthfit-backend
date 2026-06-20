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
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['workout_id'], self.exercise.id)

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
