'use strict';

/* Aster chat window — zero-dependency front-end.
 * Sends feature requests to the repo as GitHub issues labeled
 * "agent-request"; the Self-Improve workflow picks them up.
 * Reads the agent journal + open issues for the "recent improvements" feed.
 */

const LS_KEY = 'aster:config';
const LABEL = 'agent-request';
const API = 'https://api.github.com';
const RAW = 'https://raw.githubusercontent.com';

const state = { config: null, timer: null };

const $ = (id) => document.getElementById(id);

/* ---------- config ---------- */

function loadConfig() {
  try { state.config = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); }
  catch { state.config = null; }
  if (!state.config || !state.config.owner || !state.config.repo) {
    // derive from the Pages URL: https://<owner>.github.io/<repo>/
    const m = location.hostname.match(/^([^.]+)\.github\.io$/);
    const repo = (location.pathname.split('/').filter(Boolean)[0] || '');
    state.config = m && repo ? { owner: m[1], repo, token: '' } : null;
  }
}

function saveConfig(owner, repo, token) {
  state.config = { owner: owner.trim(), repo: repo.trim(), token: token.trim() };
  localStorage.setItem(LS_KEY, JSON.stringify(state.config));
}

function clearConfig() {
  state.config = null;
  localStorage.removeItem(LS_KEY);
}

const canPost = () => !!state.config && !!state.config.token;
const canRead = () => !!state.config;

function setStatus(kind, text) {
  const el = $('status');
  el.textContent = text;
  el.className = 'pill ' + kind;
}

/* ---------- GitHub client ---------- */

async function gh(path, method = 'GET', token = '', payload) {
  const res = await fetch(API + path, {
    method,
    headers: {
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(token ? { Authorization: 'Bearer ' + token } : {}),
      ...(payload ? { 'Content-Type': 'application/json' } : {}),
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).message || ''; } catch { /* ignore */ }
    throw new Error('GitHub API ' + res.status + (detail ? ': ' + detail : ''));
  }
  return res.json();
}

async function ensureLabel(cfg) {
  try {
    await gh('/repos/' + cfg.owner + '/' + cfg.repo + '/labels/' + LABEL, 'GET', cfg.token);
  } catch (e) {
    if (String(e).includes('404')) {
      await gh('/repos/' + cfg.owner + '/' + cfg.repo + '/labels', 'POST', cfg.token,
        { name: LABEL, color: 'a36bff', description: 'Feature/fix requests filed via the Aster chat window' });
    } else {
      throw e;
    }
  }
}

/* ---------- chat ---------- */

function addMessage(kind, text) {
  const el = document.createElement('div');
  el.className = 'msg ' + kind;
  const who = document.createElement('span');
  who.className = 'who';
  who.textContent = kind === 'user' ? 'You' : (kind === 'sys' ? 'notice' : 'Aster');
  el.appendChild(who);
  el.appendChild(document.createTextNode(text));
  $('messages').appendChild(el);
  el.scrollIntoView({ block: 'nearest' });
  return el;
}

function typing(el, text) {
  return new Promise((resolve) => {
    let i = 0;
    const t = setInterval(() => {
      el.lastChild.textContent = text.slice(0, ++i);
      if (i >= text.length) { clearInterval(t); resolve(); }
    }, 6);
  });
}

async function sendRequest() {
  const input = $('input');
  const text = input.value.trim();
  if (!text) return;
  if (!canPost()) {
    addMessage('sys', 'Set your GitHub PAT in ⚙ Settings first (scope: issues:write).');
    return;
  }
  input.value = '';
  addMessage('user', text);
  const cfg = state.config;
  const busy = $('send');
  busy.disabled = true;
  busy.textContent = 'Filing…';
  const pending = addMessage('bot', '');
  try {
    await typing(pending, 'Turning your request into an issue…');
    await ensureLabel(cfg);
    const title = 'Feature request: ' + text.replace(/\s+/g, ' ').trim().slice(0, 70);
    const body = [
      text.trim(),
      '',
      '---',
      '_Filed automatically from the Aster chat window._',
      '',
      '**Requested behavior:** ' + text.trim().split('\n')[0],
      '**Acceptance criteria:** (describe how you will know this is done)',
    ].join('\n');
    const issue = await gh('/repos/' + cfg.owner + '/' + cfg.repo + '/issues', 'POST', cfg.token,
      { title, body, labels: [LABEL] });
    pending.lastChild.textContent = 'Filed as issue #' + issue.number + '. The agent will pick it up shortly — watch the journal.';
    const link = document.createElement('a');
    link.href = issue.html_url;
    link.target = '_blank';
    link.textContent = 'Open issue #' + issue.number;
    pending.appendChild(document.createTextNode(' '));
    pending.appendChild(link);
    setStatus('ok', 'request filed');
    refresh();
  } catch (e) {
    pending.lastChild.textContent = '⚠ ' + e.message;
    pending.className = 'msg sys';
    setStatus('err', 'api error');
  } finally {
    busy.disabled = false;
    busy.textContent = 'Send';
  }
}

