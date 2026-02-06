# 🤖 AI-Powered GitHub Pull Request Code Reviewer

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-orange.svg)
![License](https://img.shields.io/badge/License-MIT-blue.svg)

A **production-ready backend service** that automatically reviews GitHub Pull Requests using AI. When a PR is opened or updated, this service analyzes the code changes and provides intelligent, actionable feedback through inline comments and summary reviews.

## 🎯 Features

### Core Functionality
- **Automated PR Reviews**: Triggers on `opened` and `synchronize` events
- **Intelligent Code Analysis**: Uses GPT-4 to identify bugs, security issues, performance problems, and code smells
- **Inline Comments**: Posts line-specific feedback directly on the PR
- **Summary Reviews**: Provides an overall assessment with categorized issues
- **GitHub App Authentication**: Secure, least-privilege access using GitHub Apps

### Production-Ready Features
- **Webhook Security**: HMAC-SHA256 signature verification
- **Async Processing**: Non-blocking webhook handling with background tasks
- **Rate Limiting**: Protects against GitHub and OpenAI API limits
- **Automatic Retries**: Exponential backoff for transient failures
- **Comprehensive Logging**: Structured JSON logs with sensitive data filtering
- **Configurable Limits**: Control PR size, file types, and review scope

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GITHUB                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                      │
│  │   PR Open   │ ── │  Webhook    │ ── │   Payload   │                      │
│  │  PR Sync    │    │   Event     │    │   Signed    │                      │
│  └─────────────┘    └─────────────┘    └──────┬──────┘                      │
└──────────────────────────────────────────────┼──────────────────────────────┘
                                               │
                                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         AI PR REVIEWER SERVICE                                │
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                        WEBHOOK HANDLER                                 │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                  │   │
│  │  │  Signature  │ → │   Payload   │ → │  Queue for  │                  │   │
│  │  │ Verification│   │ Validation  │   │ Background  │                  │   │
│  │  └─────────────┘   └─────────────┘   └──────┬──────┘                  │   │
│  └─────────────────────────────────────────────┼─────────────────────────┘   │
│                                                │                              │
│                    ┌───────────────────────────┴────────────────────────┐    │
│                    │              BACKGROUND PROCESSOR                   │    │
│                    │                                                     │    │
│  ┌─────────────────┴─────────────────┐    ┌─────────────────────────────┴─┐  │
│  │         GITHUB CLIENT              │    │         DIFF PARSER          ││  │
│  │  ┌─────────────────────────────┐  │    │  ┌───────────────────────┐   ││  │
│  │  │  JWT Auth (GitHub App)      │  │    │  │  Parse Unified Diffs  │   ││  │
│  │  │  Fetch PR Files & Patches   │  │    │  │  Extract Line Numbers │   ││  │
│  │  │  Post Review Comments       │  │    │  │  Build LLM Context    │   ││  │
│  │  └─────────────────────────────┘  │    │  └───────────────────────┘   ││  │
│  └───────────────────┬───────────────┘    └──────────────┬───────────────┘│  │
│                      │                                    │                │  │
│                      └──────────────┬────────────────────┘                │  │
│                                     ▼                                      │  │
│                    ┌─────────────────────────────────────┐                │  │
│                    │          AI REVIEW ENGINE           │                │  │
│                    │  ┌───────────────────────────────┐  │                │  │
│                    │  │  OpenAI GPT-4 API Integration │  │                │  │
│                    │  │  Structured JSON Prompts      │  │                │  │
│                    │  │  Response Validation          │  │                │  │
│                    │  └───────────────────────────────┘  │                │  │
│                    └─────────────────────────────────────┘                │  │
│                                                                            │  │
└────────────────────────────────────────────────────────────────────────────┘
                                               │
                                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              GITHUB PR                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  📝 Inline Comments on Specific Lines                                    │ │
│  │  📊 Summary Review with Issue Breakdown                                  │ │
│  │  ✅ APPROVE / 💬 COMMENT / ❌ REQUEST_CHANGES                            │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 📋 End-to-End PR Review Flow

### 1. Developer Opens/Updates PR
A developer creates or pushes to a pull request on GitHub.

### 2. GitHub Sends Webhook
GitHub sends a `pull_request` webhook to your configured endpoint with:
- Event type (`opened` or `synchronize`)
- Full PR metadata
- HMAC-SHA256 signature for verification

### 3. Webhook Validation (< 100ms)
The service:
- Verifies the webhook signature using your secret
- Validates the event type and action
- Returns `200 OK` immediately
- Queues the review for background processing

### 4. Background Processing
In the background, the service:
1. **Authenticates** with GitHub using App JWT → Installation Token
2. **Fetches PR Files** via GitHub REST API with pagination
3. **Filters Files** based on configuration (extensions, paths, size)
4. **Parses Diffs** to extract line-by-line changes
5. **Sends to AI** with structured prompt and file context
6. **Validates Response** against strict JSON schema
7. **Posts Review** with inline comments and summary

### 5. Developer Receives Feedback
The developer sees:
- Inline comments on specific lines with severity indicators
- A summary comment with issue breakdown by category
- Review state (COMMENT or REQUEST_CHANGES for critical issues)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- GitHub Account with permission to create Apps
- OpenAI API Key (GPT-4 access recommended)
- ngrok (for local development) or public server

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ai-pr-reviewer.git
cd ai-pr-reviewer/ai_pr_reviewer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### Configuration

Edit `.env` with your credentials:

```env
# GitHub App (see setup instructions below)
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=./private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# OpenAI
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4-turbo-preview

# Optional: Adjust limits
MAX_PR_FILES=50
MAX_DIFF_LINES=500
LOG_LEVEL=INFO
```

### Run the Server

```bash
# Development
python run.py

# Or with uvicorn directly
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Expose with ngrok (Development)

```bash
ngrok http 8000
```

Copy the ngrok URL (e.g., `https://abc123.ngrok.io`) for webhook configuration.

---

## 🔧 GitHub App Setup

### Step 1: Create a GitHub App

1. Go to **GitHub Settings** → **Developer settings** → **GitHub Apps**
2. Click **New GitHub App**
3. Fill in:
   - **Name**: `AI Code Reviewer` (or your preferred name)
   - **Homepage URL**: Your project URL
   - **Webhook URL**: `https://your-domain.com/webhook/github`
   - **Webhook Secret**: Generate a secure random string
   - **Permissions**:
     - **Repository permissions**:
       - `Contents`: Read
       - `Pull requests`: Read & Write
       - `Metadata`: Read
   - **Subscribe to events**:
     - ✅ Pull request
4. Click **Create GitHub App**

### Step 2: Generate Private Key

1. After creating the app, click **Generate a private key**
2. Download the `.pem` file
3. Save it securely (e.g., `private-key.pem` in your project root)

### Step 3: Install the App

1. Go to your GitHub App settings
2. Click **Install App** in the sidebar
3. Select the repository/organization
4. Grant access to specific repositories

### Step 4: Note Your App ID

Find your App ID on the app's settings page and add it to `.env`.

---

## 🔐 Security Considerations

### Webhook Signature Verification
Every webhook request is verified using HMAC-SHA256:
```python
expected = hmac.new(secret, payload, sha256).hexdigest()
hmac.compare_digest(signature, expected)  # Constant-time comparison
```

### Secrets Management
- All secrets via environment variables only
- Sensitive data automatically redacted from logs
- No secrets ever written to disk or logged

### Least Privilege Access
GitHub App permissions are scoped to minimum required:
- Read repository contents (for diffs)
- Write pull request comments (for reviews)
- Read metadata (for PR info)

### No Code Persistence
- Source code is fetched, analyzed, and discarded
- No permanent storage of repository code
- Only review results are retained temporarily

---

## 🔄 How Async Processing Works

```
Webhook Request
      │
      ▼
┌─────────────────────┐
│  FastAPI Receives   │ ─── Runs on Main Event Loop
│  POST /webhook/github│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Signature Check    │ ─── Sync, fast (~1ms)
│  Payload Validation │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Return 200 OK      │ ─── Client (GitHub) gets response
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  BackgroundTasks    │ ─── Added to event loop
│  .add_task(...)     │
└──────────┬──────────┘
           │
           ▼ (async, non-blocking)
┌─────────────────────┐
│  Fetch PR Files     │ ─── async/await, uses httpx
│  Parse Diffs        │
│  Call OpenAI        │
│  Post Comments      │
└─────────────────────┘
```

### Why This Design?

1. **GitHub Timeout**: GitHub expects webhook response within 10 seconds
2. **AI Processing Time**: GPT-4 can take 10-30 seconds per request
3. **Non-Blocking**: Server can handle many concurrent webhooks
4. **Reliability**: If processing fails, webhook was already acknowledged

### Future Upgrade Path

The current design uses FastAPI's `BackgroundTasks` for simplicity. For higher scale:

```python
# Current (simple, single-server)
background_tasks.add_task(process_pr_review, context)

# Future (distributed, multi-server)
celery_app.send_task("review_pr", args=[context.model_dump()])
```

---

## 📊 Example Review Output

### Inline Comment Example

```
🚨 HIGH | 🐛 BUG

**Issue:** This SQL query is vulnerable to injection attacks. User input is directly
interpolated into the query string without sanitization.

**Suggestion:** Use parameterized queries instead:
`cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))`

---
*Generated by AI Code Reviewer*
```

