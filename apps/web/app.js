const API_URL = "";


const escapeHTML = (str) => {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
};

const STATUS = {uploaded: 'Wartet', preprocessing: 'Vorbereitung', transcription: 'Transkription',
    translation: 'Übersetzung', tts_generation: 'Sprachsynthese', lip_sync: 'Lip-Sync', rendering: 'Rendern',
    qa_validation: 'Qualitätsprüfung', completed: 'Fertig', hitl_review: 'Prüfung nötig', failed: 'Fehlgeschlagen',
    edited: 'Bearbeitet – neu rendern'};
const ACTIVE = ['uploaded', 'preprocessing', 'transcription', 'translation', 'tts_generation', 'lip_sync', 'rendering', 'qa_validation'];

// State
let state = {
    token: localStorage.getItem("token"),
    view: 'login', // login, register, dashboard, jobDetail, voices
    jobs: [],
    voices: [],
    currentJobId: null
};

// Utils
const setView = (view, params = {}) => {
    state.view = view;
    if (params.jobId) state.currentJobId = params.jobId;
    render();
};

const apiCall = async (endpoint, options = {}) => {
    const headers = { ...options.headers };
    if (state.token) {
        headers["Authorization"] = `Bearer ${state.token}`;
    }
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
        options.body = JSON.stringify(options.body);
        headers["Content-Type"] = "application/json";
    }
    
    const response = await fetch(`${API_URL}${endpoint}`, { ...options, headers });
    
    if (response.status === 401 && endpoint !== "/auth/token") {
        logout();
        throw new Error("Unauthorized");
    }
    
    let data;
    try {
        data = await response.json();
    } catch (e) {
        data = null;
    }
    
    if (!response.ok) {
        throw new Error((data && data.detail) || "API Error");
    }
    return data;
};

const logout = () => {
    localStorage.removeItem("token");
    state.token = null;
    setView('login');
};

// Components
const renderHeader = () => {
    if (!state.token) {
        return `
            <header>
                <h2>Series Sync</h2>
                <div>
                    <button class="secondary" onclick="window.app.setView('login')">Login</button>
                    <button onclick="window.app.setView('register')">Registrieren</button>
                </div>
            </header>
        `;
    }
    return `
        <header>
            <h2>Series Sync</h2>
            <nav style="display: flex; gap: 10px;">
                <button class="secondary" onclick="window.app.setView('dashboard')">Dashboard</button>
                <button class="secondary" onclick="window.app.setView('voices')">Stimmen</button>
                <button class="secondary" onclick="window.app.logout()">Logout</button>
            </nav>
        </header>
    `;
};

const renderLogin = () => `
    <div class="card" style="max-width: 400px; margin: 0 auto; margin-top: 50px;">
        <h3>Login</h3>
        <div id="loginError" class="error-message hidden"></div>
        <form onsubmit="window.app.handleLogin(event)">
            <label>Email</label>
            <input type="email" id="loginEmail" required>
            <label>Passwort</label>
            <input type="password" id="loginPassword" required>
            <button type="submit" style="width: 100%;">Anmelden</button>
        </form>
        <p style="text-align: center; margin-top: 15px;">
            <a href="#" onclick="window.app.setView('register'); return false;" style="color: var(--primary-color);">Neu hier? Account erstellen</a>
        </p>
    </div>
`;

const renderRegister = () => `
    <div class="card" style="max-width: 400px; margin: 0 auto; margin-top: 50px;">
        <h3>Registrieren</h3>
        <div id="registerError" class="error-message hidden"></div>
        <form onsubmit="window.app.handleRegister(event)">
            <label>Email</label>
            <input type="email" id="regEmail" required>
            <label>Passwort (min. 10 Zeichen)</label>
            <input type="password" id="regPassword" required minlength="10">
            <label>Mandanten-Name (optional)</label>
            <input type="text" id="regTenantName">
            <button type="submit" style="width: 100%;">Account erstellen</button>
        </form>
        <p style="text-align: center; margin-top: 15px;">
            <a href="#" onclick="window.app.setView('login'); return false;" style="color: var(--primary-color);">Bereits registriert? Login</a>
        </p>
    </div>
`;

