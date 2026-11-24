# Essivivi_back — API Django

Backend de la plateforme ESSIVIVI-Sarl (gestion des ventes et des dépôts de boissons).
Django 5.2 · Django REST Framework · PostgreSQL (Supabase) · JWT · documentation OpenAPI.

---

## Démarrage en local

```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac : source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # puis adapter DATABASE_URL et SECRET_KEY
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

| URL | Description |
|---|---|
| `http://localhost:8000/api/v1/health/` | Santé de l'API |
| `http://localhost:8000/api/docs/` | Documentation Swagger (OpenAPI) |
| `http://localhost:8000/api/schema/` | Schéma OpenAPI brut |
| `http://localhost:8000/admin/` | Site d'administration Django |

```bash
python manage.py test          # lance les tests (~ 24 tests)
```

---

## Structure des applications

| Application | Rôle |
|---|---|
| `accounts` | Utilisateurs, rôles, 37 permissions, invitations par lien, 2FA TOTP, codes de secours, jetons Firebase |
| `catalog` | Boissons, stock central, mouvements de stock |
| `clients` | Fiches clients, points de livraison géolocalisés |
| `agents` | Agents, disponibilité, positions GPS, rémunération mensuelle, historique de rémunération |
| `sales` | Ventes directes et livraisons, lignes de vente, paiements, reçus numérotés |
| `core` | Notifications, journal d'activité, paramètres de plateforme |
| `config` | Settings Django, URL root, WSGI/ASGI |

---

## Routes implémentées

Toutes les routes sont préfixées par `/api/v1/`.

### Auth (`accounts`)

| Méthode | Chemin | Description |
|---|---|---|
| `POST` | `/auth/register` | Inscription client (auto-enregistrement) |
| `POST` | `/auth/email/verify` | Vérification du code reçu par e-mail |
| `POST` | `/auth/login` | Connexion (retourne les tokens JWT ou demande le 2FA) |
| `POST` | `/auth/refresh` | Renouveler le token d'accès |
| `POST` | `/auth/logout` | Révocation du refresh token (blacklist) |
| `POST` | `/auth/password/change` | Changer son propre mot de passe |
| `POST` | `/auth/2fa/setup` | Initialiser le secret TOTP |
| `POST` | `/auth/2fa/confirm` | Activer le 2FA (confirmer le code TOTP) |
| `POST` | `/auth/2fa/disable` | Désactiver le 2FA |
| `POST` | `/auth/2fa/verify` | Valider le code TOTP lors de la connexion |
| `POST` | `/auth/2fa/backup` | Se connecter avec un code de secours |
| `GET/PATCH` | `/me` | Lire et modifier son propre profil |

### Utilisateurs & rôles

| Méthode | Chemin | Permission requise |
|---|---|---|
| `GET` | `/users` | `users.manage` |
| `GET/PATCH` | `/users/<id>` | `users.manage` |
| `POST` | `/users/<id>/deactivate` | `users.manage` |
| `POST` | `/users/<id>/activate` | `users.manage` |
| `DELETE` | `/users/<id>/delete` | `users.manage` |
| `PATCH` | `/users/<id>/role` | `users.assign_role` |
| `POST` | `/users/<id>/reset-password` | `users.reset_credentials` |
| `POST` | `/users/<id>/reset-2fa` | `users.reset_credentials` |
| `GET` | `/roles/matrix` | `permissions.manage` |
| `PUT/DELETE` | `/roles/<role_id>/permissions/<perm_id>` | `permissions.manage` |

### Invitations

| Méthode | Chemin | Description |
|---|---|---|
| `GET/POST` | `/invitations` | Lister / créer une invitation (admin) |
| `GET` | `/invitations/<id>` | Détail d'une invitation (admin) |
| `POST` | `/invitations/<id>/resend` | Renvoyer le lien |
| `POST` | `/invitations/<id>/cancel` | Annuler |
| `GET` | `/invitations/<token>` | Vérifier la validité du lien (public) |
| `POST` | `/invitations/<token>/send-code` | Envoyer le code au clic sur le lien (public) |
| `POST` | `/invitations/<token>/activate` | Créer le compte avec le code + mot de passe (public) |

### Catalogue & stock

| Méthode | Chemin | Permission requise |
|---|---|---|
| `GET` | `/drinks` | `drinks.view` |
| `POST` | `/drinks` | `drinks.manage` |
| `GET/PATCH` | `/drinks/<id>` | `drinks.view` / `drinks.manage` |
| `POST` | `/drinks/<id>/deactivate` | `drinks.manage` |
| `GET` | `/stock` | `stock.view` |
| `POST` | `/stock/restock` | `stock.restock` |
| `POST` | `/stock/adjust` | `stock.restock` |
| `GET` | `/stock/movements` | `stock.view` |

---

## Rôles et permissions