### Summary Comment Example

```markdown
## 🤖 AI Code Review Summary

This PR introduces a new user authentication feature. While the overall implementation
is solid, there are a few security and performance concerns that should be addressed
before merging.

### 📊 Overview

| Metric | Count |
|--------|-------|
| Total Issues | 5 |
| 🚨 High Severity | 1 |
| ⚠️ Medium Severity | 2 |
| 💡 Low Severity | 2 |

### 📁 Issues by Category

- **Security**: 2
- **Performance**: 2
- **Style**: 1

---
*This review was automatically generated by AI Code Reviewer*
```

---

## 🛡️ Common Failure Cases and Handling

### Rate Limits

| Service | Limit | Handling |
|---------|-------|----------|
| GitHub API | 5000 req/hour | AsyncLimiter, queue backpressure |
| OpenAI API | 60 req/min | Rate limiter, exponential backoff |

### Large PRs

| Limit | Default | Behavior |
|-------|---------|----------|
| Max Files | 50 | Skip remaining files |
| Max Lines/File | 500 | Skip large files |
| Max Total Lines | 3000 | Abort review with warning |

### API Failures

| Failure | Recovery |
|---------|----------|
| GitHub 401 | Invalidate token cache, retry with new token |
| GitHub 403 | Log rate limit, wait for reset |
| OpenAI timeout | Retry with exponential backoff (3 attempts) |
| Invalid AI response | Validate JSON, skip malformed issues |
| Invalid line numbers | Find nearest valid line or skip comment |

