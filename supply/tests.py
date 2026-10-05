from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Cooperative, Member, MilkSupply, Payment, User, Medicine, MedicineRequest


class BaseTestCase(TestCase):
    password = 'S3cret-pass!'

    @classmethod
    def setUpTestData(cls):
        cls.coop = Cooperative.objects.create(name='North Coop', location='Ngozi')
        cls.other_coop = Cooperative.objects.create(name='South Coop')

        cls.admin = User.objects.create_user('admin', password=cls.password, role='ADMIN')
        cls.manager = cls.make_member('manager', 'MANAGER', cls.coop)
        cls.member = cls.make_member('alice', 'MEMBER', cls.coop, email='alice@example.com')
        cls.outsider = cls.make_member('bob', 'MEMBER', cls.other_coop)

        cls.supply = MilkSupply.objects.create(
            member=cls.member.member_profile, quantity_liters=Decimal('10'), quality_grade='A',
            price_per_liter=Decimal('1.50'))
        cls.outsider_supply = MilkSupply.objects.create(
            member=cls.outsider.member_profile, quantity_liters=Decimal('5'), quality_grade='B',
            price_per_liter=Decimal('1.20'))
        cls.medicine = Medicine.objects.create(name='Vermifuge', stock_quantity=20, price=Decimal('3.00'))

    @classmethod
    def make_member(cls, username, role, cooperative, email=''):
        user = User.objects.create_user(username, password=cls.password, role=role, email=email)
        Member.objects.create(user=user, cooperative=cooperative, first_name=username.title(),
                              last_name='Test', email=email or None)
        return user

    def login(self, user):
        self.client.force_login(user)


class ModelTests(BaseTestCase):
    def test_member_id_is_auto_incremented(self):
        ids = sorted(Member.objects.values_list('member_id', flat=True))
        self.assertEqual(ids[0], 100000)
        self.assertEqual(ids, list(range(100000, 100000 + len(ids))))

    def test_superuser_defaults_to_admin_role(self):
        user = User.objects.create_superuser('root', password=self.password)
        self.assertEqual(user.role, 'ADMIN')

    def test_fulfill_reduces_stock(self):
        request = MedicineRequest.objects.create(
            member=self.member.member_profile, medicine=self.medicine, quantity=5)
        request.fulfill(self.manager, 4)
        request.refresh_from_db()
        self.medicine.refresh_from_db()
        self.assertEqual(request.status, 'FULFILLED')
        self.assertIsNotNone(request.fulfilled_date)
        self.assertEqual(self.medicine.stock_quantity, 16)
        with self.assertRaises(ValueError):
            request.fulfill(self.manager, 1)


class PageRenderTests(BaseTestCase):
    """Every page renders for the roles allowed to see it."""

    def assert_pages_ok(self, names):
        for name, args in names:
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200, name)

    def test_public_pages(self):
        self.assert_pages_ok([('landing_page', []), ('login', []), ('medicine_list', [])])

    def test_admin_pages(self):
        self.login(self.admin)
        payment = Payment.objects.create(member=self.member.member_profile, amount=Decimal('15'))
        self.assert_pages_ok([
            ('landing_page', []), ('admin_dashboard', []), ('cooperative_list', []),
            ('cooperative_create', []), ('cooperative_update', [self.coop.pk]),
            ('cooperative_delete', [self.coop.pk]), ('member_list', []), ('member_create', []),
            ('member_update', [self.member.member_profile.pk]),
            ('member_delete', [self.member.member_profile.pk]),
            ('milk_supply_list', []), ('milk_supply_create', []),
            ('milk_supply_update', [self.supply.pk]), ('milk_supply_delete', [self.supply.pk]),
            ('payment_list', []), ('payment_create', []), ('payment_update', [payment.pk]),
            ('payment_delete', [payment.pk]), ('medicine_list', []), ('add_medicine', []),
            ('medicine_request_list', []),
        ])

    def test_manager_pages(self):
        self.login(self.manager)
        self.assert_pages_ok([
            ('manager_dashboard', []), ('member_list', []), ('member_create', []),
            ('member_update', [self.member.member_profile.pk]), ('milk_supply_list', []),
            ('milk_supply_create', []), ('payment_list', []), ('payment_create', []),
            ('medicine_request_list', []),
        ])

    def test_member_pages(self):
        self.login(self.member)
        MedicineRequest.objects.create(member=self.member.member_profile, medicine=self.medicine, quantity=2)
        self.assert_pages_ok([
            ('member_dashboard', []), ('milk_supply_list', []), ('milk_supply_create', []),
            ('payment_list', []), ('medicine_list', []), ('request_medicine', [self.medicine.pk]),
            ('member_requests', []),
        ])

    def test_landing_page_lists_medicines(self):
        response = self.client.get(reverse('landing_page'))
        self.assertContains(response, 'Vermifuge')
        self.login(self.member)
        response = self.client.get(reverse('landing_page'))
        self.assertContains(response, reverse('request_medicine', args=[self.medicine.pk]))


