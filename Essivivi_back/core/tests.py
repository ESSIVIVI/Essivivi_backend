from django.test import TestCase

from .models import PlatformSetting


class HealthTests(TestCase):
    def test_sante(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_documentation_openapi(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)


class SettingsTests(TestCase):
    def test_parametres_par_defaut(self):
        self.assertEqual(PlatformSetting.objects.get(key="order_expiry_hours").value, 24)
        self.assertEqual(PlatformSetting.objects.get(key="code_max_attempts").value, 3)
        self.assertEqual(PlatformSetting.objects.get(key="delivery_radius_m").value, 100)