Quatre rôles : `admin`, `gestionnaire`, `agent`, `client`.

37 permissions regroupées par domaine (`drinks.*`, `stock.*`, `users.*`, `sales.*`, `orders.*`, `deliveries.*`, `credit.*`, `agents.*`, `permissions.*`…). La matrice est modifiable par l'administrateur depuis `/roles/matrix` : un « switch » activé = une ligne dans la table `role_permission`.

```python
# Dans n'importe quelle vue DRF :
class MaVue(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "stock.view"
```

---

## Points techniques importants

### Déclencheur PostgreSQL — historique de rémunération

Toute modification des champs `pay_mode`, `monthly_salary` ou `commission_rate` d'un agent est automatiquement consignée dans `AgentPayHistory` (migration `agents.0002`).
Avant la modification, indiquer l'auteur dans la même transaction :

```python
from django.db import connection, transaction

with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.user_id', %s, true)", [str(request.user.pk)])
    Agent.objects.filter(pk=agent.pk).update(commission_rate=7)
```

### Numéros de reçu

Séquence PostgreSQL `receipt_number_seq` créée par `sales.0002`. Format : `RC-AAAA-000001`. Le numéro est attribué au `save()`, sans doublon même en concurrence.

### Contraintes CHECK dans la base

Les invariants métier critiques sont portés par des contraintes `CHECK` PostgreSQL :

- Stock jamais négatif.
- Vente non soldée interdite sans crédit accordé.
- Part exigée avant livraison (`upfront_required`) réglée avant de passer en statut `payee`.
- 3 essais maximum sur un code (invitation, code de livraison).
- Vente directe sans agent ; livraison avec code et coordonnées obligatoires.

Ces contraintes protègent les données même en cas de bug applicatif.

### Row-Level Security (Supabase)

```bash
python manage.py enable_rls
```

Active la sécurité par ligne sur toutes les tables. À relancer après chaque migration qui ajoute des tables. Supabase expose les tables via une API REST publique ; cette commande bloque la clé `anon`. Django n'est pas concerné.

---

## Configuration — variables d'environnement

Copier `.env.example` en `.env` et adapter :

| Variable | Description |
|---|---|
| `SECRET_KEY` | Clé secrète Django |
| `DEBUG` | `true` en dev, `false` en production |
| `ALLOWED_HOSTS` | Hôtes autorisés |
| `DATABASE_URL` | URL PostgreSQL (locale ou Supabase) |
| `DB_TRANSACTION_POOLER` | `true` si pooler en mode transaction (port 6543) |
| `WEB_APP_URL` | URL du front (lien d'invitation) |
| `CORS_ALLOWED_ORIGINS` | Origines CORS autorisées |
| `CSRF_TRUSTED_ORIGINS` | Origines CSRF (production) |
| `INVITATION_TTL_HOURS` | Durée de validité d'un lien d'invitation (défaut : 48 h) |
| `EMAIL_BACKEND` | `console` en dev, `smtp` en production |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP Brevo (production) |
| `DEFAULT_FROM_EMAIL` | Adresse expéditrice |

---

## Supabase

- **Migrations** : connexion directe ou pooler « session » (port 5432), `DB_TRANSACTION_POOLER=false`.
- **Application en production** : pooler « transaction » (port 6543), `DB_TRANSACTION_POOLER=true` (désactive les curseurs serveur et les requêtes préparées).
- Récupérer la chaîne de connexion depuis le tableau de bord Supabase → bouton **Connect**.

---

## Déploiement (Render ou équivalent)

**Build :**
```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

**Démarrage :**
```bash
gunicorn config.wsgi:application
```

**Variables d'environnement à fournir :** `DEBUG=false`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `WEB_APP_URL`, variables `EMAIL_*`.

Ne jamais commiter `.env`, mots de passe ni clés d'API.

---

## E-mails

| Contexte | Backend |
|---|---|
| Développement | `console` — les e-mails s'affichent dans le terminal |
| Tests | Django bascule automatiquement sur `mail.outbox` |
| Production | SMTP Brevo (variables `EMAIL_*`) |

---

## Dépendances principales

| Paquet | Usage |
|---|---|
| `Django 5.2` | Framework principal |
| `djangorestframework 3.18` | API REST |
| `djangorestframework-simplejwt 5.5` | Authentification JWT |
| `drf-spectacular 0.30` | Documentation OpenAPI / Swagger |
| `django-cors-headers 4.9` | CORS |
| `psycopg[binary] 3.3` | Pilote PostgreSQL |
| `dj-database-url 3.1` | Parsing de `DATABASE_URL` |
| `python-dotenv 1.2` | Chargement du `.env` |
| `whitenoise 6.12` | Fichiers statiques en production |
| `gunicorn 27` | Serveur WSGI |
| `pyotp 2.12` | 2FA TOTP |
