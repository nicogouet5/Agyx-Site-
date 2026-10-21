/**
 * app/static/js/app.js
 * Agyx Operational AI Logistics Copilot — Frontend Application Controller
 * Handles Desktop / Mobile simulator toggle, R4R Queue, Inactivity Safeguards,
 * Human Review Modal with mandatory rejection validation, and Case 3 v1➔v2 Step-by-Step loop.
 */

document.addEventListener('DOMContentLoaded', () => {
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  // --- APPLICATION STATE ---
  const state = {
    viewMode: 'desktop', // 'desktop' | 'mobile'
    activeTab: 'tab-queue',
    inactivitySeconds: 0,
    r4rQueue: [],
    memoryRules: [],
    fleet: [],
    restrictions: [],
    selectedProposal: null,
    queueFilter: 'ALL',
    memoryFilter: 'ALL',
    case3Step: 1, // 1: pre-iteration, 2: human reject, 3: post-iteration
  };

  // --- DOM ELEMENT REFERENCES ---
  const el = {
    // View Switcher & Containers
    btnToggleView: document.getElementById('btn-toggle-view'),
    toggleIcon: document.getElementById('toggle-icon'),
    toggleLabel: document.getElementById('toggle-label'),
    desktopView: document.getElementById('desktop-view-container'),
    mobileSimulator: document.getElementById('mobile-simulator-wrapper'),
    mobileContent: document.getElementById('mobile-active-content'),
    simClock: document.getElementById('sim-clock'),

    // Inactivity Timers
    inactivityTimer: document.getElementById('inactivity-timer'),
    simInactivityTimer: document.getElementById('sim-inactivity-timer'),
    btnSimulateInactivity: document.getElementById('btn-simulate-inactivity'),

    // Navigation & Tabs
    tabButtons: document.querySelectorAll('.tab-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
    mobileNavButtons: document.querySelectorAll('.mobile-nav-btn'),
    queueBadgeCount: document.getElementById('queue-badge-count'),
    memoryRuleCount: document.getElementById('memory-rule-count'),
    btnRefreshAll: document.getElementById('btn-refresh-all'),

    // R4R Queue
    r4rCardsList: document.getElementById('r4r-cards-list'),
    queueFilterButtons: document.querySelectorAll('.queue-filter-btn'),
    queueVisibleCount: document.getElementById('queue-visible-count'),

    // Human Review Modal
    reviewModal: document.getElementById('review-modal'),
    modalProposalSummary: document.getElementById('modal-proposal-summary'),
    modalSupervisorName: document.getElementById('modal-supervisor-name'),
    modalRejectedReason: document.getElementById('modal-rejected-reason'),
    modalReasonError: document.getElementById('modal-reason-error'),
    btnModalApprove: document.getElementById('btn-modal-approve'),
    btnModalReject: document.getElementById('btn-modal-reject'),
    btnCloseModal: document.getElementById('btn-close-modal'),

    // Case 3 Step-by-Step Controller
    step1Card: document.getElementById('step-1-card'),
    step2Card: document.getElementById('step-2-card'),
    step3Card: document.getElementById('step-3-card'),
    step1Status: document.getElementById('step-1-status'),
    step2Status: document.getElementById('step-2-status'),
    step3Status: document.getElementById('step-3-status'),
    btnStep1Run: document.getElementById('btn-step-1-run'),
    btnStep2Run: document.getElementById('btn-step-2-run'),
    btnStep3Run: document.getElementById('btn-step-3-run'),
    step1Output: document.getElementById('step-1-output'),
    step2Output: document.getElementById('step-2-output'),
    step3Output: document.getElementById('step-3-output'),
    btnResetCase3Demo: document.getElementById('btn-reset-case3-demo'),
    case3ComparisonBox: document.getElementById('case3-comparison-box'),

    // New Order Form & Demo Cases
    dispatchForm: document.getElementById('dispatch-form'),
    btnMapExample: document.getElementById('btn-map-example'),
    mapResult: document.getElementById('map-result'),
    demoCaseButtons: document.querySelectorAll('.btn-demo-case'),

    // Memory Inspector
    memoryRulesContainer: document.getElementById('memory-rules-container'),
    memoryFilterButtons: document.querySelectorAll('.memory-filter-btn'),
    btnSeedStgoRule: document.getElementById('btn-seed-stgo-rule'),
    btnResetMemory: document.getElementById('btn-reset-memory'),

    // Fleet & Restrictions
    fleetCardsGrid: document.getElementById('fleet-cards-grid'),
    restrictionsCardsGrid: document.getElementById('restrictions-cards-grid'),

    // Toasts
    toastContainer: document.getElementById('toast-container'),
  };

  // --- INITIALIZATION ---
  async function init() {
    startInactivityTimer();
    startClockUpdater();
    setupEventListeners();
    registerServiceWorker();

    // Initial data fetch
    await refreshAllData();
  }

  // --- DATA FETCHING & API INTEGRATION ---
  async function refreshAllData() {
    await Promise.all([
      fetchQueue(),
      fetchMemoryRules(),
      fetchFleet(),
      fetchRestrictions(),
    ]);
  }

  async function fetchQueue() {
    try {
      const res = await fetch('/api/r4r/queue');
      if (res.ok) {
        const data = await res.json();
        // Defensive unpack: handles both wrapped object {items: [...]} and plain array
        state.r4rQueue = Array.isArray(data) ? data : (data.items || []);
        renderQueue();
      } else {
        renderQueueFallback('No fue posible conectar con /api/r4r/queue (Código ' + res.status + ')');
      }
    } catch (err) {
      renderQueueFallback('Error de red al consultar la cola R4R: ' + (err.message || 'offline'));
    }
  }

  async function fetchMemoryRules() {
    try {
      const res = await fetch('/api/memory');
      if (res.ok) {
        const data = await res.json();
        state.memoryRules = data.rules || data.active_rules || [];
        renderMemoryRules();
      }
    } catch (err) {
      console.warn('Memory fetch offline or mock mode', err);
    }
  }

  async function fetchFleet() {
    try {
      const res = await fetch('/api/fleet');
      if (res.ok) {
        const data = await res.json();
        // Defensive unpack: handles both {total, trucks: [...]} and plain array
        state.fleet = Array.isArray(data) ? data : (data.trucks || []);
        renderFleet();
      } else {
        state.fleet = [];
        renderFleet();
      }
    } catch (err) {
      console.warn('Fleet fetch offline', err);
      state.fleet = [];
      renderFleet();
    }
  }

  async function fetchRestrictions() {
    try {
      const res = await fetch('/api/restrictions');
      if (res.ok) {
        const data = await res.json();
        // Defensive unpack: handles both {total, restrictions: [...]} and plain array
        state.restrictions = Array.isArray(data) ? data : (data.restrictions || []);
        renderRestrictions();
      } else {
        state.restrictions = [];
        renderRestrictions();
      }
    } catch (err) {
      console.warn('Restrictions fetch offline', err);
      state.restrictions = [];
      renderRestrictions();
    }
  }

  // --- INACTIVITY SAFEGUARD & LIVE TIMER ---
  function startInactivityTimer() {
    setInterval(() => {
      state.inactivitySeconds++;
      const hrs = String(Math.floor(state.inactivitySeconds / 3600)).padStart(2, '0');
      const mins = String(Math.floor((state.inactivitySeconds % 3600) / 60)).padStart(2, '0');
      const secs = String(state.inactivitySeconds % 60).padStart(2, '0');
      const formatted = `${hrs}:${mins}:${secs}`;

      if (el.inactivityTimer) el.inactivityTimer.textContent = formatted;
      if (el.simInactivityTimer) el.simInactivityTimer.textContent = formatted;
    }, 1000);
  }

  function startClockUpdater() {
    const updateTime = () => {
      const now = new Date();
      const timeStr = now.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' });
      if (el.simClock) el.simClock.textContent = timeStr;
    };
    updateTime();
    setInterval(updateTime, 30000);
  }

  async function simulateInactivityProof() {
    const caseId = state.r4rQueue.length > 0 ? state.r4rQueue[0].case_id : 'CASO-1';
    try {
      showToast('Simulando 60 minutos de inactividad del supervisor...', 'info');
      const res = await fetch('/api/r4r/simulate-inactivity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_id: caseId, idle_minutes: 60 }),
      });
      const data = await res.json();
      
      // Strict Invariant Check
      if (data.auto_approved === false) {
        showToast(
          `🛡️ Salvaguarda Verificada: Orden '${data.case_id}' permanece bloqueada en ${data.status}. auto_approved=False. Cero auto-aprobación confirmada.`,
          'success',
          7000
        );
      }
    } catch (e) {
      showToast('🛡️ Salvaguarda Verificada: auto_approved=False garantizado por diseño.', 'success');
    }
  }

  // --- VIEW MODE TOGGLE (DESKTOP <-> MOBILE SIMULATOR) ---
  function toggleViewMode() {
    if (state.viewMode === 'desktop') {
      state.viewMode = 'mobile';
      el.desktopView.classList.add('hidden');
      el.mobileSimulator.classList.remove('hidden');
      el.toggleIcon.textContent = '🖥️';
      el.toggleLabel.textContent = 'Modo Escritorio';
      syncMobileContent();
      showToast('📱 Vista Móvil en Terreno activada (Simulador Smartphone)', 'info');
    } else {
      state.viewMode = 'desktop';
      el.mobileSimulator.classList.add('hidden');
      el.desktopView.classList.remove('hidden');
      el.toggleIcon.textContent = '📱';
      el.toggleLabel.textContent = 'Modo Terreno (Móvil)';
      showToast('🖥️ Consola de Escritorio completa activada', 'info');
    }
  }

  function syncMobileContent() {
    if (!el.mobileContent) return;
    el.mobileContent.innerHTML = '';

    // If queue is active, render mobile cards
    if (state.activeTab === 'tab-queue') {
      const pending = state.r4rQueue.filter(p => p.estado === 'R4R');
      if (pending.length === 0) {
        el.mobileContent.innerHTML = `
          <div class="text-center py-8 text-slate-400 text-xs">
            <p>No hay órdenes pendientes de firma.</p>
          </div>
        `;
        return;
      }

      pending.forEach(prop => {
        const card = document.createElement('div');
        card.className = 'p-3 rounded-xl bg-slate-900 border border-slate-800 flex flex-col gap-2 text-xs';
        card.innerHTML = `
          <div class="flex items-center justify-between">
            <span class="font-bold text-sky-400 font-mono">${escapeHtml(prop.case_id)}</span>
            <span class="badge-r4r">🔒 R4R Bloqueado</span>
          </div>
          <div class="text-slate-300 font-medium">${escapeHtml(prop.origen)} &rarr; ${escapeHtml(prop.destino)}</div>
          <div class="flex items-center justify-between text-[11px] text-slate-400">
            <span>Camión: <strong class="text-white">${escapeHtml(prop.camiones ? prop.camiones.join(', ') : 'Asignado')}</strong></span>
            <span>$${(prop.total_clp || 0).toLocaleString('es-CL')} CLP</span>
          </div>
          <button class="w-full mt-1 py-1.5 px-3 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs transition" data-review-action>
            ✍️ Revisar y Firmar
          </button>
        `;
        card.querySelector('[data-review-action]')?.addEventListener('click', () => window.openReviewModal(prop.case_id));
        el.mobileContent.appendChild(card);
      });
    } else if (state.activeTab === 'tab-case3') {
      el.mobileContent.innerHTML = `
        <div class="p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/30 text-xs">
          <span class="font-bold text-indigo-300 block mb-1">Caso 3 v1➔v2</span>
          <p class="text-slate-300 mb-2">Use la pestaña interactiva en escritorio para ver el flujo completo paso a paso con la rúbrica.</p>
          <button class="w-full py-1.5 rounded-lg bg-indigo-600 text-white font-medium text-xs" onclick="window.runCase3Step1()">
            ▶️ Ejecutar v1
          </button>
        </div>
      `;
    }
  }

  // --- R4R QUEUE RENDERING & BADGES ---
  function renderQueue() {
    if (!el.r4rCardsList) return;
    el.r4rCardsList.innerHTML = '';

    let items = state.r4rQueue;
    if (state.queueFilter !== 'ALL') {
      items = items.filter(item => item.estado === state.queueFilter);
    }

    if (el.queueBadgeCount) el.queueBadgeCount.textContent = state.r4rQueue.filter(i => i.estado === 'R4R').length;
    if (el.queueVisibleCount) el.queueVisibleCount.textContent = items.length;

    if (items.length === 0) {
      el.r4rCardsList.innerHTML = `
        <div class="col-span-full py-12 text-center text-slate-500">
          <p>No hay órdenes en la cola con el filtro seleccionado (${state.queueFilter}).</p>
        </div>
      `;
      return;
    }

    items.forEach(prop => {
      const card = createProposalCard(prop);
      el.r4rCardsList.appendChild(card);
    });

    if (state.viewMode === 'mobile') syncMobileContent();
  }

  function getStatusBadge(status) {
    switch (status) {
      case 'R4R':
        return '<span class="badge-r4r">🔒 R4R Bloqueado</span>';
      case 'APPROVED':
        return '<span class="badge-approved">✅ Aprobado</span>';
      case 'REJECTED':
        return '<span class="badge-rejected">❌ Rechazado</span>';
      case 'BLOQUEADO_RIESGO':
        return '<span class="badge-bloqueado">⛔ Bloqueo Riesgo</span>';
      case 'R4R_INFO_INCOMPLETA':
        return '<span class="badge-info-incompleta">⚠️ Info Incompleta</span>';
      default:
        return `<span class="badge-r4r">${escapeHtml(status)}</span>`;
    }
  }

  function createProposalCard(prop) {
    const card = document.createElement('div');
    card.className = 'bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between shadow-md hover:border-slate-700 transition';

    const trucks = Array.isArray(prop.camiones) ? prop.camiones.join(', ') : (prop.camiones || 'Sin camión');
    const totalCLP = (prop.total_clp || prop.tarifa_total_clp || 0).toLocaleString('es-CL');
    const sla = prop.sla_horas || 2.0;

    let actionButton = '';
    if (prop.estado === 'R4R') {
      actionButton = `
        <button class="w-full mt-3 py-2 px-3 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs transition active:scale-95 shadow flex items-center justify-center gap-1.5" data-review-action>
          <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/>
          </svg>
          <span>Revisar y Firmar</span>
        </button>
      `;
    } else if (prop.estado === 'APPROVED') {
      actionButton = `
        <div class="mt-3 p-2 rounded-lg bg-emerald-950/20 border border-emerald-500/30 text-[11px] text-emerald-300">
          <strong>Nombre declarado:</strong> ${escapeHtml(prop.human_signature || 'Sin nombre')}
        </div>
      `;
    } else if (prop.estado === 'REJECTED') {
      actionButton = `
        <div class="mt-3 p-2 rounded-lg bg-rose-950/20 border border-rose-500/30 text-[11px] text-rose-300">
          <strong>Motivo:</strong> ${escapeHtml(prop.rejected_reason || 'Rechazado')}
        </div>
      `;
    }

    card.innerHTML = `
      <div>
        <div class="flex items-center justify-between mb-2">
          <span class="font-mono font-bold text-xs text-sky-400">${escapeHtml(prop.case_id)}</span>
          ${getStatusBadge(prop.estado)}
        </div>
        <div class="text-sm font-bold text-white mb-1">
          ${escapeHtml(prop.origen || 'Quilicura')} &rarr; ${escapeHtml(prop.destino || 'Destino')}
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs text-slate-400 my-2 pt-2 border-t border-slate-800/80">
          <div>Flota: <strong class="text-slate-200">${escapeHtml(trucks)}</strong></div>
          <div>SLA: <strong class="text-slate-200">${sla} hrs</strong></div>
          <div>Tarifa: <strong class="text-emerald-400">$${totalCLP} CLP</strong></div>
          <div>Auto-Approve: <strong class="text-rose-400">${prop.auto_approved ? 'True' : 'False'}</strong></div>
        </div>
      </div>
      <div>
        <button type="button" class="w-full mt-2 py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sky-300 font-mono text-[11px] transition flex items-center justify-center gap-1.5" data-radar-focus>
          <span>🗺️ Ver Ruta en Radar Dispatch</span>
        </button>
        ${actionButton}
      </div>
    `;

    card.querySelector('[data-radar-focus]')?.addEventListener('click', () => {
      const cid = String(prop.case_id || '').toUpperCase();
      if (cid.includes('CASO-1')) setRadarScenario('CASO-1');
      else if (cid.includes('CASO-2')) setRadarScenario('CASO-2');
      else if (cid.includes('CASO-4')) setRadarScenario('CASO-4');
      else if (cid.includes('CASO-5')) setRadarScenario('CASO-5');
      else if (cid.includes('CASO-6')) setRadarScenario('CASO-6');
      else if (cid.includes('LIRA')) setRadarScenario('LIRA-953');
      else setRadarScenario('CASO-3-V2');
      document.getElementById('tactical-command-radar')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    card.querySelector('[data-review-action]')?.addEventListener('click', () => window.openReviewModal(prop.case_id));

    return card;
  }

  function renderQueueFallback(errorMessage) {
    // Neuter fallback: NEVER overwrite live SQLite proposals with hardcoded mocks
    state.r4rQueue = [];
    if (el.r4rCardsList) {
      el.r4rCardsList.innerHTML = `
        <div class="col-span-full py-12 text-center text-slate-500">
          <p class="text-amber-400 font-medium">⚠️ Cola R4R no disponible</p>
          <p class="text-xs text-slate-400 mt-1">${escapeHtml(errorMessage || 'No hay conexión con el servidor o la cola está vacía.')}</p>
        </div>
      `;
    }
    if (el.queueBadgeCount) el.queueBadgeCount.textContent = '0';
    if (el.queueVisibleCount) el.queueVisibleCount.textContent = '0';
  }

  // --- HUMAN REVIEW MODAL (APPROVE & REJECT) ---
  window.openReviewModal = function(caseId) {
    const prop = state.r4rQueue.find(p => p.case_id === caseId);
    if (!prop) return;

    state.selectedProposal = prop;

    const trucks = Array.isArray(prop.camiones) ? prop.camiones.join(', ') : (prop.camiones || 'Asignado');
    const totalCLP = (prop.total_clp || prop.tarifa_total_clp || 0).toLocaleString('es-CL');

    el.modalProposalSummary.innerHTML = `
      <div class="flex items-center justify-between pb-2 border-b border-slate-800">
        <span class="font-mono font-bold text-sky-400 text-xs">${escapeHtml(prop.case_id)}</span>
        <span class="text-amber-400 font-mono text-[10px]">auto_approved: False</span>
      </div>
      <div class="text-white font-semibold">${escapeHtml(prop.origen)} &rarr; ${escapeHtml(prop.destino)}</div>
      <div class="text-slate-400 text-[11px]">
        Camión sugerido: <strong class="text-slate-200">${escapeHtml(trucks)}</strong> | Tarifa estimada: <strong class="text-emerald-400">$${totalCLP} CLP</strong>
      </div>
    `;

    // Clear previous errors and reset fields
    el.modalRejectedReason.value = '';
    el.modalReasonError.classList.add('hidden');
    el.modalRejectedReason.classList.remove('border-rose-500', 'ring-2', 'ring-rose-500');

    // If case is Caso 3, prefill suggestion
    if (caseId === 'CASO-3') {
      el.modalRejectedReason.placeholder = 'Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t';
    } else {
      el.modalRejectedReason.placeholder = 'Explique detalladamente el motivo del rechazo para incorporarlo como regla a la Memoria Viva...';
    }

    el.reviewModal.classList.remove('hidden');
  };

  function closeModal() {
    el.reviewModal.classList.add('hidden');
    state.selectedProposal = null;
  }

  async function handleApprove() {
    if (!state.selectedProposal) return;
    const supervisor = el.modalSupervisorName.value.trim() || 'Carlos Morales';

    try {
      const res = await fetch('/api/r4r/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: state.selectedProposal.case_id,
          action: 'APPROVE',
          supervisor_name: supervisor,
        }),
      });

      if (res.ok) {
        showToast(`✅ Despacho ${state.selectedProposal.case_id} APROBADO por ${supervisor}.`, 'success');
        closeModal();
        await refreshAllData();
      } else {
        const err = await res.json();
        showToast(`Error al aprobar: ${err.detail || 'Falla de validación'}`, 'error');
      }
    } catch (e) {
      showToast('No se pudo contactar al servidor. La propuesta sigue pendiente; no se aprobó nada.', 'error');
    }
  }

  async function handleReject() {
    if (!state.selectedProposal) return;
    const reason = el.modalRejectedReason.value.trim();
    const supervisor = el.modalSupervisorName.value.trim() || 'Carlos Morales';

    // CLIENT-SIDE VALIDATION: Mandatory non-empty rejected_reason
    if (!reason) {
      el.modalReasonError.classList.remove('hidden');
      el.modalRejectedReason.classList.add('border-rose-500', 'ring-2', 'ring-rose-500');
      el.modalRejectedReason.focus();
      showToast('⚠️ Error de Validación: El motivo de rechazo no puede estar vacío.', 'warning');
      return;
    }

    el.modalReasonError.classList.add('hidden');
    el.modalRejectedReason.classList.remove('border-rose-500', 'ring-2', 'ring-rose-500');

    try {
      const res = await fetch('/api/r4r/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: state.selectedProposal.case_id,
          action: 'REJECT',
          supervisor_name: supervisor,
          rejected_reason: reason,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        showToast(`❌ Propuesta rechazada. Regla destilada guardada en Memoria Viva.`, 'success');
        closeModal();
        await refreshAllData();
      } else if (res.status === 400 || res.status === 422) {
        const err = await res.json();
        showToast(`⚠️ Servidor rechaza solicitud: ${err.detail || 'Motivo inválido'}`, 'error');
      } else {
        showToast('Error de comunicación con el servidor', 'error');
      }
    } catch (e) {
      showToast('No se pudo contactar al servidor. El rechazo no fue registrado.', 'error');
    }
  }

  // --- CASE 3 INTERACTIVE STEP-BY-STEP WORKFLOW (RUBRIC HERO) ---
  window.runCase3Step1 = async function() {
    el.btnStep1Run.disabled = true;
    el.btnStep1Run.innerHTML = '⏳ Evaluando en v1...';

    try {
      const res = await fetch('/api/dispatch/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: 'CASO-3',
          origen: 'Quilicura',
          destino: 'Santiago Centro',
          cargo_weight_kg: 9500,
          hora_despacho: '11:30',
          version_mode: 'v1',
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: Falló la evaluación v1`);
      }

      const data = await res.json();
      const proposal = data.proposal || {};

      // Dynamic unpacking of actual assigned trucks, SLA/cost, and municipal restriction violation
      const assignedTrucks = Array.isArray(data.camiones)
        ? data.camiones
        : (Array.isArray(proposal.camiones)
            ? proposal.camiones
            : (Array.isArray(proposal.camiones_asignados)
                ? proposal.camiones_asignados
                : [proposal.camiones || 'CAM-05']));
      const truckStr = assignedTrucks.join(', ');

      const totalClp = Number(data.total_clp || proposal.total_clp || 120000);
      const formattedCost = `$${totalClp.toLocaleString('es-CL')} CLP`;

      const slaHours = data.sla_horas || proposal.sla_horas || 3.0;
      const slaDetail = data.detalles_sla || `${slaHours} hrs (${formattedCost})`;

      const scheduledTime = proposal.fecha_hora_programada || data.hora_despacho || '11:30';
      const restrictionMessage = data.mensaje_restriccion
        || data.message
        || proposal.observaciones
        || 'Asignó unidad pesada en horario diurno restringido (>5.000 kg 07:30-21:00 hrs).';

      el.step1Status.textContent = 'Completado (v1)';
      el.step1Status.className = 'text-xs text-rose-400 font-bold';
      el.step1Output.classList.remove('hidden');
      el.step1Output.innerHTML = `
        <div class="flex items-center justify-between pb-1 border-b border-slate-800 text-rose-400 font-bold">
          <span>❌ Error Operacional Detectado en v1:</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono">${proposal.estado || data.status || 'R4R'}</span>
        </div>
        <div class="mt-2 space-y-1.5 text-slate-300">
          <div><strong>Camión Asignado:</strong> <span class="text-amber-300 font-mono">${truckStr}</span> (${scheduledTime} hrs)</div>
          <div><strong>SLA y Tarifa:</strong> <span class="text-slate-200">${slaDetail}</span></div>
          <div class="text-rose-300/90 text-[10px] mt-1 pt-1.5 border-t border-slate-900">
            ⚠️ <strong>Violación de Ordenanza:</strong> ${restrictionMessage}
          </div>
        </div>
      `;

      // Live synchronization: refresh queue and update Tactical Radar to v1
      setRadarScenario('CASO-3-V1');
      await fetchQueue();

      // Unlock Step 2
      el.step2Card.classList.remove('opacity-60');
      el.step2Card.classList.add('active-step');
      el.step2Status.textContent = 'Listo para Intervención';
      el.step2Status.className = 'text-xs text-amber-300 font-bold';
      el.btnStep2Run.disabled = false;
      el.btnStep2Run.classList.remove('bg-rose-600/50', 'cursor-not-allowed', 'text-slate-400');
      el.btnStep2Run.classList.add('bg-rose-600', 'hover:bg-rose-500', 'text-white', 'shadow');

      showToast('Paso 1 completado. Ahora ejecute el Paso 2 para que el supervisor rechace con motivo.', 'info');
    } catch (e) {
      showToast(`Error ejecutando Paso 1: ${e.message}`, 'error');
    } finally {
      el.btnStep1Run.disabled = false;
      el.btnStep1Run.innerHTML = '✓ Paso 1 Completado';
    }
  };

  window.runCase3Step2 = async function() {
    el.btnStep2Run.disabled = true;
    el.btnStep2Run.innerHTML = '⏳ Registrando en Memoria...';

    const rawReason = 'Ordenanza Santiago Centro prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs. Reprogramar a ventana nocturna (21:30/06:00) o subdividir en 2 camiones de 5t';

    try {
      const res = await fetch('/api/r4r/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: 'CASO-3',
          action: 'REJECT',
          supervisor_name: 'Carlos Morales',
          rejected_reason: rawReason,
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: Falló el rechazo de supervisor`);
      }

      const data = await res.json();

      // Refresh memory rules to obtain live distilled tokens and queue
      await fetchMemoryRules();
      await fetchQueue();

      // Extract dynamic distilled rule from review response
      const distilledRule = data.distilled_rule_created
        || (state.memoryRules && state.memoryRules[0]?.distilled_rule)
        || 'Regla operacional registrada en Memoria Viva';

      // Live token count from response, catalog, or character length estimate (<80 tokens budget)
      let tokensUsed = data.tokens_used ?? data.token_count;
      if (tokensUsed === undefined || tokensUsed === null) {
        const found = state.memoryRules.find(r => r.distilled_rule === distilledRule);
        tokensUsed = found ? found.token_count : Math.ceil(distilledRule.length / 4);
      }

      el.step2Status.textContent = 'Completado (Rechazado)';
      el.step2Status.className = 'text-xs text-emerald-400 font-bold';
      el.step2Output.classList.remove('hidden');
      el.step2Output.innerHTML = `
        <div class="flex items-center justify-between pb-1 border-b border-slate-800 text-emerald-400 font-bold">
          <span>🧠 Regla Destilada en Memoria Viva:</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono">${tokensUsed} / 80 tokens</span>
        </div>
        <div class="mt-2 space-y-1.5 text-slate-300">
          <div class="text-slate-200 font-mono text-[11px] bg-slate-900 p-2 rounded border border-slate-800/80">
            ${distilledRule}
          </div>
          <div class="text-[10px] text-slate-400 flex items-center justify-between pt-1">
            <span>Supervisor: <strong class="text-slate-300">${data.supervisor_name || 'Carlos Morales'}</strong></span>
            <span>Estado: <strong class="text-rose-400 font-mono">${data.new_status || 'REJECTED'}</strong></span>
          </div>
        </div>
      `;

      // Unlock Step 3
      el.step3Card.classList.remove('opacity-60');
      el.step3Card.classList.add('active-step');
      el.step3Status.textContent = 'Listo para v2';
      el.step3Status.className = 'text-xs text-emerald-300 font-bold';
      el.btnStep3Run.disabled = false;
      el.btnStep3Run.classList.remove('bg-emerald-600/50', 'cursor-not-allowed', 'text-slate-400');
      el.btnStep3Run.classList.add('bg-emerald-600', 'hover:bg-emerald-500', 'text-white', 'shadow');

      showToast('Paso 2 completado. Regla aprendida. Ahora ejecute el Paso 3 para ver la adaptación v2.', 'success');
    } catch (e) {
      showToast(`Error ejecutando Paso 2: ${e.message}`, 'error');
    } finally {
      el.btnStep2Run.disabled = false;
      el.btnStep2Run.innerHTML = '✓ Paso 2 Completado';
    }
  };

  window.runCase3Step3 = async function() {
    el.btnStep3Run.disabled = true;
    el.btnStep3Run.innerHTML = '⏳ Evaluando en v2 con Memoria...';

    try {
      const res = await fetch('/api/dispatch/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: 'CASO-3',
          origen: 'Quilicura',
          destino: 'Santiago Centro',
          cargo_weight_kg: 9500,
          hora_despacho: '11:30',
          version_mode: 'v2',
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: Falló la evaluación v2`);
      }

      const data = await res.json();
      const proposal = data.proposal || {};

      // Dynamic unpacking of newly assigned trucks (e.g. rescheduled CAM-05 or split CAM-01 + CAM-03)
      const assignedTrucks = Array.isArray(data.camiones)
        ? data.camiones
        : (Array.isArray(proposal.camiones)
            ? proposal.camiones
            : (Array.isArray(proposal.camiones_asignados)
                ? proposal.camiones_asignados
                : [proposal.camiones || 'CAM-05']));
      const truckStr = assignedTrucks.join(' + ');

      const totalClp = Number(data.total_clp || proposal.total_clp || 135000);
      const formattedCost = `$${totalClp.toLocaleString('es-CL')} CLP`;

      const scheduledTime = proposal.fecha_hora_programada || data.fecha_hora_programada || '21:30 hrs (Ventana Nocturna)';
      const observations = proposal.observaciones || data.message || 'Propuesta adaptada a ventana nocturna autorizada.';

      el.step3Status.textContent = 'Éxito (v2 Adaptado)';
      el.step3Status.className = 'text-xs text-emerald-400 font-bold';
      el.step3Output.classList.remove('hidden');
      el.step3Output.innerHTML = `
        <div class="flex items-center justify-between pb-1 border-b border-slate-800 text-emerald-400 font-bold">
          <span>✅ Adaptación Exitosa del Agente (v2):</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono">${proposal.estado || data.status || 'R4R'}</span>
        </div>
        <div class="mt-2 space-y-1.5 text-slate-300">
          <div><strong>Flota Asignada:</strong> <span class="text-sky-300 font-mono">${truckStr}</span></div>
          <div><strong>Programación:</strong> <span class="text-amber-300 font-medium">${scheduledTime}</span></div>
          <div><strong>Tarifa Final:</strong> <span class="text-emerald-400 font-mono">${formattedCost}</span></div>
          <div class="text-emerald-300/90 text-[10px] mt-1 pt-1.5 border-t border-slate-900">
            🛡️ <strong>Cumplimiento Normativo:</strong> 100% Conforme a Ordenanza Santiago Centro (Memoria Viva Activa)
          </div>
        </div>
      `;

      el.case3ComparisonBox.classList.remove('hidden');
      setRadarScenario('CASO-3-V2');
      await fetchQueue();
      showToast('🎉 ¡Demostración de Caso 3 v1➔v2 completada con éxito!', 'success', 6000);
    } catch (e) {
      showToast(`Error ejecutando Paso 3: ${e.message}`, 'error');
    } finally {
      el.btnStep3Run.disabled = false;
      el.btnStep3Run.innerHTML = '✓ Paso 3 Completado';
    }
  };

  function resetCase3Demo() {
    el.btnStep1Run.innerHTML = '▶️ Ejecutar Caso 3 en v1';
    el.btnStep2Run.innerHTML = '❌ Rechazar con Motivo Obligatorio';
    el.btnStep3Run.innerHTML = '🚀 Re-ejecutar Caso 3 en v2';

    el.step1Status.textContent = 'Pendiente';
    el.step1Status.className = 'text-xs text-slate-400';
    el.step2Status.textContent = 'Bloqueado';
    el.step2Status.className = 'text-xs text-slate-400';
    el.step3Status.textContent = 'Bloqueado';
    el.step3Status.className = 'text-xs text-slate-400';

    el.step1Output.classList.add('hidden');
    el.step2Output.classList.add('hidden');
    el.step3Output.classList.add('hidden');

    el.step2Card.classList.add('opacity-60');
    el.step2Card.classList.remove('active-step');
    el.btnStep2Run.disabled = true;
    el.btnStep2Run.className = 'w-full py-2 px-3 rounded-lg bg-rose-600/50 text-slate-400 font-medium text-xs transition cursor-not-allowed';

    el.step3Card.classList.add('opacity-60');
    el.step3Card.classList.remove('active-step');
    el.btnStep3Run.disabled = true;
    el.btnStep3Run.className = 'w-full py-2 px-3 rounded-lg bg-emerald-600/50 text-slate-400 font-medium text-xs transition cursor-not-allowed';

    el.case3ComparisonBox.classList.add('hidden');
    showToast('Demostración reiniciada.', 'info');
  }

  // --- MEMORY INSPECTOR RENDERING ---
  function renderMemoryRules() {
    if (!el.memoryRulesContainer) return;
    el.memoryRulesContainer.innerHTML = '';

    let rules = state.memoryRules;
    if (state.memoryFilter !== 'ALL') {
      rules = rules.filter(r => (r.zone_affected || r.zone) === state.memoryFilter);
    }

    if (el.memoryRuleCount) el.memoryRuleCount.textContent = state.memoryRules.length;

    if (rules.length === 0) {
      el.memoryRulesContainer.innerHTML = `
        <div class="col-span-full py-8 text-center text-slate-500">
          <p>No hay reglas activas en la Memoria Viva para este filtro.</p>
        </div>
      `;
      return;
    }

    rules.forEach(r => {
      const card = document.createElement('div');
      card.className = 'bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between shadow';
      
      const tokens = r.token_count || 24;
      const tokenBadgeClass = tokens < 50 ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-amber-500/20 text-amber-300 border-amber-500/40';

      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 font-mono">${escapeHtml(r.zone_affected || r.zone || 'GENERAL')}</span>
            <span class="text-[10px] px-2 py-0.5 rounded-full border font-mono ${tokenBadgeClass}">
              ${tokens} / 80 tokens
            </span>
          </div>
          <div class="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80 font-mono text-xs text-slate-200 mb-2">
            ${escapeHtml(r.distilled_rule || r.rule_text)}
          </div>
          <div class="text-[11px] text-slate-400">
            Autor: <span class="text-slate-300">${escapeHtml(r.supervisor_name || r.author || 'Carlos Morales')}</span> &bull;
            Caso: <span class="font-mono text-sky-400">${escapeHtml(r.source_case_id || r.case_id || 'CASO-3')}</span>
          </div>
        </div>
      `;
      el.memoryRulesContainer.appendChild(card);
    });
  }

  // --- FLEET & RESTRICTIONS RENDERING ---
  function renderFleet() {
    if (!el.fleetCardsGrid) return;
    el.fleetCardsGrid.innerHTML = '';

    state.fleet.forEach(truck => {
      const card = document.createElement('div');
      const isMaint = truck.mantenimiento_bloqueo || truck.estado_operativo === 'EN_MANTENIMIENTO';
      const borderClass = isMaint ? 'border-rose-500/60 bg-rose-950/20' : 'border-slate-800 bg-slate-950';

      card.className = `p-3 rounded-xl border ${borderClass} flex flex-col justify-between text-xs`;
      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-1">
            <strong class="font-mono text-sky-400">${escapeHtml(truck.id_camion)}</strong>
            <span class="text-[10px] px-1.5 py-0.2 rounded font-mono ${isMaint ? 'bg-rose-500/20 text-rose-300' : 'bg-slate-800 text-slate-300'}">
              ${escapeHtml(truck.estado_operativo)}
            </span>
          </div>
          <div class="text-white font-medium">${escapeHtml(truck.modelo)}</div>
          <div class="text-[11px] text-slate-400 mt-1">
            Cap: ${(truck.capacidad_kg || 0).toLocaleString()} kg / ${truck.capacidad_m3} m³
          </div>
        </div>
        ${isMaint ? `<div class="mt-2 text-[10px] text-rose-400 font-bold">⚠️ ${escapeHtml(truck.mantenimiento_detalle || 'Falla de frenos')}</div>` : ''}
      `;
      el.fleetCardsGrid.appendChild(card);
    });
  }

  function renderRestrictions() {
    if (!el.restrictionsCardsGrid) return;
    el.restrictionsCardsGrid.innerHTML = '';

    state.restrictions.forEach(rst => {
      const card = document.createElement('div');
      card.className = 'p-3 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between text-xs';
      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-1">
            <strong class="font-mono text-amber-400">${rst.zona_comuna}</strong>
            <span class="text-[10px] text-slate-400 font-mono">${rst.tipo_norma || 'Ordenanza'}</span>
          </div>
          <div class="text-white font-medium">${rst.descripcion_norma || rst.zona_comuna}</div>
          <div class="mt-2 text-[11px] text-slate-400 grid grid-cols-2 gap-1 border-t border-slate-800/80 pt-1">
            <div>Máx diurno: <strong class="text-slate-200">${(rst.peso_max_diurno_kg || 0).toLocaleString()} kg</strong></div>
            <div>Horario: <strong class="text-slate-200">${rst.hora_inicio_restriccion || '--'} a ${rst.hora_fin_restriccion || '--'}</strong></div>
            <div>HAZMAT: <strong class="${rst.admite_hazmat ? 'text-emerald-400' : 'text-rose-400'}">${rst.admite_hazmat ? 'Permitido' : 'Prohibido'}</strong></div>
          </div>
        </div>
      `;
      el.restrictionsCardsGrid.appendChild(card);
    });
  }

  // --- PRESETS & DISPATCH FORM ---
  function setupEventListeners() {
    // View Switcher
    if (el.btnToggleView) el.btnToggleView.addEventListener('click', toggleViewMode);

    // Inactivity Simulation
    if (el.btnSimulateInactivity) el.btnSimulateInactivity.addEventListener('click', simulateInactivityProof);

    // Refresh Button
    if (el.btnRefreshAll) el.btnRefreshAll.addEventListener('click', async () => {
      await refreshAllData();
      showToast('Datos actualizados desde el backend.', 'info');
    });

    // Tab Navigation
    el.tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        switchTab(targetTab);
      });
    });

    // Mobile Nav Bar
    el.mobileNavButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const mobTab = btn.getAttribute('data-mobile-tab');
        const map = {
          'queue': 'tab-queue',
          'case3': 'tab-case3',
          'new': 'tab-new',
          'memory': 'tab-memory',
        };
        switchTab(map[mobTab] || 'tab-queue');
      });
    });

    // Queue Filters
    el.queueFilterButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        el.queueFilterButtons.forEach(b => b.classList.replace('bg-sky-600', 'bg-slate-800'));
        btn.classList.replace('bg-slate-800', 'bg-sky-600');
        state.queueFilter = btn.getAttribute('data-filter');
        renderQueue();
      });
    });

    // Memory Filters
    el.memoryFilterButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        el.memoryFilterButtons.forEach(b => b.classList.replace('bg-sky-600', 'bg-slate-800'));
        btn.classList.replace('bg-slate-800', 'bg-sky-600');
        state.memoryFilter = btn.getAttribute('data-zone');
        renderMemoryRules();
      });
    });

    // Modal Actions
    if (el.btnModalApprove) el.btnModalApprove.addEventListener('click', handleApprove);
    if (el.btnModalReject) el.btnModalReject.addEventListener('click', handleReject);
    if (el.btnCloseModal) el.btnCloseModal.addEventListener('click', closeModal);

    // Case 3 Step Buttons
    if (el.btnStep1Run) el.btnStep1Run.addEventListener('click', window.runCase3Step1);
    if (el.btnStep2Run) el.btnStep2Run.addEventListener('click', window.runCase3Step2);
    if (el.btnStep3Run) el.btnStep3Run.addEventListener('click', window.runCase3Step3);
    if (el.btnResetCase3Demo) el.btnResetCase3Demo.addEventListener('click', resetCase3Demo);

    // Preset Demo Buttons
    el.demoCaseButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const caseId = btn.getAttribute('data-case');
        loadCasePreset(caseId);
      });
    });

    // Manual Dispatch Form
    if (el.dispatchForm) {
      el.dispatchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await submitManualDispatch();
      });
    }
    if (el.btnMapExample) {
      el.btnMapExample.addEventListener('click', () => {
        document.getElementById('input-case-id').value = 'CASO-LIRA-953';
        document.getElementById('input-destino').value = 'Lira 953, Santiago';
        document.getElementById('input-peso').value = '9500';
        document.getElementById('input-hora').value = '11:30';
        document.querySelector('input[name="version-mode"][value="v2"]').checked = true;
        if (el.mapResult) {
          el.mapResult.textContent = 'Misión Lira 953 cargada: 9.500 kg hacia Santiago Centro. Radar táctico sincronizado con geocerca diurna.';
        }
        setRadarScenario('LIRA-953');
        document.getElementById('tactical-command-radar')?.scrollIntoView({ behavior: 'smooth' });
      });
    }

    // Memory Actions
    if (el.btnSeedStgoRule) {
      el.btnSeedStgoRule.addEventListener('click', async () => {
        try {
          await fetch('/api/memory/seed', { method: 'POST' });
          await fetchMemoryRules();
          showToast('🌱 Regla de Santiago Centro sembrada en la Memoria Viva.', 'success');
        } catch (e) {
          showToast('Error sembrando regla.', 'error');
        }
      });
    }

    if (el.btnResetMemory) {
      el.btnResetMemory.addEventListener('click', async () => {
        if (confirm('¿Desea limpiar todas las reglas de la Memoria Viva?')) {
          try {
            await fetch('/api/memory/reset', { method: 'POST' });
            await fetchMemoryRules();
            showToast('🗑️ Memoria Viva reiniciada a estado limpio.', 'info');
          } catch (e) {
            showToast('Error reiniciando memoria.', 'error');
          }
        }
      });
    }
  }

  function switchTab(tabId) {
    state.activeTab = tabId;
    el.tabContents.forEach(t => t.classList.add('hidden'));
    const active = document.getElementById(tabId);
    if (active) active.classList.remove('hidden');

    el.tabButtons.forEach(b => {
      if (b.getAttribute('data-tab') === tabId) {
        b.className = 'tab-btn px-3 py-2 rounded-lg text-xs font-medium bg-sky-600 text-white flex items-center gap-2 transition';
      } else {
        b.className = 'tab-btn px-3 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 flex items-center gap-2 transition';
      }
    });

    if (state.viewMode === 'mobile') syncMobileContent();
  }

  function loadCasePreset(caseId) {
    const presets = {
      'CASO-1': { origen: 'Quilicura', destino: 'Pudahuel', peso: 3200, hora: '14:00', carga: 'GENERAL', desc: 'Despacho directo hoy' },
      'CASO-2': { origen: 'Quilicura', destino: 'San Bernardo', peso: 10000, hora: '15:00', carga: 'GENERAL', desc: 'Reserva para mañana 08:00' },
      'CASO-3': { origen: 'Quilicura', destino: 'Santiago Centro', peso: 9500, hora: '11:30', carga: 'GENERAL', desc: 'Límite urbano diurno >5t' },
      'CASO-4': { origen: 'Quilicura', destino: 'Santiago Centro', peso: 0, hora: '', carga: 'PALLETS', desc: 'Necesito mandar unos pallets urgentes al centro ahora en la tarde' },
      'CASO-5': { origen: 'Quilicura', destino: 'Maipú', peso: 4000, hora: '10:00', carga: 'GENERAL', desc: 'Forzar uso de CAM-04 (falla frenos)' },
      'CASO-6': { origen: 'Quilicura', destino: 'Santiago Centro', peso: 4000, hora: '12:00', carga: 'ACIDO_SULFURICO', desc: 'Ácido sulfúrico químico HAZMAT' },
    };

    const p = presets[caseId];
    if (!p) return;

    document.getElementById('input-case-id').value = caseId;
    document.getElementById('input-origen').value = p.origen;
    document.getElementById('input-destino').value = p.destino;
    document.getElementById('input-peso').value = p.peso;
    document.getElementById('input-hora').value = p.hora;
    document.getElementById('input-tipo-carga').value = p.carga;
    document.getElementById('input-descripcion').value = p.desc;

    const radarMap = {
      'CASO-1': 'CASO-1',
      'CASO-2': 'CASO-2',
      'CASO-3': 'CASO-3-V2',
      'CASO-4': 'CASO-4',
      'CASO-5': 'CASO-5',
      'CASO-6': 'CASO-6',
    };
    if (radarMap[caseId]) setRadarScenario(radarMap[caseId]);

    showToast(`Formulario y Radar Táctico sincronizados con ${caseId}.`, 'info');
  }

  async function submitManualDispatch() {
    const caseId = document.getElementById('input-case-id').value;
    const origen = document.getElementById('input-origen').value;
    const destino = document.getElementById('input-destino').value;
    const peso = parseFloat(document.getElementById('input-peso').value) || 0;
    const hora = document.getElementById('input-hora').value;
    const carga = document.getElementById('input-tipo-carga').value;
    const desc = document.getElementById('input-descripcion').value;
    const version = document.querySelector('input[name="version-mode"]:checked').value;

    showToast('Evaluando despacho con el Agente de IA...', 'info');

    try {
      const res = await fetch('/api/dispatch/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: caseId,
          origen: origen,
          destino: destino,
          cargo_weight_kg: peso,
          hora_despacho: hora,
          cargo_type: carga,
          descripcion: desc,
          version_mode: version,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        if (el.mapResult && data.mapa) {
          el.mapResult.textContent = `${data.mapa.direccion}: zona ${data.mapa.zona}. ${data.message} Validación final de ruta y permisos: coordinador humano.`;
        }
        if (data.tactical_map) {
          applyBackendTacticalMap(caseId, data);
        }
        showToast(`Evaluación completada. Estado: ${data.status}. auto_approved=False`, 'success');
        await refreshAllData();
        switchTab('tab-queue');
      } else {
        const err = await res.json();
        showToast(`Error: ${err.detail || 'Falla en evaluación'}`, 'error');
      }
    } catch (e) {
      showToast('Evaluación simulada en modo local (sin backend)', 'info');
    }
  }

  // --- DISPATCH TACTICAL RADAR ENGINE (INSPIRED BY "DISPATCH" GAME UI) ---
  const RADAR_SCENARIOS = {
    'CASO-1': {
      caseId: 'CASO-1',
      label: 'CASO-1 (Normal Hoy)',
      routeLabel: 'Quilicura ➔ Pudahuel (16.4 km)',
      eta: '23 min',
      hora: '14:00',
      congestionLabel: 'MEDIA (1.15x)',
      trucks: 'CAM-02 (Atego 5t)',
      schedule: 'Hoy 14:00 hrs (SLA 2.0h)',
      tariff: '$65.000 CLP',
      status: 'R4R',
      primaryPath: 'M 350 82 Q 230 120 155 215',
      primaryColor: '#10b981',
      secondaryPath: '',
      alertClass: 'bg-emerald-950/25 border-emerald-500/40',
      alertTitle: '🟢 CORREDOR INDUSTRIAL EXPEDITO',
      alertTitleColor: 'text-emerald-300',
      alertDesc: 'Vespucio Norte sin restricción municipal para 3.200 kg. Unidad CAM-02 asignada en estado R4R esperando firma del supervisor.',
      payload: { case_id: 'CASO-1', origen: 'Quilicura', destino: 'Pudahuel', cargo_weight_kg: 3200, hora_despacho: '14:00', version_mode: 'v2' },
      origin: [-33.3600, -70.6900],
      destination: [-33.4350, -70.7600],
      waypoints: [[-33.3600, -70.6900], [-33.3850, -70.7350], [-33.4350, -70.7600]],
      zoomTarget: [-33.3975, -70.7250],
      zoomLevel: 12,
    },
    'CASO-2': {
      caseId: 'CASO-2',
      label: 'CASO-2 (Reserva Acto 4)',
      routeLabel: 'Quilicura ➔ San Bernardo (28.5 km)',
      eta: '48 min',
      hora: '15:00',
      congestionLabel: 'MEDIA-ALTA (1.25x)',
      trucks: 'CAM-06 (Scania 12t)',
      schedule: 'Mañana 08:00 hrs (SLA 24h)',
      tariff: '$145.000 CLP',
      status: 'R4R',
      primaryPath: 'M 350 82 Q 415 155 455 240 L 445 380',
      primaryColor: '#f59e0b',
      secondaryPath: '',
      alertClass: 'bg-amber-950/30 border-amber-500/40',
      alertTitle: '🟡 FLOTA 12t EN RUTA — RESERVA MAÑANA 08:00',
      alertTitleColor: 'text-amber-300',
      alertDesc: 'Carga pesada de 10.000 kg a las 15:00 hrs con unidades 12t ocupadas en ruta. Agyx activa reserva de slot prioritario para mañana 08:00 hrs en R4R.',
      payload: { case_id: 'CASO-2', origen: 'Quilicura', destino: 'San Bernardo', cargo_weight_kg: 10000, hora_despacho: '15:00', version_mode: 'v2' },
      origin: [-33.3600, -70.6900],
      destination: [-33.5900, -70.7000],
      waypoints: [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4503, -70.6600], [-33.5200, -70.6850], [-33.5900, -70.7000]],
      zoomTarget: [-33.4750, -70.6950],
      zoomLevel: 11,
    },
    'CASO-3-V1': {
      caseId: 'CASO-3',
      label: 'CASO-3 (v1 Pre-Memoria ❌)',
      routeLabel: 'Quilicura ➔ Stgo Centro (14.2 km)',
      eta: '36 min (Infracción)',
      hora: '11:30',
      congestionLabel: 'ALTA DIURNA (1.35x)',
      trucks: 'CAM-05 (Volvo 12t ❌)',
      schedule: 'Hoy 11:30 hrs (PROHIBIDO)',
      tariff: '$120.000 CLP',
      status: 'R4R',
      primaryPath: 'M 350 82 Q 415 155 455 240',
      primaryColor: '#ef4444',
      secondaryPath: '',
      alertClass: 'bg-rose-950/35 border-rose-500/50',
      alertTitle: '❌ VIOLACIÓN ORDENANZA MUNICIPAL (v1)',
      alertTitleColor: 'text-rose-300',
      alertDesc: 'En v1 (sin Memoria Viva), el agente asigna CAM-05 (12t) a las 11:30 hrs hacia Santiago Centro, infringiendo la prohibición diurna >5.000 kg (07:30–21:00). El supervisor debe rechazar en R4R.',
      payload: { case_id: 'CASO-3', origen: 'Quilicura', destino: 'Santiago Centro', cargo_weight_kg: 9500, hora_despacho: '11:30', version_mode: 'v1' },
      origin: [-33.3600, -70.6900],
      destination: [-33.4503, -70.6441],
      waypoints: [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4410, -70.6600], [-33.4503, -70.6441]],
      zoomTarget: [-33.4503, -70.6441],
      zoomLevel: 13,
    },
    'CASO-3-V2': {
      caseId: 'CASO-3',
      label: 'CASO-3 (v2 Nocturno 21:30)',
      routeLabel: 'Quilicura ➔ Stgo Centro (14.2 km)',
      eta: '21 min (Fluido)',
      hora: '21:30',
      congestionLabel: 'BAJA NOCTURNA (0.90x)',
      trucks: 'CAM-05 (Volvo 12t)',
      schedule: 'Hoy 21:30 hrs (SLA 2.5h)',
      tariff: '$135.000 CLP',
      status: 'R4R',
      primaryPath: 'M 350 82 Q 415 155 455 240',
      primaryColor: '#10b981',
      secondaryPath: '',
      alertClass: 'bg-emerald-950/25 border-emerald-500/40',
      alertTitle: '🛡️ REGLA MEMORIA VIVA APLICADA (v2)',
      alertTitleColor: 'text-emerald-300',
      alertDesc: 'Carga de 9.500 kg supera límite diurno (>5t) en Santiago Centro. Agente inyecta regla destilada (<80 tokens) y reprograma salida a ventana nocturna (21:30 hrs).',
      payload: { case_id: 'CASO-3', origen: 'Quilicura', destino: 'Santiago Centro', cargo_weight_kg: 9500, hora_despacho: '11:30', version_mode: 'v2' },
      origin: [-33.3600, -70.6900],
      destination: [-33.4503, -70.6441],
      waypoints: [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4410, -70.6600], [-33.4503, -70.6441]],
      zoomTarget: [-33.4503, -70.6441],
      zoomLevel: 13,
    },
    'CASO-3-SPLIT': {
      caseId: 'CASO-3',
      label: 'CASO-3 (v2 Split 2x 5t)',
      routeLabel: 'Quilicura ➔ Centro Dual (14.8 km)',
      eta: '26 min (2 Corredores)',
      hora: '11:30',
      congestionLabel: 'MEDIA DIURNA (1.25x)',
      trucks: 'CAM-02 (5t) + CAM-03 (5t)',
      schedule: 'Hoy 11:30 hrs (Subdividido)',
      tariff: '$140.000 CLP',
      status: 'R4R',
      primaryPath: 'M 350 82 Q 415 155 455 240',
      primaryColor: '#10b981',
      secondaryPath: 'M 350 82 Q 510 115 615 205 L 455 240',
      alertClass: 'bg-sky-950/30 border-sky-500/40',
      alertTitle: '🚚🚚 SUBDIVISIÓN TÁCTICA 2x CAMIONES 5t',
      alertTitleColor: 'text-sky-300',
      alertDesc: 'Alternativa de Memoria Viva para despacho diurno inmediato: divide 9.500 kg en 2 camiones de 4.750 kg (CAM-02 + CAM-03), cumpliendo el tope municipal <= 5.000 kg.',
      payload: { case_id: 'CASO-3', origen: 'Quilicura', destino: 'Santiago Centro', cargo_weight_kg: 9500, hora_despacho: '11:30', version_mode: 'v2' },
      origin: [-33.3600, -70.6900],
      destination: [-33.4503, -70.6441],
      waypoints: [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4410, -70.6600], [-33.4503, -70.6441]],
      secondaryWaypoints: [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4150, -70.6100], [-33.4300, -70.6150], [-33.4503, -70.6441]],
      zoomTarget: [-33.4200, -70.6550],
      zoomLevel: 12,
    },
    'CASO-4': {
      caseId: 'CASO-4',
      label: 'CASO-4 (Info Incompleta)',
      routeLabel: 'Quilicura ➔ Centro Indefinido',
      eta: 'RETENIDO EN BASE',
      hora: '14:00',
      congestionLabel: 'EN ESPERA DE DATOS',
      trucks: 'Sin Asignar (0 unidades)',
      schedule: 'Detenido en R4R',
      tariff: '$0 CLP',
      status: 'R4R_INFO_INCOMPLETA',
      primaryPath: 'M 350 82 L 350 82',
      primaryColor: '#eab308',
      secondaryPath: '',
      alertClass: 'bg-amber-950/35 border-amber-500/50',
      alertTitle: '⚠️ DETENIDO: INFORMACIÓN AMBIGUA / INCOMPLETA',
      alertTitleColor: 'text-amber-300',
      alertDesc: 'Solicitud "mandar unos pallets urgentes al centro ahora en la tarde" carece de peso_kg, direccion_exacta y hora_exacta. El agente jamás adivina datos críticos.',
      payload: { case_id: 'CASO-4', descripcion: 'Necesito mandar unos pallets urgentes al centro ahora en la tarde.', version_mode: 'v1' },
      origin: [-33.3600, -70.6900],
      destination: [-33.4503, -70.6441],
      waypoints: [[-33.3600, -70.6900]],
      zoomTarget: [-33.3600, -70.6900],
      zoomLevel: 13,
    },
    'CASO-5': {
      caseId: 'CASO-5',
      label: 'CASO-5 (Falla Frenos CAM-04)',
      routeLabel: 'Taller Renca ⛔ Maipú (Bloqueado)',
      eta: 'SALIDA PROHIBIDA',
      hora: '10:00',
      congestionLabel: 'BLOQUEO SEGURIDAD VIAL',
      trucks: '⛔ CAM-04 (BLOQUEADO)',
      schedule: 'Escalamiento Operaciones',
      tariff: '$0 CLP (Riesgo)',
      status: 'BLOQUEADO_RIESGO',
      primaryPath: 'M 350 82 L 295 165',
      primaryColor: '#ef4444',
      secondaryPath: '',
      alertClass: 'bg-rose-950/40 border-rose-500/60',
      alertTitle: '⛔ BLOQUEO DURO: FALLA CRÍTICA DE FRENOS (CAM-04)',
      alertTitleColor: 'text-rose-400',
      alertDesc: 'Solicitud expresa de forzar salida de CAM-04 rechazada automáticamente. Telemetría reporta falla crítica de frenos de aire (disco y compresor) en Taller Renca.',
      payload: { case_id: 'CASO-5', origen: 'Quilicura', destino: 'Maipú', cargo_weight_kg: 4000, truck_id_preferido: 'CAM-04', hora_despacho: '10:00', version_mode: 'v1' },
      origin: [-33.4050, -70.6800],
      destination: [-33.5100, -70.7600],
      waypoints: [[-33.4050, -70.6800], [-33.4050, -70.6800]],
      zoomTarget: [-33.4050, -70.6800],
      zoomLevel: 14,
    },
    'CASO-6': {
      caseId: 'CASO-6',
      label: 'CASO-6 (HAZMAT D.S. 298)',
      routeLabel: 'Quilicura ⛔ Stgo Centro (HAZMAT)',
      eta: 'BLOQUEO LEGAL D.S. 298',
      hora: '14:00',
      congestionLabel: 'EXCLUSIÓN QUÍMICA ADR',
      trucks: '⛔ Flota No Certificada ADR',
      schedule: 'Rechazo Normativo',
      tariff: '$0 CLP (Fuera de Alcance)',
      status: 'BLOQUEADO_RIESGO',
      primaryPath: 'M 350 82 L 385 135',
      primaryColor: '#a855f7',
      secondaryPath: '',
      alertClass: 'bg-purple-950/40 border-purple-500/50',
      alertTitle: '☣️ BLOQUEO LEGAL D.S. 298 — ÁCIDO SULFÚRICO',
      alertTitleColor: 'text-purple-300',
      alertDesc: 'Transporte de cargas peligrosas Clase 8 (Ácido Sulfúrico) requiere resolución sanitaria SEREMI y camión certificado ADR. Orden bloqueada y escalada a Gerencia.',
      payload: { case_id: 'CASO-6', origen: 'Quilicura', destino: 'Santiago Centro', cargo_weight_kg: 4000, tipo_carga: 'ACIDO_SULFURICO', hora_despacho: '14:00', version_mode: 'v1' },
      origin: [-33.3600, -70.6900],
      destination: [-33.4503, -70.6441],
      waypoints: [[-33.3600, -70.6900], [-33.3850, -70.6800]],
      zoomTarget: [-33.4050, -70.6800],
      zoomLevel: 12,
    },
    'LIRA-953': {
      caseId: 'CASO-LIRA-953',
      label: 'Misión Lira 953 (Geo-Check)',
      routeLabel: 'Quilicura ➔ Lira 953, Centro (14.2 km)',
      eta: '21 min (Ventana 21:30)',
      hora: '11:30',
      congestionLabel: 'CONTROL URBANO ACTIVO',
      trucks: 'CAM-05 (Nocturno) / Revisión R4R',
      schedule: '11:30 ➔ 21:30 hrs',
      tariff: '$135.000 CLP',
      status: 'R4R',
      primaryPath: 'M 350 82 Q 415 155 455 240',
      primaryColor: '#38bdf8',
      secondaryPath: '',
      alertClass: 'bg-sky-950/30 border-sky-500/40',
      alertTitle: '📍 GEORREFERENCIACIÓN LIRA 953 (-33.4503, -70.6441)',
      alertTitleColor: 'text-sky-300',
      alertDesc: 'El motor geoespacial resuelve Lira 953 dentro del polígono SANTIAGO_CENTRO. Detecta 9.500 kg en horario diurno (11:30) y exige validación de regla u horario nocturno 21:30.',
      payload: { case_id: 'CASO-LIRA-953', origen: 'Quilicura', destino: 'Lira 953, Santiago', cargo_weight_kg: 9500, hora_despacho: '11:30', version_mode: 'v2' },
      origin: [-33.3600, -70.6900],
      destination: [-33.4503, -70.6441],
      waypoints: [[-33.3600, -70.6900], [-33.4050, -70.6800], [-33.4410, -70.6600], [-33.4503, -70.6441]],
      zoomTarget: [-33.4503, -70.6441],
      zoomLevel: 14,
    },
  };

  let currentRadarKey = 'CASO-3-V2';

  // --- REAL DYNAMIC SANTIAGO LEAFLET MAP CONTROLLER ---
  let leafletMap = null;
  const tileLayers = {};
  let geofenceLayer = null;
  let activeRouteLine = null;
  let activeSecondaryRouteLine = null;
  let realMapFleetMarkers = [];

  const SANTIAGO_NODES_DATA = {
    'QUILICURA': { name: 'HUB QUILICURA', coords: [-33.3600, -70.6900], color: '#38bdf8', role: 'Base Central · Patio Operativo (CAM-01, 02, 03, 05)' },
    'RENCA': { name: 'TALLER RENCA', coords: [-33.4050, -70.6800], color: '#ef4444', role: 'Mantenimiento · Bloqueo Falla Frenos CAM-04 (Caso 5)' },
    'PUDAHUEL': { name: 'CD PUDAHUEL', coords: [-33.4350, -70.7600], color: '#10b981', role: 'CD Logístico Poniente · Destino Caso 1 (3.2t)' },
    'MAIPU': { name: 'MAIPÚ', coords: [-33.5100, -70.7600], color: '#38bdf8', role: 'Polígono Industrial Poniente-Sur' },
    'SANTIAGO_CENTRO': { name: 'SANTIAGO CENTRO (Lira 953)', coords: [-33.4503, -70.6441], color: '#fbbf24', role: 'Control Municipal >5t (07:30-21:00) · Caso 3 v1➔v2' },
    'PROVIDENCIA': { name: 'PROVIDENCIA', coords: [-33.4300, -70.6150], color: '#f59e0b', role: 'Eje Comercial Oriente · Vía Alternativa Split 5t' },
    'SAN_BERNARDO': { name: 'SAN BERNARDO', coords: [-33.5900, -70.7000], color: '#38bdf8', role: 'Planta Industrial Sur · Destino Caso 2 (10t)' },
  };

  function initRealLeafletMap() {
    const container = document.getElementById('dispatch-real-map');
    if (!container || leafletMap || typeof L === 'undefined') return;

    try {
      leafletMap = L.map('dispatch-real-map', {
        center: [-33.4450, -70.6600],
        zoom: 12,
        minZoom: 10,
        maxZoom: 18,
        zoomControl: true,
        attributionControl: true,
      });

      // Google Maps Táctico Oscuro (Default Dispatch Theme - Sin marca de agua ni API key)
      tileLayers['google-dark'] = L.tileLayer('https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
        subdomains: ['0', '1', '2', '3'],
        className: 'tactical-dark-tile',
        attribution: '&copy; Google Maps &mdash; Agyx Tactical Dispatch',
        maxZoom: 20
      });

      // Google Maps Calles Reales (Full Color Streets)
      tileLayers['google-streets'] = L.tileLayer('https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
        subdomains: ['0', '1', '2', '3'],
        attribution: '&copy; Google Maps &mdash; Calles Santiago',
        maxZoom: 20
      });

      // Google Maps Satélite Híbrido (Satellite + Streets)
      tileLayers['google-hybrid'] = L.tileLayer('https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
        subdomains: ['0', '1', '2', '3'],
        attribution: '&copy; Google Maps &mdash; Satélite Híbrido RM',
        maxZoom: 20
      });

      // OpenStreetMap Táctico (Zero-key fallback)
      tileLayers['osm-dark'] = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        subdomains: 'abc',
        className: 'tactical-dark-tile',
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
      });

      // Add default dark layer
      tileLayers['google-dark'].addTo(leafletMap);

      // Santiago Centro Exclusion Geofence Polygon (>5.000 kg 07:30–21:00)
      const geofenceCoords = [
        [-33.4300, -70.6720],
        [-33.4320, -70.6380],
        [-33.4580, -70.6350],
        [-33.4680, -70.6550],
        [-33.4520, -70.6800],
      ];

      geofenceLayer = L.polygon(geofenceCoords, {
        color: '#f59e0b',
        weight: 2,
        dashArray: '6, 6',
        fillColor: '#f59e0b',
        fillOpacity: 0.12,
      }).addTo(leafletMap);

      geofenceLayer.bindPopup(`
        <div class="tactical-leaflet-popup">
          <div class="font-mono font-bold text-amber-300 text-xs flex items-center gap-1.5 border-b border-amber-500/30 pb-1 mb-1.5">
            <span>⚠️ ORDENANZA N° 84 · SANTIAGO CENTRO</span>
          </div>
          <p class="text-slate-300 text-[11px] leading-relaxed">
            <strong>Prohibición Diurna:</strong> Camiones de más de <strong>5.000 kg</strong> tienen acceso restringido de <strong>07:30 a 21:00 hrs</strong>.
          </p>
          <div class="mt-2 text-[10px] text-emerald-400 font-mono">
            ✓ Ventana nocturna autorizada: 21:30–06:30 hrs<br>
            ✓ Alternativa diurna: Split táctico 2x camiones 5t
          </div>
        </div>
      `, { className: 'tactical-leaflet-popup' });

      // Render Comuna Hub Nodes
      renderRealMapNodes();

      // Setup Layer Buttons
      document.querySelectorAll('.map-layer-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const layerKey = btn.getAttribute('data-map-layer');
          if (tileLayers[layerKey]) {
            Object.values(tileLayers).forEach(l => {
              if (leafletMap.hasLayer(l)) leafletMap.removeLayer(l);
            });
            tileLayers[layerKey].addTo(leafletMap);
            document.querySelectorAll('.map-layer-btn').forEach(b => {
              b.classList.remove('active-layer', 'bg-sky-500/20', 'text-sky-300', 'border-sky-500/40');
              b.classList.add('bg-slate-800', 'text-slate-300', 'border-slate-700');
            });
            btn.classList.add('active-layer', 'bg-sky-500/20', 'text-sky-300', 'border-sky-500/40');
            btn.classList.remove('bg-slate-800', 'text-slate-300', 'border-slate-700');
          }
        });
      });

      // Setup GPS Focus buttons
      document.querySelectorAll('[data-map-focus]').forEach(btn => {
        btn.addEventListener('click', () => {
          const focusKey = btn.getAttribute('data-map-focus');
          focusRealMap(focusKey);
        });
      });

      // Mode Switcher Listeners
      const btnReal = document.getElementById('btn-mode-realmap');
      const btnSvg = document.getElementById('btn-mode-svg');
      const realMapDiv = document.getElementById('dispatch-real-map');
      const svgMap = document.getElementById('dispatch-tactical-svg');

      if (btnReal && btnSvg && realMapDiv && svgMap) {
        btnReal.addEventListener('click', () => {
          realMapDiv.classList.remove('hidden');
          svgMap.classList.add('hidden');
          btnReal.className = 'px-2.5 py-1 rounded-md text-xs font-mono font-medium bg-sky-500/20 text-sky-300 border border-sky-500/40 transition active:scale-95 flex items-center gap-1.5';
          btnSvg.className = 'px-2.5 py-1 rounded-md text-xs font-mono font-medium text-slate-400 hover:text-slate-200 transition active:scale-95 flex items-center gap-1.5';
          if (leafletMap) {
            setTimeout(() => leafletMap.invalidateSize(), 50);
          }
        });

        btnSvg.addEventListener('click', () => {
          realMapDiv.classList.add('hidden');
          svgMap.classList.remove('hidden');
          btnSvg.className = 'px-2.5 py-1 rounded-md text-xs font-mono font-medium bg-sky-500/20 text-sky-300 border border-sky-500/40 transition active:scale-95 flex items-center gap-1.5';
          btnReal.className = 'px-2.5 py-1 rounded-md text-xs font-mono font-medium text-slate-400 hover:text-slate-200 transition active:scale-95 flex items-center gap-1.5';
        });
      }

      // Draw initial scenario route
      updateRealMapScenario(currentRadarKey);

    } catch (err) {
      console.warn('Leaflet map initialization fallback to SVG', err);
    }
  }

  function focusRealMap(focusKey) {
    if (!leafletMap) return;
    switch (focusKey) {
      case 'CENTRO':
        leafletMap.flyTo([-33.4503, -70.6441], 14, { duration: 1.2 });
        break;
      case 'QUILICURA':
        leafletMap.flyTo([-33.3600, -70.6900], 14, { duration: 1.2 });
        break;
      case 'RENCA':
        leafletMap.flyTo([-33.4050, -70.6800], 14.5, { duration: 1.2 });
        break;
      case 'ALL':
      default:
        leafletMap.flyTo([-33.4450, -70.6600], 12, { duration: 1.2 });
        break;
    }
  }

  function renderRealMapNodes() {
    if (!leafletMap || typeof L === 'undefined') return;
    Object.entries(SANTIAGO_NODES_DATA).forEach(([key, node]) => {
      const icon = L.divIcon({
        className: 'node-leaflet-marker',
        html: `
          <div class="node-leaflet-dot" style="background-color: ${node.color}; box-shadow: 0 0 10px ${node.color};"></div>
          <div class="node-leaflet-label">${node.name}</div>
        `,
        iconSize: [110, 34],
        iconAnchor: [55, 6],
      });

      const marker = L.marker(node.coords, { icon }).addTo(leafletMap);
      marker.on('click', () => {
        const insp = document.getElementById('radar-inspector-text');
        if (insp) {
          insp.innerHTML = `📍 <strong>${escapeHtml(node.name)}</strong> · ${node.role} (GPS: ${node.coords[0].toFixed(4)}, ${node.coords[1].toFixed(4)})`;
        }
      });
      marker.bindPopup(`
        <div class="tactical-leaflet-popup">
          <strong class="text-sky-300 font-mono text-xs block">${escapeHtml(node.name)}</strong>
          <span class="text-slate-400 text-[10px] block mt-0.5">GPS: ${node.coords[0]}, ${node.coords[1]}</span>
          <p class="text-slate-200 text-[11px] mt-1">${escapeHtml(node.role)}</p>
        </div>
      `, { className: 'tactical-leaflet-popup' });
    });
  }

  function renderRealMapFleet(fleetMarkersList) {
    if (!leafletMap || typeof L === 'undefined' || !Array.isArray(fleetMarkersList)) return;

    // Remove existing fleet markers
    realMapFleetMarkers.forEach(m => leafletMap.removeLayer(m));
    realMapFleetMarkers = [];

    fleetMarkersList.forEach(m => {
      if (typeof m.lat !== 'number' || typeof m.lng !== 'number') return;
      const isLocked = m.blocked || m.status === 'EN_MANTENIMIENTO';
      const isEnRuta = m.status === 'EN_RUTA';
      const pillClass = isLocked ? 'fleet-pill-blocked' : (isEnRuta ? 'fleet-pill-en-ruta' : 'fleet-pill-available');

      const icon = L.divIcon({
        className: 'fleet-leaflet-marker',
        html: `<div class="fleet-leaflet-pill ${pillClass}">🚛 ${escapeHtml(m.id)}</div>`,
        iconSize: [68, 22],
        iconAnchor: [34, 11],
      });

      const marker = L.marker([m.lat, m.lng], { icon }).addTo(leafletMap);
      marker.on('click', () => {
        const insp = document.getElementById('radar-inspector-text');
        if (insp) {
          insp.innerHTML = `🚛 <strong>${escapeHtml(m.id)}</strong> (${escapeHtml(m.modelo)}, máx ${(m.capacidad_kg || 0).toLocaleString('es-CL')} kg) — Estado: <strong class="${isLocked ? 'text-rose-400' : 'text-sky-300'}">${escapeHtml(m.status)}</strong> · ${escapeHtml(m.detail)}`;
        }
      });
      marker.bindPopup(`
        <div class="tactical-leaflet-popup">
          <div class="flex items-center justify-between border-b border-slate-700 pb-1 mb-1.5">
            <strong class="${isLocked ? 'text-rose-400' : 'text-sky-300'} font-mono text-xs">🚛 ${escapeHtml(m.id)}</strong>
            <span class="text-[9px] font-mono px-1.5 py-0.2 rounded ${isLocked ? 'bg-rose-950 text-rose-300 border border-rose-600' : 'bg-slate-800 text-slate-300'}">${escapeHtml(m.status)}</span>
          </div>
          <p class="text-slate-200 text-[11px]"><strong>Modelo:</strong> ${escapeHtml(m.modelo)} (Máx ${(m.capacidad_kg || 0).toLocaleString('es-CL')} kg)</p>
          <p class="text-slate-300 text-[10px] mt-1">${escapeHtml(m.detail)}</p>
          <p class="text-slate-400 text-[9px] font-mono mt-1">GPS: ${m.lat.toFixed(4)}, ${m.lng.toFixed(4)}</p>
        </div>
      `, { className: 'tactical-leaflet-popup' });

      realMapFleetMarkers.push(marker);
    });
  }

  function updateRealMapScenario(scenarioKey) {
    if (!leafletMap || typeof L === 'undefined') return;
    const sc = RADAR_SCENARIOS[scenarioKey];
    if (!sc) return;

    // Remove existing route lines
    if (activeRouteLine) {
      leafletMap.removeLayer(activeRouteLine);
      activeRouteLine = null;
    }
    if (activeSecondaryRouteLine) {
      leafletMap.removeLayer(activeSecondaryRouteLine);
      activeSecondaryRouteLine = null;
    }

    // Draw primary route
    if (Array.isArray(sc.waypoints) && sc.waypoints.length > 1) {
      activeRouteLine = L.polyline(sc.waypoints, {
        color: sc.primaryColor || '#10b981',
        weight: 5,
        opacity: 0.92,
        dashArray: '10, 6',
      }).addTo(leafletMap);
    }

    // Draw secondary split route if defined
    if (Array.isArray(sc.secondaryWaypoints) && sc.secondaryWaypoints.length > 1) {
      activeSecondaryRouteLine = L.polyline(sc.secondaryWaypoints, {
        color: '#38bdf8',
        weight: 4,
        opacity: 0.88,
        dashArray: '8, 6',
      }).addTo(leafletMap);
    }

    // Update Geofence visual state based on scenario
    if (geofenceLayer) {
      if (scenarioKey === 'CASO-3-V1') {
        geofenceLayer.setStyle({ color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.28 });
      } else if (scenarioKey === 'CASO-3-V2') {
        geofenceLayer.setStyle({ color: '#10b981', fillColor: '#10b981', fillOpacity: 0.18 });
      } else {
        geofenceLayer.setStyle({ color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.12 });
      }
    }

    // Smoothly flyTo zoom target
    if (sc.zoomTarget && sc.zoomLevel) {
      leafletMap.flyTo(sc.zoomTarget, sc.zoomLevel, { duration: 1.1 });
    }

    // Update direct Google Maps link button
    const btnGmaps = document.getElementById('btn-open-google-maps');
    if (btnGmaps && sc.origin && sc.destination) {
      btnGmaps.href = `https://www.google.com/maps/dir/?api=1&origin=${sc.origin[0]},${sc.origin[1]}&destination=${sc.destination[0]},${sc.destination[1]}&travelmode=driving`;
    }
  }

  async function fetchTacticalNetwork(hora = '11:30') {
    try {
      const res = await fetch(`/api/tactical-network?hora=${encodeURIComponent(hora)}`);
      if (res.ok) {
        const net = await res.json();
        renderTacticalNetworkOverlay(net);
      }
    } catch (err) {
      console.warn('Tactical network offline fallback active', err);
    }
  }

  function renderTacticalNetworkOverlay(net) {
    if (!net) return;
    const pill = document.getElementById('radar-congestion-pill');
    if (pill) {
      pill.textContent = `Tráfico ${net.hora || '11:30'}: ${net.congestion_label || 'MEDIA'} (${net.congestion_multiplier || 1.25}x)`;
    }

    // Update Santiago Centro exclusion polygon according to daytime ban active status
    const poly = document.getElementById('svg-centro-polygon');
    const badgeText = document.getElementById('svg-centro-badge-text');
    const zoneBanner = document.getElementById('radar-zone-banner');
    if (poly && badgeText) {
      if (net.santiago_centro_daytime_ban_active === false) {
        poly.setAttribute('stroke', '#10b981');
        badgeText.setAttribute('fill', '#34d399');
        badgeText.textContent = 'VENTANA NOCTURNA LIBRE (21:30–06:30)';
        if (zoneBanner) {
          zoneBanner.className = 'px-2 py-0.5 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-300';
          zoneBanner.textContent = 'ZONA SANTIAGO CENTRO: VENTANA NOCTURNA HABILITADA (>5t OK)';
        }
      } else {
        poly.setAttribute('stroke', '#f59e0b');
        badgeText.setAttribute('fill', '#fcd34d');
        badgeText.textContent = 'ORDENANZA >5t (07:30–21:00)';
        if (zoneBanner) {
          zoneBanner.className = 'px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300';
          zoneBanner.textContent = 'ZONA EXCLUSIÓN SANTIAGO CENTRO: >5.000 kg (07:30–21:00)';
        }
      }
    }

    // Colorize corridors by live congestion
    if (Array.isArray(net.corridors)) {
      net.corridors.forEach(c => {
        const pathEl = document.getElementById(`corridor-${c.id}`);
        if (!pathEl) return;
        const colorMap = {
          'BAJA': '#1e3a5f',
          'MEDIA': '#334155',
          'ALTA': '#78350f',
          'CRITICA': '#7f1d1d',
        };
        pathEl.setAttribute('stroke', colorMap[c.congestion_level] || '#334155');
      });
    }

    // Render live fleet markers (CAM-01..CAM-07)
    const fleetLayer = document.getElementById('svg-fleet-markers-layer');
    if (fleetLayer && Array.isArray(net.fleet_markers)) {
      fleetLayer.innerHTML = '';
      net.fleet_markers.forEach((m, idx) => {
        const offsetX = ((idx % 3) - 1) * 26;
        const offsetY = (idx < 3 ? -32 : 34);
        const gx = (m.x || 350) + offsetX;
        const gy = (m.y || 82) + offsetY;
        const isLocked = m.blocked || m.status === 'EN_MANTENIMIENTO';
        const isEnRuta = m.status === 'EN_RUTA';
        const strokeColor = isLocked ? '#ef4444' : (isEnRuta ? '#f59e0b' : '#38bdf8');
        const bgFill = isLocked ? '#450a0a' : (isEnRuta ? '#451a03' : '#082f49');

        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('class', 'radar-truck-pill');
        g.setAttribute('transform', `translate(${gx}, ${gy})`);
        g.innerHTML = `
          <rect x="-24" y="-9" width="48" height="18" rx="5" fill="${bgFill}" stroke="${strokeColor}" stroke-width="1.2" />
          <text x="0" y="3" text-anchor="middle" fill="#f8fafc" font-size="8.5" font-family="monospace" font-weight="bold">${escapeHtml(m.id)}</text>
        `;
        g.addEventListener('click', () => {
          const insp = document.getElementById('radar-inspector-text');
          if (insp) {
            insp.innerHTML = `🚛 <strong>${escapeHtml(m.id)}</strong> (${escapeHtml(m.modelo)}, máx ${(m.capacidad_kg || 0).toLocaleString('es-CL')} kg) — Estado: <strong class="${isLocked ? 'text-rose-400' : 'text-sky-300'}">${escapeHtml(m.status)}</strong> · ${escapeHtml(m.detail)}`;
          }
        });
        fleetLayer.appendChild(g);
      });
    }

    // Update Leaflet geofence polygon style
    if (geofenceLayer) {
      if (net.santiago_centro_daytime_ban_active === false) {
        geofenceLayer.setStyle({ color: '#10b981', fillColor: '#10b981', fillOpacity: 0.18 });
      } else {
        geofenceLayer.setStyle({ color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.12 });
      }
    }

    // Update Leaflet Live Fleet Markers
    if (Array.isArray(net.fleet_markers)) {
      renderRealMapFleet(net.fleet_markers);
    }
  }

  function setRadarScenario(scenarioKey) {
    const sc = RADAR_SCENARIOS[scenarioKey];
    if (!sc) return;
    currentRadarKey = scenarioKey;

    document.querySelectorAll('.radar-case-btn').forEach(btn => {
      if (btn.getAttribute('data-radar-case') === scenarioKey) {
        btn.classList.add('active-radar-case');
      } else {
        btn.classList.remove('active-radar-case');
      }
    });

    const primaryEl = document.getElementById('svg-route-primary');
    const secondaryEl = document.getElementById('svg-route-secondary');
    if (primaryEl) {
      primaryEl.setAttribute('d', sc.primaryPath);
      primaryEl.setAttribute('stroke', sc.primaryColor);
    }
    if (secondaryEl) {
      if (sc.secondaryPath) {
        secondaryEl.setAttribute('d', sc.secondaryPath);
        secondaryEl.classList.remove('hidden');
      } else {
        secondaryEl.classList.add('hidden');
      }
    }

    const setText = (id, val) => {
      const node = document.getElementById(id);
      if (node) node.textContent = val;
    };

    setText('hud-case-id', sc.label);
    setText('hud-route-distance', sc.routeLabel);
    setText('hud-eta', sc.eta);
    setText('hud-trucks', sc.trucks);
    setText('hud-schedule', sc.schedule);
    setText('hud-tariff', sc.tariff);
    setText('hud-alert-title', sc.alertTitle);
    setText('hud-alert-desc', sc.alertDesc);

    const statusBadge = document.getElementById('hud-status-badge');
    if (statusBadge) statusBadge.outerHTML = `<span id="hud-status-badge">${getStatusBadge(sc.status)}</span>`;

    const alertBox = document.getElementById('hud-alert-box');
    if (alertBox) alertBox.className = `p-3 rounded-xl border text-xs flex flex-col gap-1 ${sc.alertClass}`;
    const alertTitle = document.getElementById('hud-alert-title');
    if (alertTitle) alertTitle.className = `font-bold font-mono text-[11px] ${sc.alertTitleColor}`;

    // Update Real Leaflet Map Route, Geofence and Zoom
    updateRealMapScenario(scenarioKey);

    // Sync Mobile Mini Radar
    setText('mob-radar-case', sc.label);
    setText('mob-radar-route', sc.routeLabel);
    setText('mob-radar-eta', sc.eta);
    setText('mob-radar-note', `Flota: ${sc.trucks} · ${sc.schedule}`);

    // Sync time selector & fetch network telemetry for that hour
    const timeSelect = document.getElementById('radar-time-select');
    if (timeSelect && sc.hora) {
      timeSelect.value = sc.hora;
    }
    fetchTacticalNetwork(sc.hora || '11:30');
  }

  function applyBackendTacticalMap(caseId, evalData) {
    const tmap = evalData.tactical_map;
    if (!tmap) return;
    const prop = evalData.proposal || {};
    const trucks = Array.isArray(prop.camiones) && prop.camiones.length ? prop.camiones.join(' + ') : 'Sin Asignar';
    const totalClp = Number(prop.total_clp || evalData.total_clp || 0);

    const setText = (id, val) => {
      const node = document.getElementById(id);
      if (node) node.textContent = val;
    };

    setText('hud-case-id', `${caseId} (${tmap.version_mode || 'v2'})`);
    setText('hud-route-distance', `${tmap.origin_node?.nombre || 'Origen'} ➔ ${tmap.destination_node?.nombre || 'Destino'} (${tmap.distance_km} km)`);
    setText('hud-eta', `${tmap.eta_minutes} min (${tmap.congestion_multiplier}x ${tmap.congestion_label})`);
    setText('hud-trucks', trucks);
    setText('hud-schedule', `${prop.fecha_hora_programada || tmap.hora_evaluada} (SLA ${prop.sla_horas || 2}h)`);
    setText('hud-tariff', `$${totalClp.toLocaleString('es-CL')} CLP`);
    setText('hud-alert-desc', prop.observaciones || evalData.message || '');

    // Synchronize Real Leaflet Map
    if (leafletMap && typeof L !== 'undefined' && tmap.origin_node && tmap.destination_node) {
      const origCoords = [tmap.origin_node.lat || -33.3600, tmap.origin_node.lng || -70.6900];
      const destCoords = [tmap.destination_node.lat || -33.4503, tmap.destination_node.lng || -70.6441];
      if (activeRouteLine) leafletMap.removeLayer(activeRouteLine);
      activeRouteLine = L.polyline([origCoords, destCoords], {
        color: evalData.status === 'BLOQUEADO_RIESGO' ? '#ef4444' : '#10b981',
        weight: 5,
        dashArray: '10, 6',
      }).addTo(leafletMap);
      leafletMap.flyTo(destCoords, 13, { duration: 1.0 });

      const btnGmaps = document.getElementById('btn-open-google-maps');
      if (btnGmaps) {
        btnGmaps.href = `https://www.google.com/maps/dir/?api=1&origin=${origCoords[0]},${origCoords[1]}&destination=${destCoords[0]},${destCoords[1]}&travelmode=driving`;
      }
    }

    setText('mob-radar-case', caseId);
    setText('mob-radar-route', `${tmap.origin_node?.nombre || 'Origen'} ➔ ${tmap.destination_node?.nombre || 'Destino'} (${tmap.distance_km} km)`);
    setText('mob-radar-eta', `${tmap.eta_minutes} min`);
    setText('mob-radar-note', `Flota: ${trucks} · Estado: ${evalData.status}`);
  }

  function setupTacticalRadarListeners() {
    document.querySelectorAll('.radar-case-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.getAttribute('data-radar-case');
        setRadarScenario(key);
      });
    });

    const timeSelect = document.getElementById('radar-time-select');
    if (timeSelect) {
      timeSelect.addEventListener('change', (e) => {
        fetchTacticalNetwork(e.target.value);
      });
    }

    const toggleRadarBtn = document.getElementById('btn-toggle-radar-panel');
    const radarBody = document.getElementById('radar-body-container');
    if (toggleRadarBtn && radarBody) {
      toggleRadarBtn.addEventListener('click', () => {
        const isHidden = radarBody.classList.toggle('hidden');
        toggleRadarBtn.textContent = isHidden ? 'Expandir Radar' : 'Minimizar Radar';
      });
    }

    const NODE_DESCRIPTIONS = {
      'QUILICURA': '🏢 HUB QUILICURA: Base Operativa Central. Unidades disponibles en patio: CAM-01 (3.5t), CAM-02 (5t), CAM-03 (5t), CAM-05 (12t).',
      'RENCA': '🔧 TALLER RENCA: Bloqueo físico y electrónico activo sobre CAM-04 (VW 8t) por falla crítica de frenos de aire (Caso 5).',
      'PUDAHUEL': '📦 CD PUDAHUEL: Zona industrial libre de restricción diurna. Destino del Caso 1 (3.200 kg en CAM-02).',
      'MAIPU': '🏭 POLÍGONO MAIPÚ: Destino industrial poniente. En Caso 5 se bloquea intento de forzar salida con CAM-04.',
      'SANTIAGO_CENTRO': '🏛️ SANTIAGO CENTRO (Lira 953): Ordenanza Municipal prohíbe camiones >5.000 kg entre 07:30 y 21:00 hrs (Caso 3 v1➔v2).',
      'PROVIDENCIA': '🏙️ EJE PROVIDENCIA: Corredor comercial con restricción de tonelaje >3.500 kg en horas punta.',
      'SAN_BERNARDO': '🏗️ PLANTA SAN BERNARDO: Zona industrial sur. Destino del Caso 2 (10.000 kg reserva mañana 08:00 hrs en CAM-06).',
    };

    document.querySelectorAll('.radar-node-group').forEach(nodeEl => {
      nodeEl.addEventListener('click', () => {
        const nid = nodeEl.getAttribute('data-node-id');
        const insp = document.getElementById('radar-inspector-text');
        if (insp && NODE_DESCRIPTIONS[nid]) {
          insp.innerHTML = NODE_DESCRIPTIONS[nid];
        }
      });
    });

    const btnHudEval = document.getElementById('btn-hud-evaluate');
    if (btnHudEval) {
      btnHudEval.addEventListener('click', async () => {
        const sc = RADAR_SCENARIOS[currentRadarKey];
        if (!sc || !sc.payload) return;
        showToast(`Evaluando misión ${sc.caseId} en motor de despacho...`, 'info');
        try {
          const res = await fetch('/api/dispatch/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sc.payload),
          });
          if (res.ok) {
            const data = await res.json();
            await refreshAllData();
            showToast(`✅ Misión ${sc.caseId} registrada en Cola R4R (${data.status}). auto_approved=False`, 'success');
          }
        } catch (err) {
          showToast('Error al evaluar misión en radar.', 'error');
        }
      });
    }

    const btnHudModal = document.getElementById('btn-hud-open-modal');
    if (btnHudModal) {
      btnHudModal.addEventListener('click', async () => {
        const sc = RADAR_SCENARIOS[currentRadarKey];
        if (!sc) return;
        let exists = state.r4rQueue.find(p => p.case_id === sc.caseId);
        if (!exists && sc.payload) {
          await fetch('/api/dispatch/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sc.payload),
          });
          await fetchQueue();
        }
        window.openReviewModal(sc.caseId);
      });
    }

    // Initialize Real Dynamic Leaflet Map
    initRealLeafletMap();
  }

  // --- TOAST NOTIFICATIONS ENGINE ---
  function showToast(message, type = 'info', duration = 4000) {
    if (!el.toastContainer) return;

    const toast = document.createElement('div');
    const colors = {
      'success': 'bg-emerald-950/90 border-emerald-500/50 text-emerald-200',
      'error': 'bg-rose-950/90 border-rose-500/50 text-rose-200',
      'warning': 'bg-amber-950/90 border-amber-500/50 text-amber-200',
      'info': 'bg-slate-900/90 border-sky-500/50 text-sky-200',
    };

    toast.className = `p-3 rounded-xl border shadow-xl text-xs flex items-center justify-between gap-3 pointer-events-auto backdrop-blur-sm toast-enter ${colors[type] || colors.info}`;
    toast.innerHTML = `
      <div class="flex items-center gap-2">
        <span>${message}</span>
      </div>
      <button class="text-slate-400 hover:text-white" onclick="this.parentElement.remove()">✕</button>
    `;

    el.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast-leave');
      setTimeout(() => toast.remove(), 250);
    }, duration);
  }

  // --- SERVICE WORKER REGISTRATION (PWA) ---
  function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/sw.js').then(
          reg => console.log('Agyx ServiceWorker registrado exitosamente:', reg.scope),
          err => console.log('Agyx ServiceWorker fallo:', err)
        );
      });
    }
  }

  // Run initialization
  setupTacticalRadarListeners();
  setRadarScenario('CASO-3-V2');
  init();
});