const renderDashboard = () => `
    <div>
        <div id="statsContainer"></div>
        <div class="grid">
            <div class="card">
                <h3>Neuer Job</h3>
                <div id="uploadError" class="error-message hidden"></div>
                <form id="uploadForm" onsubmit="window.app.handleUpload(event)">
                    <label>Video hochladen (MP4, MOV, MKV, WebM)</label>
                    <input type="file" id="videoFile" accept=".mp4,.mov,.mkv,.webm,.m4v,.avi" required>
                    <div id="progressContainer" class="progress-container hidden">
                        <div id="progressBar" class="progress-bar"></div>
                    </div>
                    <button type="button" id="uploadBtn" onclick="window.app.uploadFile()" style="width:100%">Hochladen</button>
                    
                    <div id="jobDetailsForm" class="hidden" style="margin-top: 20px;">
                        <input type="hidden" id="uploadId">
                        <label>Titel</label>
                        <input type="text" id="jobTitle" required>
                        <label>Zielsprache</label>
                        <select id="targetLanguage">
                            <option value="de">Deutsch</option>
                            <option value="en">Englisch</option>
                            <option value="fr">Französisch</option>
                            <option value="es">Spanisch</option>
                            <option value="it">Italienisch</option>
                            <option value="tr">Türkisch</option>
                            <option value="pl">Polnisch</option>
                        </select>
                        <label>Stimme</label>
                        <select id="voiceSelect"></select>
                        <label>Hintergrund-Lautstärke (<span id="bgVolVal">0.18</span>)</label>
                        <input type="range" id="bgVol" min="0" max="1" step="0.02" value="0.18" oninput="document.getElementById('bgVolVal').textContent=this.value">
                        
                        <label class="checkbox-label" style="margin-top: 15px;">
                            <input type="checkbox" id="rightsConsent" required>
                            <span>Ich bestätige, dass ich die erforderlichen Rechte besitze, um dieses Material zu verarbeiten und zu synchronisieren.</span>
                        </label>
                        
                        <button type="submit" style="width: 100%; margin-top: 15px;">Job starten</button>
                    </div>
                </form>
            </div>
            
            <div class="card" style="grid-column: span 2;">
                <h3>Meine Jobs</h3>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>Titel</th>
                                <th>Status</th>
                                <th>Erstellt am</th>
                                <th>Aktion</th>
                            </tr>
                        </thead>
                        <tbody id="jobsTableBody">
                            <tr><td colspan="4">Lade...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
`;

const renderJobDetail = () => `
    <div>
        <button class="secondary" onclick="window.app.setView('dashboard')" style="margin-bottom: 20px;">&larr; Zurück</button>
        <div id="jobDetailContent">Lade Job Details...</div>
    </div>
`;

const renderVoices = () => `
    <div>
        <h2>Stimmen-Verwaltung</h2>
        <div class="grid">
            <div class="card">
                <h3>Standardstimme anlegen</h3>
                <form onsubmit="window.app.createStockVoice(event)">
                    <label>Stimmen-Name</label>
                    <input type="text" id="stockVoiceName" required>
                    <label>Provider ID (z.B. pNInz6obpgDQGcFmaJcg)</label>
                    <input type="text" id="stockVoiceId" required>
                    <button type="submit">Standardstimme speichern</button>
                </form>
            </div>
            
            <div class="card">
                <h3>Stimmklon hochladen</h3>
                <form onsubmit="window.app.createVoiceClone(event)">
                    <label>Stimmen-Name</label>
                    <input type="text" id="cloneName" required>
                    <label>Referenz-Audio (.wav, .mp3)</label>
                    <input type="file" id="cloneAudio" accept="audio/*" required>
                    
                    <label class="checkbox-label" style="margin-top: 15px;">
                        <input type="checkbox" id="cloneConsent" required>
                        <span>Ich bestätige das Vorliegen einer expliziten, dokumentierten Einwilligung der sprechenden Person zur Erstellung und Nutzung dieses Stimmklons.</span>
                    </label>
                    
                    <button type="submit" style="margin-top: 15px;">Stimmklon erstellen</button>
                </form>
            </div>
        </div>
        
        <div class="card" style="margin-top: 20px;">
            <h3>Meine Stimmen</h3>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Typ</th>
                        <th>Status</th>
                        <th>Aktionen</th>
                    </tr>
                </thead>
                <tbody id="voicesTableBody">
                    <tr><td colspan="4">Lade...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
`;

