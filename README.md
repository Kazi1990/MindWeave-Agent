

# 🧠 MindWeave

**A multi-agent decision system where four specialized AI agents debate before answering.**

Built for the **Global AI Hackathon Series with Qwen Cloud 2026** — Track 3: *Agent Society*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Built with Qwen Cloud](https://img.shields.io/badge/Built%20with-Qwen%20Cloud-1976d2)](https://www.qwencloud.com)
[![Deployed on Alibaba Cloud](https://img.shields.io/badge/Deployed%20on-Alibaba%20Cloud%20ECS-ff9800)](#deployment)

</div>

---

## 📐 Architecture

![MindWeave Architecture](./architecture-diagram.png)

## 🖥️ Live Backend Proof

> _Screenshot showing the app running on Alibaba Cloud ECS — to be added._
>
> `![Backend running on Alibaba Cloud](./backend-screenshot.png)`

## 🎬 Demo Video

> **[▶ Watch the 3-minute demo on YouTube](#)** — link to be added once recorded.

---

## 💡 The Idea

Most AI assistants give you one model's opinion, dressed up as an answer. **MindWeave doesn't trust a single perspective.**

Every user query goes through four specialized agents that each reason independently and then debate before a final judge synthesizes their positions into one answer — with a transparent confidence score attached. It's less "ask a chatbot," more "convene a small panel."

## 🤖 The Agent Pipeline

```
User Request
     │
     ▼
┌─────────────────────────────────────────┐
│  Sriti   — Memory & Context Intelligence  │  Recalls relevant history from OSS,
└─────────────────────────────────────────┘  extracts entities, forms an initial view
     │
     ▼
┌─────────────────────────────────────────┐
│  Buddhi  — Reasoning & Logic Intelligence │  Breaks the problem down logically,
└─────────────────────────────────────────┘  builds evidence-based arguments
     │
     ▼
┌─────────────────────────────────────────┐
│  Hriday  — Emotion & Ethics Intelligence  │  Evaluates sentiment and ethical
└─────────────────────────────────────────┘  implications, challenges cold logic
     │
     ▼
┌─────────────────────────────────────────┐
│      Consolidated Debate Layer            │  Agreements, disagreements, and a
└─────────────────────────────────────────┘  synthesized outcome are compiled
     │
     ▼
┌─────────────────────────────────────────┐
│  Mat     — Final Judge & Response Builder │  Arbitrates all perspectives, scores
└─────────────────────────────────────────┘  confidence, writes the final answer
     │
     ▼
Response delivered to user
     │
     ▼ (async, non-blocking)
┌─────────────────────────────────────────┐
│  Sriti   — Memory Feedback Loop           │  Writes the interaction back to OSS
└─────────────────────────────────────────┘  for future sessions
```

| Agent | Role | Reads | Writes |
|---|---|---|---|
| **Sriti** | Memory & Context | User input, OSS history | Context profile, ranked memory |
| **Buddhi** | Reasoning & Logic | Sriti's context + opinion | Structured reasoning, logical stance |
| **Hriday** | Emotion & Ethics | Buddhi's reasoning + Sriti's context | Sentiment breakdown, ethical stance |
| **Mat** | Final Judge | All three opinions + debate result | Final answer, confidence score |

## ✨ What Makes This Different

- **No guessed confidence scores.** Every agent is forced to return structured JSON (`response_format=json_object`); confidence numbers come straight from the model's own output — never a hardcoded fallback.
- **No silent failures.** Every Qwen Cloud / OSS call raises a specific exception on failure and surfaces it as a real warning in the API response, instead of quietly faking a result.
- **One fixed memory schema, everywhere.** Every memory object — `uuid`, `type`, `importance`, `tags`, `created_at`, `updated_at`, `last_accessed`, `access_count`, `expires_at`, `source` — follows the same structure across every agent and every session.
- **Persistent, evolving memory.** After each response is delivered, an asynchronous job lets Sriti write the interaction back to Alibaba Cloud OSS — deduplicated and importance-ranked — so the system genuinely accumulates context over time instead of resetting every session.
- **Bilingual by design.** Built to serve both English and Bengali-speaking users naturally.

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **AI Engine** | Qwen Cloud API — Qwen3.7-Plus, all four agents |
| **Backend** | FastAPI (Python) |
| **Hosting** | Alibaba Cloud ECS, Ubuntu 22.04 |
| **Persistent Memory** | Alibaba Cloud OSS (JSON document store) |
| **Frontend** | Vanilla HTML / CSS / JS |

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Runs a message through the full agent pipeline, returns the final synthesized response |
| `GET` | `/api/memory/{user_id}` | Retrieves stored memory for a given user |
| `DELETE` | `/api/memory/{user_id}` | Clears stored memory for a given user |
| `GET` | `/api/health` | Health check — reports whether Qwen Cloud and OSS are configured |

## 📁 Project Structure

```
MindWeave/
├── main.py              # FastAPI backend — all four agents + memory pipeline
├── requirements.txt      # Python dependencies
├── static/
│   ├── index.html         # Frontend UI
│   ├── app.js              # Frontend logic (chat, bilingual support)
│   └── styles.css          # Styling
├── LICENSE                # MIT
└── README.md
```

## 🚀 Running Locally

```bash
git clone https://github.com/Kazi1990/MindWeave.git
cd MindWeave
pip install -r requirements.txt
```

Create a `.env` file in the project root with:

```
DASHSCOPE_API_KEY=your_qwen_cloud_api_key
OSS_ACCESS_KEY_ID=your_oss_access_key
OSS_ACCESS_KEY_SECRET=your_oss_secret_key
```

Then run:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser.

## ☁️ Deployment

MindWeave runs in production on **Alibaba Cloud ECS (Ubuntu 22.04)**, with persistent memory backed by **Alibaba Cloud OSS**, and every agent powered by the **Qwen Cloud API (Qwen3.7-Plus)**.

## 🏆 Hackathon Details

- **Event:** Global AI Hackathon Series with Qwen Cloud 2026
- **Track:** Track 3 — Agent Society
- **Built With:** Qwen Cloud, FastAPI, Python, Alibaba Cloud OSS, Alibaba Cloud ECS

## 👤 Author

**Kazi Humayun Rashid**
Lead System Architect, TechTown
[GitHub](https://github.com/Kazi1990) · [LinkedIn](https://linkedin.com/in/kazi-humayun-rashid-661a53331)

## 📄 License

Released under the [MIT License](./LICENSE).
