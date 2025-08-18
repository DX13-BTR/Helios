# Helios System Development Summary - 2025-07-29

## 🧱 1. Helios Architecture Decisions

- ✅ Python will be used for core agent logic
- ✅ React + Tailwind will remain the UI layer
- ✅ Sheets will remain short-term backend, but will migrate to `.json` or SQLite
- ✅ Each FSS/CIE module will be moved to `/agents/*.py`
- ✅ `main.py` and `scheduler.py` will orchestrate everything
- ✅ All outputs will be written as `.json` for React to consume
- ✅ Flask will serve the `.json` outputs as `/api/*` routes
- ✅ Dashboard will continue running as PWA with Ngrok

## 🔐 2. Security Layer

- Tokens stored in `.env` only
- Flask endpoints protected with `x-helios-token` header
- iPad/PWA will include token in API calls
- Optional Ngrok auth for external access

## 🧠 3. Agentic Migration Strategy (FSS)

- `generateWeeklyDigest()` → `fss_digest_agent.py`: ✅ Complete
- `generateAIAdvice()` → `fss_advice_agent.py`: 🔜
- Other advice generators to be split into agents: 🔜
- `copySuggestedTransfersToSheet()` and `processTransferApprovals()` to be restructured: 🔜
- Output formats unified to JSON

## 📱 4. iPad + Remote Usage

- Confirmed working via Ngrok + PWA
- Full mobile access to dashboard
- Security headers must be included in mobile API calls

## 📣 5. Voice Integration (Future)

- Voice control layer feasible (Gideon mode)
- Web Speech API for React (iPad/desktop)
- Python mic-based loop (`speech_recognition`, `pyttsx3`)
- Future audio feedback via ElevenLabs

## 📦 6. Deployment Strategy

- System remains local, with global UI exposure
- Build Electron-ready, defer packaging
- Standardised `/helios/` structure
- `start_helios.py` to unify startup
- Agentic Builder planned for future module scaffolding

## 📋 7. Immediate Next Steps

- Translate remaining `.gs` modules to Python: 🔜
- Scaffold Flask API endpoints + middleware: 🔜
- Wire API outputs to React dashboard: 🔜
- Build `main.py` and `scheduler.py`: 🔜
