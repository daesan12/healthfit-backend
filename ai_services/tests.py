import json
import os
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile
from diets.models import Food, FoodSnapshot, Meal, SavedMeal, SavedMealPlan
from workouts.models import Exercise, RoutineItem, WorkoutLog, WorkoutLogSet, WorkoutRoutine

from .models import AIChat, AIRecommendation, DietFeedback
from .prompts import MEDICAL_BLOCKED_MESSAGE, UNSUPPORTED_BLOCKED_MESSAGE
from .services.gms_client import GMSClient
from .services.gms_client import GMSAPIError, GMSResponseError
from .services.guardrail_service import classify_healthfit_input
from .services.recommendation_service import select_exercise_candidates


class AIApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='ai-user',
            email='ai@example.com',
            password='password123!',
        )
        self.other_user = User.objects.create_user(
            username='other-user',
            email='other@example.com',
            password='password123!',
        )
        Profile.objects.create(
            user=self.user,
            gender='male',
            age=27,
            height=180,
            weight=75,
            body_type='normal',
            activity_level='normal',
            workout_goal='fat_loss',
            workout_experience='beginner',
        )
        self.default_food = Food.objects.create(
            name='닭가슴살',
            category='육류',
            calories=165,
            carbohydrate=0,
            protein=31,
            fat=3.6,
        )
        self.rice = Food.objects.create(
            name='현미밥',
            category='밥류',
            calories=150,
            carbohydrate=32,
            protein=3,
            fat=1,
        )
        self.other_food = Food.objects.create(
            user=self.other_user,
            name='다른 사용자 음식',
            category='기타',
            calories=100,
            carbohydrate=10,
            protein=10,
            fat=2,
        )
        self.impractical_food = Food.objects.create(
            name='생선_육_말린것_대표_평균',
            category='어패류 및 기타 수산물',
            calories=420,
            carbohydrate=1,
            protein=81,
            fat=8,
        )
        self.default_exercise = Exercise.objects.create(
            exercise_id='test-default-exercise',
            name='푸쉬업',
            body_parts=['가슴'],
            equipments=['맨몸'],
            target_muscles=['대흉근'],
            secondary_muscles=['삼두근'],
            instructions=['자세를 유지합니다.'],
        )
        self.barbell_exercise = Exercise.objects.create(
            exercise_id='bench-progression',
            name='Bench Press',
            body_parts=['chest'],
            equipments=['barbell'],
            target_muscles=['pectorals'],
            secondary_muscles=['triceps', 'delts'],
            instructions=['Press the bar.'],
        )
        self.delt_exercise = Exercise.objects.create(
            exercise_id='delt-progression',
            name='Shoulder Press',
            body_parts=['shoulders'],
            equipments=['dumbbell'],
            target_muscles=['delts'],
            secondary_muscles=['triceps'],
            instructions=['Press the dumbbells.'],
        )
        self.client.force_authenticate(self.user)
        self.guardrail_patcher = patch(
            'ai_services.services.recommendation_service.classify_healthfit_input',
            return_value={
                'is_allowed': True,
                'category': 'health_habit',
                'risk_level': 'normal',
                'relevant_summary': 'HealthFit 관련 요청',
                'reason': '테스트 기본 허용',
                'blocked_message': '',
            },
        )
        self.mock_recommendation_guardrail = self.guardrail_patcher.start()
        self.addCleanup(self.guardrail_patcher.stop)

    def test_missing_gms_key_returns_required_common_error(self):
        with patch.dict(os.environ, {'GMS_KEY': ''}):
            response = self.client.post(
                '/api/v1/ai/diet/evaluations/',
                {'target_date': '2026-06-20'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data,
            {
                'success': False,
                'message': 'AI API key is not configured.',
                'errors': {'GMS_KEY': ['GMS_KEY is missing.']},
            },
        )

    @patch('ai_services.services.gms_client.requests.post')
    def test_gms_client_uses_ssafy_proxy_endpoint(self, mock_post):
        response = mock_post.return_value
        response.status_code = 200
        response.content = json.dumps({
            'candidates': [
                {'content': {'parts': [{'text': '```json\n{"ok":true}\n```'}]}},
            ],
        }).encode('utf-8')
        response.json.return_value = json.loads(response.content.decode('utf-8'))

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            result = GMSClient().generate_json('JSON으로 응답하세요.')

        request_url = mock_post.call_args.args[0]
        request_payload = mock_post.call_args.kwargs['json']
        self.assertEqual(
            request_url,
            'https://gms.ssafy.io/gmsapi/'
            'generativelanguage.googleapis.com/v1beta/'
            'models/gemini-2.5-flash-lite:generateContent',
        )
        self.assertEqual(list(request_payload), ['contents', 'generationConfig'])
        self.assertEqual(
            request_payload['generationConfig']['responseMimeType'],
            'application/json',
        )
        self.assertEqual(result, {'ok': True})

    @patch('ai_services.services.gms_client.requests.post')
    def test_gms_client_retries_one_empty_success_response(self, mock_post):
        empty_response = MagicMock()
        empty_response.status_code = 200
        empty_response.content = b''
        valid_response = MagicMock()
        valid_response.status_code = 200
        valid_response.content = json.dumps({
            'candidates': [
                {'content': {'parts': [{'text': '{"ok":true}'}]}},
            ],
        }).encode('utf-8')
        valid_response.json.return_value = json.loads(valid_response.content.decode('utf-8'))
        mock_post.side_effect = [empty_response, valid_response]

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            result = GMSClient().generate_json('JSON으로 응답하세요.')

        self.assertEqual(result, {'ok': True})
        self.assertEqual(mock_post.call_count, 2)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_diet_evaluation_saves_feedback(self, mock_generate):
        Meal.objects.create(
            user=self.user,
            meal_type='dinner',
            intake_date='2026-06-20',
            total_calories=600,
            total_carbohydrate=60,
            total_protein=45,
            total_fat=20,
        )
        mock_generate.return_value = {
            'score': 82,
            'summary': '단백질 섭취가 좋습니다.',
            'good_points': ['단백질 섭취가 적절합니다.'],
            'improvement_points': ['채소를 추가하세요.'],
            'recommendation': '샐러드를 곁들이세요.',
        }

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/evaluations/',
                {'target_date': '2026-06-20'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['score'], 82)
        self.assertEqual(response.data['data']['strengths'], ['단백질 섭취가 적절합니다.'])
        self.assertEqual(response.data['data']['recommended_actions'], ['샐러드를 곁들이세요.'])
        self.assertEqual(response.data['data']['result_data']['total_calories'], 600)
        self.assertEqual(DietFeedback.objects.filter(user=self.user).count(), 1)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_diet_recommendation_recalculates_nutrition_and_saves_result(self, mock_generate):
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'conditions': {'max_candidates': 60}},
            {
                'title': '고단백 저녁 식단',
                'summary': '단백질 중심 식단입니다.',
                'items': [
                    {'food_id': self.default_food.id, 'amount': 150, 'role': 'protein'},
                    {'food_id': self.rice.id, 'amount': 120, 'role': 'carb'},
                ],
            },
        ]

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {
                    'message': '고단백 저녁 추천해줘',
                    'meal_type': 'dinner',
                    'target_date': '2026-06-20',
                    'food_source': 'all',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        item = response.data['data']['items'][0]
        self.assertEqual(item['food_id'], self.default_food.id)
        self.assertEqual(item['calories'], 247.5)
        self.assertEqual(item['protein'], 46.5)
        self.assertEqual(response.data['data']['food_source'], 'all')
        self.assertTrue(response.data['data']['save_available'])
        self.assertEqual(AIRecommendation.objects.filter(user=self.user).count(), 1)
        recommendation = AIRecommendation.objects.get(user=self.user)
        self.assertEqual(recommendation.input_data['message'], '고단백 저녁 추천해줘')
        self.mock_recommendation_guardrail.assert_called_with(
            '고단백 저녁 추천해줘',
            request_context='diet recommendation request',
        )
        condition_prompt = mock_generate.call_args_list[0].args[0]
        recommendation_prompt = mock_generate.call_args_list[1].args[0]
        self.assertIn('HealthFit 관련 요청', condition_prompt)
        self.assertIn('HealthFit PT coach voice', recommendation_prompt)
        self.assertNotIn(self.impractical_food.name, recommendation_prompt)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_diet_recommendation_rejects_other_users_food_id(self, mock_generate):
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'conditions': {'max_candidates': 60}},
            {
                'title': '잘못된 식단',
                'summary': '사용할 수 없는 음식입니다.',
                'items': [
                    {'food_id': self.other_food.id, 'amount': 100, 'role': 'protein'},
                    {'food_id': self.rice.id, 'amount': 100, 'role': 'carb'},
                ],
            },
        ]

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {
                    'message': '저녁 추천해줘',
                    'target_date': '2026-06-20',
                    'food_source': 'all',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertFalse(response.data['success'])
        self.assertEqual(AIRecommendation.objects.count(), 0)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_full_day_five_meal_recommendation_and_plan_save(self, mock_generate):
        meals = [
            {
                'meal_order': order,
                'meal_label': f'{order}번째 식사',
                'items': [
                    {'food_id': self.default_food.id, 'amount': 100, 'role': 'protein'},
                    {'food_id': self.rice.id, 'amount': 100, 'role': 'carb'},
                ],
            }
            for order in range(1, 6)
        ]
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'scope': 'day', 'meal_count': 5, 'conditions': {}},
            {'title': '하루 5끼 식단', 'summary': '균형 잡힌 식단', 'meals': meals},
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {
                    'scope': 'day', 'message': '하루 5끼 식단',
                    'target_date': '2026-06-21', 'food_source': 'all', 'meal_count': 5,
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['meals']), 5)
        daily_target = response.data['data']['daily_target']['target_calories']
        self.assertEqual(
            [meal['target_calories'] for meal in response.data['data']['meals']],
            [round(daily_target * ratio / 100, 2) for ratio in [20, 25, 10, 25, 20]],
        )
        save_response = self.client.post(
            f"/api/v1/ai/diet/recommendations/{response.data['data']['recommendation_id']}/save/",
            {'save_target': 'meal_plan', 'title': '나의 5끼 식단', 'description': '테스트'},
            format='json',
        )
        self.assertEqual(save_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SavedMealPlan.objects.get(user=self.user).meals.count(), 5)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_full_day_retries_when_gms_returns_wrong_meal_count(self, mock_generate):
        valid_meals = [
            {
                'meal_order': order,
                'meal_label': f'{order}번째 식사',
                'items': [
                    {'food_id': self.default_food.id, 'amount': 100, 'role': 'protein'},
                    {'food_id': self.rice.id, 'amount': 100, 'role': 'carb'},
                ],
            }
            for order in range(1, 6)
        ]
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'scope': 'day', 'meal_count': 1, 'conditions': {}},
            {'title': '잘못된 한 끼', 'summary': '끼니 수 오류', 'meals': [valid_meals[0]]},
            {'title': '교정된 다섯 끼', 'summary': '요청대로 교정', 'meals': valid_meals},
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {
                    'scope': 'day', 'message': '하루 식단을 추천해줘',
                    'target_date': '2026-06-21', 'food_source': 'all', 'meal_count': 5,
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['meals']), 5)
        self.assertEqual(mock_generate.call_count, 3)
        retry_prompt = mock_generate.call_args_list[2].args[0]
        self.assertIn('반드시 meals를 5개', retry_prompt)
        self.assertIn('[1, 2, 3, 4, 5]', retry_prompt)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_remaining_recommendation_uses_existing_meal_totals(self, mock_generate):
        Meal.objects.create(
            user=self.user,
            meal_type='meal',
            intake_date='2026-06-21',
            total_calories=700,
            total_carbohydrate=80,
            total_protein=45,
            total_fat=20,
        )
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'scope': 'remaining', 'conditions': {}},
            {
                'title': '남은 영양 식단',
                'summary': '남은 목표 반영',
                'meals': [{
                    'meal_order': 2,
                    'meal_label': '저녁',
                    'items': [
                        {'food_id': self.default_food.id, 'amount': 120, 'role': 'protein'},
                        {'food_id': self.rice.id, 'amount': 100, 'role': 'carb'},
                    ],
                }],
            },
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {
                    'scope': 'remaining', 'message': '남은 목표에 맞춰줘',
                    'target_date': '2026-06-21', 'food_source': 'all',
                    'meal_order': 2, 'meal_label': '저녁',
                },
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['already_eaten']['calories'], 700)
        self.assertEqual(response.data['data']['meal']['meal_order'], 2)

    def test_recommendation_detail_is_owner_only(self):
        recommendation = self.create_diet_recommendation()
        own_response = self.client.get(f'/api/v1/ai/diet/recommendations/{recommendation.id}/')
        self.assertEqual(own_response.status_code, status.HTTP_200_OK)
        self.assertEqual(own_response.data['data']['content']['title'], '고단백 저녁 식단')

        self.client.force_authenticate(self.other_user)
        other_response = self.client.get(f'/api/v1/ai/diet/recommendations/{recommendation.id}/')
        self.assertEqual(other_response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_replace_creates_child_without_mutating_original(self, mock_generate):
        recommendation = self.create_diet_recommendation()
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'excluded_foods': [], 'conditions': {}},
            {'item': {'food_id': self.rice.id, 'amount': 120, 'role': 'carb'}},
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                f'/api/v1/ai/diet/recommendations/{recommendation.id}/replace/',
                {'meal_order': 1, 'replace_food_id': self.default_food.id, 'message': '현미밥으로 바꿔줘'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        child = AIRecommendation.objects.get(pk=response.data['data']['recommendation_id'])
        self.assertEqual(child.parent_recommendation, recommendation)
        self.assertEqual(child.recommendation_scope, AIRecommendation.SCOPE_REPLACEMENT)
        recommendation.refresh_from_db()
        self.assertEqual(recommendation.content['items'][0]['food_id'], self.default_food.id)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_reroll_preserves_source_and_creates_child(self, mock_generate):
        recommendation = self.create_diet_recommendation()
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'excluded_foods': [], 'conditions': {}},
            {
                'title': '다시 추천한 식단', 'summary': '간단한 식단',
                'meals': [{
                    'meal_order': 1, 'meal_label': '저녁',
                    'items': [
                        {'food_id': self.rice.id, 'amount': 120, 'role': 'carb'},
                        {'food_id': self.default_food.id, 'amount': 100, 'role': 'protein'},
                    ],
                }],
            },
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                f'/api/v1/ai/diet/recommendations/{recommendation.id}/reroll/',
                {'message': '더 간단하게 다시 추천해줘'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        child = AIRecommendation.objects.get(pk=response.data['data']['recommendation_id'])
        self.assertEqual(child.parent_recommendation, recommendation)
        self.assertEqual(child.recommendation_scope, AIRecommendation.SCOPE_REROLL)
        self.assertEqual(child.food_source, 'all')
        self.assertEqual(child.content['original_scope'], 'meal')

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_my_fridge_uses_only_current_user_foods(self, mock_generate):
        tofu = Food.objects.create(
            user=self.user, name='내 두부', category='구이류',
            calories=95, carbohydrate=3, protein=10, fat=5,
        )
        potato = Food.objects.create(
            user=self.user, name='내 감자', category='감자류 및 전분류',
            calories=80, carbohydrate=18, protein=2, fat=0,
        )
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'conditions': {}},
            {
                'title': '냉장고 식단', 'summary': '내 음식만 사용',
                'meals': [{
                    'meal_order': 1, 'meal_label': '저녁',
                    'items': [
                        {'food_id': tofu.id, 'amount': 150, 'role': 'protein'},
                        {'food_id': potato.id, 'amount': 150, 'role': 'carb'},
                    ],
                }],
            },
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {'message': '내 음식으로 추천', 'target_date': '2026-06-21', 'food_source': 'my_fridge'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prompt = mock_generate.call_args_list[1].args[0]
        self.assertIn('내 두부', prompt)
        self.assertNotIn(self.default_food.name, prompt)

    def test_free_full_day_plan_can_be_saved(self):
        recommendation = self.create_free_diet_recommendation(scope='day', meal_count=2)
        response = self.client.post(
            f'/api/v1/ai/diet/recommendations/{recommendation.id}/save/',
            {'save_target': 'meal_plan', 'title': '자유 하루 플랜'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SavedMealPlan.objects.get(user=self.user).meals.count(), 2)
        self.assertEqual(FoodSnapshot.objects.count(), 4)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_free_replace_creates_new_snapshot_content(self, mock_generate):
        recommendation = self.create_free_diet_recommendation()
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'conditions': {}},
            {'item': {
                'food_id': None, 'ai_food_key': 'free_fish_new', 'name': '흰살생선구이',
                'amount': 140, 'role': 'protein',
                'nutrition_per_100g': {'calories': 130, 'carbohydrate': 0, 'protein': 24, 'fat': 4},
            }},
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                f'/api/v1/ai/diet/recommendations/{recommendation.id}/replace/',
                {'meal_order': 1, 'replace_ai_food_key': 'free_protein_1', 'message': '생선으로 교체'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['items'][0]['ai_food_key'], 'free_fish_new')

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_free_reroll_preserves_free_source(self, mock_generate):
        recommendation = self.create_free_diet_recommendation()
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'conditions': {}},
            {
                'title': '새 자유 식단', 'summary': '다시 추천',
                'meals': [self.free_meal(1, '저녁', key_suffix='reroll')],
            },
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                f'/api/v1/ai/diet/recommendations/{recommendation.id}/reroll/',
                {'message': '더 간단하게'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        child = AIRecommendation.objects.get(pk=response.data['data']['recommendation_id'])
        self.assertEqual(child.food_source, 'free')
        self.assertEqual(child.recommendation_scope, AIRecommendation.SCOPE_REROLL)

    def test_remaining_too_low_returns_helpful_error_without_gms_call(self):
        Meal.objects.create(
            user=self.user, meal_type='meal', intake_date='2026-06-21',
            total_calories=10000, total_carbohydrate=1000, total_protein=1000, total_fat=1000,
        )
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {'scope': 'remaining', 'target_date': '2026-06-21', 'food_source': 'all'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('remaining_calories', response.data['errors'])

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_day_scope_defaults_to_three_meals(self, mock_generate):
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'conditions': {}},
            {
                'title': '기본 세 끼', 'summary': '세 끼 식단',
                'meals': [
                    {
                        'meal_order': order, 'meal_label': f'{order}번째 식사',
                        'items': [
                            {'food_id': self.default_food.id, 'amount': 100, 'role': 'protein'},
                            {'food_id': self.rice.id, 'amount': 100, 'role': 'carb'},
                        ],
                    }
                    for order in range(1, 4)
                ],
            },
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {'scope': 'day', 'target_date': '2026-06-21', 'food_source': 'all'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['meals']), 3)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_free_day_normalizes_common_gms_field_variants(self, mock_generate):
        mock_generate.side_effect = [
            {
                'intent': 'diet_recommendation',
                'preferred_foods': None,
                'excluded_foods': None,
                'conditions': {},
            },
            {
                'title': '자유 세 끼',
                'description': '간단한 세 끼 식단',
                'meals': [
                    {
                        'foods': [
                            {
                                'food_name': '두부구이',
                                'amount': '150g',
                                'nutrition': {
                                    'kcal': '97 kcal', 'carbs': '3g',
                                    'proteins': '10g', 'fats': '5g',
                                },
                            },
                            {
                                'food_name': '현미밥',
                                'amount': '120 g',
                                'nutrition': {
                                    'kcal': 150, 'carbs': 32,
                                    'proteins': 3, 'fats': 1,
                                },
                            },
                        ],
                    }
                    for _ in range(3)
                ],
            },
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {
                    'scope': 'day', 'message': '하루 세 끼 자유식 추천',
                    'target_date': '2026-06-21', 'food_source': 'free', 'meal_count': 3,
                },
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['meals']), 3)
        first_item = response.data['data']['meals'][0]['items'][0]
        self.assertEqual(first_item['amount'], 150.0)
        self.assertEqual(first_item['ai_food_key'], 'free_1_1')
        self.assertEqual(first_item['carbohydrate'], 4.5)

    def test_diet_ai_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            '/api/v1/ai/diet/recommendations/',
            {'target_date': '2026-06-21'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_free_diet_recommendation_can_be_saved_as_meal(self, mock_generate):
        mock_generate.side_effect = [
            {'intent': 'diet_recommendation', 'conditions': {}},
            {
                'title': '자유 추천 식단',
                'summary': 'DB 외 음식 추천입니다.',
                'meals': [{
                    'meal_order': 1,
                    'meal_label': '저녁',
                    'items': [
                        {
                            'food_id': None,
                            'ai_food_key': 'free_salmon_001',
                            'name': '연어구이',
                            'amount': 150,
                            'role': 'protein',
                            'nutrition_per_100g': {
                                'calories': 208, 'carbohydrate': 0,
                                'protein': 20, 'fat': 13,
                            },
                        },
                        {
                            'food_id': None,
                            'ai_food_key': 'free_salad_001',
                            'name': '채소 샐러드',
                            'amount': 120,
                            'role': 'vegetable',
                            'nutrition_per_100g': {
                                'calories': 35, 'carbohydrate': 7,
                                'protein': 2, 'fat': 0.5,
                            },
                        },
                    ],
                }],
            },
        ]
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            recommendation_response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {
                    'message': '자유롭게 추천해줘',
                    'target_date': '2026-06-20',
                    'food_source': 'free',
                },
                format='json',
            )

        recommendation_id = recommendation_response.data['data']['recommendation_id']
        response = self.client.post(
            f'/api/v1/ai/diet/recommendations/{recommendation_id}/save/',
            {'save_target': 'meals', 'title': '자유 추천 저녁'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Meal.objects.count(), 1)
        self.assertEqual(FoodSnapshot.objects.count(), 2)

    def test_diet_recommendation_can_be_saved_as_meal_and_saved_meal(self):
        recommendation = self.create_diet_recommendation()

        meal_response = self.client.post(
            f'/api/v1/ai/recommendations/{recommendation.id}/save-meal/',
            {'meal_type': 'dinner', 'intake_date': '2026-06-20'},
            format='json',
        )
        saved_meal_response = self.client.post(
            f'/api/v1/ai/diet/recommendations/{recommendation.id}/save/',
            {'name': 'AI 저녁 식단', 'description': '고단백 식단'},
            format='json',
        )

        self.assertEqual(meal_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(saved_meal_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Meal.objects.filter(user=self.user).count(), 1)
        self.assertEqual(SavedMeal.objects.filter(user=self.user).count(), 1)
        recommendation.refresh_from_db()
        self.assertTrue(recommendation.is_saved)

    def test_workout_recommendation_can_be_saved_as_routine(self):
        recommendation = AIRecommendation.objects.create(
            user=self.user,
            recommendation_type=AIRecommendation.WORKOUT,
            input_data={},
            source='all',
            result_data={
                'type': 'workout',
                'items': [
                    {
                        'exercise_id': self.default_exercise.id,
                        'exercise_name': self.default_exercise.name,
                        'order': 1,
                        'sets': 3,
                        'reps': 12,
                        'weight': 0,
                        'rest_seconds': 60,
                    }
                ],
            },
        )

        response = self.client.post(
            f'/api/v1/ai/recommendations/{recommendation.id}/save-routine/',
            {'name': 'AI 가슴 루틴', 'description': '초보자 루틴'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        routine = WorkoutRoutine.objects.get(user=self.user)
        self.assertEqual(RoutineItem.objects.get(routine=routine).exercise, self.default_exercise)

    @patch('ai_services.services.recommendation_service.GMSClient.generate_json')
    def test_workout_recommendation_uses_exercise_database_pk(self, mock_generate):
        mock_generate.side_effect = [
            {'intent': 'workout_recommendation', 'conditions': {'max_candidates': 60}},
            {
                'title': '초보자 가슴 루틴',
                'description': '맨몸 운동 중심입니다.',
                'items': [
                    {
                        'exercise_id': self.barbell_exercise.id,
                        'order': 1,
                        'sets': 3,
                        'reps': 12,
                        'weight': 0,
                        'rest_seconds': 60,
                    }
                ],
            },
        ]

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/workout/recommendations/',
                {
                    'message': '초보자 가슴 루틴 추천해줘',
                    'target_body_part': '가슴',
                    'available_time': 60,
                    'exercise_source': 'all',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data['data']['items'][0]
        self.assertEqual(item['exercise_id'], self.barbell_exercise.pk)
        self.assertEqual(item['exercise_name'], self.barbell_exercise.name)
        self.assertEqual(response.data['data']['exercise_source'], 'all')
        self.assertEqual(AIRecommendation.objects.filter(user=self.user).count(), 1)

    def test_workout_candidates_filter_before_limit(self):
        Exercise.objects.bulk_create([
            Exercise(
                exercise_id=f'distractor-{index}',
                name=f'Irrelevant Exercise {index}',
                body_parts=['legs'],
                equipments=['machine'],
                target_muscles=['quadriceps'],
                secondary_muscles=[],
                instructions=['Move.'],
            )
            for index in range(205)
        ])
        late_match = Exercise.objects.create(
            exercise_id='late-chest-match',
            name='Late Chest Press',
            body_parts=['chest'],
            equipments=['barbell'],
            target_muscles=['pectorals'],
            secondary_muscles=['triceps'],
            instructions=['Press.'],
        )

        candidates = select_exercise_candidates(
            self.user,
            'all',
            {
                'body_part_keywords': ['chest'],
                'equipment_keywords': ['barbell'],
                'max_candidates': 30,
            },
        )

        self.assertIn(late_match, candidates)
        self.assertTrue(all('chest' in exercise.body_parts for exercise in candidates))
        self.assertTrue(all('barbell' in exercise.equipments for exercise in candidates))

    def test_workout_candidates_do_not_fallback_to_unrelated_exercises(self):
        candidates = select_exercise_candidates(
            self.user,
            'all',
            {'body_part_keywords': ['존재하지않는부위'], 'max_candidates': 60},
        )

        self.assertEqual(candidates, [])

    @patch('ai_services.services.workout_progression_service.GMSClient.generate_json')
    def test_workout_progression_without_history_is_conservative(self, mock_generate):
        mock_generate.return_value = {'invalid': True}
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/workout/progression/',
                {
                    'workout_id': self.barbell_exercise.id,
                    'target_date': '2026-06-24',
                    'goal': 'muscle_gain',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['decision'], 'insufficient_history')
        self.assertEqual(response.data['data']['recommendation']['set_count'], 3)
        self.assertIsNone(response.data['data']['recommendation']['weight_kg'])

    @patch('ai_services.services.workout_progression_service.GMSClient.generate_json')
    def test_workout_progression_increases_stable_recovered_history(self, mock_generate):
        self.create_workout_log(
            self.barbell_exercise,
            date(2026, 6, 21),
            [(60, 10, 8), (60, 10, 8), (60, 10, 8.5)],
        )
        mock_generate.return_value = {
            'decision': 'increase',
            'recommendation': {
                'set_count': 3, 'repetition': 10,
                'weight_kg': 62.5, 'rest_seconds': 120,
            },
            'reason': '세 세트 반복이 안정적이고 관련 근육이 3일 회복되었습니다.',
            'safety_note': '체감 난이도에 따라 직접 조절하세요.',
        }
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/workout/progression/',
                {
                    'workout_id': self.barbell_exercise.id,
                    'target_date': '2026-06-24',
                    'goal': 'muscle_gain',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['decision'], 'increase')
        self.assertEqual(data['recommendation']['weight_kg'], 62.5)
        self.assertEqual(data['history_summary'][0]['total_volume'], 1800.0)
        self.assertTrue(all(item['status'] == 'recovered' for item in data['recovery_summary']))

    @patch('ai_services.services.workout_progression_service.GMSClient.generate_json')
    def test_recent_secondary_muscle_blocks_unsafe_gms_increase_and_memo_is_not_sent(self, mock_generate):
        self.create_workout_log(
            self.barbell_exercise,
            date(2026, 6, 21),
            [(60, 10, 8), (60, 10, 8), (60, 10, 8)],
            memo='절대로 AI에 보내면 안 되는 메모',
        )
        self.create_workout_log(
            self.delt_exercise,
            date(2026, 6, 23),
            [(10, 12, 8), (10, 12, 8)],
            memo='통증이라는 단어도 판단에 사용 금지',
        )
        mock_generate.return_value = {
            'decision': 'increase',
            'recommendation': {
                'set_count': 3, 'repetition': 10,
                'weight_kg': 62.5, 'rest_seconds': 120,
            },
            'reason': '증가',
            'safety_note': '직접 조절하세요.',
        }
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/workout/progression/',
                {
                    'workout_id': self.barbell_exercise.id,
                    'target_date': '2026-06-24',
                    'message': '다음 목표를 추천해줘.',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['decision'], 'maintain')
        self.assertEqual(data['recommendation']['weight_kg'], 60.0)
        delts = next(item for item in data['recovery_summary'] if item['muscle'] == 'delts')
        self.assertEqual(delts['days_since'], 1)
        prompt = mock_generate.call_args.args[0]
        self.assertNotIn('절대로 AI에 보내면 안 되는 메모', prompt)
        self.assertNotIn('통증이라는 단어도 판단에 사용 금지', prompt)

    @patch('ai_services.services.workout_progression_service.GMSClient.generate_json')
    def test_gms_failure_falls_back_to_backend_decrease(self, mock_generate):
        self.create_workout_log(
            self.barbell_exercise,
            date(2026, 6, 20),
            [(60, 8, 8), (60, 6, 9), (60, 4, 10)],
        )
        mock_generate.side_effect = GMSAPIError('temporary failure', status_code=502)
        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/workout/progression/',
                {'workout_id': self.barbell_exercise.id, 'target_date': '2026-06-24'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['decision'], 'decrease')
        self.assertEqual(response.data['data']['recommendation']['weight_kg'], 57.5)

    def create_diet_recommendation(self):
        amount = 150
        content = {
            'type': 'diet',
            'scope': 'meal',
            'food_source': 'all',
            'title': '고단백 저녁 식단',
            'summary': '단백질 중심 식단입니다.',
            'meals': [{
                'meal_order': 1,
                'meal_label': '저녁',
                'items': [
                    {
                        'food_id': self.default_food.id,
                        'food_name': self.default_food.name,
                        'name': self.default_food.name,
                        'amount': amount,
                        'role': 'protein',
                        'calories': 247.5,
                        'carbohydrate': 0,
                        'protein': 46.5,
                        'fat': 5.4,
                    }
                ],
                'total_calories': 247.5,
                'total_carbohydrate': 0,
                'total_protein': 46.5,
                'total_fat': 5.4,
            }],
            'items': [
                {
                    'food_id': self.default_food.id,
                    'food_name': self.default_food.name,
                    'name': self.default_food.name,
                    'amount': amount,
                    'role': 'protein',
                    'calories': 247.5,
                    'carbohydrate': 0,
                    'protein': 46.5,
                    'fat': 5.4,
                }
            ],
            'total_calories': 247.5,
            'total_carbohydrate': 0,
            'total_protein': 46.5,
            'total_fat': 5.4,
        }
        return AIRecommendation.objects.create(
            user=self.user,
            recommendation_type=AIRecommendation.DIET,
            input_data={'scope': 'meal', 'target_date': '2026-06-20', 'food_source': 'all'},
            source='all',
            food_source='all',
            target_date='2026-06-20',
            result_data=content,
            content=content,
        )

    def create_workout_log(self, exercise, workout_date, sets, memo=''):
        log = WorkoutLog.objects.create(
            user=self.user,
            exercise=exercise,
            workout_date=workout_date,
            workout_time=30,
            memo=memo,
        )
        WorkoutLogSet.objects.bulk_create([
            WorkoutLogSet(
                workout_log=log,
                set_order=index,
                weight_kg=weight,
                repetition=repetition,
                rpe=rpe,
                is_warmup=False,
            )
            for index, (weight, repetition, rpe) in enumerate(sets, start=1)
        ])
        log.update_summary_from_sets()
        return log

    def free_meal(self, order, label, key_suffix=None):
        suffix = key_suffix or str(order)
        return {
            'meal_order': order,
            'meal_label': label,
            'items': [
                {
                    'food_id': None, 'ai_food_key': f'free_protein_{suffix}',
                    'name': '두부구이', 'amount': 150, 'role': 'protein',
                    'nutrition_per_100g': {
                        'calories': 97, 'carbohydrate': 3, 'protein': 10, 'fat': 5,
                    },
                    'calories': 145.5, 'carbohydrate': 4.5, 'protein': 15, 'fat': 7.5,
                },
                {
                    'food_id': None, 'ai_food_key': f'free_rice_{suffix}',
                    'name': '현미밥', 'amount': 120, 'role': 'carb',
                    'nutrition_per_100g': {
                        'calories': 150, 'carbohydrate': 32, 'protein': 3, 'fat': 1,
                    },
                    'calories': 180, 'carbohydrate': 38.4, 'protein': 3.6, 'fat': 1.2,
                },
            ],
            'total_calories': 325.5,
            'total_carbohydrate': 42.9,
            'total_protein': 18.6,
            'total_fat': 8.7,
        }

    def create_free_diet_recommendation(self, scope='meal', meal_count=1):
        meals = [self.free_meal(order, f'{order}번째 식사') for order in range(1, meal_count + 1)]
        content = {
            'type': 'diet', 'scope': scope, 'food_source': 'free',
            'title': '자유 추천 식단', 'summary': 'DB 밖 음식 포함',
            'meals': meals, 'items': meals[0]['items'],
            'total_calories': meals[0]['total_calories'],
            'total_carbohydrate': meals[0]['total_carbohydrate'],
            'total_protein': meals[0]['total_protein'],
            'total_fat': meals[0]['total_fat'],
            'daily_target': {
                'target_calories': 2000, 'target_carbohydrate': 250,
                'target_protein': 150, 'target_fat': 44.4,
            },
            'daily_totals': {
                'total_calories': 325.5 * meal_count,
                'total_carbohydrate': 42.9 * meal_count,
                'total_protein': 18.6 * meal_count,
                'total_fat': 8.7 * meal_count,
            },
        }
        return AIRecommendation.objects.create(
            user=self.user,
            recommendation_type=AIRecommendation.DIET,
            recommendation_scope=scope,
            food_source='free',
            source='free',
            target_date='2026-06-20',
            input_data={
                'scope': scope, 'target_date': '2026-06-20',
                'food_source': 'free', 'meal_count': meal_count,
            },
            result_data=content,
            content=content,
        )


class AIGuardrailAndChatTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='guardrail-user',
            email='guardrail@example.com',
            password='password123!',
        )
        Profile.objects.create(
            user=self.user,
            gender='male',
            age=30,
            height=175,
            weight=75,
            body_type='normal',
            activity_level='normal',
            workout_goal='fat_loss',
            workout_experience='beginner',
        )
        self.client.force_authenticate(self.user)

    @patch('ai_services.services.guardrail_service.GMSClient.generate_json')
    def test_guardrail_parse_failure_uses_safe_fallback(self, mock_generate):
        mock_generate.side_effect = GMSResponseError('invalid JSON')

        result = classify_healthfit_input(
            '게임 랭크 올리는 법 알려줘',
            request_context='AI chat question',
        )

        self.assertFalse(result['is_allowed'])
        self.assertEqual(result['category'], 'unsupported')
        self.assertEqual(result['blocked_message'], UNSUPPORTED_BLOCKED_MESSAGE)
        self.assertIn('Failed to parse', result['reason'])
        self.assertEqual(mock_generate.call_args.kwargs['temperature'], 0)

    @patch('ai_services.services.chat_service.GMSClient.generate_json')
    @patch('ai_services.services.chat_service.classify_healthfit_input')
    def test_allowed_chat_uses_latest_five_history_and_preserves_question(
        self,
        mock_classify,
        mock_generate,
    ):
        for index in range(6):
            AIChat.objects.create(
                user=self.user,
                question=f'이전 질문 {index}',
                answer=f'이전 답변 {index}',
            )
        mock_classify.return_value = {
            'is_allowed': True,
            'category': 'diet',
            'risk_level': 'normal',
            'relevant_summary': '내일 식단을 이어서 추천해 달라는 요청',
            'reason': '최근 식단 대화와 이어지는 질문',
            'blocked_message': '',
        }
        mock_generate.return_value = {'answer': '좋습니다. 내일은 단백질부터 확보합니다.'}
        question = '그럼 내일은?'

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post('/api/v1/ai/chats/', {'question': question}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        chat = AIChat.objects.get(pk=response.data['data']['id'])
        self.assertEqual(chat.question, question)
        self.assertEqual(chat.answer, '좋습니다. 내일은 단백질부터 확보합니다.')
        history = mock_classify.call_args.kwargs['recent_history']
        self.assertNotIn('이전 질문 0', history)
        self.assertIn('이전 질문 1', history)
        self.assertLess(history.index('이전 질문 1'), history.index('이전 질문 5'))
        self.assertEqual(mock_generate.call_args.kwargs['temperature'], 0.7)

    @patch('ai_services.services.chat_service.GMSClient.generate_json')
    @patch('ai_services.services.chat_service.classify_healthfit_input')
    def test_unsupported_chat_saves_fixed_blocked_answer(self, mock_classify, mock_generate):
        mock_classify.return_value = {
            'is_allowed': False,
            'category': 'unsupported',
            'risk_level': 'normal',
            'relevant_summary': '',
            'reason': 'HealthFit 범위 밖 질문',
            'blocked_message': UNSUPPORTED_BLOCKED_MESSAGE,
        }

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/chats/',
                {'question': '리그 오브 레전드 랭크 올리는 법 알려줘'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['answer'], UNSUPPORTED_BLOCKED_MESSAGE)
        self.assertEqual(AIChat.objects.get().answer, UNSUPPORTED_BLOCKED_MESSAGE)
        mock_generate.assert_not_called()

    @patch('ai_services.services.recommendation_service.classify_healthfit_input')
    def test_medical_diet_preference_returns_common_blocked_error(self, mock_classify):
        mock_classify.return_value = {
            'is_allowed': False,
            'category': 'medical_caution',
            'risk_level': 'unsafe',
            'relevant_summary': '',
            'reason': '치료 또는 위험한 식단 요청',
            'blocked_message': MEDICAL_BLOCKED_MESSAGE,
        }

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/diet/recommendations/',
                {
                    'scope': 'meal',
                    'message': '약을 끊고 극단적으로 굶는 식단을 짜줘',
                    'target_date': '2026-06-21',
                    'food_source': 'all',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['errors']['guardrail'], [MEDICAL_BLOCKED_MESSAGE])
        self.assertFalse(AIRecommendation.objects.exists())

    @patch('ai_services.services.recommendation_service.classify_healthfit_input')
    def test_unrelated_workout_preference_returns_common_blocked_error(self, mock_classify):
        mock_classify.return_value = {
            'is_allowed': False,
            'category': 'unsupported',
            'risk_level': 'normal',
            'relevant_summary': '',
            'reason': '운동과 무관한 요청',
            'blocked_message': UNSUPPORTED_BLOCKED_MESSAGE,
        }

        with patch.dict(os.environ, {'GMS_KEY': 'test-key'}):
            response = self.client.post(
                '/api/v1/ai/workout/recommendations/',
                {
                    'message': '게임 랭크 올리는 방법 알려줘',
                    'available_time': 40,
                    'exercise_source': 'all',
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['errors']['guardrail'], [UNSUPPORTED_BLOCKED_MESSAGE])
        self.assertFalse(AIRecommendation.objects.exists())

    def test_chat_history_is_owner_only_and_paginated(self):
        User = get_user_model()
        other = User.objects.create_user(
            username='other-chat-user',
            email='other-chat@example.com',
            password='password123!',
        )
        AIChat.objects.bulk_create([
            AIChat(user=self.user, question=f'질문 {index}', answer=f'답변 {index}')
            for index in range(23)
        ])
        AIChat.objects.create(user=other, question='타인 질문', answer='타인 답변')

        response = self.client.get('/api/v1/ai/chats/?page=2&page_size=10')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['count'], 23)
        self.assertEqual(len(response.data['data']['results']), 10)
        self.assertTrue(all(item['question'] != '타인 질문' for item in response.data['data']['results']))

    def test_chat_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get('/api/v1/ai/chats/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data['success'])
