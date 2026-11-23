from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "Active la sécurité par ligne (RLS) sur toutes les tables du schéma public, sans politique. "
        "Supabase expose les tables par une API REST publique : cela bloque tout accès via la clé "
        "publique. Django, connecté avec le rôle postgres, n'est pas concerné. "
        "À relancer après chaque migration qui ajoute des tables."
    )

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                cursor.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
        self.stdout.write(self.style.SUCCESS(f"RLS activée sur {len(tables)} tables."))
