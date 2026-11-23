# Essivivi_back — API Django

Backend de la plateforme ESSIVIVI-Sarl (gestion des ventes et des dépôts de boissons).
Django 5.2 + Django REST Framework, PostgreSQL (Supabase), JWT, documentation OpenAPI.

## Démarrage en local

```bash
python -m venv venv
source venv/bin/activate            # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # puis adapter DATABASE_URL
python manage.py migrate
python manage.py createsuperuser    # crée le premier compte administrateur
python manage.py runserver
```

- Santé de l'API : http://localhost:8000/api/v1/health/
- Documentation OpenAPI (Swagger) : http://localhost:8000/api/docs/
- Site d'administration Django (lecture et débogage) : http://localhost:8000/admin/

Tests : `python manage.py test` (28 tests : données initiales, permissions, contraintes
de la base, crédit, historique de rémunération, numéros de reçu).

## Structure

| Application | Contenu |
|---|---|
| `accounts` | Utilisateurs, rôles, permissions (tableau à switchs), invitations, codes de secours 2FA, jetons Firebase |
| `catalog` | Boissons, stock central, mouvements de stock |
| `clients` | Fiches clients, points de livraison |
| `agents` | Agents, positions, rémunération mensuelle, historique de rémunération |
| `sales` | Ventes (directes et livraisons), lignes, paiements, reçus |
| `core` | Notifications, historique des activités, paramètres de la plateforme |

Les noms de tables sont ceux de `essivivi_schema.sql` (dépôt `Essivivi_doc`). **À partir de
maintenant, les migrations Django font référence** : toute évolution du schéma passe par
`makemigrations`.

Les contraintes importantes sont dans la base (CHECK) : stock jamais négatif, pas de vente
non soldée sans crédit accordé, part à payer avant livraison, 3 essais maximum pour un code,
etc. Elles protègent les données même en cas de bug dans le code.

## Ce qui est déjà en place

- Rôles, 37 permissions et matrice par défaut (migration `accounts.0002`), paramètres par défaut (`core.0002`).
- `User.has_permission("code")` et la classe DRF `accounts.permissions.HasPermission`
  (`required_permission = "stock.view"` sur la vue). La portée (« siennes », « affectées ») se règle dans `get_queryset()`.
- Déclencheur PostgreSQL qui consigne toute modification de rémunération d'un agent
  (`agents.0002`). Avant de modifier la rémunération, indiquer l'auteur dans la même transaction :

  ```python
  with transaction.atomic():
      with connection.cursor() as cursor:
          cursor.execute("SELECT set_config('app.user_id', %s, true)", [str(request.user.pk)])  # = SET LOCAL
      Agent.objects.filter(pk=agent.pk).update(commission_rate=7)
  ```
- Séquence PostgreSQL des numéros de reçu (`RC-AAAA-000001`) (`sales.0002`).
- Commande `python manage.py enable_rls` : active la sécurité par ligne sur toutes les tables
  (Supabase expose les tables par une API REST publique ; cela bloque la clé publique, Django n'est pas concerné).
  À relancer après chaque migration qui ajoute des tables.

## Supabase

- Utiliser la chaîne de connexion du tableau de bord Supabase (bouton **Connect**). Vérifier
  dans ce tableau de bord le mode de connexion adapté à l'hébergement (la connexion directe
  peut ne pas être joignable depuis certains hébergeurs : utiliser alors le pooler).
- **Migrations** : connexion directe ou pooler en mode « session » (port 5432).
- **Application en production** : pooler en mode « transaction » (port 6543) avec
  `DB_TRANSACTION_POOLER=true` (désactive les curseurs serveur et les requêtes préparées).

## Déploiement sur Render

- Build : `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
- Démarrage : `gunicorn config.wsgi:application`
- Variables d'environnement : celles de `.env.example` (`DEBUG=false`, `SECRET_KEY`, `DATABASE_URL`,
  `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `WEB_APP_URL`, identifiants Brevo).
- Ne jamais commiter `.env`, mots de passe ni clés d'API.

## E-mails

- Développement : `console` (le lien d'invitation et le code s'affichent dans le terminal).
- Tests : Django bascule automatiquement sur le mode mémoire (`mail.outbox`).
- Production : SMTP Brevo (variables `EMAIL_*`).

## Prochaines étapes (phase P1)

1. Connexion JWT, 2FA TOTP (`pyotp`) et codes de secours.
2. Invitations (jeton haché, code envoyé au clic, 3 essais) et inscription du client.
3. Routes `/me`, utilisateurs, matrice rôles / permissions.
4. Journal d'activité.

Voir le contrat d'API (`Essivivi_doc`) pour la liste complète des routes.
