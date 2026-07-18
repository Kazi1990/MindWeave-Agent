/**
 * MindWeave - Multi-Agent Decision System
 * Track 3: Agent Society
 *
 * This file talks ONLY to our own FastAPI backend (/api/chat, /api/memory/:id).
 * It never calls Qwen directly and never stores memory in localStorage --
 * that logic lives in main.py (Sriti -> Buddhi -> Hriday -> Debate -> Mat ->
 * Sriti Memory Feedback, all on Alibaba Cloud ECS + OSS). Every value shown
 * here (confidence, opinions, memory) comes straight from the backend's
 * JSON response, never guessed or regex-parsed on the frontend.
 */

const CONFIG = {
    API_BASE: '', // same-origin: FastAPI serves this file, so relative paths work
    DEFAULT_USER_ID: 'user_' + Date.now()
};

let state = {
    userId: localStorage.getItem('mw_userId') || CONFIG.DEFAULT_USER_ID,
    language: localStorage.getItem('mw_language') || 'en',
    sessionId: 'session_' + Date.now(),
    isProcessing: false,
    memoryCount: 0
};

// Agent proper names (Sriti/Buddhi/Hriday/Mat) never translate -- only their
// role words and every other static UI string switch with the language.
const AGENT_META = {
    sriti:  { color: '#2E7D8C' },
    buddhi: { color: '#2F6FB0' },
    hriday: { color: '#C2416B' },
    mat:    { color: '#2E8B57' }
};

const I18N = {
    en: {
        tagline: 'Track 3: Agent Society - Your Personal Decision Team',
        role_sriti: 'Memory', role_buddhi: 'Logic', role_hriday: 'Emotion', role_mat: 'Coordinator',
        agent_label_sriti: '📚 Sriti (Memory)',
        agent_label_buddhi: '🧠 Buddhi (Logic)',
        agent_label_hriday: '💝 Hriday (Emotion)',
        agent_label_mat: '⚖️ Mat (Coordinator)',
        welcomeTitle: 'Welcome to MindWeave',
        welcomeText1: 'I am your personal decision team. Share your thoughts, dilemmas, or decisions.',
        welcomeText2: 'My agents will remember, analyze, and help you decide.',
        quick1_label: 'Difficult Decision', quick1_msg: 'I need to make a difficult decision',
        quick2_label: 'Analyze Situation', quick2_msg: 'Help me analyze a situation',
        quick3_label: 'Recall Past', quick3_msg: 'What did I decide before?',
        inputPlaceholder: 'Share your thoughts, dilemma, or question...',
        sessionPrefix: 'Session: ', memoriesPrefix: 'Memories: ',
        settingsTitle: 'Settings', labelUserId: 'User ID', labelLanguage: 'Language',
        userIdPlaceholder: 'Enter your user ID',
        saveBtn: 'Save', closeBtn: 'Close',
        settingsSaved: 'Settings saved',
        negotiationTitle: 'Agent Negotiation', disagreements: 'Disagreements:', error: 'Error',
        relevantMemories: 'Relevant Memories'
    },
    bn: {
        tagline: 'ট্র্যাক ৩: এজেন্ট সোসাইটি - আপনার ব্যক্তিগত সিদ্ধান্ত দল',
        role_sriti: 'স্মৃতি', role_buddhi: 'যুক্তি', role_hriday: 'আবেগ', role_mat: 'সমন্বয়কারী',
        agent_label_sriti: '📚 স্মৃতি (Sriti)',
        agent_label_buddhi: '🧠 যুক্তি (Buddhi)',
        agent_label_hriday: '💝 আবেগ (Hriday)',
        agent_label_mat: '⚖️ সমন্বয়কারী (Mat)',
        welcomeTitle: 'মাইন্ডউইভে স্বাগতম',
        welcomeText1: 'আমি আপনার ব্যক্তিগত সিদ্ধান্ত দল। আপনার চিন্তা, দ্বিধা বা সিদ্ধান্ত শেয়ার করুন।',
        welcomeText2: 'আমার এজেন্টরা মনে রাখবে, বিশ্লেষণ করবে এবং সিদ্ধান্ত নিতে সাহায্য করবে।',
        quick1_label: 'কঠিন সিদ্ধান্ত', quick1_msg: 'আমার একটা কঠিন সিদ্ধান্ত নিতে হবে',
        quick2_label: 'পরিস্থিতি বিশ্লেষণ', quick2_msg: 'আমাকে একটা পরিস্থিতি বিশ্লেষণ করতে সাহায্য করো',
        quick3_label: 'আগের সিদ্ধান্ত', quick3_msg: 'আমি আগে কী সিদ্ধান্ত নিয়েছিলাম?',
        inputPlaceholder: 'আপনার চিন্তা, দ্বিধা বা প্রশ্ন লিখুন...',
        sessionPrefix: 'সেশন: ', memoriesPrefix: 'স্মৃতি: ',
        settingsTitle: 'সেটিংস', labelUserId: 'ইউজার আইডি', labelLanguage: 'ভাষা',
        userIdPlaceholder: 'আপনার ইউজার আইডি লিখুন',
        saveBtn: 'সেভ', closeBtn: 'বন্ধ',
        settingsSaved: 'সেটিংস সেভ হয়েছে',
        negotiationTitle: 'এজেন্ট বিতর্ক', disagreements: 'মতভেদ:', error: 'ত্রুটি',
        relevantMemories: 'প্রাসঙ্গিক স্মৃতি'
    }
};

