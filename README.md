# Notifier

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2+-092E20?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Celery](https://img.shields.io/badge/Celery-5.4+-37814A?style=flat-square&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/Redis-Queue-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![LM Studio](https://img.shields.io/badge/LM%20Studio-OpenAI%20Compatible-00ADD8?style=flat-square&logo=openai&logoColor=white)](https://lmstudio.ai/)
[![Render](https://img.shields.io/badge/Render-Deploy%20Ready-46E3B7?style=flat-square&logo=render&logoColor=black)](https://render.com/)

> **AI-Powered Inbox Intelligence, Background Sync & Multi-Stage Email Filtering Pipeline**

Notifier is an intelligent email ingestion and relevance engine that continuously monitors incoming emails across multiple IMAP providers (Gmail, Outlook, Yahoo, iCloud, Custom IMAP), filters high-signal messages matching user-defined interest topics, generates structured AI summaries using local **LM Studio** models (e.g. `qwen/qwen3-1.7b` or any OpenAI-compatible LLM), and delivers instant push notifications directly to your mobile device.

---

## Architecture: Multi-Stage Pipeline & Background Processing

Notifier combines asynchronous worker queues with a two-stage cascaded filtering funnel to balance low latency, minimal compute cost, and high semantic precision:

```mermaid
flowchart TD
    Beat[Celery Beat Scheduler - Every 5 min] -->|Dispatches Task| Redis[(Redis Broker)]
    Manual[Web UI / CLI Trigger] -->|Dispatches Task| Redis
    Redis -->|Polls Task| Worker[Celery Worker]
    Worker -->|IMAP SSL| Mailbox[User Mailboxes - Gmail, Outlook, Yahoo, iCloud]
    Mailbox -->|Raw Email Stream| Chunker[HTML Cleaning & Text Splitter]
    Chunker --> Stage1[Stage 1: Bi-Encoder Embeddings & Cosine Filter]
    Stage1 -->|Cosine Similarity >= Threshold| Stage2[Stage 2: LM Studio / OpenAI-Compatible LLM Verification & Synthesis]
    Stage1 -->|Low Similarity| Discard[Discarded]
    Stage2 -->|Filtered Out by LLM| Discard
    Stage2 -->|Verified Relevant| SaveMatch[Store EmailMatch in Database]
    SaveMatch --> WebDashboard[Web Dashboard & Reader]
    SaveMatch --> MobilePush[Mobile Push Notifications - ntfy.sh / Telegram]
```

### Pipeline Details:
1. **Stage 1 — Fast Cosine Similarity Filter (Bi-Encoder)**:
   - Splits incoming email bodies using `RecursiveCharacterTextSplitter`.
   - Generates high-fidelity vector embeddings via `all-mpnet-base-v2` (768-dimensional).
   - Compares vector embeddings against user topics to discard irrelevant mail at near-zero cost.
2. **Stage 2 — LM Studio LLM Semantic Verification & Structured Synthesis**:
   - Forwards candidate chunks to LM Studio (`qwen/qwen3-1.7b` via `http://127.0.0.1:1234/v1`).
   - Verifies whether the email genuinely matches the topic context.
   - Extracts structured key takeaways and action items.
3. **Stage 3 — Real-Time Mobile Dispatch**:
   - Immediately dispatches a push notification to your phone via `ntfy.sh` or `Telegram` with the platform tag, subject, sender, and AI summary.

---

## Core Features

- **Asynchronous Task Queue**: Background processing powered by Celery and Redis to prevent blocking web requests.
- **Automated 5-Minute Polling**: Celery Beat scheduler continuously synchronizes connected mailboxes without manual intervention.
- **Instant Mobile Push Notifications**: Zero-setup alerts on your phone lock screen via `ntfy.sh` or Telegram with platform tags (`[Gmail]`, `[Outlook]`, etc.).
- **LM Studio & Local AI Integration**: Full OpenAI-compatible REST API support for local inference (e.g. Qwen 3, Llama 3, Mistral) with zero cloud leaks and zero API costs.
- **Platform Agnostic IMAP**: Connect any email provider (Gmail, Outlook, Yahoo, Apple iCloud, or custom corporate IMAP servers).
- **Sandboxed Security**: Sandboxed rendering for HTML emails preventing script execution or style leakage.
- **Production Ready**: Pre-configured with Gunicorn, WhiteNoise static files serving, PostgreSQL database support, and Render Blueprints.

---

## Security & Privacy Architecture

- **Local LLM Execution**: With LM Studio, all email content stays 100% on your local machine.
- **Encrypted Storage at Rest**:
  - IMAP passwords and custom AI API keys are encrypted at rest using `Fernet` (AES-128-CBC + HMAC-SHA256) with a 256-bit key derived via SHA-256.
  - Plaintext credentials exist strictly in memory during active IMAP connections and AI calls.
- **XSS & Isolation**:
  - HTML emails are rendered in an isolated `<iframe>` with strict sandbox restrictions (`allow-same-origin allow-popups`).
- **User Scoping**:
  - All database queries, mailboxes, topics, and notifications are scoped strictly to `request.user`.

---

## Getting Started: Setup & Onboarding Guide

### Part 1: Developer / Local Server Setup
Follow these steps to run the server on your computer:

#### 1. Clone Repository & Setup Environment
```bash
git clone https://github.com/AniceKV/Notifier.git
cd Notifier

# Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 2. Start LM Studio Server
- Open **LM Studio** and load your desired model (e.g. `qwen/qwen3-1.7b`).
- Start the Local Server on port `1234` (OpenAI-compatible endpoint `http://127.0.0.1:1234/v1`).

#### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` to configure your settings:
```env
SECRET_KEY="your-cryptographically-secure-random-secret-key"
DJANGO_DEBUG="True"
ALLOWED_HOSTS="127.0.0.1,localhost"
TIME_ZONE="Asia/Kolkata"

# Local AI Engine (LM Studio)
LM_STUDIO_URL="http://127.0.0.1:1234/v1"
LM_STUDIO_MODEL="qwen/qwen3-1.7b"

# Mobile push notification topic (subscribe to this in the free ntfy mobile app)
NTFY_TOPIC="Notifier_for_anish"

# Celery Redis broker URL (defaults to localhost:6379)
CELERY_BROKER_URL="redis://localhost:6379/0"
CELERY_RESULT_BACKEND="redis://localhost:6379/0"
```

#### 4. Apply Database Migrations & Create Admin
```bash
cd djangoproj
python manage.py migrate
python manage.py createsuperuser
```

#### 5. Launch the Server Suite
- **Option A (1-Click Launch on Windows)**:
  Run `start.bat` from the root directory. It automatically starts Redis in WSL, launches Celery Worker, Celery Beat, and the Django web server in coordinated windows.
- **Option B (Manual Launch)**:
  Start Redis on port 6379, then open three terminals inside `djangoproj/`:
  - Terminal 1: `python manage.py runserver`
  - Terminal 2: `celery -A djangoproj worker -l info --pool=solo`
  - Terminal 3: `celery -A djangoproj beat -l info`

---

### Part 2: Web App User Onboarding
Once the server is running, complete these steps in the browser to start receiving AI summaries:

#### Step 1: Create an Account & Sign In
- Navigate to `http://127.0.0.1:8000/` (or your live deployed URL).
- Register a new user account and log in.

#### Step 2: Configure LM Studio / Local AI
- Go to **Profile & Settings** (`/profile/`).
- Under **LM Studio & Local AI**, confirm your endpoint URL (`http://127.0.0.1:1234/v1`) and target model (`qwen/qwen3-1.7b`).
- Click **⚡ Test Connection** to verify live connectivity.

#### Step 3: Connect an Email Mailbox
- In **Connected Mailboxes**, click **Connect Mailbox**:
  - **Platform**: Select Gmail, Outlook, Yahoo, iCloud, or Custom IMAP.
  - **Email Address**: Your email address (e.g. `you@gmail.com`).
  - **App Password**: Your 16-character IMAP App Password (for Gmail, generate one in Google Account -> Security -> 2-Step Verification -> App Passwords).

#### Step 4: Define Interest Topics to Track
- Under **AI Topic Classifiers**, click **Add Topic**:
  - **Topic Name**: (e.g. `Machine Learning Research`, `Job Offers`, `Internship Updates`)
  - **Description**: What you are looking for (e.g. `Paper acceptances, NeurIPS/ICLR updates, PyTorch releases`).
  - **Similarity Threshold**: Default `0.45`.

#### Step 5: (Optional) Subscribe to Mobile Notifications
- Install the free **ntfy** app on your phone (Android / iOS).
- Tap **+ Subscribe to topic** and enter the topic configured in your `.env` (e.g. `Notifier_for_anish`).
- When an email matches your topic, your phone will instantly receive the notification with the AI summary!

---

## Production Cloud Deployment (Render)

Notifier includes a ready-to-use `render.yaml` Blueprint specification for 1-click cloud deployment.

---

## Roadmap

- [x] Multi-stage email ingestion and semantic filtering pipeline.
- [x] LM Studio and OpenAI-compatible local AI integration.
- [x] Live model connectivity testing and discovery.
- [x] Platform-agnostic IMAP credentials management with AES-256 encryption.
- [x] Background asynchronous email synchronization via Celery + Redis worker queue.
- [x] Automated 5-minute scheduled polling via Celery Beat.
- [x] Instant mobile push notifications via ntfy.sh and Telegram.
- [x] 1-Click local development orchestration script (`start.bat`).
- [x] Production deployment configuration for Render (Gunicorn, WhiteNoise, PostgreSQL).
- [ ] Email categorization rules and webhook actions.
- [ ] Multi-account digest summary generation.

