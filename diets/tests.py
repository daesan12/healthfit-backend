from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Food, Meal, MealItem, SavedMeal


class DietPaginationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='diet-pagination',
            email='diet-pagination@example.com',
            password='password123!',
        )
        self.client.force_authenticate(user=self.user)
        Food.objects.bulk_create([
            Food(
                name=f'닭가슴살 {index:02d}',
                category='육류',
                calories=100 + index,
                carbohydrate=0,
                protein=20,
                fat=2,
            )
            for index in range(25)
        ])
        Food.objects.create(
            user=self.user,
            name='내 오트밀',
            category='곡류',
            calories=380,
            carbohydrate=65,
            protein=13,
            fat=7,
        )

    def assert_paginated(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        for field in [
            'count', 'page', 'page_size', 'total_pages', 'next', 'previous',
            'has_next', 'has_previous', 'results',
        ]:
            self.assertIn(field, response.data['data'])

    def test_foods_use_page_size_and_search_before_pagination(self):
        response = self.client.get('/api/v1/foods/?search=닭가슴살&page=2&page_size=10')

        self.assert_paginated(response)
        data = response.data['data']
        self.assertEqual(data['count'], 25)
        self.assertEqual(data['page'], 2)
        self.assertEqual(data['page_size'], 10)
        self.assertEqual(len(data['results']), 10)
        self.assertTrue(all('닭가슴살' in item['name'] for item in data['results']))
        self.assertTrue(data['has_previous'])

    def test_food_source_and_max_page_size_are_supported(self):
        response = self.client.get('/api/v1/foods/?source=my&page_size=1000')

        self.assert_paginated(response)
        data = response.data['data']
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['page_size'], 100)
        self.assertEqual(data['results'][0]['name'], '내 오트밀')

    def test_invalid_and_out_of_range_pages_use_common_error(self):
        invalid = self.client.get('/api/v1/foods/?page=abc')
        out_of_range = self.client.get('/api/v1/foods/?page=999')
        invalid_size = self.client.get('/api/v1/foods/?page_size=0')

        for response in [invalid, out_of_range, invalid_size]:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data['success'])
            self.assertEqual(response.data['message'], '페이지 조회에 실패했습니다.')

    def test_meals_paginate_after_date_and_label_filters(self):
        start = date(2026, 2, 1)
        for index in range(12):
            Meal.objects.create(
                user=self.user,
                meal_type='custom',
                meal_order=index + 1,
                meal_label='운동 전' if index < 7 else '운동 후',
                intake_date=start + timedelta(days=index % 3),
            )

        response = self.client.get(
            '/api/v1/meals/?start_date=2026-02-01&end_date=2026-02-03&meal_label=운동 전&page_size=5'
        )

        self.assert_paginated(response)
        data = response.data['data']
        self.assertEqual(data['count'], 7)
        self.assertEqual(len(data['results']), 5)
        self.assertTrue(all(item['meal_label'] == '운동 전' for item in data['results']))

    def test_saved_meals_are_paginated_and_searchable(self):
        SavedMeal.objects.bulk_create([
            SavedMeal(user=self.user, name=f'고단백 식단 {index}', description='운동 식단')
            for index in range(23)
        ])
        SavedMeal.objects.create(user=self.user, name='채식 식단', description='야채')

        response = self.client.get('/api/v1/saved-meals/?search=고단백&page_size=10')

        self.assert_paginated(response)
        self.assertEqual(response.data['data']['count'], 23)
        self.assertEqual(len(response.data['data']['results']), 10)


class MealLoggingApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='meal-user', email='meal@example.com', password='password123!'
        )
        self.other_user = User.objects.create_user(
            username='other-meal-user', email='other-meal@example.com', password='password123!'
        )
        self.rice = Food.objects.create(
            name='밥', category='곡류', calories=150,
            carbohydrate=32, protein=3, fat=1,
        )
        self.chicken = Food.objects.create(
            name='닭가슴살', category='육류', calories=165,
            carbohydrate=0, protein=31, fat=3.6,
        )
        self.other_food = Food.objects.create(
            user=self.other_user,
            name='다른 사용자 음식', category='기타', calories=200,
            carbohydrate=20, protein=20, fat=5,
        )
        self.client.force_authenticate(self.user)

    def meal_payload(self):
        return {
            'meal_type': 'breakfast',
            'intake_date': '2026-06-21',
            'items': [
                {'food_id': self.rice.id, 'amount': 100},
                {'food_id': self.chicken.id, 'amount': 150},
            ],
        }

    def test_create_meal_calculates_items_and_totals_and_filters_by_date(self):
        created = self.client.post('/api/v1/meals/', self.meal_payload(), format='json')

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data['data']['total_calories'], 397.5)
        self.assertEqual(created.data['data']['total_protein'], 49.5)
        self.assertEqual(len(created.data['data']['meal_items']), 2)

        listed = self.client.get('/api/v1/meals/?date=2026-06-21&meal_type=breakfast')
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(listed.data['data']['count'], 1)
        self.assertEqual(
            listed.data['data']['results'][0]['meal_items'][0]['food_name'],
            '밥',
        )

    def test_invalid_food_rolls_back_entire_meal_and_invalid_input_is_rejected(self):
        payload = self.meal_payload()
        payload['items'].append({'food_id': self.other_food.id, 'amount': 100})

        inaccessible = self.client.post('/api/v1/meals/', payload, format='json')
        invalid_type = self.client.post(
            '/api/v1/meals/',
            {**self.meal_payload(), 'meal_type': 'custom'},
            format='json',
        )
        empty_items = self.client.post(
            '/api/v1/meals/',
            {**self.meal_payload(), 'items': []},
            format='json',
        )
        invalid_date = self.client.get('/api/v1/meals/?date=not-a-date')

        for response in [inaccessible, invalid_type, empty_items, invalid_date]:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertFalse(response.data['success'])
        self.assertEqual(Meal.objects.count(), 0)
        self.assertEqual(MealItem.objects.count(), 0)

    def test_meal_item_add_update_delete_recalculates_totals(self):
        created = self.client.post('/api/v1/meals/', self.meal_payload(), format='json')
        meal_id = created.data['data']['id']

        added = self.client.post(
            f'/api/v1/meals/{meal_id}/items/',
            {'food_id': self.chicken.id, 'amount': 100},
            format='json',
        )
        self.assertEqual(added.status_code, status.HTTP_201_CREATED)
        item_id = added.data['data']['id']
        self.assertEqual(Meal.objects.get(pk=meal_id).total_calories, 562.5)

        updated = self.client.patch(
            f'/api/v1/meal-items/{item_id}/',
            {'amount': 200},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data['data']['calories'], 330)
        self.assertEqual(Meal.objects.get(pk=meal_id).total_calories, 727.5)

        deleted = self.client.delete(f'/api/v1/meal-items/{item_id}/')
        self.assertEqual(deleted.status_code, status.HTTP_200_OK)
        self.assertEqual(Meal.objects.get(pk=meal_id).total_calories, 397.5)

    def test_meal_item_is_owner_only_and_last_item_cannot_be_deleted(self):
        created = self.client.post(
            '/api/v1/meals/',
            {
                'meal_type': 'snack',
                'intake_date': '2026-06-21',
                'items': [{'food_id': self.rice.id, 'amount': 100}],
            },
            format='json',
        )
        item_id = created.data['data']['meal_items'][0]['id']

        last_item = self.client.delete(f'/api/v1/meal-items/{item_id}/')
        self.assertEqual(last_item.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.other_user)
        other_user = self.client.patch(
            f'/api/v1/meal-items/{item_id}/', {'amount': 50}, format='json'
        )
        self.assertEqual(other_user.status_code, status.HTTP_404_NOT_FOUND)