function applyLanguage() {
    const t = I18N[state.language] || I18N.en;
    document.getElementById('tagline').textContent = t.tagline;
    document.getElementById('role-sriti').textContent = t.role_sriti;
    document.getElementById('role-buddhi').textContent = t.role_buddhi;
    document.getElementById('role-hriday').textContent = t.role_hriday;
    document.getElementById('role-mat').textContent = t.role_mat;
    document.getElementById('welcomeTitle').textContent = t.welcomeTitle;
    document.getElementById('welcomeText1').textContent = t.welcomeText1;
    document.getElementById('welcomeText2').textContent = t.welcomeText2;
    document.getElementById('quick1').textContent = t.quick1_label;
    document.getElementById('quick2').textContent = t.quick2_label;
    document.getElementById('quick3').textContent = t.quick3_label;
    userInput.placeholder = t.inputPlaceholder;
    document.getElementById('settingsTitle').textContent = t.settingsTitle;
    document.getElementById('labelUserId').textContent = t.labelUserId;
    document.getElementById('labelLanguage').textContent = t.labelLanguage;
    document.getElementById('userId').placeholder = t.userIdPlaceholder;
    document.getElementById('saveBtn').textContent = t.saveBtn;
    document.getElementById('closeBtn').textContent = t.closeBtn;
    sessionInfo.textContent = `${t.sessionPrefix}${state.sessionId.slice(-6)}`;
    memoryCount.textContent = `${t.memoriesPrefix}${state.memoryCount}`;
}

function onLanguageChange() {
    // Live switch -- no need to press Save for the language itself.
    state.language = document.getElementById('language').value;
    localStorage.setItem('mw_language', state.language);
    applyLanguage();
}

const chatContainer = document.getElementById('chatContainer');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const sessionInfo = document.getElementById('sessionInfo');
const memoryCount = document.getElementById('memoryCount');