// Logic Handlers
window.app = {
    setView,
    logout,
    
    handleLogin: async (e) => {
        e.preventDefault();
        const errDiv = document.getElementById("loginError");
        errDiv.classList.add("hidden");
        try {
            const formData = new FormData();
            formData.append('username', document.getElementById("loginEmail").value);
            formData.append('password', document.getElementById("loginPassword").value);
            
            const res = await fetch(`${API_URL}/auth/token`, { method: "POST", body: formData });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Login fehlgeschlagen");
            
            localStorage.setItem("token", data.access_token);
            state.token = data.access_token;
            setView('dashboard');
        } catch (err) {
            errDiv.textContent = err.message;
            errDiv.classList.remove("hidden");
        }
    },
    
    handleRegister: async (e) => {
        e.preventDefault();
        const errDiv = document.getElementById("registerError");
        errDiv.classList.add("hidden");
        try {
            const body = {
                email: document.getElementById("regEmail").value,
                password: document.getElementById("regPassword").value
            };
            const tName = document.getElementById("regTenantName").value;
            if (tName) body.tenant_name = tName;
            
            await apiCall("/auth/register", { method: "POST", body });
            
            // Auto-login
            const formData = new FormData();
            formData.append('username', body.email);
            formData.append('password', body.password);
            const res = await fetch(`${API_URL}/auth/token`, { method: "POST", body: formData });
            const data = await res.json();
            localStorage.setItem("token", data.access_token);
            state.token = data.access_token;
            setView('dashboard');
        } catch (err) {
            errDiv.textContent = err.message;
            errDiv.classList.remove("hidden");
        }
    },
    
    uploadFile: async () => {
        const fileInput = document.getElementById("videoFile");
        if (!fileInput.files.length) return alert("Bitte wähle eine Datei aus");
        const file = fileInput.files[0];
        
        const errDiv = document.getElementById("uploadError");
        errDiv.classList.add("hidden");
        
        const formData = new FormData();
        formData.append("file", file);
        
        document.getElementById("progressContainer").classList.remove("hidden");
        const progressBar = document.getElementById("progressBar");
        document.getElementById("uploadBtn").disabled = true;
        
        try {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", `${API_URL}/uploads`, true);
            xhr.setRequestHeader("Authorization", `Bearer ${state.token}`);
            
            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    progressBar.style.width = percentComplete + '%';
                }
            };
            
            xhr.onload = async () => {
                if (xhr.status === 200 || xhr.status === 201) {
                    const data = JSON.parse(xhr.responseText);
                    document.getElementById("uploadId").value = data.upload_id;
                    state.formKey = crypto.randomUUID();  // one job per submitted form, even on double click
                    document.getElementById("uploadBtn").classList.add("hidden");
                    fileInput.disabled = true;
                    document.getElementById("jobDetailsForm").classList.remove("hidden");
                    
                    // Load voices
                    const voices = await apiCall("/voices");
                    const select = document.getElementById("voiceSelect");
                    select.innerHTML = `<option value="">Standardstimme (System)</option>` + voices.voices
                        .filter(v => v.consent)
                        .map(v => `<option value="${v.id}">${escapeHTML(v.speaker_name)} (${v.cloned ? 'Stimmklon' : 'Standard'})</option>`).join("");
                } else {
                    errDiv.textContent = "Upload fehlgeschlagen: " + xhr.responseText;
                    errDiv.classList.remove("hidden");
                    document.getElementById("uploadBtn").disabled = false;
                }
            };
            
            xhr.onerror = () => {
                errDiv.textContent = "Netzwerkfehler beim Upload";
                errDiv.classList.remove("hidden");
                document.getElementById("uploadBtn").disabled = false;
            };
            
            xhr.send(formData);
        } catch (err) {
            errDiv.textContent = err.message;
            errDiv.classList.remove("hidden");
            document.getElementById("uploadBtn").disabled = false;
        }
    },
    
    handleUpload: async (e) => {
        e.preventDefault();
        const uploadId = document.getElementById("uploadId").value;
        if (!uploadId) return;
        const submitBtn = e.submitter || e.target.querySelector('button[type=submit]');
        if (submitBtn) submitBtn.disabled = true;
        
        try {
            await apiCall("/jobs", {
                method: "POST",
                body: {
                    upload_id: uploadId,
                    title: document.getElementById("jobTitle").value,
                    target_language: document.getElementById("targetLanguage").value,
                    voice_profile_id: document.getElementById("voiceSelect").value || null,
                    background_volume: parseFloat(document.getElementById("bgVol").value),
                    rights: document.getElementById("rightsConsent").checked,
                    idempotency_key: state.formKey
                }
            });
            // Reset form
            document.getElementById("uploadForm").reset();
            document.getElementById("uploadBtn").classList.remove("hidden");
            document.getElementById("uploadBtn").disabled = false;
            document.getElementById("videoFile").disabled = false;
            document.getElementById("jobDetailsForm").classList.add("hidden");
            document.getElementById("progressContainer").classList.add("hidden");
            document.getElementById("progressBar").style.width = "0%";
            
            window.app.loadJobs();
            window.app.loadStats();
        } catch (err) {
            alert(err.message);
        } finally {
            if (submitBtn) submitBtn.disabled = false;
        }
    },
    
    loadStats: async () => {
        if (state.view !== 'dashboard') return;
        try {
            const stats = await apiCall("/stats");
            const container = document.getElementById("statsContainer");
            if (container) {
                container.innerHTML = `
                    <div class="stats-container">
                        <div class="stat-card"><h3>Gesamt</h3><div class="value">${stats.total_jobs}</div></div>
                        <div class="stat-card"><h3>In Arbeit</h3><div class="value">${stats.processing}</div></div>
                        <div class="stat-card"><h3>Review nötig</h3><div class="value" style="color: #ff9800">${stats.in_review}</div></div>
                        <div class="stat-card"><h3>Fertig</h3><div class="value" style="color: var(--secondary-color)">${stats.completed_jobs}</div></div>
                        <div class="stat-card"><h3>Minuten (Audio)</h3><div class="value">${stats.minutes_dubbed}</div></div>
                    </div>
                `;
            }
        } catch (e) { console.error("Stats error", e); }
    },
    
    loadJobs: async () => {
        if (state.view !== 'dashboard') return;
        try {
            const data = await apiCall("/jobs");
            const tbody = document.getElementById("jobsTableBody");
            if (!tbody) return;
            
            if (data.jobs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4">Keine Jobs gefunden.</td></tr>';
                return;
            }
            
            tbody.innerHTML = data.jobs.map(job => `
                <tr>
                    <td>${escapeHTML(job.title || 'Ohne Titel')}</td>
                    <td><span class="badge ${job.status}">${STATUS[job.status] || job.status}</span></td>
                    <td>${new Date(job.created_at).toLocaleString()}</td>
                    <td>
                        <button class="secondary" onclick="window.app.setView('jobDetail', {jobId: '${job.id}'})">Details</button>
                    </td>
                </tr>
            `).join("");
        } catch (e) {
            const tbody = document.getElementById("jobsTableBody");
            if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="error-message">Fehler beim Laden der Jobs</td></tr>';
        }
    },
    
    loadJobDetail: async () => {
        if (!state.currentJobId || state.view !== 'jobDetail') return;
        const container = document.getElementById("jobDetailContent");
        if (!container) return;
        
        try {
            const job = await apiCall(`/jobs/${state.currentJobId}`);
            let content = `
                <div class="card">
                    <h2>${escapeHTML(job.title || 'Ohne Titel')}</h2>
                    <p>Status: <span class="badge ${job.status}">${STATUS[job.status] || job.status}</span>
                       ${job.duration_seconds ? ` · ${(job.duration_seconds / 60).toFixed(1)} min` : ''}
                       · ${escapeHTML(job.source_language)} → ${escapeHTML(job.target_language)}</p>
                    ${job.errors && job.errors.length ? `<p class="error-message">${job.errors.map(escapeHTML).join('<br>')}</p>` : ''}
                    ${job.status === 'failed' ? `<button onclick="window.app.renderJob('${job.id}')">Erneut versuchen</button>` : ''}
                    ${ACTIVE.includes(job.status) ? `<button class="secondary" onclick="window.app.cancelJob('${job.id}')">Abbrechen</button>
                        <button class="secondary" onclick="window.app.renderJob('${job.id}')" title="Falls die Verarbeitung hängt (z. B. nach einem Neustart)">Fortsetzen</button>` : ''}
                </div>
            `;
            if (ACTIVE.includes(job.status)) {
                setTimeout(() => { if (state.view === 'jobDetail' && state.currentJobId === job.id) window.app.loadJobDetail(); }, 4000);
            }

            if (job.status === 'completed' || job.status === 'hitl_review') {
                content += `
                    <div class="card">
                        <h3>Ergebnis</h3>
                        <button onclick="window.app.downloadVideo('${job.id}')" style="margin-bottom: 15px;">Herunterladen & Ansehen</button>
                        <div id="videoContainer"></div>
                    </div>
                `;
            }
            
            if (job.qa_report && ['hitl_review', 'completed', 'edited'].includes(job.status)) {
                const qa = job.qa_report;
                content += `
                    <div class="card">
                        <h3>QA-Bericht · Qualität ${Math.round((qa.quality_score || 0) * 100)}%</h3>
                        <p>Timing ${Math.round(qa.timing_score * 100)}% · Übersetzung ${Math.round(qa.translation_accuracy_score * 100)}%
                           · Ton ${Math.round(qa.audio_quality_score * 100)}% · ${qa.lines} Zeilen, ${qa.lines_speed_adjusted} beschleunigt</p>
                        ${qa.issues.length ? `<ul>${qa.issues.map(i => `<li>${escapeHTML(i)}</li>`).join('')}</ul>` : '<p>Keine automatisch erkannten Probleme.</p>'}
                    </div>`;
            }
            if (['hitl_review', 'completed', 'edited'].includes(job.status)) {
                const flagged = (job.qa_report && job.qa_report.lines_flagged) || [];
                content += `
                    <div class="card">
                        <h3>Review & Bearbeitung</h3>
                        <div id="segmentsContainer">Lade Segmente...</div>
                        <div style="margin-top: 20px; display: flex; gap: 10px; flex-wrap: wrap;">
                            <button onclick="window.app.renderJob('${job.id}')" ${job.status === 'edited' ? '' : 'disabled title="Erst eine Zeile ändern"'}>Neu rendern</button>
                            ${job.status === 'hitl_review' ? `<button onclick="window.app.approveJob('${job.id}')" style="background-color: var(--secondary-color); color: #000;">Freigeben</button>` : ''}
                        </div>
                    </div>
                `;
                container.innerHTML = content;
                window.app.loadSegments(job.id, flagged);
            } else {
                container.innerHTML = content;
            }
        } catch (e) {
            container.innerHTML = `<div class="error-message">Fehler beim Laden des Jobs: ${e.message}</div>`;
        }
    },
    
    loadSegments: async (jobId, issueIndices) => {
        try {
            const segments = (await apiCall(`/jobs/${jobId}/segments`)).segments;
            const container = document.getElementById("segmentsContainer");

            window.currentSegments = segments; // store for editing
            
            container.innerHTML = `
                <table style="font-size: 0.9em;">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Zeit</th>
                            <th>Original</th>
                            <th>Übersetzung (Bearbeiten)</th>
                            <th>Aktion</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${segments.map((s, i) => {
                            const isProb = issueIndices.includes(i) || !s.translation || s.translation === s.text;
                            return `
                                <tr class="${isProb ? 'problematic' : ''}">
                                    <td>${i + 1}</td>
                                    <td>${s.start.toFixed(1)} - ${s.end.toFixed(1)}</td>
                                    <td>${escapeHTML(s.text)}${s.tempo > 1 ? `<br><small>Tempo ×${s.tempo}</small>` : ''}</td>
                                    <td>
                                        <textarea id="seg_${i}" rows="2" style="width:100%; font-family:inherit;">${escapeHTML(s.translation) || ''}</textarea>
                                    </td>
                                    <td>
                                        <button class="secondary" onclick="window.app.updateSegment('${jobId}', ${i})">Speichern</button>
                                    </td>
                                </tr>
                            `;
                        }).join("")}
                    </tbody>
                </table>
            `;
        } catch (e) {
            document.getElementById("segmentsContainer").innerHTML = "Fehler beim Laden der Segmente";
        }
    },
    
    updateSegment: async (jobId, index) => {
        try {
            const text = document.getElementById(`seg_${index}`).value;
            await apiCall(`/jobs/${jobId}/segments/${index}`, {
                method: "PATCH",
                body: { translation: text }
            });
            window.app.loadJobDetail();
        } catch (e) {
            alert("Fehler: " + e.message);
        }
    },
    
    renderJob: async (jobId) => {
        try {
            await apiCall(`/jobs/${jobId}/render`, { method: "POST" });
            window.app.loadJobDetail();
        } catch (e) { alert(e.message); }
    },
    
    cancelJob: async (jobId) => {
        if (!confirm("Verarbeitung abbrechen? Bereits erzeugte Zwischenergebnisse bleiben erhalten.")) return;
        try { await apiCall(`/jobs/${jobId}/cancel`, { method: "POST" }); window.app.loadJobDetail(); }
        catch (e) { alert(e.message); }
    },

    approveJob: async (jobId) => {
        try {
            await apiCall(`/jobs/${jobId}/approve`, { method: "POST" });
            alert("Job freigegeben!");
            setView('dashboard');
        } catch (e) { alert(e.message); }
    },
    
    downloadVideo: async (jobId) => {
        const container = document.getElementById("videoContainer");
        container.innerHTML = "Lade Video...";
        try {
            const res = await fetch(`${API_URL}/jobs/${jobId}/output`, {
                headers: { "Authorization": `Bearer ${state.token}` }
            });
            if (!res.ok) throw new Error("Video nicht gefunden oder Fehler");
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            container.innerHTML = `
                <video controls src="${url}" style="max-width: 100%; max-height: 500px;"></video>
                <br>
                <a href="${url}" download="sync_output.mp4" style="color: var(--primary-color);">Download MP4</a>
            `;
        } catch (e) {
            container.innerHTML = `<span class="error-message">${e.message}</span>`;
        }
    },
    
    loadVoices: async () => {
        if (state.view !== 'voices') return;
        try {
            const data = await apiCall("/voices");
            const tbody = document.getElementById("voicesTableBody");
            if (!tbody) return;
            
            tbody.innerHTML = data.voices.length ? data.voices.map(v => `
                <tr>
                    <td>${escapeHTML(v.speaker_name)}</td>
                    <td>${v.cloned ? 'Stimmklon' : 'Standard'}</td>
                    <td>${v.consent ? 'Einwilligung liegt vor' : 'keine Einwilligung'}</td>
                    <td>
                        <button class="danger" onclick="window.app.revokeConsent('${v.id}')">${v.cloned ? 'Einwilligung widerrufen' : 'Löschen'}</button>
                    </td>
                </tr>
            `).join("") : '<tr><td colspan="4">Noch keine Stimmen.</td></tr>';
        } catch (e) {}
    },
    
    createStockVoice: async (e) => {
        e.preventDefault();
        try {
            await apiCall("/voices", {
                method: "POST",
                body: {
                    speaker_name: document.getElementById("stockVoiceName").value,
                    voice_preset: document.getElementById("stockVoiceId").value,
                    consent: true
                }
            });
            e.target.reset();
            window.app.loadVoices();
        } catch (err) { alert(err.message); }
    },
    
    createVoiceClone: async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById("cloneAudio");
        if (!fileInput.files.length) return alert("Audio fehlt");
        
        try {
            const formData = new FormData();
            formData.append("sample", fileInput.files[0]);
            formData.append("speaker_name", document.getElementById("cloneName").value);
            formData.append("consent", document.getElementById("cloneConsent").checked ? "true" : "false");
            
            await apiCall("/voices/clone", {
                method: "POST",
                body: formData, // fetch will set content-type multipart automatically
                // don't stringify body for FormData
            });
            e.target.reset();
            window.app.loadVoices();
        } catch (err) { alert(err.message); }
    },
    
    revokeConsent: async (voiceId) => {
        if (!confirm("WARNUNG: Dies löscht die Stimme, Referenzaufnahme und alle damit erzeugten Synchronfassungen unwiderruflich! Wirklich widerrufen?")) return;
        try {
            await apiCall(`/voices/${voiceId}/consent`, { method: "DELETE" });
            alert("Erfolgreich widerrufen und gelöscht.");
            window.app.loadVoices();
        } catch (e) { alert(e.message); }
    }
};

let pollInterval = null;

const render = () => {
    const appDiv = document.getElementById("app");
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    
    let content = renderHeader();
    
    if (!state.token) {
        content += state.view === 'register' ? renderRegister() : renderLogin();
    } else {
        if (state.view === 'dashboard') {
            content += renderDashboard();
            setTimeout(() => {
                window.app.loadStats();
                window.app.loadJobs();
                pollInterval = setInterval(window.app.loadJobs, 5000);
            }, 0);
        } else if (state.view === 'jobDetail') {
            content += renderJobDetail();
            setTimeout(window.app.loadJobDetail, 0);
        } else if (state.view === 'voices') {
            content += renderVoices();
            setTimeout(window.app.loadVoices, 0);
        } else {
            content += renderDashboard();
        }
    }
    
    appDiv.innerHTML = content;
};

// Init
if (!state.token) {
    state.view = 'login';
} else {
    state.view = 'dashboard';
}
render();
