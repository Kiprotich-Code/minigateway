# minigateway

minigateway is a minimal Django payment gateway that demonstrates how to build provider-agnostic payment infrastructure. It uses Safaricom Daraja STK Push (M-Pesa) as the concrete implementation, but the architecture is designed so that adding a second provider — Stripe, Flutterwave, whatever — requires touching exactly one file. The `parking` app shows how a business module consumes the gateway without knowing anything about the underlying payment provider.

---

## What this project is NOT

- **Not production-ready.** No authentication or authorization on any view.
- **No HTTPS handling.** You need a reverse proxy (nginx, Caddy) to terminate TLS in production.
- **No secrets management.** `SECRET_KEY` is hardcoded in `settings.py`. Credentials are stored as plaintext in SQLite.
- **SQLite only.** Fine for development; swap to Postgres for anything real.
- **Daraja sandbox only by default.** The `DarajaAdapter` defaults to Safaricom's sandbox environment. Production requires a live Safaricom account.

This is a learning and reference project. Read the code, understand the patterns, then adapt them.

---

## Architecture

### The core idea: provider-agnostic gateway

The `payments` app is a self-contained gateway. Business modules — like `parking` — never import Daraja, never read credentials, and never know that M-Pesa exists. They call one method:

```python
tx = PaymentGateway().charge(intent)
```

They get back a `Transaction`. That's the entire interface. When you add Stripe tomorrow, `parking` doesn't change at all.

---

### The two apps

#### `payments/` — the gateway

Owns everything payment-related.

**Models (`payments/models.py`)**

