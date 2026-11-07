from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class RegistrationTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def _register(self, **over):
        body = {"username": "alice", "email": "Alice@Example.com", "password": "correct-horse-9"}
        body.update(over)
        return self.api.post("/auth/register/", body, format="json")

    def test_email_is_normalised_and_unique_case_insensitively(self):
        self.assertEqual(self._register().status_code, 201)
        self.assertEqual(User.objects.get(username="alice").email, "alice@example.com")
        dup = self._register(username="alice2", email="ALICE@example.com")
        self.assertEqual(dup.status_code, 400)
        self.assertIn("email", dup.json())

    def test_username_taken(self):
        self._register()
        r = self._register(email="other@example.com", username="ALICE")
        self.assertEqual(r.status_code, 400)
        self.assertIn("username", r.json())

    def test_weak_password_rejected(self):
        r = self._register(password="12345678")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.json())


class LoginTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        User.objects.create_user("bob", email="bob@example.com", password="correct-horse-9")

    def _login(self, ident, pw):
        return self.api.post("/auth/login/", {"username": ident, "password": pw}, format="json")

    def test_login_is_case_insensitive_on_email(self):
        r = self._login("BOB@Example.com", "correct-horse-9")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.json())
        self.assertNotIn("refresh", r.json())  # only ever in the cookie

    def test_wrong_password_and_unknown_user_look_identical(self):
        a = self._login("bob@example.com", "nope")
        b = self._login("ghost@example.com", "nope")
        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(a.json(), b.json())

    def test_duplicate_emails_in_legacy_data_do_not_500(self):
        User.objects.create_user("bob2", email="bob@example.com", password="x-correct-horse-9")
        r = self._login("bob@example.com", "correct-horse-9")
        self.assertIn(r.status_code, (200, 400))


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("carol", email="carol@example.com", password="correct-horse-9")
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def test_patch_keeping_own_email_is_allowed(self):
        r = self.api.patch("/auth/profile/", {"email": "carol@example.com"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_password_change_is_hashed(self):
        r = self.api.patch("/auth/profile/", {"password": "another-horse-77"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.password, "another-horse-77")
        self.assertTrue(self.user.check_password("another-horse-77"))
