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

## Was heute funktioniert (v1.0)

Ende-zu-Ende-Pipeline mit echten Dateien, jede Stufe mit Checkpoint (Absturz/Korrektur → nichts wird doppelt bezahlt):

1. **Upload** (`POST /uploads`): Video wird gespeichert und mit ffprobe geprüft (Bild + Ton, Länge, Größe).
2. **Transkription** mit Zeitstempeln pro Satz (Whisper, lange Folgen werden in 20-Min-Stücke geteilt).
3. **Synchron-Übersetzung** per LLM: Slang, Wortwitz und Tonfall bleiben, Länge wird auf die Sprechzeit der Zeile begrenzt.
4. **Sprachsynthese** pro Zeile (ElevenLabs, Standardstimme oder Stimmklon mit dokumentierter Einwilligung).
5. **Timing-Anpassung**: Jede Zeile wird ohne Tonhöhenänderung in ihr Zeitfenster eingepasst (max. 1,3×).
6. **Mischung & Export**: Synchronstimme + Originalton leise darunter (Musik/Effekte), Lautheit nach EBU R128,
   MP4 mit deutscher Tonspur (Standard) + Originalspur, KI-Kennzeichnung in den Metadaten (EU AI Act Art. 50).
7. **Automatische QA**: Timing-Überläufe, unübersetzte Zeilen, Lautstärke, Länge → `completed` oder `hitl_review`.
8. **Human-in-the-loop**: Zeilen ansehen (`GET /jobs/{id}/segments`), korrigieren (`PATCH .../segments/{n}`),
   neu rendern (`POST /jobs/{id}/render`, nur geänderte Zeilen werden neu vertont), freigeben (`POST .../approve`).

Weitere Endpunkte: `GET /jobs`, `GET /jobs/{id}/output` (Download), `POST /jobs/{id}/cancel`, `DELETE /jobs/{id}`,
`POST /voices` (Standardstimme), `POST /voices/clone` (Stimmklon), `DELETE /voices/{id}/consent`
(Widerruf: Stimme, Referenzaufnahme, Klon beim Anbieter und alle damit erzeugten Synchronfassungen werden gelöscht),
`GET /stats`. Interaktive API-Doku unter `/docs`.

### Sicherheit
- Mandantentrennung doppelt: jede Abfrage filtert auf den Mandanten aus dem Token, zusätzlich Postgres-RLS.
- Kein Client-Pfad oder -URL wird je geöffnet: Quellen sind nur eigene Uploads (`upload:<uuid>`) → kein SSRF/LFI.
- Löschen und Download nur innerhalb des Mandanten-Speichers.
- Fehlertexte für Kunden enthalten keine Interna.

### Grenzen (ehrlich)
- **Lip-Sync** ist als Schnittstelle vorhanden, aber standardmäßig aus (braucht GPU-Modell wie Wav2Lip/LatentSync
  oder einen gehosteten Lip-Sync-Dienst). Ergebnis heute: hochwertige Synchronfassung ohne Lippenanpassung.
- **Eine Stimme pro Job**: Sprechertrennung (Diarization) für mehrere Figuren ist noch nicht eingebaut.
- **Hintergrund** wird leiser gemischt statt per Stem-Separation (Demucs) sauber getrennt.
- Verarbeitung läuft im API-Prozess (BackgroundTasks); für viele parallele Kunden einen Worker (z.B. arq/Celery) ergänzen.

## Setup

```bash
cp .env.example .env            # Werte eintragen
pip install -r requirements.txt # + ffmpeg installieren
alembic upgrade head            # als DB-Owner; App läuft mit eigener Rolle ohne Owner-Rechte
uvicorn apps.api.main:app
```

Lokale Demo ohne API-Kosten: `ENV=development PROVIDER_MODE=fake uvicorn apps.api.main:app` (Platzhalter-Töne statt Stimmen).

Docker: `docker build -t series-sync . && docker run -p 8000:8000 --env-file .env -v seriessync:/app/var series-sync`

## Tests

```bash
pytest -q                                            # Pipeline + API (echtes ffmpeg, Fake-KI)
DATABASE_URL=postgresql+asyncpg://app:...@localhost/seriessync_test pytest tests/test_rls.py   # RLS gegen Postgres
```