function init() {
    document.getElementById('language').value = state.language;
    applyLanguage();
    refreshMemoryCount();

    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// ==================== SETTINGS (user_id + language only -- no API key here) ====================
function openSettings() {
    document.getElementById('settingsModal').classList.add('active');
    document.getElementById('userId').value = state.userId;
    document.getElementById('language').value = state.language;
}

function closeSettings() {
    document.getElementById('settingsModal').classList.remove('active');
}

function saveSettings() {
    state.userId = document.getElementById('userId').value.trim() || CONFIG.DEFAULT_USER_ID;
    localStorage.setItem('mw_userId', state.userId);
    // language is already applied live by onLanguageChange(); this just persists userId.

    closeSettings();
    showToast(I18N[state.language].settingsSaved);
    refreshMemoryCount();
}

// ==================== BACKEND CALLS (the only source of truth) ====================
async function callBackendChat(message) {
    const resp = await fetch(`${CONFIG.API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: message,
            user_id: state.userId,
            session_id: state.sessionId,
            language: state.language
        })
    });

    if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try {
            const err = await resp.json();
            detail = err.detail || detail;
        } catch (_) { /* ignore parse failure, keep HTTP status */ }
        throw new Error(detail);
    }

    return resp.json(); // ChatResponse shape from main.py, used as-is
}

async function refreshMemoryCount() {
    try {
        const resp = await fetch(`${CONFIG.API_BASE}/api/memory/${encodeURIComponent(state.userId)}`);
        if (!resp.ok) return;
        const data = await resp.json();
        state.memoryCount = data.count || 0;
        memoryCount.textContent = `Memories: ${state.memoryCount}`;
    } catch (_) {
        // network hiccup on a background refresh is not worth alarming the user about
    }
}

// ==================== RENDERING (all values below are read verbatim from the backend) ====================
function addUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message message-user';
    div.textContent = text;
    chatContainer.appendChild(div);
    scrollToBottom();
}

function addAgentMessage(agentKey, contentObj, confidence) {
    const meta = AGENT_META[agentKey];
    const label = I18N[state.language][`agent_label_${agentKey}`];
    const div = document.createElement('div');
    div.className = `message message-${agentKey}`;

    const bodyText = formatAgentContent(agentKey, contentObj);
    const confBadge = (confidence === null || confidence === undefined)
        ? ''
        : `<span class="confidence-badge" style="border-color:${meta.color}">${confidence}%</span>`;

    div.innerHTML = `
        <div class="agent-label" style="color:${meta.color}">${label} ${confBadge}</div>
        <div>${bodyText}</div>
    `;
    chatContainer.appendChild(div);
    scrollToBottom();
}

function formatAgentContent(agentKey, c) {
    // Renders the exact structured fields main.py returns for each agent --
    // nothing here is invented on the frontend.
    const esc = (s) => (s === undefined || s === null) ? '' : String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    if (agentKey === 'sriti') {
        return `${esc(c.initial_analysis)}<br><em>${esc(c.sriti_opinion)}</em>`;
    }
    if (agentKey === 'buddhi') {
        const args = (c.arguments || []).map(a => `<li>${esc(a)}</li>`).join('');
        return `${esc(c.reasoning)}${args ? `<ul>${args}</ul>` : ''}<br><em>${esc(c.buddhi_opinion)}</em>`;
    }
    if (agentKey === 'hriday') {
        return `${esc(c.emotional_analysis)} ${esc(c.ethical_analysis)}<br><em>${esc(c.hriday_opinion)}</em>`;
    }
    if (agentKey === 'mat') {
        return `<strong>${esc(c.final_answer)}</strong><br>${esc(c.reasoning_summary)}`;
    }
    return esc(JSON.stringify(c));
}

function showDebate(debateResult, buddhi, hriday) {
    if (!debateResult) return;
    const div = document.createElement('div');
    div.className = 'negotiation-box';

    const rows = [
        { agent: 'Buddhi', color: AGENT_META.buddhi.color, confidence: buddhi.confidence, opinion: buddhi.content.buddhi_opinion },
        { agent: 'Hriday', color: AGENT_META.hriday.color, confidence: hriday.confidence, opinion: hriday.content.hriday_opinion }
    ];

    const t = I18N[state.language];
    let html = `<div class="negotiation-title">⚖️ ${t.negotiationTitle}</div>`;
    rows.forEach(v => {
        const conf = (v.confidence === null || v.confidence === undefined) ? 0 : v.confidence;
        html += `
            <div class="vote-row">
                <span class="vote-name" style="color:${v.color}">${v.agent}</span>
                <div class="vote-bar-bg">
                    <div class="vote-bar-fill" style="width:${conf}%; background:${v.color}"></div>
                </div>
                <span class="vote-opinion">${(v.opinion || '').toString()}</span>
            </div>
        `;
    });

    if (debateResult.disagreements && debateResult.disagreements.length) {
        html += `<div class="debate-disagreements"><strong>${t.disagreements}</strong> ${debateResult.disagreements.join('; ')}</div>`;
    }

    div.innerHTML = html;
    chatContainer.appendChild(div);
    scrollToBottom();
}

function showMemoryTimeline(memoriesUsed) {
    if (!memoriesUsed || memoriesUsed.length === 0) return;
    const div = document.createElement('div');
    div.className = 'memory-timeline';

    const summaryField = state.language === 'bn' ? 'summary_bn' : 'summary_en';
    let html = `<div class="agent-label" style="color:${AGENT_META.sriti.color}">📚 ${I18N[state.language].relevantMemories}</div>`;

    memoriesUsed.forEach(m => {
        const date = m.created_at ? new Date(m.created_at).toLocaleDateString() : '';
        const text = m[summaryField] || m.summary_en || m.content || '';
        html += `
            <div class="memory-item">
                <span class="memory-time">${date}</span>
                <span class="memory-content">${text}</span>
            </div>
        `;
    });

    div.innerHTML = html;
    chatContainer.appendChild(div);
    scrollToBottom();
}

function showWarnings(warnings) {
    if (!warnings || warnings.length === 0) return;
    warnings.forEach(w => {
        const div = document.createElement('div');
        div.className = 'warning-banner';
        div.textContent = `⚠️ ${w}`;
        chatContainer.appendChild(div);
    });
    scrollToBottom();
}

function activateAgent(agentKey) {
    document.querySelectorAll('.agent-badge').forEach(b => b.classList.remove('active'));
    const badge = document.getElementById(agentKey + '-badge');
    if (badge) badge.classList.add('active');
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
        background: var(--primary); color: white; padding: 10px 20px;
        border-radius: 8px; z-index: 1000; animation: fadeIn 0.3s;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
}

// ==================== MAIN FLOW ====================
async function processWithAgents(userMessage) {
    state.isProcessing = true;
    sendBtn.disabled = true;
    activateAgent('sriti');

    try {
        const data = await callBackendChat(userMessage);
        // data: { sriti, buddhi, hriday, debate_result, mat, memories_used, memory_feedback, warnings }

        activateAgent('sriti');
        showMemoryTimeline(data.memories_used);
        addAgentMessage('sriti', data.sriti.content, data.sriti.confidence);

        activateAgent('buddhi');
        addAgentMessage('buddhi', data.buddhi.content, data.buddhi.confidence);

        activateAgent('hriday');
        addAgentMessage('hriday', data.hriday.content, data.hriday.confidence);

        showDebate(data.debate_result, data.buddhi, data.hriday);

        activateAgent('mat');
        addAgentMessage('mat', data.mat.content, data.mat.confidence);

        showWarnings(data.warnings);
        refreshMemoryCount();

    } catch (error) {
        console.error('Backend chat error:', error);
        const div = document.createElement('div');
        div.className = 'message message-mat';
        div.innerHTML = `<div class="agent-label" style="color:#c0392b">⚠️ ${I18N[state.language].error}</div><div>${error.message}</div>`;
        chatContainer.appendChild(div);
        scrollToBottom();
    } finally {
        state.isProcessing = false;
        sendBtn.disabled = false;
    }
}

function sendMessage() {
    const text = userInput.value.trim();
    if (!text || state.isProcessing) return;

    addUserMessage(text);
    userInput.value = '';
    processWithAgents(text);
}

function sendQuick(key) {
    const t = I18N[state.language];
    userInput.value = t[`${key}_msg`];
    sendMessage();
}

document.addEventListener('DOMContentLoaded', init);
