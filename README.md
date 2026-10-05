# SeaSky Milk

Django application for a dairy cooperative: members, milk supply records, payments and
veterinary medicine requests, with dashboards for three roles.

| Role    | Can do |
|---------|--------|
| Admin   | Manage cooperatives, all members, supplies, payments, medicines and requests |
| Manager | Manage members, supplies, payments and medicine requests of their own cooperative |
| Member  | See their own supplies/payments, record supplies, request medicines |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # superusers get the Admin role automatically
python manage.py runserver
```

Then open http://127.0.0.1:8000/ and log in at `/login/`.

Managers must have a member profile attached to a cooperative (create them from
*Members → Add Member* as an admin and choose the *Cooperative Manager* role).

Milk prices default by grade when no price is entered: A $1.50, B $1.20, C $0.90 per liter.

## E-mail

E-mails (payment notifications, contact form) are printed to the console by default.
To send real mail set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and
`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`.

## Tests

```bash
python manage.py test supply
```