- `PaymentChannel` — one row per configured provider. Stores credentials (consumer key, secret, passkey, shortcode), callback URL, environment (`sandbox` / `production`), and an `enabled` flag. Credentials are read fresh from the database on every charge, so you can update them in the admin without restarting the server.
- `Transaction` — one row per charge attempt. Fields: `reference` (UUID), `channel` (FK), `amount`, `status` (`pending` / `completed` / `failed` / `cancelled`), `provider_reference` (e.g. Daraja's `CheckoutRequestID`), `provider_transaction` (full JSON response), `metadata`.

**`gateway.py` — the single entry point**

```python
class PaymentGateway:
    def charge(self, intent: dict) -> Transaction:
        ...
```

`intent` is a plain dict with these keys:

| Key | Required | Description |
|-----|----------|-------------|
| `channel_id` | yes | PK of the `PaymentChannel` to use |
| `amount` | yes | Decimal/str/int |
| `phone` | yes | Payer's phone number |
| `reference` | no | UUID — a new one is generated if omitted |
| `metadata` | no | Any extra dict you want stored on the transaction |

**`registry.py` — the provider map**

```python
PROVIDER_REGISTRY = {
    "mpesa": DarajaAdapter,
}

def resolve(channel) -> BaseAdapter:
    adapter_class = PROVIDER_REGISTRY[channel.provider_type]
    return adapter_class(channel)
```

`resolve()` takes a `PaymentChannel`, looks up its `provider_type` in the registry, and returns an instantiated adapter.

**`adapters/base.py` — the adapter contract**

```python
@dataclass
class StandardResult:
    status: str                 # "pending" | "completed" | "failed"
    provider_reference: str     # e.g. CheckoutRequestID from Daraja
    provider_transaction: dict  # full provider response payload
    message: str
    raw_response: Any

class BaseAdapter(ABC):
    @abstractmethod
    def charge(self, intent: dict) -> StandardResult: ...

    @abstractmethod
    def parse_callback(self, data: dict) -> StandardResult: ...
```

Every provider adapter must implement these two methods and return a `StandardResult`. The gateway only ever sees `StandardResult` — it never sees provider-specific response shapes.

**`adapters/daraja.py` — the M-Pesa implementation**

`DarajaAdapter.__init__` receives a `PaymentChannel` instance and reads all credentials from it:

```python
self.consumer_key = channel.consumer_key
self.consumer_secret = channel.consumer_secret
self.passkey = channel.passkey
self.shortcode = channel.shortcode
self.base_url = self.SANDBOX_BASE if channel.environment == "sandbox" else self.PRODUCTION_BASE
```

`charge()` fetches an OAuth token, generates the STK Push password (`base64(shortcode + passkey + timestamp)`), and POSTs the STK Push payload. On success it returns `StandardResult(status="pending", provider_reference=CheckoutRequestID)`.

`parse_callback()` parses Safaricom's async POST. `ResultCode == 0` → `status="completed"`, anything else → `status="failed"`.

**`callbacks.py` — the async callback receiver**

```python
@csrf_exempt
def daraja_callback(request):
    # POST /payments/callbacks/daraja/
    ...
    transaction = Transaction.objects.get(provider_reference=checkout_request_id)
    result = DarajaAdapter(transaction.channel).parse_callback(data)
    transaction.status = result.status
    transaction.save()

    if result.status == "completed":
        payment_completed.send(sender=Transaction, transaction=transaction)
    elif result.status == "failed":
        payment_failed.send(sender=Transaction, transaction=transaction)
```

**`signals.py` — the notification layer**

```python
payment_completed = Signal()  # kwargs: transaction
payment_failed = Signal()     # kwargs: transaction
```

These are standard Django signals. Any app can listen for them without `payments` knowing it exists.

---

#### `parking/` — a business module

Demonstrates how to consume the gateway.

**Models (`parking/models.py`)**

- `ParkingSlot` — slot number and location.
- `ParkingSession` — plate number, phone, amount, `status` (`active` / `paid` / `cancelled`), and a FK to `payments.Transaction`. No M-Pesa knowledge anywhere.

**`views.py` — calling the gateway**

```python
def pay_view(request):
    if request.method == "POST":
        form = ParkingPayForm(request.POST)
        if form.is_valid():
            intent = {
                "amount": form.cleaned_data["amount"],
                "phone": form.cleaned_data["phone"],
                "channel_id": form.cleaned_data["channel"].id,
                "reference": uuid.uuid4(),
                "metadata": {"plate_number": form.cleaned_data["plate_number"]},
            }
            tx = PaymentGateway().charge(intent)
            session = ParkingSession.objects.create(
                plate_number=form.cleaned_data["plate_number"],
                phone=form.cleaned_data["phone"],
                amount=form.cleaned_data["amount"],
                transaction=tx,
                status="active",
            )
            return redirect("parking:session_status", session_id=session.pk)
```

That's the entire integration. Build an intent dict, call `PaymentGateway().charge()`, store the returned `Transaction` on the session.

**`listeners.py` — reacting to payment completion**

```python
def on_payment_completed(sender, transaction, **kwargs):
    from parking.models import ParkingSession
    try:
        session = ParkingSession.objects.get(transaction=transaction)
        session.status = "paid"
        session.save()
    except ParkingSession.DoesNotExist:
        pass
```

**`apps.py` — wiring the listener at startup**

```python
class ParkingConfig(AppConfig):
    name = 'parking'

    def ready(self):
        from payments.signals import payment_completed
        from parking.listeners import on_payment_completed
        payment_completed.connect(on_payment_completed)
```

`ready()` runs once when Django starts. This is the standard place to connect signal handlers.

---

### The charge flow — step by step

1. User submits the parking pay form: plate number, phone, amount, channel selection.
2. `pay_view` builds the `intent` dict and calls `PaymentGateway().charge(intent)`.
3. `charge()` loads the `PaymentChannel` from the database — credentials are read fresh here.
4. `resolve(channel)` looks up `PROVIDER_REGISTRY["mpesa"]` and returns `DarajaAdapter(channel)`.
5. `DarajaAdapter.charge(intent)` runs:
   - POSTs to Safaricom's OAuth endpoint with consumer key/secret → gets an access token.
   - Generates the STK Push password: `base64(shortcode + passkey + timestamp)`.
   - POSTs the STK Push payload → Safaricom sends a payment prompt to the user's phone.
   - Returns `StandardResult(status="pending", provider_reference=CheckoutRequestID)`.
6. `charge()` creates a `Transaction` row with `status="pending"` and returns it.
7. `pay_view` creates a `ParkingSession` linked to that transaction and redirects to the status page.
8. Safaricom POSTs the payment result to `POST /payments/callbacks/daraja/`.
9. `daraja_callback` parses the payload, finds the `Transaction` by `CheckoutRequestID`, updates `status` to `"completed"` or `"failed"`.
10. Fires `payment_completed.send(sender=Transaction, transaction=tx)` (or `payment_failed`).
11. `on_payment_completed` finds the linked `ParkingSession` and sets `status="paid"`.
12. User refreshes the status page — sees the updated state.

---

### Dependency direction

```
parking  →  payments   (parking imports PaymentGateway, Transaction)
payments  →  parking   (NEVER — payments has no knowledge of parking)
```

The signal system is what allows `payments` to notify `parking` after a payment completes without creating a reverse import. `payments` fires `payment_completed`; `parking` listens. The two apps never have a circular dependency.

---

### Adding a new payment provider

Three steps to add Stripe (or anything else):

1. Create `payments/adapters/stripe.py` implementing `BaseAdapter` — `charge()` and `parse_callback()`, both returning `StandardResult`.
2. Add one entry to `PROVIDER_REGISTRY` in `payments/registry.py`:
   ```python
   from payments.adapters.stripe import StripeAdapter

   PROVIDER_REGISTRY = {
       "mpesa": DarajaAdapter,
       "stripe": StripeAdapter,
   }
   ```
3. Nothing else changes. The gateway, all business modules, and all existing tests are unaffected.

---

### Credentials live in the database

`PaymentChannel` stores all provider credentials. `DarajaAdapter.__init__` receives the channel object at runtime and reads credentials from it directly. This means you can update credentials in the Django admin and they take effect on the next charge — no restart, no redeployment, no environment variable changes. It's a deliberate demo convenience; in production you'd want to encrypt these fields at rest.

---

## Project structure

```
minigateway/
├── manage.py
├── minigateway/              # Django project config
│   ├── settings.py
│   ├── urls.py
│   └── views.py              # dashboard view
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── payments/
│   │   ├── channel_list.html
│   │   ├── channel_form_step1.html
│   │   └── channel_form_step2.html
│   └── parking/
│       ├── pay.html
│       └── session_status.html
├── payments/
│   ├── models.py             # PaymentChannel, Transaction
│   ├── gateway.py            # PaymentGateway.charge()
│   ├── registry.py           # PROVIDER_REGISTRY + resolve()
│   ├── signals.py            # payment_completed, payment_failed
│   ├── callbacks.py          # Daraja callback endpoint
│   ├── forms.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   └── adapters/
│       ├── base.py           # BaseAdapter, StandardResult
│       └── daraja.py         # DarajaAdapter
└── parking/
    ├── models.py             # ParkingSlot, ParkingSession
    ├── views.py              # pay_view, session_status_view
    ├── forms.py
    ├── listeners.py          # on_payment_completed
    ├── apps.py               # signal connection in ready()
    └── urls.py
```

---

## Setup

### Prerequisites

- Python 3.10 or later. Check: `python --version`
- pip (comes with Python). Check: `pip --version`
- git (to clone). Check: `git --version`
- A Safaricom Developer account at https://developer.safaricom.co.ke — needed for real STK Push. Sandbox apps are free.

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd minigateway
```

### 2. Create a virtual environment

A virtual environment isolates this project's dependencies from the rest of your system. Create one and activate it:

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

You'll know it's active when you see `(venv)` at the start of your terminal prompt.

### 3. Install dependencies

```bash
pip install django requests
```

That's the complete dependency list — Django and the `requests` HTTP library.

### 4. Run migrations

```bash
python manage.py migrate
```

This creates `db.sqlite3` and all tables. You'll see a list of migrations being applied.

### 5. Create a superuser

```bash
python manage.py createsuperuser
```

Follow the prompts — username, email (optional), password. This gives you access to `/admin/`.

### 6. Start the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` — you'll see the dashboard.

### 7. Run the tests

```bash
python manage.py test
```

All tests should pass. Daraja API calls are mocked — no external services are contacted.

---

## Getting a real STK Push working

### Step 1 — Get your sandbox credentials

1. Go to https://developer.safaricom.co.ke
2. Create an account and log in.
3. Go to **My Apps** → create a new app.
4. On the app dashboard: copy your **Consumer Key** and **Consumer Secret**.
5. For the STK Push passkey: go to the **Test Credentials** section under *Lipa Na M-Pesa Online*. Safaricom provides a test shortcode (`174379`) and a test passkey.

### Step 2 — Expose your local server (for callbacks)

Safaricom needs to POST the payment result to a publicly reachable URL. During development your machine isn't accessible from the internet, so you need a tunnel. The easiest option is [ngrok](https://ngrok.com):

```bash
ngrok http 8000
```

ngrok gives you a public URL like `https://abc123.ngrok.io`. Use that as your callback URL base.

### Step 3 — Create a Payment Channel

1. Open `http://127.0.0.1:8000/payments/channels/new/step1/`
2. Name: anything (e.g. `My Sandbox Channel`), Provider: **M-Pesa** → Next
3. Fill in the form:
   - **Shortcode**: `174379`
   - **Callback URL**: `https://abc123.ngrok.io/payments/callbacks/daraja/`
   - **Consumer Key** and **Consumer Secret**: from your Safaricom app dashboard
   - **Passkey**: from the Lipa Na M-Pesa test credentials page
   - **Environment**: `sandbox`
4. Save.

### Step 4 — Trigger a payment

1. Go to `http://127.0.0.1:8000/parking/pay/`
2. Enter a plate number, your real phone number (must be registered for M-Pesa), an amount (minimum KES 1), and select your channel.
3. Click **Pay Now**.
4. Your phone will receive an M-Pesa STK Push prompt — enter your PIN.
5. Safaricom will POST the result to your callback URL.
6. Refresh the session status page to see the updated status.

---

## URL reference

| URL | Purpose | Notes |
|-----|---------|-------|
| `/` | Dashboard | |
| `/payments/channels/` | List payment channels | |
| `/payments/channels/new/step1/` | Create channel — step 1 (name + provider) | |
| `/payments/channels/new/step2/` | Create channel — step 2 (credentials) | |
| `/payments/callbacks/daraja/` | Safaricom callback endpoint | POST only, CSRF exempt |
| `/parking/pay/` | Parking payment form | |
| `/parking/session/<id>/` | Parking session status | |
| `/admin/` | Django admin | |

---

## Key design decisions

**No session storage between form steps.** The two-step channel creation form passes `name` and `provider_type` via URL query params and a hidden field. Simple, and it avoids any dependency on session middleware configuration.

**Signals over direct calls.** `payments` fires `payment_completed`; `parking` listens. The connection is made in `ParkingConfig.ready()` at startup. Adding another business module means connecting its own listener the same way — `payments` never needs to change.

**Credentials in the database, not environment variables.** A deliberate demo choice. Changing a credential in the admin takes effect immediately on the next charge. In production you'd want to encrypt the credential fields at rest, and you might want to cache the access token rather than fetching a new one on every charge.

**SQLite.** Fine for a demo. To switch to Postgres, change the `DATABASES` setting in `minigateway/settings.py` and install `psycopg2`.