### Network Issues

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=30),
    retry=retry_if_exception_type((HTTPError, TimeoutError))
)
async def make_request(...):
    ...
```

---

## 📈 Scaling Considerations

### Current Single-Server Capacity

- ~100 concurrent webhook requests
- ~10 parallel AI reviews (limited by OpenAI rate limits)
- ~1000 PRs/day typical workload

### Horizontal Scaling

1. **Load Balancer**: Add nginx/HAProxy in front of multiple instances
2. **Shared State**: Use Redis for rate limiting and deduplication
3. **Task Queue**: Move to Celery for distributed processing
4. **Separate Workers**: Split webhook receivers from AI processors

### Vertical Scaling

```yaml
# docker-compose.yml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

### Monitoring

- Prometheus metrics endpoint (future)
- Structured JSON logs for ELK/Datadog
- Health and readiness endpoints for orchestrators

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_webhook.py -v

# Run specific test
pytest tests/test_models.py::TestReviewModels::test_review_issue_valid -v
```

---

## 📁 Project Structure

```
ai_pr_reviewer/
├── app/
│   ├── __init__.py              # Package init
│   ├── config.py                # Configuration management
│   ├── logging_config.py        # Structured logging setup
│   ├── main.py                  # FastAPI application
│   ├── models.py                # Pydantic data models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ai_engine.py         # OpenAI integration
│   │   ├── diff_parser.py       # Unified diff parsing
│   │   ├── github_auth.py       # GitHub App JWT auth
│   │   └── github_client.py     # GitHub API client
│   └── webhook/
│       ├── __init__.py
│       ├── handler.py           # Webhook endpoint
│       ├── processor.py         # Review orchestrator
│       └── security.py          # Signature verification
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Test fixtures
│   ├── test_diff_parser.py
│   ├── test_models.py
│   └── test_webhook.py
├── .env.example                 # Environment template
├── requirements.txt             # Python dependencies
├── run.py                       # Application runner
└── README.md                    # This file
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [OpenAI](https://openai.com/) - GPT-4 for intelligent code analysis
- [PyGithub](https://github.com/PyGithub/PyGithub) - Inspiration for GitHub API patterns
- [structlog](https://www.structlog.org/) - Structured logging library