/* ---------- journal + issues feed ---------- */

function mdLite(src) {
  return src
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^### (.*)$/gm, '<h4>$1</h4>')
    .replace(/^## (.*)$/gm, '<h3>$1</h3>')
    .replace(/^# (.*)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^- (.*)$/gm, '<li>$1</li>')
    .replace(/\n/g, '<br>');
}

async function loadJournal() {
  if (!canRead()) return;
  const cfg = state.config;
  try {
    const res = await fetch(RAW + '/' + cfg.owner + '/' + cfg.repo + '/main/AGENT_JOURNAL.md');
    if (!res.ok) throw new Error('journal fetch ' + res.status);
    $('journal').innerHTML = mdLite(await res.text());
  } catch (e) {
    $('journal').innerHTML = '<p class="dim">Journal unavailable (' + e.message + '). It appears after the first agent run.</p>';
  }
}

async function loadIssues() {
  if (!canRead()) return;
  const cfg = state.config;
  try {
    const issues = await gh('/repos/' + cfg.owner + '/' + cfg.repo + '/issues?labels=' + LABEL +
      '&state=all&sort=updated&direction=desc&per_page=5', 'GET', cfg.token);
    let html = '';
    if (!issues.length) {
      html = '<p class="dim">No requests yet — be the first.</p>';
    } else {
      html = '<ul style="margin:0;padding-left:16px">';
      for (const it of issues.slice(0, 5)) {
        const stateMark = it.state === 'open' ? '🟣' : '✅';
        html += '<li style="margin-bottom:6px">' + stateMark + ' <a href="' + it.html_url +
          '" target="_blank" style="color:var(--accent2)">#' + it.number + ' ' +
          it.title.replace(/</g, '&lt;') + '</a><br><span class="dim">' +
          new Date(it.updated_at).toLocaleString() + '</span></li>';
      }
      html += '</ul>';
    }
    const el = document.getElementById('recent');
    if (el) el.innerHTML = html;
  } catch (e) {
    setStatus('err', 'api error');
  }
}

function refresh() {
  loadJournal();
  loadIssues();
}

/* ---------- settings modal ---------- */

function openModal() {
  const cfg = state.config || {};
  $('cfgOwner').value = cfg.owner || '';
  $('cfgRepo').value = cfg.repo || '';
  $('cfgToken').value = cfg.token || '';
  $('cfgError').classList.add('hidden');
  $('modal').classList.remove('hidden');
}

function closeModal() { $('modal').classList.add('hidden'); }

$('settingsBtn').addEventListener('click', openModal);
$('cfgClose').addEventListener('click', closeModal);

$('cfgSave').addEventListener('click', () => {
  const owner = $('cfgOwner').value;
  const repo = $('cfgRepo').value;
  const token = $('cfgToken').value;
  if (!owner || !repo) {
    $('cfgError').textContent = 'Owner and repository are required.';
    $('cfgError').classList.remove('hidden');
    return;
  }
  saveConfig(owner, repo, token);
  closeModal();
  setStatus(canPost() ? 'ready' : 'dim', canPost() ? 'ready to file' : 'read-only');
  refresh();
  addMessage('bot', 'Connected to ' + owner + '/' + repo +
    (canPost() ? '. I can file requests now.' : ' (no token — read-only)'));
});

$('cfgClear').addEventListener('click', () => {
  clearConfig();
  $('cfgToken').value = '';
  closeModal();
  setStatus('dim', 'offline');
  addMessage('sys', 'Token cleared from this browser.');
});

$('composer').addEventListener('submit', (e) => { e.preventDefault(); sendRequest(); });

$('input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendRequest(); }
});

/* ---------- boot ---------- */

function boot() {
  loadConfig();
  if (canRead()) {
    setStatus(canPost() ? 'ready' : 'dim', canPost() ? 'ready to file' : 'read-only');
    addMessage('bot', 'Hi. I\'m Aster — the agent living inside ' + state.config.owner + '/' + state.config.repo +
      '. Ask me to improve the repo and I\'ll file it as an issue, then do the work and report back here.');
  } else {
    setStatus('dim', 'not configured');
    addMessage('bot', 'Hi. I\'m Aster — the agent living inside this repository. ' +
      'I read my soul (SOUL.md), edit my own code, run the tests, commit, and re-publish myself.\n\n' +
      'To point me at a repo: ⚙ Settings → owner, repository, and a GitHub PAT (issues:write).');
  }
  refresh();
  state.timer = setInterval(refresh, 30000);
}

boot();