class AuthTests(BaseTestCase):
    def test_login_redirects_by_role(self):
        for user, target in [(self.admin, 'admin_dashboard'), (self.manager, 'manager_dashboard'),
                             (self.member, 'member_dashboard')]:
            with self.subTest(user=user.username):
                self.client.logout()
                response = self.client.post(reverse('login'),
                                            {'username': user.username, 'password': self.password})
                self.assertRedirects(response, reverse(target))

    def test_invalid_login(self):
        response = self.client.post(reverse('login'), {'username': 'admin', 'password': 'nope'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid username or password.')

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse('admin_dashboard'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('admin_dashboard')}")

    def test_role_restrictions(self):
        self.login(self.member)
        for name in ['admin_dashboard', 'manager_dashboard', 'cooperative_list', 'member_list',
                     'payment_create', 'medicine_request_list', 'add_medicine']:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_manager_cannot_touch_other_cooperative(self):
        self.login(self.manager)
        outsider = self.outsider.member_profile
        self.assertEqual(self.client.get(reverse('member_update', args=[outsider.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('milk_supply_update', args=[self.outsider_supply.pk])).status_code, 403)
        response = self.client.get(reverse('milk_supply_list'))
        self.assertNotContains(response, 'Bob Test')


class MemberManagementTests(BaseTestCase):
    def test_admin_creates_member_with_login(self):
        self.login(self.admin)
        response = self.client.post(reverse('member_create'), {
            'username': 'carol', 'password': 'Another-pass1', 'role': 'MEMBER',
            'first_name': 'Carol', 'last_name': 'Ndayi', 'cooperative': self.coop.pk,
            'email': 'carol@example.com', 'contact_number': '', 'joined_date': '2025-01-01',
        })
        self.assertRedirects(response, reverse('member_list'))
        user = User.objects.get(username='carol')
        self.assertTrue(user.check_password('Another-pass1'))
        self.assertEqual(user.member_profile.cooperative, self.coop)

    def test_manager_creates_member_in_own_cooperative(self):
        self.login(self.manager)
        response = self.client.post(reverse('member_create'), {
            'username': 'dave', 'password': 'Another-pass1', 'role': 'ADMIN',
            'first_name': 'Dave', 'last_name': 'K', 'cooperative': self.other_coop.pk,
            'joined_date': '2025-01-01',
        })
        self.assertRedirects(response, reverse('member_list'))
        user = User.objects.get(username='dave')
        self.assertEqual(user.role, 'MEMBER')  # managers cannot escalate roles
        self.assertEqual(user.member_profile.cooperative, self.coop)

    def test_password_required_for_new_member(self):
        self.login(self.admin)
        response = self.client.post(reverse('member_create'), {
            'username': 'erin', 'role': 'MEMBER', 'first_name': 'Erin', 'last_name': 'X',
            'joined_date': '2025-01-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='erin').exists())

    def test_update_keeps_password_when_blank(self):
        self.login(self.admin)
        profile = self.member.member_profile
        response = self.client.post(reverse('member_update', args=[profile.pk]), {
            'username': 'alice2', 'password': '', 'role': 'MEMBER', 'first_name': 'Alice',
            'last_name': 'Test', 'cooperative': self.coop.pk, 'email': 'alice@example.com',
            'joined_date': '2025-01-01',
        })
        self.assertRedirects(response, reverse('member_list'))
        self.member.refresh_from_db()
        self.assertEqual(self.member.username, 'alice2')
        self.assertTrue(self.member.check_password(self.password))

    def test_delete_member_removes_user(self):
        self.login(self.admin)
        response = self.client.post(reverse('member_delete', args=[self.outsider.member_profile.pk]))
        self.assertRedirects(response, reverse('member_list'))
        self.assertFalse(User.objects.filter(username='bob').exists())


class MilkSupplyTests(BaseTestCase):
    def test_manager_modal_uses_member_number_and_default_price(self):
        self.login(self.manager)
        profile = self.member.member_profile
        response = self.client.post(reverse('milk_supply_create'), {
            'member_id': str(profile.member_id), 'supply_date': '2025-06-01',
            'quantity_liters': '12.5', 'quality_grade': 'B', 'price_per_liter': '',
        })
        self.assertRedirects(response, reverse('manager_dashboard'))
        supply = MilkSupply.objects.latest('recorded_at')
        self.assertEqual(supply.member, profile)
        self.assertEqual(supply.price_per_liter, Decimal('1.20'))

    def test_manager_modal_rejects_member_from_other_cooperative(self):
        self.login(self.manager)
        count = MilkSupply.objects.count()
        response = self.client.post(reverse('milk_supply_create'), {
            'member_id': str(self.outsider.member_profile.member_id), 'supply_date': '2025-06-01',
            'quantity_liters': '3', 'quality_grade': 'A',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MilkSupply.objects.count(), count)

    def test_member_price_is_fixed_by_grade(self):
        self.login(self.member)
        self.client.post(reverse('milk_supply_create'), {
            'supply_date': '2025-06-01', 'quantity_liters': '4', 'quality_grade': 'C',
            'price_per_liter': '99',
        })
        supply = MilkSupply.objects.latest('recorded_at')
        self.assertEqual(supply.member, self.member.member_profile)
        self.assertEqual(supply.price_per_liter, Decimal('0.90'))

    def test_validate_member_api(self):
        self.login(self.manager)
        ok = self.client.get(reverse('validate_member', args=[self.member.member_profile.member_id]))
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()['valid'])
        missing = self.client.get(reverse('validate_member', args=[self.outsider.member_profile.member_id]))
        self.assertEqual(missing.status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('validate_member', args=['1'])).status_code, 302)


class PaymentTests(BaseTestCase):
    def test_payment_amount_computed_and_member_notified(self):
        self.login(self.manager)
        response = self.client.post(reverse('payment_create'), {
            'member': self.member.member_profile.pk, 'payment_date': '2025-06-02',
            'status': 'PAID', 'transaction_id': 'TX1', 'milk_supply_ids': str(self.supply.pk),
        })
        self.assertRedirects(response, reverse('payment_list'))
        payment = Payment.objects.get(transaction_id='TX1')
        self.assertEqual(payment.amount, Decimal('15.00'))
        self.assertTrue(payment.notified)
        self.assertEqual(len(mail.outbox), 1)

    def test_payment_rejects_supplies_of_other_member(self):
        self.login(self.admin)
        response = self.client.post(reverse('payment_create'), {
            'member': self.member.member_profile.pk, 'payment_date': '2025-06-02',
            'status': 'PENDING', 'milk_supply_ids': f'{self.supply.pk},{self.outsider_supply.pk}',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.exists())


class MedicineTests(BaseTestCase):
    def test_member_requests_and_manager_fulfills(self):
        self.login(self.member)
        response = self.client.post(reverse('request_medicine', args=[self.medicine.pk]), {'quantity': '3'})
        self.assertRedirects(response, reverse('member_requests'))
        request = MedicineRequest.objects.get()

        self.login(self.manager)
        response = self.client.post(reverse('medicine_request_fulfill', args=[request.pk]), {'quantity': '3'})
        self.assertRedirects(response, reverse('medicine_request_list'))
        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.stock_quantity, 17)

    def test_invalid_quantity_does_not_crash(self):
        self.login(self.member)
        response = self.client.post(reverse('request_medicine', args=[self.medicine.pk]), {'quantity': 'abc'})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('request_medicine', args=[self.medicine.pk]), {'quantity': '999'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MedicineRequest.objects.exists())

    def test_manager_cannot_fulfill_other_cooperative_request(self):
        request = MedicineRequest.objects.create(
            member=self.outsider.member_profile, medicine=self.medicine, quantity=1)
        self.login(self.manager)
        response = self.client.post(reverse('medicine_request_fulfill', args=[request.pk]), {'quantity': '1'})
        self.assertEqual(response.status_code, 403)

    def test_contact_form_sends_mail(self):
        response = self.client.post(reverse('landing_page'), {
            'name': 'Visitor', 'email': 'v@example.com', 'message': 'Hello'})
        self.assertRedirects(response, reverse('landing_page'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Hello', mail.outbox[0].body)
