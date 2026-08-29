# 🎙️ GeordieDaz — JARVIS-Inspired AI Voice Agent & Companion

[![React](https://img.shields.io/badge/Frontend-React%2018%20%7C%20Vite-00f0ff?style=for-the-badge&logo=react)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Python%203.11-00d4aa?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%20%2B%20pgvector-336791?style=for-the-badge&logo=postgresql)](https://github.com/pgvector/pgvector)
[![ElevenLabs](https://img.shields.io/badge/Voice-ElevenLabs%20Streaming%20TTS-ff9e00?style=for-the-badge)](https://elevenlabs.io/)
[![OpenAI](https://img.shields.io/badge/Model-OpenAI%20Realtime%20API-412991?style=for-the-badge&logo=openai)](https://openai.com/)

> **"Not just an AI with an accent. A genuine character with warmth, wit, presence, and persistent memory."**

**GeordieDaz** is a state-of-the-art conversational AI voice companion from Newcastle upon Tyne, inspired by the charismatic, warm, late-night radio presence of **Alan Robson** (*Metro Radio’s Night Owls*). Designed with a futuristic **Iron Man JARVIS holographic HUD**, persistent neural vector memory, real-time voice streaming, and a modular architecture built to evolve into a central life & business automation hub.

---

## 🌟 Core Highlights

### 1. 🖥️ JARVIS Holographic HUD Interface
* **Acoustic Spatial Synapse:** Central HTML5 Canvas rendering multi-layered rotating HUD rings, real-time audio spectrum waves, and dynamic particle vortex.
* **Neural Memory Bank:** Translucent glassmorphism panel displaying categorized memory nodes (`[FACT]`, `[PREF]`, `[SESSION]`), vector DB sync telemetry, and confidence ratings.
* **Conversation Transcript:** Live audio stream feed with low-latency typing indicators and audio codec readouts.
* **Dual Aesthetic Themes:** Dynamic switching between **Cyan Core** (*Friendly Mode*) and **Amber/Gold HUD** (*Driving Banter Mode*).

### 2. 🧠 Persistent Long-Term Neural Memory
* **Semantic Memory (pgvector):** Auto-extracts personal facts, preferences, relationships, and context into high-dimensional vector embeddings with UPSERT conflict resolution.
* **Episodic Memory (Session Summaries):** Automatically summarizes completed conversations into historical event nodes for chronological recall (*"Where were we driving last Friday?"*).
* **Working Memory (Redis):** Sub-millisecond conversation turn buffer with 24-hour TTL.
* **Hybrid Active Retrieval:** The agent autonomously calls `search_memory` and `search_history` tools silently before answering personal or temporal questions.

### 3. 🎙️ Dual Persona Modalities
* **Friendly Geordie (Night Owls Warmth):** Warm, thoughtful, late-night radio broadcaster charm with natural conversational cadence, genuine empathy, and authentic Tyneside vocabulary (*"howay man", "proper mint", "canny", "bonny lad"*).
* **Driving Banter Mode:** High-octane, razor-sharp sarcastic co-pilot riding shotgun. Roasts driving habits, mirror checks, and music playlists with rapid-fire comedic wit.

### 4. ⚡ High-Speed Voice Pipeline & Barge-In
* Full-duplex audio at 16kHz/24kHz PCM16 via `AudioWorklet` with zero browser-freezing.
* Server-side and client-side Voice Activity Detection (VAD).
* Instant **Barge-In**: User speech immediately interrupts AI audio playback and cancels active generation buffers.

### 5. 🔌 Future Automation Hub Ready (MCP)
Engineered with modular tool dispatching designed to integrate:
* Proton Mail & Gmail inbox automation
* Social Media multi-platform scheduling (X, TikTok, Instagram, LinkedIn)
* Smart Home IoT triggers & Calendar management
* Crypto, stocks & real-time portfolio telemetry

---

## 🏗️ Architecture

```
                               ┌─────────────────────────────────────────┐
                               │           BROWSER CLIENT                │
                               │  • React 18 + Vite (JARVIS HUD)         │
                               │  • AudioWorklet (16kHz PCM Streamer)    │
                               │  • Canvas Particle & Ring Renderer      │
                               └────────────────────┬────────────────────┘
                                                    │ Full-Duplex WS
                                                    ▼
                               ┌─────────────────────────────────────────┐
                               │            FASTAPI BACKEND              │
                               │  • WebSocket Duplex Stream Router       │
                               │  • LangGraph Agent Orchestrator         │
                               │  • Persona Manager (Hot-Swap)           │
                               └──────┬───────────────────┬──────────────┘
                                      │                   │
                 ┌────────────────────┴──────┐     ┌──────┴────────────────────┐
                 ▼                           ▼     ▼                           ▼
      ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
      │ OpenAI Realtime API  │   │  ElevenLabs Engine   │   │ PostgreSQL (pgvector)│
      │ • gpt-4o-transcribe  │   │  • Alan Robson Voice │   │ • Semantic Memory    │
      │ • Reasoning & Brain  │   │  • Low-Latency Flash │   │ • Episodic Summary   │
      │ • Tool Call Loop     │   │  • Expressive Tags   │   │ • Redis Working Mem  │
      └──────────────────────┘   └──────────────────────┘   └──────────────────────┘
```

---

## 🚀 Quick Start (Local Setup)

### Prerequisites
* **Docker Desktop** (for PostgreSQL + pgvector and Redis)
* **Python 3.11+**
* **Node.js 18+**
* **OpenAI API Key** (and optional **ElevenLabs API Key**)

### 1. Launch Infrastructure
```bash
# Start PostgreSQL (with pgvector) and Redis
docker-compose up -d
```

### 2. Configure Backend
```bash
cd backend
cp .env.example .env
# Edit .env with your OPENAI_API_KEY and optional ELEVENLABS credentials
```

### 3. Install Python Dependencies & Run Migrations
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
```

### 4. Start Backend Server
```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Install & Run Frontend
```bash
cd ../frontend
npm install
npm run dev
```

Navigate to **`http://localhost:5173`** in your browser.

---

## 🧪 Testing Suite

Run full automated backend test suites covering authentication, vector memory, persona switching, and LangGraph pipelines:

```bash
cd backend
pytest tests/ -v
```

---

## 📂 Project Structure

```
geordiedaz/
├── backend/
│   ├── alembic/            # Database schema migrations
│   ├── app/
│   │   ├── agent/          # LangGraph nodes & memory orchestrator
│   │   ├── api/            # REST API endpoints (Auth, Memory, Personas)
│   │   ├── models/         # SQLAlchemy 2.0 ORM models
│   │   ├── personas/       # YAML persona definitions (Alan Robson & Driving)
│   │   ├── schemas/        # Pydantic validation schemas
│   │   ├── services/       # ElevenLabs TTS, Memory & Embedding services
│   │   ├── ws/             # Full-duplex WebSocket handler
│   │   ├── config.py       # Pydantic Settings
│   │   └── main.py         # FastAPI application entrypoint
│   └── tests/              # Pytest test cases
├── frontend/
│   ├── src/
│   │   ├── components/     # Holographic VoiceOrb, Neural BrainPanel, Transcript
│   │   ├── hooks/          # useWebSocket, useVoice, useAuth
│   │   ├── stores/         # Zustand global state
│   │   └── styles/         # JARVIS HUD design system (index.css)
│   └── index.html          # Google Fonts & HUD Shell
├── docs/                   # Character Bible, Mockups & Architecture Specs
└── docker-compose.yml      # Local DB & Cache stack
```

---

## 👤 Author & Maintainer

* **GitHub:** [@MIbrahimM67](https://github.com/MIbrahimM67)
* **Repository:** [GoerdieDaz-AI-VOICE-AGENT-AND-Assistant](https://github.com/MIbrahimM67/GoerdieDaz-AI-VOICE-AGENT-AND-Assistant)

---

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
