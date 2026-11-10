# Projekt 4: Series Sync — Automatische Synchronisation von Serien/Filmen

## Vision
Ein Programm das Serien und Filme automatisch ins Deutsche synchronisiert. Lippenbewegung wird angepasst, Stimmklone werden erstellt, Slang und Stimmcharakteristika werden übertragen. Output ist eine perfekte, fehlerfreie deutsche Synchronisation.

## Kernfunktionen
- **Upload:** Hochladen von Folgen/Episoden
- **Transkription:** Automatische Transkription der Originalsprache
- **Übersetzung:** Übersetzung ins Deutsche mit Beibehaltung von Slang, Wortwitz, kulturellen Referenzen
- **Stimmklon:** Erstellung von Stimmklonen für jeden Charakter (Voice Cloning)
- **Lip-Sync:** Anpassung der Lippenbewegung an die deutsche Synchronisation
- **Stimmcharakteristika:** Übertragung von Stimmmerkmalen (Tonhöhe, Tempo, Emotion)
- **Qualitätsprüfung:** Automatische Prüfung auf Fehler (Lip-Sync, Audio-Qualität, Übersetzungsfehler)
- **Output:** Perfekte, fehlerfreie deutsche Folge

## Zielgruppe
Streaming-Plattformen, Filmstudios, Content-Distributoren, YouTuber

## Technische Anforderungen
- AI Voice Cloning (ElevenLabs, Coqui TTS)
- Lip-Sync AI (Wav2Lip, SadTalker)
- Speech-to-Text (Whisper)
- Machine Translation (DeepL, GPT-4)
- Video Processing (FFmpeg)
- Quality Assurance Pipeline (automatische Fehlererkennung)

## Monetarisierung
- Pay-per-Episode
- Monatliches Abo für Studios
- Enterprise-Lizenz

## Setup

1. **Environment Config**: Create a `.env` file from the provided settings (see `apps/core/config.py`). You will need `DATABASE_URL` (PostgreSQL) and other keys.
2. **Dependencies**: Ensure you have PostgreSQL, FFmpeg, and Python >= 3.11 installed. Run `pip install -r requirements.txt`.
3. **Database Migration**: Start the Postgres server, create the `seriessync` database, and run `alembic upgrade head`.
4. **Testing**: Run tests via `pytest tests/ -v`.
5. **Run the server**: Start the FastAPI server using `uvicorn apps.api.main:app --reload`.
