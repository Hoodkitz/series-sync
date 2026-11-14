# Series Sync: Betriebsanleitung (Operations Guide)

Dieses Dokument beschreibt den Betrieb von Series Sync, insbesondere die Handhabung von Kontingenten (Google Gemini Free-Tier Limits: 10 TTS/Tag), die Wiederaufnahme pausierter Jobs und die Steuerung des Hintergrund-Workers.

---

## 1. Übersicht & Architektur der Wiederaufnahme

Series Sync arbeitet mit einer stufenbasierten Checkpoint-Architektur. Jede Verarbeitungsstufe speichert ihren Zwischenstand persistent in der Datenbank (`SyncJob.segments`, `SyncJob.source_audio`, etc.) sowie im Speicherverzeichnis des Jobs:

1. **Preprocessing**: Extrahierte Audiodatei (`speech.mp3`)
2. **Transkription (ASR)**: Segmente mit Zeitstempeln (`job.segments`)
3. **Übersetzung**: Übersetzter Text pro Zeile (`segment["translation"]`)
4. **Sprachsynthese (TTS)**: Synthetisierte und zeitlich angepasste WAV-Dateien pro Zeile (`segments/{index}.wav`, `segment["fitted"]`)
5. **Mischung & Muxing**: Finale gemuffte MP4-Datei (`output.mp4`)
6. **Qualitätsprüfung (QA)**: Automatisierter QA-Report (`job.qa_report`)

### Was passiert bei Quota-Erschöpfung?
Wenn beim Gemini Free Tier das Tageslimit (10 TTS-Aufrufe/Tag) oder die Rate-Limits (3 RPM) erreicht werden:
- Ein Aufruf wirft `QuotaExceeded` (Spezialisierung von `ProviderError`).
- Alle bis zu diesem Zeitpunkt fertiggestellten Zeilen werden mit `_save_segments` in der Datenbank und auf der Festplatte gesichert.
- Der Job geht in den Status **`JobStatus.TTS_GENERATION`** (`tts_generation`), anstatt auf `FAILED` zu springen.
- `job.errors` enthält den Hinweis auf das Quota-Limit und das Datum des Resets.
- **Kein Datenverlust:** Bereits synthetisierte Zeilen sowie ASR und Übersetzung müssen am nächsten Tag **nicht** neu bezahlt oder neu berechnet werden!

---

## 2. Gemini-Konfiguration & Free-Tier-Simulation

In der `.env`-Datei oder als Umgebungsvariablen:

```bash
# Echter Gemini-Modus
PROVIDER_MODE=gemini
GEMINI_API_KEY=AIzaSy...              # oder Datei ~/.secrets/gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
GEMINI_TTS_VOICE=Kore

# Free-Tier Simulation & Tests (ohne API-Kosten)
# 0 = unbegrenzt; >0 = simuliert das tägliche TTS-Limit (z.B. 10/Tag)
GEMINI_MOCK_TTS_LIMIT=10
```

### Automatischer Tagesreset im Mock-Modus
`MockGeminiTTS` zählt die Aufrufe gruppiert nach UTC-Datum (`YYYY-MM-DD`). Sobald der Kalendertag wechselt (00:00 UTC), steht das Kontingent von 10 Aufrufen automatisch wieder zur Verfügung.

Im Test- oder Wartungsbetrieb kann das Kontingent programmatisch zurückgesetzt werden:
```python
from apps.services.providers import MockGeminiTTS
MockGeminiTTS.reset()
```

---

## 3. Wiederaufnahme von Jobs (2 Wege)

Sobald das Kontingent wieder zur Verfügung steht (am Folgetag oder nach Upgrade), kann ein pausierter Job auf zwei Arten wieder aufgenommen werden:

### Weg A: Automatisch via Hintergrund-Worker (Empfohlen)

Series Sync bietet einen dedizierten Worker (`apps.services.worker`), der periodisch nach Jobs im Status `tts_generation` oder `uploaded` sucht, die nicht gerade aktiv verarbeitet werden:

#### Option 1: Integriert in den FastAPI-Server
In `.env` aktivieren:
```bash
WORKER_ENABLED=true
WORKER_POLL_INTERVAL=30.0   # Prüfintervall in Sekunden
```
Beim Start der API (`uvicorn apps.api.main:app`) läuft der Worker automatisch im Hintergrund als asyncio-Task.

#### Option 2: Als eigenständiger CLI-Dienst oder Systemd-Service
Für Produktionsumgebungen mit separatem Worker-Container:
```bash
# Kontinuierlicher Worker
python -m apps.worker --interval 30

# Einmaliger Durchlauf (z.B. für Cronjob um 00:05 UTC)
python -m apps.worker --once
```

Beispiel für Cronjob (`crontab -e`):
```cron
# Jeden Tag um 00:05 UTC pausierte Jobs wieder anstoßen
5 0 * * * cd /home/administrator/series-sync && /home/administrator/series-sync/.venv/bin/python -m apps.worker --once >> /var/log/seriessync-worker.log 2>&1
```

### Weg B: Manuell über die API (`POST /jobs/{id}/render`)

Ein autorisierter Benutzer oder Tenant-Admin kann den Job jederzeit über den Endpunkt `/render` manuell wieder aufnehmen:

```bash
curl -X POST "https://api.example.com/jobs/<JOB_UUID>/render" \
     -H "Authorization: Bearer <TOKEN>"
```

Der Endpunkt prüft, ob der Job aktiv läuft (`is_running`). Wenn der Job aufgrund von QuotaExceeded pausiert war, wird er unmittelbar erneut in die Pipeline eingereiht und ab der ersten fehlenden Zeile fortgesetzt.

---

## 4. Monitoring & Diagnose

### Job-Status prüfen
```bash
curl -X GET "https://api.example.com/jobs/<JOB_UUID>" \
     -H "Authorization: Bearer <TOKEN>"
```

Beispiel-Rückgabe bei Quota-Pause:
```json
{
  "id": "c1f7b9e0-...",
  "status": "tts_generation",
  "errors": [
    "Gemini TTS daily quota limit (10/day) exceeded for 2026-11-14. Resumable tomorrow when the daily free-tier quota resets."
  ],
  "segments": [ ... ]
}
```

### Fortschritt der Zeilen einsehen
```bash
curl -X GET "https://api.example.com/jobs/<JOB_UUID>/segments" \
     -H "Authorization: Bearer <TOKEN>"
```
Zeigt alle Zeilen inklusive Übersetzung, Start-/Endzeit und Sprecher an.

---

## 5. Kostenkontrolle & Sicherheit
- **Keine unbeabsichtigten Kosten:** Mit `GEMINI_MOCK_TTS_LIMIT` und `PROVIDER_MODE=gemini` können Tests und lokale Pipelines komplett kostenlos gefahren werden.
- **Tenant-Isolierung & RLS:** Der Worker respektiert das Row Level Security (RLS) Schema von PostgreSQL. Alle Pipeline-Aktionen laufen strikt im Mandantenkontext (`app.current_tenant`).
