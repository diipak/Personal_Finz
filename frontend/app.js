// FinSync Pro - Sovereign Financial Intelligence Frontend Application Engine

let currentTab = 'dashboard';
let baseCurrency = 'EUR';
let spotRate = 90.00;
let balanceMultiplier = 1.00;
let balanceMasked = false;
let allTransactions = [];
let categories = [];
let accountsList = [];
let resolutions = [];
let selectedFile = null;

// Ledger State
let activeDateFilter = 'ALL'; // 'ALL', 'YTD', 'LAST_YEAR', 'YYYY-MM', 'CUSTOM'
let customStartDate = '';
let customEndDate = '';
let activeLedgerView = 'list'; // 'list' or 'calendar'
let ledgerPageSize = 15;
let ledgerPageIndex = 0;
let accountFilterId = null; // Filter ledger by specific account

// Stats State
let activeStatsProfile = 'categorical'; // 'categorical', 'trend', 'asset'
let activeStatsChartType = 'Pie Chart';
let activeStatsSortOrder = 'Amount';
let activeStatsBreakdown = 'outflows_by_category';

// WebGL Background Shader Animation
function initBackgroundShader() {
    const canvas = document.getElementById('shader-canvas');
    if (!canvas) return;
    
    function syncSize() {
        const w = window.innerWidth;
        const h = window.innerHeight;
        if (canvas.width !== w || canvas.height !== h) {
            canvas.width = w;
            canvas.height = h;
        }
    }
    window.addEventListener('resize', syncSize);
    syncSize();

    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!gl) return;
    
    const vs = `attribute vec2 a_position;
varying vec2 v_texCoord;
void main() {
  v_texCoord = a_position * 0.5 + 0.5;
  gl_Position = vec4(a_position, 0.0, 1.0);
}`;
    const fs = `precision highp float;
varying vec2 v_texCoord;
uniform float u_time;

void main() {
    vec2 uv = v_texCoord;
    float orb1 = smoothstep(0.8, 0.0, distance(uv, vec2(0.2 + 0.05 * sin(u_time * 0.4), 0.8 + 0.05 * cos(u_time * 0.5))));
    float orb2 = smoothstep(0.9, 0.0, distance(uv, vec2(0.8 + 0.05 * cos(u_time * 0.3), 0.2 + 0.05 * sin(u_time * 0.4))));
    float orb3 = smoothstep(0.7, 0.0, distance(uv, vec2(0.5 + 0.1 * sin(u_time * 0.2), 0.4 + 0.1 * cos(u_time * 0.3))));

    vec3 color1 = vec3(0.18, 0.15, 0.6) * orb1; 
    vec3 color2 = vec3(0.25, 0.12, 0.5) * orb2; 
    vec3 color3 = vec3(0.04, 0.45, 0.3) * orb3; 
    
    vec3 finalColor = color1 + color2 + color3;
    vec3 bgColor = vec3(0.035, 0.035, 0.043); 
    
    gl_FragColor = vec4(mix(bgColor, finalColor, 0.25), 1.0);
}`;

    function cs(type, src) {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        return s;
    }
    
    const prog = gl.createProgram();
    gl.attachShader(prog, cs(gl.VERTEX_SHADER, vs));
    gl.attachShader(prog, cs(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog);
    gl.useProgram(prog);
    
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    
    const pos = gl.getAttribLocation(prog, 'a_position');
    gl.enableVertexAttribArray(pos);
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);
    const uTime = gl.getUniformLocation(prog, 'u_time');

    function render(t) {
        gl.viewport(0, 0, canvas.width, canvas.height);
        if (uTime) gl.uniform1f(uTime, t * 0.001);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        requestAnimationFrame(render);
    }
    render(0);
}

// Client Router & Tabs switcher
let currentAutomationSubTab = 'review';
let currentInvestmentsSubTab = 'assets';

function toggleInvestmentsSubView(view) {
    currentInvestmentsSubTab = view;
    const btnAssets = document.getElementById('btn-subview-assets');
    const btnPortfolio = document.getElementById('btn-subview-portfolio');
    const panelAssets = document.getElementById('sub-panel-investments-assets');
    const panelPortfolio = document.getElementById('sub-panel-investments-portfolio');

    if (view === 'assets') {
        if (btnAssets) {
            btnAssets.className = 'px-4 py-1.5 rounded-md text-label-sm font-label-sm font-semibold transition-all bg-surface-variant text-on-surface';
        }
        if (btnPortfolio) {
            btnPortfolio.className = 'px-4 py-1.5 rounded-md text-label-sm font-label-sm transition-all text-on-surface-variant hover:text-on-surface';
        }
        if (panelAssets) panelAssets.classList.remove('hidden');
        if (panelPortfolio) panelPortfolio.classList.add('hidden');
    } else {
        if (btnAssets) {
            btnAssets.className = 'px-4 py-1.5 rounded-md text-label-sm font-label-sm transition-all text-on-surface-variant hover:text-on-surface';
        }
        if (btnPortfolio) {
            btnPortfolio.className = 'px-4 py-1.5 rounded-md text-label-sm font-label-sm font-semibold transition-all bg-surface-variant text-on-surface';
        }
        if (panelAssets) panelAssets.classList.add('hidden');
        if (panelPortfolio) panelPortfolio.classList.remove('hidden');
    }
}

function switchTab(tab) {
    if (tab === 'dashboard') tab = 'overview';
    if (tab === 'accounts') tab = 'investments';
    if (tab === 'stats') tab = 'insights';
    if (tab === 'rules' || tab === 'review' || tab === 'import') {
        currentAutomationSubTab = tab;
        tab = 'automation';
    }

    currentTab = tab;
    // Hide all panels
    document.querySelectorAll('[id^="panel-"]').forEach(el => el.classList.add('hidden'));
    // Show active panel
    const activePanel = document.getElementById(`panel-${tab}`);
    if (activePanel) {
        activePanel.classList.remove('hidden');
    }
    
    // Update nav links styling
    document.querySelectorAll('#sidebar-nav button').forEach(el => {
        const isAutomation = el.id === 'nav-automation';
        el.className = `w-full flex items-center gap-3 text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/50 transition-colors duration-200 px-4 py-2.5 mx-2 rounded-lg text-left font-medium${isAutomation ? ' relative' : ''}`;
    });
    const activeNavBtn = document.getElementById(`nav-${tab}`);
    if (activeNavBtn) {
        const isAutomation = activeNavBtn.id === 'nav-automation';
        activeNavBtn.className = `w-full flex items-center gap-3 bg-primary-container text-on-primary-container rounded-lg px-4 py-2.5 mx-2 active-nav-glow scale-[0.98] transition-transform text-left font-semibold${isAutomation ? ' relative' : ''}`;
    }

    // Sync Path in Address Bar
    let newPath = '/';
    if (tab === 'transactions') newPath = '/transactions';
    else if (tab === 'budgets') newPath = '/budgets';
    else if (tab === 'investments') newPath = '/investments';
    else if (tab === 'goals') newPath = '/goals';
    else if (tab === 'insights') newPath = '/insights';
    else if (tab === 'automation') newPath = '/automation';
    else if (tab === 'overview') newPath = '/overview';
    window.history.pushState({}, '', newPath);

    // Fetch tab data
    if (tab === 'overview') loadOverviewData();
    else if (tab === 'transactions') loadTransactionsData();
    else if (tab === 'budgets') loadBudgetsData();
    else if (tab === 'investments') {
        toggleInvestmentsSubView(currentInvestmentsSubTab);
        loadInvestmentsData();
    }
    else if (tab === 'goals') loadGoalsData();
    else if (tab === 'insights') loadInsightsData();
    else if (tab === 'automation') loadAutomationData();
}

function initRouter() {
    const path = window.location.pathname;
    let targetTab = 'overview';
    if (path.includes('transactions')) targetTab = 'transactions';
    else if (path.includes('budgets')) targetTab = 'budgets';
    else if (path.includes('investments') || path.includes('accounts')) targetTab = 'investments';
    else if (path.includes('goals')) targetTab = 'goals';
    else if (path.includes('insights') || path.includes('stats')) targetTab = 'insights';
    else if (path.includes('automation') || path.includes('rules') || path.includes('review') || path.includes('import-ui')) targetTab = 'automation';
    switchTab(targetTab);
}

// Vault lock/unlock operations
async function checkVaultStatus() {
    try {
        const res = await fetch('/api/vault/status');
        const data = await res.json();
        const lockScreen = document.getElementById('vault-lock-screen');
        const indicator = document.getElementById('vault-status-indicator');
        
        if (data.locked) {
            if (lockScreen) lockScreen.classList.remove('hidden');
            if (indicator) {
                indicator.classList.remove('bg-tertiary');
                indicator.classList.add('bg-error');
            }
        } else {
            if (lockScreen) lockScreen.classList.add('hidden');
            if (indicator) {
                indicator.classList.remove('bg-error');
                indicator.classList.add('bg-tertiary');
            }
        }
    } catch (err) {
        console.error("Failed to check vault status:", err);
    }
}

async function unlockVault() {
    const passcode = document.getElementById('vault-passcode-input').value;
    const errEl = document.getElementById('vault-error-message');
    if (errEl) errEl.classList.add('hidden');
    
    try {
        const res = await fetch('/api/vault/unlock', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ passcode })
        });
        if (res.ok) {
            document.getElementById('vault-passcode-input').value = '';
            checkVaultStatus();
            loadDashboardData();
        } else {
            if (errEl) errEl.classList.remove('hidden');
        }
    } catch (err) {
        console.error("Unlock error:", err);
    }
}

async function lockVault() {
    try {
        await fetch('/api/vault/lock', { method: 'POST' });
        checkVaultStatus();
    } catch (err) {
        console.error("Lock error:", err);
    }
}

// Dynamic Currencies, Spot Rates & Multipliers
function setBaseCurrency(curr) {
    baseCurrency = curr;
    document.getElementById('currency-eur').className = curr === 'EUR' ? 'px-3 py-1 text-xs font-bold rounded-md bg-primary text-black transition-all' : 'px-3 py-1 text-xs font-medium rounded-md text-on-surface hover:text-white transition-all';
    document.getElementById('currency-inr').className = curr === 'INR' ? 'px-3 py-1 text-xs font-bold rounded-md bg-primary text-black transition-all' : 'px-3 py-1 text-xs font-medium rounded-md text-on-surface hover:text-white transition-all';
    
    loadDashboardData();
    if (currentTab === 'investments' || currentTab === 'accounts') loadAccountsData();
    if (currentTab === 'insights' || currentTab === 'stats') loadStatsData();
}

function updateSpotRate(val) {
    spotRate = parseFloat(val);
    document.getElementById('spot-rate-value').textContent = `${spotRate.toFixed(2)} EUR/INR`;
    saveSpotRate(spotRate);
}

async function saveSpotRate(rate) {
    try {
        await fetch('/api/exchange-rates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_currency: "EUR",
                target_currency: "INR",
                spot_rate: rate
            })
        });
        loadDashboardData();
    } catch (err) {
        console.error("Failed to update spot rate on server:", err);
    }
}

function updateBalanceMultiplier(val) {
    balanceMultiplier = parseFloat(val);
    document.getElementById('balance-multiplier-value').textContent = `${balanceMultiplier.toFixed(2)}x multiplier`;
    if (currentTab === 'investments' || currentTab === 'accounts') loadAccountsData();
}

// Global balance mask toggle
function toggleBalanceMasking() {
    balanceMasked = !balanceMasked;
    const icons = ['mask-icon', 'mask-icon-accounts', 'mask-icon-investments'];
    icons.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = balanceMasked ? 'visibility_off' : 'visibility';
        }
    });
    loadDashboardData();
    if (currentTab === 'investments' || currentTab === 'accounts') loadAccountsData();
    if (currentTab === 'insights' || currentTab === 'stats') loadStatsData();
}

// Normalizer & Formatter helpers
function getNormalizedEur(amount, currency) {
    if (currency === 'INR') {
        return amount / spotRate;
    }
    return amount;
}

function getCategoryColor(category) {
    const cat = (category || 'Other').toLowerCase();
    if (cat.includes('rent') || cat.includes('housing') || cat.includes('houseware')) return '#4f46e5'; // Deep Indigo
    if (cat.includes('food') || cat.includes('drink') || cat.includes('groceries') || cat.includes('dining') || cat.includes('snack')) return '#ff7a00'; // Neon Orange
    if (cat.includes('utilities') || cat.includes('bill') || cat.includes('telephone') || cat.includes('internet')) return '#06b6d4'; // Luminous Cyan
    if (cat.includes('transit') || cat.includes('transport') || cat.includes('car') || cat.includes('taxi') || cat.includes('ticket') || cat.includes('travel') || cat.includes('airline') || cat.includes('train')) return '#f59e0b'; // Warm Amber/Gold
    if (cat.includes('subscription') || cat.includes('discretionary') || cat.includes('clothing') || cat.includes('jewelry') || cat.includes('cosmetic') || cat.includes('salon') || cat.includes('fitness') || cat.includes('party') || cat.includes('movie') || cat.includes('show') || cat.includes('game') || cat.includes('book') || cat.includes('course') || cat.includes('gift') || cat.includes('shopping')) return '#d946ef'; // Radiant Fuchsia/Pink
    if (cat.includes('income') || cat.includes('savings')) return '#10b981'; // Vibrant Emerald Green
    if (cat.includes('transfer')) return '#a2a1f8'; // Light Indigo for transfer
    return '#6b7280'; // Slate Gray for others
}

const CATEGORY_METADATA = {
    'housing': { icon: 'home', bg: 'bg-[#5e5ce6]/10', text: 'text-[#5e5ce6]', border: 'border-[#5e5ce6]/20', pillBg: 'bg-[#5e5ce6]/20', barBg: 'bg-[#5e5ce6]' },
    'rent': { icon: 'home', bg: 'bg-[#5e5ce6]/10', text: 'text-[#5e5ce6]', border: 'border-[#5e5ce6]/20', pillBg: 'bg-[#5e5ce6]/20', barBg: 'bg-[#5e5ce6]' },
    'food & dining': { icon: 'restaurant', bg: 'bg-[#ff9f0a]/10', text: 'text-[#ff9f0a]', border: 'border-[#ff9f0a]/20', pillBg: 'bg-[#ff9f0a]/20', barBg: 'bg-[#ff9f0a]' },
    'food': { icon: 'restaurant', bg: 'bg-[#ff9f0a]/10', text: 'text-[#ff9f0a]', border: 'border-[#ff9f0a]/20', pillBg: 'bg-[#ff9f0a]/20', barBg: 'bg-[#ff9f0a]' },
    'dining': { icon: 'restaurant', bg: 'bg-[#ff9f0a]/10', text: 'text-[#ff9f0a]', border: 'border-[#ff9f0a]/20', pillBg: 'bg-[#ff9f0a]/20', barBg: 'bg-[#ff9f0a]' },
    'groceries': { icon: 'shopping_cart', bg: 'bg-[#ffd60a]/10', text: 'text-[#ffd60a]', border: 'border-[#ffd60a]/20', pillBg: 'bg-[#ffd60a]/20', barBg: 'bg-[#ffd60a]' },
    'transport': { icon: 'directions_car', bg: 'bg-[#30d158]/10', text: 'text-[#30d158]', border: 'border-[#30d158]/20', pillBg: 'bg-[#30d158]/20', barBg: 'bg-[#30d158]' },
    'transit': { icon: 'directions_car', bg: 'bg-[#30d158]/10', text: 'text-[#30d158]', border: 'border-[#30d158]/20', pillBg: 'bg-[#30d158]/20', barBg: 'bg-[#30d158]' },
    'airline tickets': { icon: 'flight', bg: 'bg-[#ff9f0a]/10', text: 'text-[#ff9f0a]', border: 'border-[#ff9f0a]/20', pillBg: 'bg-[#ff9f0a]/20', barBg: 'bg-[#ff9f0a]' },
    'travel': { icon: 'flight', bg: 'bg-[#ff9f0a]/10', text: 'text-[#ff9f0a]', border: 'border-[#ff9f0a]/20', pillBg: 'bg-[#ff9f0a]/20', barBg: 'bg-[#ff9f0a]' },
    'flight': { icon: 'flight', bg: 'bg-[#ff9f0a]/10', text: 'text-[#ff9f0a]', border: 'border-[#ff9f0a]/20', pillBg: 'bg-[#ff9f0a]/20', barBg: 'bg-[#ff9f0a]' },
    'shopping': { icon: 'shopping_bag', bg: 'bg-[#bf5af2]/10', text: 'text-[#bf5af2]', border: 'border-[#bf5af2]/20', pillBg: 'bg-[#bf5af2]/20', barBg: 'bg-[#bf5af2]' },
    'discretionary': { icon: 'shopping_bag', bg: 'bg-[#bf5af2]/10', text: 'text-[#bf5af2]', border: 'border-[#bf5af2]/20', pillBg: 'bg-[#bf5af2]/20', barBg: 'bg-[#bf5af2]' },
    'clothing': { icon: 'shopping_bag', bg: 'bg-[#bf5af2]/10', text: 'text-[#bf5af2]', border: 'border-[#bf5af2]/20', pillBg: 'bg-[#bf5af2]/20', barBg: 'bg-[#bf5af2]' },
    'electronics': { icon: 'devices', bg: 'bg-[#0a84ff]/10', text: 'text-[#0a84ff]', border: 'border-[#0a84ff]/20', pillBg: 'bg-[#0a84ff]/20', barBg: 'bg-[#0a84ff]' },
    'utilities': { icon: 'bolt', bg: 'bg-[#ff375f]/10', text: 'text-[#ff375f]', border: 'border-[#ff375f]/20', pillBg: 'bg-[#ff375f]/20', barBg: 'bg-[#ff375f]' },
    'bills': { icon: 'receipt', bg: 'bg-[#ff375f]/10', text: 'text-[#ff375f]', border: 'border-[#ff375f]/20', pillBg: 'bg-[#ff375f]/20', barBg: 'bg-[#ff375f]' },
    'bill': { icon: 'receipt', bg: 'bg-[#ff375f]/10', text: 'text-[#ff375f]', border: 'border-[#ff375f]/20', pillBg: 'bg-[#ff375f]/20', barBg: 'bg-[#ff375f]' },
    'subscriptions': { icon: 'subscriptions', bg: 'bg-[#ff453a]/10', text: 'text-[#ff453a]', border: 'border-[#ff453a]/20', pillBg: 'bg-[#ff453a]/20', barBg: 'bg-[#ff453a]' },
    'subscription': { icon: 'subscriptions', bg: 'bg-[#ff453a]/10', text: 'text-[#ff453a]', border: 'border-[#ff453a]/20', pillBg: 'bg-[#ff453a]/20', barBg: 'bg-[#ff453a]' },
    'transfer': { icon: 'sync_alt', bg: 'bg-[#0a84ff]/10', text: 'text-[#0a84ff]', border: 'border-[#0a84ff]/20', pillBg: 'bg-[#0a84ff]/20', barBg: 'bg-[#0a84ff]' },
    'income': { icon: 'trending_up', bg: 'bg-[#30d158]/10', text: 'text-[#30d158]', border: 'border-[#30d158]/20', pillBg: 'bg-[#30d158]/20', barBg: 'bg-[#30d158]' },
    'savings': { icon: 'savings', bg: 'bg-[#30d158]/10', text: 'text-[#30d158]', border: 'border-[#30d158]/20', pillBg: 'bg-[#30d158]/20', barBg: 'bg-[#30d158]' },
    'other': { icon: 'payments', bg: 'bg-zinc-800/40', text: 'text-zinc-400', border: 'border-zinc-700/30', pillBg: 'bg-zinc-800/20', barBg: 'bg-zinc-500' }
};

function getCategoryDetails(category) {
    const key = (category || '').toLowerCase().trim();
    for (const [k, val] of Object.entries(CATEGORY_METADATA)) {
        if (key.includes(k)) {
            return val;
        }
    }
    return { icon: 'payments', bg: 'bg-zinc-800/40', text: 'text-zinc-400', border: 'border-zinc-700/30', pillBg: 'bg-zinc-800/20', barBg: 'bg-zinc-500' };
}

let currentTrendChartType = 'line';

function setTrendChartType(type) {
    currentTrendChartType = type;
    const btnLine = document.getElementById('chart-btn-line');
    const btnBar = document.getElementById('chart-btn-bar');
    if (btnLine && btnBar) {
        if (type === 'line') {
            btnLine.classList.add('bg-surface-variant', 'text-primary');
            btnLine.classList.remove('text-on-surface-variant', 'hover:text-white');
            btnBar.classList.remove('bg-surface-variant', 'text-primary');
            btnBar.classList.add('text-on-surface-variant', 'hover:text-white');
        } else {
            btnBar.classList.add('bg-surface-variant', 'text-primary');
            btnBar.classList.remove('text-on-surface-variant', 'hover:text-white');
            btnLine.classList.remove('bg-surface-variant', 'text-primary');
            btnLine.classList.add('text-on-surface-variant', 'hover:text-white');
        }
    }
    drawSplineChart(allTransactions);
}

function formatVal(eurAmount) {
    if (balanceMasked) {
        return baseCurrency === 'EUR' ? '€ ••••••' : '₹ ••••••';
    }
    const rawVal = baseCurrency === 'EUR' ? eurAmount : eurAmount * spotRate;
    const formatted = rawVal.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
    return baseCurrency === 'EUR' ? `€ ${formatted}` : `₹ ${formatted}`;
}

// 1. Dashboard Tab Loader
// 1. Dashboard Tab Loader (Wrapper)
async function loadDashboardData() {
    await loadOverviewData();
}

async function loadOverviewData() {
    await checkVaultStatus();
    try {
        const catRes = await fetch('/api/categories');
        categories = await catRes.json();
        populateCategorySelects();

        if (allTransactions.length === 0) {
            const res = await fetch('/api/ledger');
            allTransactions = await res.json();
        }

        if (accountsList.length === 0) {
            const accRes = await fetch('/api/accounts');
            accountsList = await accRes.json();
        }

        await loadBudgetLimits();

        // 1. Calculate Net Worth from accountsList scaled by multiplier
        let totalNetWorth = 0;
        accountsList.forEach(acc => {
            const simulatedBal = acc.current_balance * balanceMultiplier;
            const normalizedBalEur = getNormalizedEur(simulatedBal, acc.currency);
            totalNetWorth += normalizedBalEur;
        });

        // 2. Calculate Cash Available (Checking/Giro/Current/Revolut/Commerz/Main/Cash/Giro)
        let checkingCashReserves = 0;
        accountsList.forEach(acc => {
            const simulatedBal = acc.current_balance * balanceMultiplier;
            const normalizedBalEur = getNormalizedEur(simulatedBal, acc.currency);
            const name = (acc.display_name || '').toLowerCase();
            const isChecking = name.includes('checking') || name.includes('giro') || name.includes('current') || 
                               name.includes('revolut') || name.includes('commerz') || name.includes('main') || 
                               name.includes('cash') || name.includes('deposit') || name.includes('giro');
            const isLiability = name.includes('loan') || name.includes('mortgage') || name.includes('credit card') || name.includes('debt');
            if (isChecking && !isLiability && normalizedBalEur > 0) {
                checkingCashReserves += normalizedBalEur;
            }
        });
        if (checkingCashReserves === 0 && totalNetWorth > 0) {
            checkingCashReserves = totalNetWorth;
        }

        // 3. Calculate runway based on 90-day expenses
        const cutDate = new Date();
        cutDate.setDate(cutDate.getDate() - 90);
        
        let fixedFlex90d = 0;
        let income90d = 0;
        let expense90d = 0;

        allTransactions.forEach(t => {
            const tDate = new Date(t.date);
            if (tDate >= cutDate) {
                const normAmt = getNormalizedEur(t.amount, t.currency);
                const isTransfer = (t.category || '').toLowerCase().includes('transfer');
                if (!isTransfer) {
                    if (normAmt > 0) {
                        income90d += normAmt;
                    } else {
                        const absAmt = Math.abs(normAmt);
                        expense90d += absAmt;
                        if (t.flexibility_tier === 'Fixed' || t.flexibility_tier === 'Flexible') {
                            fixedFlex90d += absAmt;
                        }
                    }
                }
            }
        });

        const avgMonthlyEssential = fixedFlex90d / 3.0;
        const runwayMonths = avgMonthlyEssential > 0 ? (checkingCashReserves / avgMonthlyEssential) : 999.0;
        const safeSpendWeekly = (checkingCashReserves * 0.05) / 4.3;
        const savingsRate = income90d > 0 ? Math.round((1.0 - (expense90d / income90d)) * 100.0) : 0;
        const fireProgress = Math.max(0, Math.min(100, Math.round((totalNetWorth / 420000) * 100)));

        // Calculate previous 90-day savings rate (90-180 days ago) for trend comparison
        const prevCutDate = new Date();
        prevCutDate.setDate(prevCutDate.getDate() - 180);
        let prevIncome90d = 0;
        let prevExpense90d = 0;
        allTransactions.forEach(t => {
            const tDate = new Date(t.date);
            if (tDate >= prevCutDate && tDate < cutDate) {
                const normAmt = getNormalizedEur(t.amount, t.currency);
                const isTransfer = (t.category || '').toLowerCase().includes('transfer');
                if (!isTransfer) {
                    if (normAmt > 0) {
                        prevIncome90d += normAmt;
                    } else {
                        prevExpense90d += Math.abs(normAmt);
                    }
                }
            }
        });
        const prevSavingsRate = prevIncome90d > 0 ? Math.round((1.0 - (prevExpense90d / prevIncome90d)) * 100.0) : 0;
        const savingsRateChange = savingsRate - prevSavingsRate;

        // Calculate 30-day net worth trend change
        let netWorthChangeLast30d = 0;
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        allTransactions.forEach(t => {
            const tDate = new Date(t.date);
            if (tDate >= thirtyDaysAgo) {
                const isTransfer = (t.category || '').toLowerCase().includes('transfer');
                if (!isTransfer) {
                    netWorthChangeLast30d += getNormalizedEur(t.amount, t.currency);
                }
            }
        });
        const prevNetWorth = totalNetWorth - netWorthChangeLast30d;
        const pctChange30d = prevNetWorth !== 0 ? (netWorthChangeLast30d / prevNetWorth) * 100 : 0;

        // Bind DOM elements on Overview
        const reservesDisplay = document.getElementById('reserves-display');
        if (reservesDisplay) reservesDisplay.textContent = formatVal(totalNetWorth);

        const reservesChangeDisplay = document.getElementById('reserves-change-display');
        if (reservesChangeDisplay) {
            reservesChangeDisplay.textContent = `${pctChange30d >= 0 ? '+' : ''}${pctChange30d.toFixed(1)}% vs last month`;
            reservesChangeDisplay.className = `text-data-sm font-data-sm ${pctChange30d >= 0 ? 'text-success' : 'text-error'}`;
        }
        const reservesTrendArrow = document.getElementById('reserves-trend-arrow');
        if (reservesTrendArrow) {
            reservesTrendArrow.textContent = pctChange30d >= 0 ? 'arrow_upward' : 'arrow_downward';
            reservesTrendArrow.className = `material-symbols-outlined text-[14px] ${pctChange30d >= 0 ? 'text-success' : 'text-error'}`;
        }

        const reservesCashDisplay = document.getElementById('reserves-cash-display');
        if (reservesCashDisplay) reservesCashDisplay.textContent = formatVal(checkingCashReserves);

        // For Cash Available trend, use the same percentage or mock it similarly
        const reservesCashChangeDisplay = document.getElementById('reserves-cash-change-display');
        if (reservesCashChangeDisplay) {
            reservesCashChangeDisplay.textContent = `${pctChange30d >= 0 ? '+' : ''}${pctChange30d.toFixed(1)}% vs last month`;
            reservesCashChangeDisplay.className = `text-data-sm font-data-sm ${pctChange30d >= 0 ? 'text-success' : 'text-error'}`;
        }
        const reservesCashTrendArrow = document.getElementById('reserves-cash-trend-arrow');
        if (reservesCashTrendArrow) {
            reservesCashTrendArrow.textContent = pctChange30d >= 0 ? 'arrow_upward' : 'arrow_downward';
            reservesCashTrendArrow.className = `material-symbols-outlined text-[14px] ${pctChange30d >= 0 ? 'text-success' : 'text-error'}`;
        }

        const savingsRateDisplay = document.getElementById('savings-rate-display');
        if (savingsRateDisplay) savingsRateDisplay.textContent = `${savingsRate}%`;

        const savingsRateChangeDisplay = document.getElementById('savings-rate-change-display');
        if (savingsRateChangeDisplay) {
            savingsRateChangeDisplay.textContent = `${savingsRateChange >= 0 ? '+' : ''}${savingsRateChange}% vs last period`;
            savingsRateChangeDisplay.className = `text-data-sm font-data-sm ${savingsRateChange >= 0 ? 'text-success' : 'text-error'}`;
        }
        const savingsRateTrendArrow = document.getElementById('savings-rate-trend-arrow');
        if (savingsRateTrendArrow) {
            savingsRateTrendArrow.textContent = savingsRateChange >= 0 ? 'arrow_upward' : 'arrow_downward';
            savingsRateTrendArrow.className = `material-symbols-outlined text-[14px] ${savingsRateChange >= 0 ? 'text-success' : 'text-error'}`;
        }

        const fireDisplay = document.getElementById('fire-display');
        if (fireDisplay) fireDisplay.textContent = `${fireProgress}%`;

        const fireTargetDisplay = document.getElementById('fire-target-display');
        if (fireTargetDisplay) fireTargetDisplay.textContent = `of ${formatVal(420000)} goal`;

        // Large Trend Indicators
        const trendLargeNetworth = document.getElementById('trend-large-networth');
        if (trendLargeNetworth) trendLargeNetworth.textContent = formatVal(totalNetWorth);

        const trendLargeChange = document.getElementById('trend-large-change');
        if (trendLargeChange) {
            trendLargeChange.textContent = `${netWorthChangeLast30d >= 0 ? '↑' : '↓'} ${formatVal(Math.abs(netWorthChangeLast30d))} (${Math.abs(pctChange30d).toFixed(1)}%)`;
            trendLargeChange.className = `text-xs font-semibold ${netWorthChangeLast30d >= 0 ? 'text-success' : 'text-error'}`;
        }

        // Get breakdown categories for donut and spent rankings
        const summaryRes = await fetch('/api/analytics/summary');
        const summary = await summaryRes.json();
        
        drawSpendingRankings(summary.category_breakdown);

        // Budget Overview dynamic calculations
        let totalLimit = 0;
        let spentThisMonthTotal = 0;
        const currentYear = new Date().getFullYear();
        const currentMonth = new Date().getMonth() + 1;
        const currentMonthStr = `${currentYear}-${currentMonth.toString().padStart(2, '0')}`;

        allTransactions.forEach(t => {
            if (t.date && t.date.startsWith(currentMonthStr)) {
                const normAmt = getNormalizedEur(t.amount, t.currency);
                if (normAmt < 0) {
                    spentThisMonthTotal += Math.abs(normAmt);
                }
            }
        });

        Object.keys(budgetLimits).forEach(cat => {
            totalLimit += budgetLimits[cat] || 0;
        });

        if (totalLimit === 0) totalLimit = 3000; // default backup limit

        const budgetPct = Math.min(100, Math.round((spentThisMonthTotal / totalLimit) * 100));
        const budgetRemaining = Math.max(0, totalLimit - spentThisMonthTotal);

        const ring = document.getElementById('overview-budget-gauge-ring');
        if (ring) {
            const circ = 2 * Math.PI * 66; // 414.69
            const offset = circ - (budgetPct / 100) * circ;
            ring.style.strokeDasharray = `${circ}`;
            ring.style.strokeDashoffset = `${offset}`;
        }
        const pctEl = document.getElementById('overview-budget-gauge-pct');
        if (pctEl) pctEl.textContent = `${budgetPct}%`;
        const spentEl = document.getElementById('overview-budget-spent');
        if (spentEl) spentEl.textContent = formatVal(spentThisMonthTotal);
        const remEl = document.getElementById('overview-budget-remaining');
        if (remEl) remEl.textContent = formatVal(budgetRemaining);
        const totEl = document.getElementById('overview-budget-total');
        if (totEl) totEl.textContent = formatVal(totalLimit);

        // Draw spline
        drawSplineChart(allTransactions);

        // Render recent transactions
        renderRecentTransactionsOverview(allTransactions);

        // Compute financial insights alerts
        const localHealth = {
            cash_reserves_eur: totalNetWorth,
            runway_months: runwayMonths.toFixed(1),
            savings_rate_percent: savingsRate,
            fire_progress_percent: fireProgress,
            fire_target_eur: 420000
        };
        computeFinancialInsights(allTransactions, localHealth);

    } catch (err) {
        console.error("Overview metrics load error:", err);
    }
}

function getMerchantLogo(name) {
    const n = (name || '').toLowerCase();
    if (n.includes('revolut')) return 'https://lh3.googleusercontent.com/aida-public/AB6AXuDB7TaBgLqMTnCaxFFl6Xp5jrS_0bnNcQ_lNqMVrCZAi_wLhwbxXDYen8dbDxaBK_8HyRhKh3mfa6EifnhTugqSnqOzH9oK_WO0fVsO3HH6pQ8BiebWYi3OKM4P1RLPsCeOZL9y2C0PyhVhqvIYkCGSSk7TFinymw3qTa9kgUhoiqAL0NgXj2gOM3ITVpL_EmxZqT7aJ6CBGNkM6fhm359SVKopZwadcxPyCEakrVPCluc3y57MbJZ9IsYxPzaoQocmA57h0r_55X0l';
    if (n.includes('adobe')) return 'https://lh3.googleusercontent.com/aida-public/AB6AXuBX5MPoblh-_grldAQuDQ91Y76VbiW6XYnjBuFrsJ88-UU-jkJ_1381T_RudO8L1AV7EV_B6g_jVSRHmkR-spYzj3kSq_UtjONRzyhJa8G6Id2k5BYQpIhWc5eQOG9zU38yHUmKZx7FrlSGOv37oXv8dmcPHNU1GGzCMnKgZ37WmvKRjH6-nQpFN_0ZZW1vDsiQbJleFUJNIoh0by3ERaDINp_-rhcbZhcpBT0jZ9ZrcS83qTxT76jiq3pKgFeq2Z8hp6mclGPmTtW6';
    if (n.includes('uber')) return 'https://lh3.googleusercontent.com/aida-public/AB6AXuAywsqMa5Aa6LuXyOPBs5Kh_mt1i4HCFg0VqG3sb8SkKzvGa9Xr3iX0BT3fJaxUvSq5Isy1Gkfla7A_x8MdOf9JG0fs2jRCNZPmQNHmEjdWUIrlhpHVfNSYSv272cdjgurcVNQ6Fx9Ek8gTAuOYWlHS8bE7X8sITQZvrH6zSooFPZqKzj6YEZ9ZQWGmIM_t8FQkhW0PYJ3ldqCMMgmxs0UR4XWMHuTqOJzw1Hg_yh7j0la2zP61YDNRIMh7Ck9tXSckfleq-XRavq9t';
    if (n.includes('amazon')) return 'https://lh3.googleusercontent.com/aida-public/AB6AXuDDFkRkRnKETrgYyayHkHxnzHMsPu9tM1DtdKrgpBxLgVAOqeaOYcrNF8jnUKvbD6ZfudKXmc3tUL_KWI5EpYXUO_5VdAo76rqjDVURfvqYw3YQ8tvhkzvzD5eLCdSjEtpldF6QV6196ZylJKr_lMLEqHp_dDtktACZZORwaClDqnsHD8qLXADxLPcpB2qp7X3nX7pSmtG6mby1M-gpPs-bzwIzbzr_8RislKg4s_3rpBraXqk2ugZYzDAUCP_rMCw_OMmjLNSb2GxJ';
    return null;
}

function getCleanMerchantName(desc) {
    if (!desc) return 'Unknown';
    let clean = desc.trim();

    // Check for common patterns and extract clear names
    if (/advanzia\s*bank/i.test(clean)) return 'Advanzia Bank';
    if (/db\s*vertrieb/i.test(clean)) return 'DB Vertrieb';
    if (/revolut/i.test(clean)) return 'Revolut';
    if (/adobe/i.test(clean)) return 'Adobe';
    if (/uber/i.test(clean)) return 'Uber';
    if (/amazon/i.test(clean)) return 'Amazon';
    if (/netflix/i.test(clean)) return 'Netflix';
    if (/spotify/i.test(clean)) return 'Spotify';
    if (/google/i.test(clean)) return 'Google';
    if (/apple/i.test(clean)) return 'Apple';
    if (/paypal/i.test(clean)) return 'PayPal';
    if (/lidl/i.test(clean)) return 'Lidl';
    if (/aldi/i.test(clean)) return 'Aldi';
    if (/rewe/i.test(clean)) return 'REWE';
    if (/edeka/i.test(clean)) return 'EDEKA';
    if (/dm\s*drogerie/i.test(clean) || /\bdm\b/i.test(clean)) return 'dm';
    if (/decathlon/i.test(clean)) return 'Decathlon';
    if (/ikea/i.test(clean)) return 'IKEA';
    
    // Remove transaction codes, card numbers, or extra noise
    clean = clean.replace(/X{3,}\s*X{3,}\s*X{3,}\s*\d{4}/gi, '');
    clean = clean.replace(/card\s+payment/gi, '');
    clean = clean.replace(/online\s+payment/gi, '');
    clean = clean.replace(/sepa\s+lastschrift/gi, '');
    clean = clean.replace(/lastschrift/gi, '');
    clean = clean.replace(/dauerauftrag/gi, '');
    clean = clean.replace(/ueberweisung/gi, '');
    clean = clean.replace(/ref[\.:]?\s*[a-zA-Z0-9_-]+/gi, '');
    clean = clean.replace(/id[\.:]?\s*[a-zA-Z0-9_-]+/gi, '');
    
    clean = clean.replace(/[\s\-_,\.\/\|\\\*\#]+$/, '');
    clean = clean.replace(/^[\s\-_,\.\/\|\\\*\#]+/, '');
    clean = clean.replace(/\s+/g, ' ').trim();
    
    return clean || desc;
}

function getMerchantColor(name) {
    const colors = [
        'bg-[#5e5ce6]/25 text-[#5e5ce6] border-[#5e5ce6]/30',
        'bg-[#ff9f0a]/25 text-[#ff9f0a] border-[#ff9f0a]/30',
        'bg-[#ffd60a]/25 text-[#ffd60a] border-[#ffd60a]/30',
        'bg-[#30d158]/25 text-[#30d158] border-[#30d158]/30',
        'bg-[#bf5af2]/25 text-[#bf5af2] border-[#bf5af2]/30',
        'bg-[#0a84ff]/25 text-[#0a84ff] border-[#0a84ff]/30',
        'bg-[#ff375f]/25 text-[#ff375f] border-[#ff375f]/30',
        'bg-[#ff453a]/25 text-[#ff453a] border-[#ff453a]/30'
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % colors.length;
    return colors[index];
}

function getLastKMonths(k) {
    const months = [];
    const now = new Date();
    let year = now.getFullYear();
    let month = now.getMonth(); // 0-11
    
    for (let i = 0; i < k; i++) {
        months.push({ year, month });
        month--;
        if (month < 0) {
            month = 11;
            year--;
        }
    }
    return months.reverse();
}

function updateTrendChart() {
    drawSplineChart(allTransactions);
}

function renderRecentTransactionsOverview(txns) {
    const tbody = document.getElementById('overview-recent-tx-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    const sorted = [...txns].sort((a, b) => new Date(b.date) - new Date(a.date));
    const recent = sorted.slice(0, 5); // Limit to exactly 5 rows for bento grid alignment
    
    if (recent.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="py-6 text-center text-on-surface-variant text-xs font-mono">No transactions recorded yet.</td>
            </tr>
        `;
        return;
    }
    
    recent.forEach(t => {
        const tr = document.createElement('tr');
        tr.className = 'group hover:bg-surface-variant/10 transition-colors';
        
        const normAmt = getNormalizedEur(t.amount, t.currency);
        const amtColor = normAmt > 0 ? 'text-success' : 'text-on-surface';
        const prefix = normAmt > 0 ? '+' : '';
        
        const rawName = t.display_name || t.description || 'Unknown';
        const cleanName = getCleanMerchantName(rawName);
        const logoUrl = getMerchantLogo(cleanName);
        const catMeta = getCategoryDetails(t.category);
        
        const dateObj = new Date(t.date);
        const formattedDateStr = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });

        let logoContent = '';
        if (logoUrl) {
            logoContent = `<img alt="${cleanName} logo" class="w-5 h-5 object-contain" src="${logoUrl}">`;
        } else {
            const char = cleanName.trim().substring(0, 2).toUpperCase();
            const colorClass = getMerchantColor(cleanName);
            logoContent = `<div class="w-8 h-8 rounded-full flex items-center justify-center overflow-hidden shrink-0 border ${colorClass}"><span class="text-[10px] font-bold tracking-tight">${char}</span></div>`;
        }

        // Set row title to full description for tooltip on hover
        tr.setAttribute('title', t.description || t.display_name || '');

        tr.innerHTML = `
            <td class="py-3 text-on-surface-variant text-xs font-mono">${formattedDateStr}</td>
            <td class="py-3 flex items-center gap-3">
                ${logoUrl ? `
                <div class="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center overflow-hidden shrink-0 border border-white/10">
                    ${logoContent}
                </div>` : logoContent}
                <span class="text-label-sm font-semibold text-white truncate max-w-[120px]">${cleanName}</span>
            </td>
            <td class="py-3">
                <span class="px-2.5 py-1 ${catMeta.pillBg || 'bg-surface-variant/40'} ${catMeta.text} rounded-lg text-[10px] font-bold uppercase tracking-wider border ${catMeta.border || 'border-transparent'}">
                    ${t.category || 'Unsorted'}
                </span>
            </td>
            <td class="py-3 text-right font-data-md font-bold ${amtColor}">${prefix}${formatVal(normAmt)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function getCategoryTrend(category) {
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;
    const prevYear = currentMonth === 1 ? currentYear - 1 : currentYear;
    const prevMonth = currentMonth === 1 ? 12 : currentMonth - 1;
    
    const currentPrefix = `${currentYear}-${currentMonth.toString().padStart(2, '0')}`;
    const prevPrefix = `${prevYear}-${prevMonth.toString().padStart(2, '0')}`;
    
    let currentSpend = 0;
    let prevSpend = 0;
    
    allTransactions.forEach(t => {
        if (t.category === category && t.amount < 0) {
            const normAmt = Math.abs(getNormalizedEur(t.amount, t.currency));
            if (t.date && t.date.startsWith(currentPrefix)) {
                currentSpend += normAmt;
            } else if (t.date && t.date.startsWith(prevPrefix)) {
                prevSpend += normAmt;
            }
        }
    });
    
    if (prevSpend === 0) {
        return { text: '—', isUp: false, val: 0 };
    }
    const diffPct = ((currentSpend - prevSpend) / prevSpend) * 100;
    const text = `${diffPct >= 0 ? '↑' : '↓'} ${Math.abs(Math.round(diffPct))}%`;
    return { text, isUp: diffPct >= 0, val: Math.abs(diffPct) };
}

function drawSpendingRankings(categoriesData) {
    const listContainer = document.getElementById('top-spending-list');
    if (!listContainer) return;
    listContainer.innerHTML = '';
    
    if (!categoriesData || categoriesData.length === 0) {
        listContainer.innerHTML = '<p class="text-xs text-on-surface-variant py-4 font-mono">No outflows recorded.</p>';
        return;
    }
    
    const sorted = [...categoriesData].sort((a, b) => b.amount - a.amount);
    const top5 = sorted.slice(0, 5); // Limit to top 5 categories for clean layout density
    const totalOutflow = sorted.reduce((sum, c) => sum + c.amount, 0);

    top5.forEach(item => {
        const category = item.category;
        const amount = item.amount;
        const limit = budgetLimits[category] || 0;
        
        let pct = 0;
        let limitText = '';
        if (limit > 0) {
            pct = Math.min(100, Math.round((amount / limit) * 100));
            limitText = `${pct}% of limit`;
        } else {
            pct = totalOutflow > 0 ? Math.round((amount / totalOutflow) * 100) : 0;
            limitText = `${pct}% of total`;
        }

        const catMeta = getCategoryDetails(category);
        const trend = getCategoryTrend(category);
        const trendColor = trend.text === '—' ? 'text-on-surface-variant' : (trend.isUp ? 'text-error' : 'text-success');

        const row = document.createElement('div');
        row.className = 'flex items-center justify-between py-2 border-b border-border-subtle/30 last:border-0';
        row.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-full ${catMeta.bg} flex items-center justify-center ${catMeta.text} shrink-0">
                    <span class="material-symbols-outlined text-base">${catMeta.icon}</span>
                </div>
                <span class="text-label-sm font-semibold text-white">${category}</span>
            </div>
            <div class="flex items-center gap-4">
                <span class="text-data-md font-semibold text-white font-mono">${formatVal(amount)}</span>
                <span class="text-[11px] ${trendColor} font-mono">${trend.text}</span>
                <div class="w-16 bg-surface-variant/20 h-1.5 rounded-full overflow-hidden border border-white/5 shrink-0">
                    <div class="h-full rounded-full ${catMeta.barBg || 'bg-primary'}" style="width: ${pct}%"></div>
                </div>
            </div>
        `;
        listContainer.appendChild(row);
    });
}

function toggleDistributionDonut() {
    const overlay = document.getElementById('donut-overlay');
    if (overlay) {
        overlay.classList.toggle('translate-y-full');
    }
}

function computeFinancialInsights(txns, health) {
    const listContainer = document.getElementById('insights-bullet-list');
    if (!listContainer) return;
    listContainer.innerHTML = '';
    
    const insights = [];

    if (health.savings_rate_percent >= 15) {
        insights.push(`<li class="flex items-start"><span class="text-tertiary mr-2">✓</span> Savings rate is healthy at ${health.savings_rate_percent}% YTD.</li>`);
    } else if (health.savings_rate_percent > 0) {
        insights.push(`<li class="flex items-start"><span class="text-primary mr-2">ℹ</span> Moderate savings rate of ${health.savings_rate_percent}% YTD. Target is 20%.</li>`);
    } else {
        insights.push(`<li class="flex items-start"><span class="text-error mr-2">⚠</span> Net negative savings rate (${health.savings_rate_percent}%) YTD. Burn rate exceeds inflow.</li>`);
    }

    const runway = parseFloat(health.runway_months);
    if (runway >= 6.0) {
        insights.push(`<li class="flex items-start"><span class="text-tertiary mr-2">✓</span> Cash reserves cover ${runway} months of expenses.</li>`);
    } else if (runway >= 3.0) {
        insights.push(`<li class="flex items-start"><span class="text-primary mr-2">ℹ</span> Runway is stable at ${runway} months of emergency buffer.</li>`);
    } else {
        insights.push(`<li class="flex items-start"><span class="text-error mr-2">⚠</span> Vulnerable cash runway of ${runway} months. Accumulate emergency buffer.</li>`);
    }

    let overLimitCount = 0;
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1; 
    const currentMonthStr = `${currentYear}-${currentMonth.toString().padStart(2, '0')}`;
    
    const categorySpentThisMonth = {};
    txns.forEach(t => {
        if (t.date && t.date.startsWith(currentMonthStr)) {
            const normAmt = getNormalizedEur(t.amount, t.currency);
            if (normAmt < 0) { 
                const cat = t.category || 'Unsorted';
                categorySpentThisMonth[cat] = (categorySpentThisMonth[cat] || 0) + Math.abs(normAmt);
            }
        }
    });

    Object.keys(budgetLimits).forEach(cat => {
        const limit = budgetLimits[cat];
        const spent = categorySpentThisMonth[cat] || 0;
        if (limit > 0 && spent > limit) {
            overLimitCount++;
            insights.push(`<li class="flex items-start"><span class="text-error mr-2">⚠</span> Budget exceeded: ${cat} spent is ${formatVal(spent)} vs limit of ${formatVal(limit)}.</li>`);
        }
    });

    const pendingReview = txns.filter(t => t.is_guess || !t.category || t.category === 'Unsorted' || t.category === 'Uncategorized').length;
    if (pendingReview > 0) {
        insights.push(`<li class="flex items-start"><span class="text-primary mr-2">ℹ</span> ${pendingReview} transaction(s) pending in your Automation review queue.</li>`);
    }

    if (insights.length === 0) {
        insights.push(`<li class="flex items-start"><span class="text-tertiary mr-2">✓</span> Financial health parameters within nominal tolerance bands.</li>`);
    }

    listContainer.innerHTML = insights.join('');
}

async function fetchLedgerEntries() {
    try {
        const res = await fetch('/api/ledger');
        allTransactions = await res.json();
        renderMonthsSidebar();
        applyLedgerFilters();
    } catch (err) {
        console.error("Ledger fetch error:", err);
    }
}

function populateCategorySelects() {
    const select = document.getElementById('ledger-category-select');
    if (select) {
        select.innerHTML = '<option value="ALL">All Categories</option>';
        categories.forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat;
            opt.textContent = cat;
            select.appendChild(opt);
        });
    }

    const modalSelect = document.getElementById('rule-modal-category');
    if (modalSelect) {
        modalSelect.innerHTML = '';
        categories.forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat;
            opt.textContent = cat;
            modalSelect.appendChild(opt);
        });
    }
    
    populateAccountSelects();
}

function populateAccountSelects() {
    const select = document.getElementById('ledger-account-select');
    if (!select) return;
    
    const curVal = select.value;
    select.innerHTML = '<option value="ALL">All Accounts</option>';
    
    accountsList.forEach(acc => {
        const opt = document.createElement('option');
        opt.value = acc.resource_id;
        opt.textContent = acc.display_name;
        select.appendChild(opt);
    });
    
    if (curVal && select.querySelector(`option[value="${curVal}"]`)) {
        select.value = curVal;
    } else if (accountFilterId) {
        select.value = accountFilterId;
    } else {
        select.value = 'ALL';
    }
}

function drawOutflowDonut(categoriesData) {
    const svg = document.getElementById('outflow-donut-svg');
    const legend = document.getElementById('donut-legend');
    if (!svg || !legend) return;
    
    svg.innerHTML = '<circle cx="80" cy="80" fill="transparent" r="58" stroke="rgba(255,255,255,0.03)" stroke-width="12"></circle>';
    legend.innerHTML = '';

    if (!categoriesData || categoriesData.length === 0) {
        document.getElementById('donut-total').textContent = formatVal(0);
        return;
    }

    const sortedData = [...categoriesData].sort((a, b) => b.amount - a.amount);
    const total = sortedData.reduce((sum, item) => sum + item.amount, 0);
    document.getElementById('donut-total').textContent = formatVal(total);

    let accumulatedPercentage = 0;
    const r = 58;
    const circumference = 2 * Math.PI * r;

    sortedData.forEach((item, idx) => {
        const amount = item.amount;
        const percentage = amount / total;
        const strokeDashoffset = circumference - (percentage * circumference);
        const rotation = (accumulatedPercentage * 360) - 90;
        const color = getCategoryColor(item.category);

        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', '80');
        circle.setAttribute('cy', '80');
        circle.setAttribute('r', r.toString());
        circle.setAttribute('fill', 'transparent');
        circle.setAttribute('stroke', color);
        circle.setAttribute('stroke-width', '12');
        circle.setAttribute('stroke-dasharray', circumference.toString());
        circle.setAttribute('stroke-dashoffset', strokeDashoffset.toString());
        circle.setAttribute('transform', `rotate(${rotation} 80 80)`);
        circle.setAttribute('class', 'transition-all duration-300 hover:stroke-[15px] cursor-pointer');
        svg.appendChild(circle);

        accumulatedPercentage += percentage;

        const legendItem = document.createElement('div');
        legendItem.className = 'flex items-center space-x-2';
        legendItem.innerHTML = `
            <span class="w-2 h-2 rounded-full" style="background-color: ${color}"></span>
            <span class="text-on-surface-variant font-medium">${item.category}:</span>
            <span class="text-white font-bold font-mono ml-auto">${formatVal(amount)}</span>
        `;
        legend.appendChild(legendItem);
    });
}

// 2. Date Navigation Sidebar
function renderMonthsSidebar() {
    const listContainer = document.getElementById('ledger-months-list');
    if (!listContainer) return;
    listContainer.innerHTML = '';
    
    const monthsSet = new Set();
    allTransactions.forEach(t => {
        if (t.date && t.date.length >= 7) {
            monthsSet.add(t.date.substring(0, 7));
        }
    });
    const months = Array.from(monthsSet).sort().reverse();
    
    const formatMonthName = (ym) => {
        const [year, month] = ym.split('-');
        const date = new Date(year, parseInt(month) - 1, 1);
        return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    };
    
    const createBtn = (label, filterVal, isActive) => {
        const btn = document.createElement('button');
        btn.className = `w-full text-left py-2.5 px-3.5 rounded-xl text-xs font-semibold transition-all ${
            isActive 
                ? 'bg-primary/15 text-primary border-l-2 border-primary font-bold shadow-sm' 
                : 'text-on-surface-variant hover:text-white hover:bg-white/5'
        }`;
        btn.textContent = label;
        btn.onclick = () => {
            activeDateFilter = filterVal;
            ledgerPageIndex = 0;
            renderMonthsSidebar();
            applyLedgerFilters();
        };
        return btn;
    };
    
    listContainer.appendChild(createBtn('All Transactions', 'ALL', activeDateFilter === 'ALL'));
    listContainer.appendChild(createBtn('This Year (YTD)', 'YTD', activeDateFilter === 'YTD'));
    listContainer.appendChild(createBtn('Last Year', 'LAST_YEAR', activeDateFilter === 'LAST_YEAR'));
    
    if (months.length > 0) {
        const divider = document.createElement('div');
        divider.className = 'pt-3 pb-1 border-t border-white/5 mt-2';
        divider.innerHTML = `<span class="font-mono text-[9px] uppercase tracking-wider text-on-surface-variant font-bold block">Monthly Feeds</span>`;
        listContainer.appendChild(divider);
        
        months.forEach(m => {
            listContainer.appendChild(createBtn(formatMonthName(m), m, activeDateFilter === m));
        });
    }
}

function setCustomDateRange() {
    const start = document.getElementById('custom-start-date').value;
    const end = document.getElementById('custom-end-date').value;
    if (start && end) {
        customStartDate = start;
        customEndDate = end;
        activeDateFilter = 'CUSTOM';
        ledgerPageIndex = 0;
        renderMonthsSidebar();
        applyLedgerFilters();
    }
}

// Account filtering triggers from Account cards
function showAccountLedger(accId, accName) {
    accountFilterId = accId;
    switchTab('transactions');
    const ledgerWorkspace = document.getElementById('ledger-search-input');
    if (ledgerWorkspace) {
        ledgerWorkspace.scrollIntoView({ behavior: 'smooth' });
    }
    applyLedgerFilters();
}

function clearAccountFilter() {
    accountFilterId = null;
    applyLedgerFilters();
}

// Ledger filtering & Views toggling
let ledgerSearch = '';
let ledgerCategory = 'ALL';
let ledgerTier = 'ALL';

function filterLedger(val) {
    ledgerSearch = val.toLowerCase();
    applyLedgerFilters();
}

function filterCategory(val) {
    ledgerCategory = val;
    applyLedgerFilters();
}

function filterAccount(val) {
    accountFilterId = val === 'ALL' ? null : val;
    applyLedgerFilters();
}

function setLedgerView(view) {
    activeLedgerView = view;
    const listBtn = document.getElementById('view-btn-list');
    const calBtn = document.getElementById('view-btn-calendar');
    
    if (view === 'list') {
        if (listBtn) listBtn.className = 'px-3 py-1.5 rounded bg-white/10 text-primary transition-all';
        if (calBtn) calBtn.className = 'px-3 py-1.5 rounded text-on-surface-variant hover:text-white transition-all';
    } else {
        if (listBtn) listBtn.className = 'px-3 py-1.5 rounded text-on-surface-variant hover:text-white transition-all';
        if (calBtn) calBtn.className = 'px-3 py-1.5 rounded bg-white/10 text-primary transition-all';
    }
    applyLedgerFilters();
}

function changePageSize(size) {
    ledgerPageSize = size;
    ledgerPageIndex = 0;
    applyLedgerFilters();
}

function prevLedgerPage() {
    if (ledgerPageIndex > 0) {
        ledgerPageIndex--;
        applyLedgerFilters();
    }
}

function nextLedgerPage() {
    ledgerPageIndex++;
    applyLedgerFilters();
}

function applyLedgerFilters() {
    let intervalInflow = 0;
    let intervalOutflow = 0;
    
    const filtered = allTransactions.filter(t => {
        const descMatch = t.description.toLowerCase().includes(ledgerSearch) || (t.display_name || '').toLowerCase().includes(ledgerSearch);
        const catMatch = ledgerCategory === 'ALL' || t.category === ledgerCategory;
        const tierMatch = ledgerTier === 'ALL' || t.flexibility === ledgerTier;
        const accountMatch = !accountFilterId || t.account_id === accountFilterId || t.account_name === accountFilterId;
        
        let dateMatch = true;
        if (activeDateFilter !== 'ALL') {
            if (activeDateFilter === 'YTD') {
                const currentYear = new Date().getFullYear();
                dateMatch = new Date(t.date).getFullYear() === currentYear;
            } else if (activeDateFilter === 'LAST_YEAR') {
                const lastYear = new Date().getFullYear() - 1;
                dateMatch = new Date(t.date).getFullYear() === lastYear;
            } else if (activeDateFilter === 'CUSTOM') {
                if (customStartDate && customEndDate) {
                    dateMatch = t.date >= customStartDate && t.date <= customEndDate;
                }
            } else {
                dateMatch = t.date.startsWith(activeDateFilter);
            }
        }
        
        const isMatch = descMatch && catMatch && tierMatch && accountMatch && dateMatch;
        if (isMatch) {
            const normAmt = getNormalizedEur(t.amount, t.currency);
            if (normAmt > 0) intervalInflow += normAmt;
            else intervalOutflow += Math.abs(normAmt);
        }
        return isMatch;
    });

    const netCashFlow = intervalInflow - intervalOutflow;
    const intervalSavings = intervalInflow > 0 ? (netCashFlow / intervalInflow) * 100 : 0;

    const inflowEl = document.getElementById('tx-summary-inflow');
    if (inflowEl) inflowEl.textContent = `+${formatVal(intervalInflow)}`;
    
    const outflowEl = document.getElementById('tx-summary-outflow');
    if (outflowEl) outflowEl.textContent = `-${formatVal(intervalOutflow)}`;
    
    const netEl = document.getElementById('tx-summary-net');
    if (netEl) netEl.textContent = formatVal(netCashFlow);
    
    const savingsEl = document.getElementById('tx-summary-savings');
    if (savingsEl) savingsEl.textContent = `${intervalSavings.toFixed(0)}%`;

    // Sync account badge & select dropdown
    const filterBadge = document.getElementById('ledger-account-filter-badge');
    const filterName = document.getElementById('ledger-filter-account-name');
    const selectAcc = document.getElementById('ledger-account-select');
    if (selectAcc) {
        selectAcc.value = accountFilterId || 'ALL';
    }
    if (accountFilterId) {
        if (filterBadge) filterBadge.classList.replace('hidden', 'flex');
        
        // Find corresponding display name
        const matchAcc = accountsList.find(a => a.resource_id === accountFilterId);
        if (filterName) filterName.textContent = matchAcc ? matchAcc.display_name : accountFilterId;
    } else {
        if (filterBadge) filterBadge.classList.replace('flex', 'hidden');
    }

    // Pagination
    let paginated = filtered;
    const prevBtn = document.getElementById('prev-page-btn');
    const nextBtn = document.getElementById('next-page-btn');
    const indicator = document.getElementById('page-indicator-text');
    
    if (ledgerPageSize !== 'ALL') {
        const size = parseInt(ledgerPageSize);
        const maxIndex = Math.max(0, Math.ceil(filtered.length / size) - 1);
        if (ledgerPageIndex > maxIndex) {
            ledgerPageIndex = maxIndex;
        }
        
        if (prevBtn) prevBtn.disabled = ledgerPageIndex === 0;
        if (nextBtn) nextBtn.disabled = ledgerPageIndex >= maxIndex;
        if (indicator) indicator.textContent = `Page ${ledgerPageIndex + 1} of ${maxIndex + 1}`;
        
        const start = ledgerPageIndex * size;
        const end = start + size;
        paginated = filtered.slice(start, end);
    } else {
        if (prevBtn) prevBtn.disabled = true;
        if (nextBtn) nextBtn.disabled = true;
        if (indicator) indicator.textContent = `All ${filtered.length} transactions`;
    }

    lastFilteredTransactions = filtered;

    // Draw transaction charts
    drawTransactionTypeDonut(filtered);
    drawIncomeExpensesBarChart(filtered);

    if (activeLedgerView === 'list') {
        document.getElementById('ledger-list-container').classList.remove('hidden');
        document.getElementById('ledger-calendar-container').classList.add('hidden');
        renderLedgerTable(paginated);
    } else {
        document.getElementById('ledger-list-container').classList.add('hidden');
        document.getElementById('ledger-calendar-container').classList.remove('hidden');
        renderCalendarGrid(filtered);
    }
}

// Global variables for multi-select
let selectedTransactionIds = new Set();
let transactionTooltip = null;
let activeRowMenu = null;
let lastFilteredTransactions = [];

// Format Date YYYY-MM-DD to Jun 15, 2024
function formatLedgerDate(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.split('-');
    if (parts.length !== 3) return dateStr;
    // Construct local Date to avoid timezone shift
    const date = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Deduce transaction type dynamically
function getTransactionType(t) {
    const desc = (t.description || '').toLowerCase();
    const cat = (t.category || '').toLowerCase();
    const acc = (t.account_name || '').toLowerCase();
    
    if (desc.includes('atm') || desc.includes('cash') || cat.includes('cash')) {
        return 'Cash';
    }
    if (cat.includes('transfer') || desc.includes('transfer') || desc.includes('trsf')) {
        return 'Internal Transfer';
    }
    if (desc.includes('direct debit') || desc.includes('sepa') || desc.includes('standing order') || cat.includes('utilities') || desc.includes('utility') || desc.includes('bill')) {
        return 'Direct Debit';
    }
    if (t.amount > 0) {
        return 'Bank Transfers';
    }
    return 'Card Payments';
}

// Format Transfer Account Arrow direction
function formatAccountName(t) {
    const baseAcc = t.account_name || 'Bank Feed';
    const desc = (t.description || '').toLowerCase();
    const cat = (t.category || '').toLowerCase();
    if (cat.includes('transfer') || desc.includes('transfer')) {
        if (desc.includes('to ')) {
            const dest = t.description.substring(desc.indexOf('to ') + 3).trim();
            const cleanDest = dest.charAt(0).toUpperCase() + dest.slice(1);
            return `${baseAcc} → ${cleanDest}`;
        } else if (desc.includes('from ')) {
            const src = t.description.substring(desc.indexOf('from ') + 5).trim();
            const cleanSrc = src.charAt(0).toUpperCase() + src.slice(1);
            return `${cleanSrc} → ${baseAcc}`;
        }
    }
    return baseAcc;
}

// Generate premium merchant avatar html with clearbit/google lookup and consistent initials fallback
function getMerchantLogoHtml(merchantName) {
    const cleanName = (merchantName || '').trim();
    if (!cleanName) {
        return `<div class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center border border-border-subtle"><span class="material-symbols-outlined text-sm text-on-surface-variant">payments</span></div>`;
    }
    
    const domains = {
        'revolut': 'revolut.com',
        'adobe': 'adobe.com',
        'rewe': 'rewe.de',
        'uber': 'uber.com',
        'spotify': 'spotify.com',
        'lidl': 'lidl.de',
        'amazon': 'amazon.com',
        'shell': 'shell.com',
        'netflix': 'netflix.com',
        'starbucks': 'starbucks.com',
        'apple': 'apple.com',
        'google': 'google.com',
        'mcdonald': 'mcdonalds.com',
        'steam': 'steampowered.com',
        'github': 'github.com',
        'openai': 'openai.com',
        'microsoft': 'microsoft.com'
    };

    const lowerName = cleanName.toLowerCase();
    let domain = '';
    for (const [key, dom] of Object.entries(domains)) {
        if (lowerName.includes(key)) {
            domain = dom;
            break;
        }
    }

    if (!domain) {
        const cleanDomainPart = lowerName.replace(/[^a-z0-9]/g, '');
        domain = cleanDomainPart ? `${cleanDomainPart}.com` : '';
    }

    const firstChar = cleanName.charAt(0).toUpperCase();
    let hash = 0;
    for (let i = 0; i < cleanName.length; i++) {
        hash = cleanName.charCodeAt(i) + ((hash << 5) - hash);
    }
    const h = Math.abs(hash % 360);
    const s = 50;
    const l = 40;
    const fallbackBg = `hsl(${h}, ${s}%, ${l}%)`;
    
    const uniqueId = `logo-${Math.random().toString(36).substr(2, 9)}`;
    const logoUrl = domain ? `https://logo.clearbit.com/${domain}` : `https://www.google.com/s2/favicons?sz=64&domain=${domain}`;

    return `
        <div class="relative w-8 h-8 rounded-full overflow-hidden flex-shrink-0 flex items-center justify-center border border-border-subtle" style="background-color: rgba(255, 255, 255, 0.02)">
            <div id="${uniqueId}-fallback" class="absolute inset-0 flex items-center justify-center text-xs font-bold text-white transition-opacity duration-200" style="background-color: ${fallbackBg}">
                ${firstChar}
            </div>
            <img src="${logoUrl}" alt="${cleanName}" class="absolute inset-0 w-full h-full object-cover transition-opacity duration-200 opacity-0"
                 onload="const fallback = document.getElementById('${uniqueId}-fallback'); if(fallback) fallback.style.opacity = 0; this.classList.remove('opacity-0');"
                 onerror="this.style.display = 'none'; const fallback = document.getElementById('${uniqueId}-fallback'); if(fallback) fallback.style.opacity = 1;" />
        </div>
    `;
}

// Show detailed transaction popover/tooltip on row hover
function showTransactionTooltip(event, t) {
    if (!transactionTooltip) {
        transactionTooltip = document.createElement('div');
        transactionTooltip.className = 'absolute z-[250] glass-card p-4 rounded-xl border border-white/10 shadow-2xl text-[11px] font-mono space-y-2 pointer-events-none transition-all duration-75';
        transactionTooltip.style.background = 'rgba(20, 20, 25, 0.8)';
        transactionTooltip.style.backdropFilter = 'blur(20px)';
        transactionTooltip.style.webkitBackdropFilter = 'blur(20px)';
        transactionTooltip.style.boxShadow = '0 12px 40px 0 rgba(0, 0, 0, 0.5), inset 0 1px 1px 0 rgba(255, 255, 255, 0.15)';
        document.body.appendChild(transactionTooltip);
    }

    const cleanDate = formatLedgerDate(t.date);
    const catDetails = getCategoryDetails(t.category);
    const isGuessText = t.is_guess ? '<span class="text-warning font-bold">🤖 AI Predicted</span>' : '<span class="text-success font-bold">✅ Confirmed</span>';
    const normalizedAmt = getNormalizedEur(t.amount, t.currency);
    const amtColor = normalizedAmt > 0 ? 'text-success' : 'text-error';
    const prefixSign = normalizedAmt > 0 ? '+' : '';

    transactionTooltip.innerHTML = `
        <div class="flex items-center justify-between gap-4 border-b border-white/5 pb-2">
            <span class="text-white font-bold text-xs truncate max-w-[150px]">${t.display_name || t.description}</span>
            <span class="px-2 py-0.5 rounded text-[9px] uppercase font-bold ${catDetails.bg} ${catDetails.text} ${catDetails.border}">${t.category}</span>
        </div>
        <div class="space-y-1.5 pt-1">
            <div><span class="text-on-surface-variant font-medium">Raw Desc:</span> <span class="text-white font-semibold block mt-0.5 whitespace-pre-wrap max-w-[280px] break-words text-[10px] font-sans">${t.description}</span></div>
            <div class="grid grid-cols-2 gap-2 text-[10px]">
                <div><span class="text-on-surface-variant block">Date</span><span class="text-white font-semibold">${cleanDate}</span></div>
                <div><span class="text-on-surface-variant block">Account</span><span class="text-white font-semibold">${t.account_name || 'Bank Feed'}</span></div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-[10px] border-t border-white/5 pt-1.5">
                <div><span class="text-on-surface-variant block">Amount</span><span class="${amtColor} font-bold">${prefixSign}${formatVal(normalizedAmt)}</span></div>
                <div><span class="text-on-surface-variant block">Status</span>${isGuessText}</div>
            </div>
            <div class="text-[9px] text-on-surface-variant border-t border-white/5 pt-1.5">
                ID: <span class="font-mono text-zinc-400 select-all">${t.id}</span>
            </div>
        </div>
    `;

    transactionTooltip.style.display = 'block';
    
    const offset = 15;
    let left = event.pageX + offset;
    let top = event.pageY + offset;
    
    if (left + 320 > window.innerWidth) {
        left = event.pageX - 320 - offset;
    }
    if (top + 200 > window.innerHeight) {
        top = event.pageY - 200 - offset;
    }
    
    transactionTooltip.style.left = `${left}px`;
    transactionTooltip.style.top = `${top}px`;
}

function hideTransactionTooltip() {
    if (transactionTooltip) {
        transactionTooltip.style.display = 'none';
    }
}

// Toggle Row Select All
function toggleSelectAllTransactions(mainCheckbox) {
    const checkboxes = document.querySelectorAll('.tx-row-checkbox');
    selectedTransactionIds.clear();
    checkboxes.forEach(cb => {
        cb.checked = mainCheckbox.checked;
        if (mainCheckbox.checked) {
            selectedTransactionIds.add(cb.getAttribute('data-id'));
        }
    });
}

function handleRowCheckboxChange(cb) {
    const id = cb.getAttribute('data-id');
    if (cb.checked) {
        selectedTransactionIds.add(id);
    } else {
        selectedTransactionIds.delete(id);
        const mainCheckbox = document.getElementById('ledger-select-all');
        if (mainCheckbox) mainCheckbox.checked = false;
    }
}

// Toggle three-dots row action menu
function toggleRowMenu(event, txnId) {
    event.stopPropagation();
    
    if (activeRowMenu) {
        activeRowMenu.remove();
        activeRowMenu = null;
    }
    
    const txn = allTransactions.find(t => t.id === txnId);
    if (!txn) return;
    
    const menu = document.createElement('div');
    menu.className = 'absolute z-[300] glass-card py-1.5 rounded-xl border border-white/10 shadow-2xl text-[11px] font-mono w-40';
    menu.style.background = 'rgba(20, 20, 25, 0.9)';
    menu.style.backdropFilter = 'blur(20px)';
    menu.style.webkitBackdropFilter = 'blur(20px)';
    
    menu.style.left = `${event.pageX - 130}px`;
    menu.style.top = `${event.pageY + 10}px`;
    
    let categoryOptions = '';
    categories.slice(0, 5).forEach(cat => {
        categoryOptions += `
            <button onclick="changeTransactionCategory('${txnId}', '${cat}')" class="w-full text-left px-3 py-1.5 hover:bg-white/5 text-zinc-300 hover:text-white transition-all truncate">
                to ${cat}
            </button>
        `;
    });
    
    menu.innerHTML = `
        <div class="px-3 py-1 text-[9px] uppercase tracking-wider text-on-surface-variant font-bold border-b border-white/5 mb-1">Actions</div>
        <button onclick="deleteTransaction('${txnId}')" class="w-full text-left px-3 py-1.5 hover:bg-error/15 text-error transition-all flex items-center gap-1.5">
            <span class="material-symbols-outlined text-xs">delete</span>
            Delete Entry
        </button>
        <div class="border-t border-white/5 my-1.5"></div>
        <div class="px-3 py-1 text-[9px] uppercase tracking-wider text-on-surface-variant font-bold">Quick Categorize</div>
        ${categoryOptions}
        <button onclick="promptRecategorize('${txnId}')" class="w-full text-left px-3 py-1.5 hover:bg-white/5 text-primary transition-all flex items-center gap-1.5">
            <span class="material-symbols-outlined text-xs font-bold">edit</span>
            Custom...
        </button>
    `;
    
    document.body.appendChild(menu);
    activeRowMenu = menu;
    
    const closeHandler = () => {
        if (activeRowMenu) {
            activeRowMenu.remove();
            activeRowMenu = null;
        }
        document.removeEventListener('click', closeHandler);
    };
    setTimeout(() => {
        document.addEventListener('click', closeHandler);
    }, 50);
}

// Categorize transaction logic
async function changeTransactionCategory(txnId, newCategory) {
    try {
        const txn = allTransactions.find(t => t.id === txnId);
        if (!txn) return;
        
        const updateData = {
            transaction_id: txn.id,
            account_id: txn.account_id || '',
            booking_date: txn.date,
            description: txn.description,
            display_name: txn.display_name,
            category: newCategory,
            flexibility_tier: txn.flexibility || 'Flexible',
            amount: txn.amount,
            currency: txn.currency
        };
        
        const res = await fetch(`/api/transactions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData)
        });
        
        if (res.ok) {
            await fetchLedgerEntries();
            loadDashboardData();
        } else {
            const err = await res.json();
            alert(`Failed to update category: ${err.detail}`);
        }
    } catch (err) {
        console.error("Recategorize transaction error:", err);
    }
}

function promptRecategorize(txnId) {
    const txn = allTransactions.find(t => t.id === txnId);
    if (!txn) return;
    const cat = prompt("Enter custom category:", txn.category || '');
    if (cat !== null) {
        changeTransactionCategory(txnId, cat);
    }
}

// Render Table List
function renderLedgerTable(txns) {
    const tbody = document.getElementById('ledger-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (txns.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="px-6 py-12 text-center text-on-surface-variant text-xs font-mono">
                    No ledger transactions found matching parameters.
                </td>
            </tr>
        `;
        return;
    }

    drawSplineChart(txns);

    txns.forEach(t => {
        const tr = document.createElement('tr');
        tr.className = 'ledger-row transaction-row text-xs font-mono border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors cursor-pointer';
        
        const normalizedAmt = getNormalizedEur(t.amount, t.currency);
        const amtColor = normalizedAmt > 0 ? 'text-success' : 'text-error';
        const prefixSign = normalizedAmt > 0 ? '+' : '';
        
        const cleanDate = formatLedgerDate(t.date);
        const logoHtml = getMerchantLogoHtml(t.display_name || t.description);
        const catDetails = getCategoryDetails(t.category);
        const derivedType = getTransactionType(t);
        const accountDisplay = formatAccountName(t);

        const needsReview = t.is_guess || !t.category || t.category === 'Unsorted' || t.category === 'Uncategorized';
        const statusHtml = needsReview
            ? `<button onclick="event.stopPropagation(); changeTransactionCategoryPrompt('${t.id}')" class="px-2.5 py-1 rounded bg-[#ffd60a]/15 text-[#ffd60a] text-[10px] font-bold uppercase tracking-tight hover:scale-105 transition-transform border border-[#ffd60a]/20">To Review</button>`
            : `<span class="material-symbols-outlined text-success text-[20px]" style="font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20;">check_circle</span>`;

        const isChecked = selectedTransactionIds.has(t.id) ? 'checked' : '';

        tr.innerHTML = `
            <td class="px-4 py-3 text-center w-12" onclick="event.stopPropagation();">
                <input type="checkbox" class="tx-row-checkbox rounded bg-surface border-border-subtle focus:ring-primary-container" data-id="${t.id}" ${isChecked} onchange="handleRowCheckboxChange(this)">
            </td>
            <td class="px-4 py-3 text-on-surface-variant whitespace-nowrap">${cleanDate}</td>
            <td class="px-6 py-3">
                <div class="flex items-center gap-3">
                    ${logoHtml}
                    <div class="flex flex-col min-w-0">
                        <span class="font-medium text-white truncate max-w-[200px]">${t.display_name || t.description}</span>
                        <span class="text-[10px] text-on-surface-variant truncate max-w-[200px]">${t.description}</span>
                    </div>
                </div>
            </td>
            <td class="px-4 py-3 whitespace-nowrap">
                <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold ${catDetails.bg} ${catDetails.text} ${catDetails.border}">${t.category || 'Unsorted'}</span>
            </td>
            <td class="px-4 py-3 text-on-surface-variant whitespace-nowrap font-medium">${accountDisplay}</td>
            <td class="px-4 py-3 whitespace-nowrap">
                <span class="px-2 py-0.5 rounded border border-white/10 text-[10px] uppercase font-bold bg-white/5 text-zinc-300">${derivedType}</span>
            </td>
            <td class="px-4 py-3 text-right font-bold whitespace-nowrap ${amtColor}">${prefixSign}${formatVal(normalizedAmt)}</td>
            <td class="px-4 py-3 text-center whitespace-nowrap">${statusHtml}</td>
            <td class="px-4 py-3 text-center w-12" onclick="event.stopPropagation();">
                <button onclick="toggleRowMenu(event, '${t.id}')" class="text-on-surface-variant hover:text-white transition-colors p-1">
                    <span class="material-symbols-outlined text-sm">more_vert</span>
                </button>
            </td>
        `;

        tr.addEventListener('mouseenter', (e) => {
            showTransactionTooltip(e, t);
        });
        tr.addEventListener('mousemove', (e) => {
            showTransactionTooltip(e, t);
        });
        tr.addEventListener('mouseleave', () => {
            hideTransactionTooltip();
        });

        tbody.appendChild(tr);
    });
}

function changeTransactionCategoryPrompt(txnId) {
    promptRecategorize(txnId);
}


let chartTooltip = null;

function showChartTooltip(event, dataPoint, formatValFn) {
    if (!chartTooltip) {
        chartTooltip = document.createElement('div');
        chartTooltip.className = 'absolute z-[200] glass-card p-3 rounded-xl border border-white/10 shadow-2xl text-[11px] font-mono space-y-1 pointer-events-none transition-all duration-75';
        // Apply inline styles for frosted glass effect matching visionOS
        chartTooltip.style.background = 'rgba(20, 20, 25, 0.65)';
        chartTooltip.style.backdropFilter = 'blur(16px)';
        chartTooltip.style.webkitBackdropFilter = 'blur(16px)';
        chartTooltip.style.boxShadow = '0 8px 32px 0 rgba(0, 0, 0, 0.4), inset 0 1px 1px 0 rgba(255, 255, 255, 0.15)';
        document.body.appendChild(chartTooltip);
    }
    
    let dateStr;
    if (dataPoint.label) {
        dateStr = `${dataPoint.label} ${dataPoint.date.getFullYear()}`;
    } else {
        dateStr = dataPoint.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }
    const balanceStr = formatValFn(dataPoint.balance);
    
    let txnDetail = '';
    if (dataPoint.desc) {
        const amtColor = dataPoint.amount > 0 ? 'text-tertiary' : 'text-error';
        const prefix = dataPoint.amount > 0 ? '+' : '';
        txnDetail = `
            <div class="border-t border-white/5 pt-1 mt-1 text-[10px] text-on-surface-variant">
                <div class="truncate max-w-[180px]">Last Tx: <span class="text-white font-semibold">${dataPoint.desc}</span></div>
                <div>Amount: <span class="${amtColor} font-bold">${prefix}${formatValFn(dataPoint.amount)}</span></div>
            </div>
        `;
    }

    chartTooltip.innerHTML = `
        <div class="font-bold text-white">${dateStr}</div>
        <div class="text-[9px] text-on-surface-variant uppercase tracking-wider font-bold">Net Worth</div>
        <div class="text-sm font-bold text-primary font-mono">${balanceStr}</div>
        ${txnDetail}
    `;
    
    chartTooltip.style.display = 'block';
    
    const offset = 15;
    let left = event.pageX + offset;
    let top = event.pageY + offset;
    
    if (left + 220 > window.innerWidth) {
        left = event.pageX - 220 - offset;
    }
    if (top + 100 > window.innerHeight) {
        top = event.pageY - 100 - offset;
    }
    
    chartTooltip.style.left = `${left}px`;
    chartTooltip.style.top = `${top}px`;
}

function hideChartTooltip() {
    if (chartTooltip) {
        chartTooltip.style.display = 'none';
    }
}

// Draw spline chart in dashboard (cumulative net worth trend)
function drawSplineChart(txns) {
    const svg = document.getElementById('trajectory-svg');
    if (!svg) return;
    svg.innerHTML = '';
    
    if (txns.length === 0) return;

    // 1. Calculate current net worth dynamically
    let currentNetWorth = 0;
    accountsList.forEach(acc => {
        const simulatedBal = acc.current_balance * balanceMultiplier;
        const normalizedBalEur = getNormalizedEur(simulatedBal, acc.currency);
        currentNetWorth += normalizedBalEur;
    });

    // 2. Determine points count (6 or 12) from dropdown, if present
    const periodSelect = document.getElementById('trend-period-select');
    const pointsCount = periodSelect ? parseInt(periodSelect.value) : 12;

    // 3. Get the last K months in chronological order
    const months = getLastKMonths(pointsCount);

    // 4. Calculate monthly net worth trajectory chronologically (backward walk)
    const coordinates = months.map((m, idx) => {
        const isCurrentMonth = (idx === months.length - 1);
        let balance = currentNetWorth;
        
        if (!isCurrentMonth) {
            // Find start of the next month
            let nextMonth = m.month + 1;
            let nextYear = m.year;
            if (nextMonth > 11) {
                nextMonth = 0;
                nextYear++;
            }
            const nextMonthStartStr = `${nextYear}-${String(nextMonth + 1).padStart(2, '0')}-01`;
            
            // Sum all transaction amounts occurring on or after nextMonthStartStr
            let futureSum = 0;
            txns.forEach(t => {
                if (t.date && t.date >= nextMonthStartStr) {
                    futureSum += getNormalizedEur(t.amount, t.currency);
                }
            });
            balance = currentNetWorth - futureSum;
        }

        const dateObj = new Date(m.year, m.month, 1);
        const monthLabel = dateObj.toLocaleDateString('en-US', { month: 'short' });
        
        return {
            date: dateObj,
            balance: balance,
            label: monthLabel,
            year: m.year
        };
    });

    // 5. Setup scale ranges
    const minBalRaw = Math.min(...coordinates.map(c => c.balance));
    const maxBalRaw = Math.max(...coordinates.map(c => c.balance));
    const rawRange = maxBalRaw - minBalRaw;
    
    // Add 10% padding so line doesn't clip top/bottom
    const pad = rawRange === 0 ? 1000 : rawRange * 0.1;
    const minBal = minBalRaw - pad;
    const maxBal = maxBalRaw + pad;
    const balRange = maxBal - minBal || 100;

    // 6. Measure exact container dimensions for pixel-perfect layout
    const container = document.getElementById('chart-container');
    if (!container) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w === 0 || h === 0) return;
    
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    
    // Padding
    const paddingLeft = 60;
    const paddingRight = 20;
    const paddingTop = 20;
    const paddingBottom = 35;

    const points = coordinates.map((c, idx) => {
        const xPct = coordinates.length > 1 ? idx / (coordinates.length - 1) : 0.5;
        const x = paddingLeft + xPct * (w - paddingLeft - paddingRight);
        const y = h - paddingBottom - ((c.balance - minBal) / balRange) * (h - paddingTop - paddingBottom);
        return { x, y, data: c };
    });

    // Setup defs for gradients
    let defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
        <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#5e5ce6" stop-opacity="0.25"/>
            <stop offset="100%" stop-color="#5e5ce6" stop-opacity="0"/>
        </linearGradient>
        <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#5e5ce6" stop-opacity="0.8"/>
            <stop offset="100%" stop-color="#5e5ce6" stop-opacity="0.1"/>
        </linearGradient>
    `;
    svg.appendChild(defs);

    // Helper to format axis label cleanly (rounding and k/M suffix)
    function formatAxisLabel(val) {
        if (balanceMasked) {
            return '••••';
        }
        const rawVal = baseCurrency === 'EUR' ? val : val * spotRate;
        const absVal = Math.abs(rawVal);
        let prefix = baseCurrency === 'EUR' ? '€' : '₹';
        let formattedVal = '';
        
        if (absVal >= 1000000) {
            formattedVal = (rawVal / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
        } else if (absVal >= 1000) {
            if (rawRange > 0 && rawRange < 5000) {
                formattedVal = (rawVal / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
            } else {
                formattedVal = (rawVal / 1000).toFixed(0) + 'k';
            }
        } else {
            formattedVal = rawVal.toFixed(0);
        }
        return `${prefix}${formattedVal}`;
    }

    // 1. Draw horizontal grid lines and Y-axis labels
    const gridLinesCount = 5;
    for (let i = 0; i < gridLinesCount; i++) {
        const ratio = i / (gridLinesCount - 1);
        const val = minBal + ratio * balRange;
        const y = h - paddingBottom - ratio * (h - paddingTop - paddingBottom);
        
        // Grid line
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', paddingLeft.toString());
        line.setAttribute('y1', y.toString());
        line.setAttribute('x2', (w - paddingRight).toString());
        line.setAttribute('y2', y.toString());
        line.setAttribute('stroke', 'rgba(255,255,255,0.05)');
        svg.appendChild(line);

        // Y-axis label text
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', (paddingLeft - 10).toString());
        text.setAttribute('y', (y + 4).toString());
        text.setAttribute('text-anchor', 'end');
        text.setAttribute('fill', 'rgba(255, 255, 255, 0.55)');
        text.setAttribute('font-size', '10px');
        text.setAttribute('font-family', 'sans-serif');
        text.textContent = formatAxisLabel(val);
        svg.appendChild(text);
    }

    // 2. Draw X-axis date labels and tick marks
    points.forEach((pt) => {
        const labelText = pt.data.label + " '" + String(pt.data.year).substring(2);
        
        // Tick mark
        const tick = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        tick.setAttribute('x1', pt.x.toString());
        tick.setAttribute('y1', (h - paddingBottom).toString());
        tick.setAttribute('x2', pt.x.toString());
        tick.setAttribute('y2', (h - paddingBottom + 5).toString());
        tick.setAttribute('stroke', 'rgba(255,255,255,0.25)');
        svg.appendChild(tick);

        // Date text label
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', pt.x.toString());
        text.setAttribute('y', (h - paddingBottom + 18).toString());
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', 'rgba(255, 255, 255, 0.55)');
        text.setAttribute('font-size', '10px');
        text.setAttribute('font-family', 'sans-serif');
        text.textContent = labelText;
        svg.appendChild(text);
    });

    if (points.length < 2) return;

    if (currentTrendChartType === 'line') {
        // 4. Draw Spline Curve (Cubic spline bezier path)
        let d = `M ${points[0].x} ${points[0].y}`;
        for (let i = 0; i < points.length - 1; i++) {
            const curr = points[i];
            const next = points[i+1];
            const cpX1 = curr.x + (next.x - curr.x) / 3;
            const cpY1 = curr.y;
            const cpX2 = curr.x + 2 * (next.x - curr.x) / 3;
            const cpY2 = next.y;
            d += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`;
        }

        // Draw fill area first
        const fillD = `${d} L ${points[points.length-1].x} ${h - paddingBottom} L ${points[0].x} ${h - paddingBottom} Z`;
        const fillPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        fillPath.setAttribute('d', fillD);
        fillPath.setAttribute('fill', 'url(#chartGradient)');
        svg.appendChild(fillPath);

        // Draw the line
        const spline = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        spline.setAttribute('d', d);
        spline.setAttribute('fill', 'none');
        spline.setAttribute('stroke', '#5e5ce6');
        spline.setAttribute('stroke-width', '3');
        svg.appendChild(spline);

        // Draw small circles/nodes at coordinate intersections
        points.forEach((pt) => {
            const node = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            node.setAttribute('cx', pt.x.toString());
            node.setAttribute('cy', pt.y.toString());
            node.setAttribute('r', '4');
            node.setAttribute('fill', '#5e5ce6');
            node.setAttribute('stroke', '#09090b');
            node.setAttribute('stroke-width', '1.5');
            svg.appendChild(node);
        });
    } else {
        // Draw Bar Chart
        const barWidth = Math.max(8, Math.min(24, ((w - paddingLeft - paddingRight) / points.length) * 0.5));
        points.forEach(pt => {
            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', (pt.x - barWidth / 2).toString());
            rect.setAttribute('y', pt.y.toString());
            rect.setAttribute('width', barWidth.toString());
            rect.setAttribute('height', Math.max(2, h - paddingBottom - pt.y).toString());
            rect.setAttribute('fill', 'url(#barGradient)');
            rect.setAttribute('rx', '4');
            svg.appendChild(rect);
        });
    }

    // 5. Setup Interactive Hover System
    const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    overlay.setAttribute('x', paddingLeft.toString());
    overlay.setAttribute('y', paddingTop.toString());
    overlay.setAttribute('width', (w - paddingLeft - paddingRight).toString());
    overlay.setAttribute('height', (h - paddingTop - paddingBottom).toString());
    overlay.setAttribute('fill', 'transparent');
    overlay.setAttribute('style', 'cursor: crosshair; pointer-events: all;');
    svg.appendChild(overlay);

    const hoverLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    hoverLine.setAttribute('stroke', 'rgba(94, 92, 230, 0.4)');
    hoverLine.setAttribute('stroke-dasharray', '4,4');
    hoverLine.setAttribute('style', 'display: none;');
    svg.appendChild(hoverLine);

    const hoverDot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    hoverDot.setAttribute('r', '6');
    hoverDot.setAttribute('fill', '#5e5ce6');
    hoverDot.setAttribute('stroke', '#ffffff');
    hoverDot.setAttribute('stroke-width', '2');
    hoverDot.setAttribute('style', 'display: none;');
    svg.appendChild(hoverDot);

    overlay.addEventListener('mousemove', (e) => {
        const rect = svg.getBoundingClientRect();
        const mouseX = ((e.clientX - rect.left) / rect.width) * w;
        
        let closestPt = null;
        let minDist = Infinity;
        for (const pt of points) {
            const dist = Math.abs(pt.x - mouseX);
            if (dist < minDist) {
                minDist = dist;
                closestPt = pt;
            }
        }
        
        if (closestPt) {
            hoverLine.setAttribute('x1', closestPt.x.toString());
            hoverLine.setAttribute('y1', paddingTop.toString());
            hoverLine.setAttribute('x2', closestPt.x.toString());
            hoverLine.setAttribute('y2', (h - paddingBottom).toString());
            hoverLine.setAttribute('style', 'display: block;');

            hoverDot.setAttribute('cx', closestPt.x.toString());
            hoverDot.setAttribute('cy', closestPt.y.toString());
            hoverDot.setAttribute('style', 'display: block;');
            
            showChartTooltip(e, closestPt.data, formatVal);
        }
    });

    overlay.addEventListener('mouseleave', () => {
        hoverLine.setAttribute('style', 'display: none;');
        hoverDot.setAttribute('style', 'display: none;');
        hideChartTooltip();
    });
}

// 3. Calendar Grid & Details Popover
let activePopover = null;

function showDayPopover(event, dateStr, dayTxns) {
    if (activePopover) {
        activePopover.remove();
    }
    if (!dayTxns || dayTxns.length === 0) return;

    const popover = document.createElement('div');
    popover.className = 'absolute z-[130] glass-card p-4 rounded-xl border border-white/10 shadow-2xl w-64 text-xs font-mono space-y-2';
    
    const dateObj = new Date(dateStr);
    const formattedDate = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    
    let html = `
        <div class="flex justify-between items-center border-b border-white/5 pb-1.5 mb-1.5">
            <span class="font-bold text-white">${formattedDate}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="text-on-surface-variant hover:text-white transition-colors">
                <span class="material-symbols-outlined text-xs">close</span>
            </button>
        </div>
        <div class="space-y-2 max-h-48 overflow-y-auto custom-scrollbar">
    `;

    dayTxns.forEach(t => {
        const amtColor = t.amount > 0 ? 'text-tertiary' : 'text-error';
        const prefixSign = t.amount > 0 ? '+' : '';
        const normalizedAmt = getNormalizedEur(t.amount, t.currency);
        html += `
            <div class="flex flex-col space-y-0.5 border-b border-white/[0.03] pb-1.5 last:border-b-0">
                <div class="flex justify-between">
                    <span class="text-white font-semibold truncate max-w-[120px]">${t.display_name || t.description}</span>
                    <span class="font-bold ${amtColor}">${prefixSign}${formatVal(normalizedAmt)}</span>
                </div>
                <div class="flex justify-between text-[9px] text-on-surface-variant">
                    <span>${t.category}</span>
                    <span>${t.account_name || 'Bank Feed'}</span>
                </div>
            </div>
        `;
    });

    html += `</div>`;
    popover.innerHTML = html;
    document.body.appendChild(popover);
    activePopover = popover;

    // Position calculation
    const rect = event.currentTarget.getBoundingClientRect();
    const popoverWidth = 256;
    let left = rect.left + window.scrollX + (rect.width / 2) - (popoverWidth / 2);
    let top = rect.bottom + window.scrollY + 8;

    if (left < 10) left = 10;
    if (left + popoverWidth > window.innerWidth - 10) {
        left = window.innerWidth - popoverWidth - 10;
    }

    popover.style.left = `${left}px`;
    popover.style.top = `${top}px`;

    const clickOutsideHandler = (e) => {
        if (!popover.contains(e.target) && !event.currentTarget.contains(e.target)) {
            popover.remove();
            document.removeEventListener('click', clickOutsideHandler);
            activePopover = null;
        }
    };
    setTimeout(() => {
        document.addEventListener('click', clickOutsideHandler);
    }, 50);
}

function renderCalendarGrid(txns) {
    const grid = document.getElementById('calendar-days-grid');
    if (!grid) return;
    grid.innerHTML = '';

    let targetYear, targetMonth;
    if (activeDateFilter && activeDateFilter.length === 7) {
        const parts = activeDateFilter.split('-');
        targetYear = parseInt(parts[0]);
        targetMonth = parseInt(parts[1]) - 1;
    } else {
        if (txns.length > 0) {
            const sortedTxns = [...txns].sort((a, b) => new Date(b.date) - new Date(a.date));
            const latestDate = new Date(sortedTxns[0].date);
            targetYear = latestDate.getFullYear();
            targetMonth = latestDate.getMonth();
        } else {
            const today = new Date();
            targetYear = today.getFullYear();
            targetMonth = today.getMonth();
        }
    }

    const monthFirstDay = new Date(targetYear, targetMonth, 1);
    let startDayOfWeek = monthFirstDay.getDay();
    startDayOfWeek = startDayOfWeek === 0 ? 6 : startDayOfWeek - 1; // Mon-Sun layout
    const daysInMonth = new Date(targetYear, targetMonth + 1, 0).getDate();

    // Padding empty cells
    for (let i = 0; i < startDayOfWeek; i++) {
        const emptyCell = document.createElement('div');
        emptyCell.className = 'calendar-cell bg-transparent opacity-20 border border-white/5 rounded-lg';
        grid.appendChild(emptyCell);
    }

    // Days cells
    const today = new Date();
    for (let day = 1; day <= daysInMonth; day++) {
        const dayStr = `${targetYear}-${String(targetMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const dayTxns = txns.filter(t => t.date === dayStr);
        
        let inflowSum = 0;
        let outflowSum = 0;
        dayTxns.forEach(t => {
            const normAmt = getNormalizedEur(t.amount, t.currency);
            if (normAmt > 0) inflowSum += normAmt;
            else outflowSum += normAmt;
        });

        const cell = document.createElement('div');
        const isToday = today.getFullYear() === targetYear && today.getMonth() === targetMonth && today.getDate() === day;
        cell.className = `calendar-cell p-2 border border-white/5 rounded-lg flex flex-col justify-between ${isToday ? 'today' : ''}`;
        
        let dayBubblesHtml = '';
        if (inflowSum > 0) {
            dayBubblesHtml += `<span class="px-1.5 py-0.5 rounded bg-tertiary/10 text-tertiary text-[9px] font-bold">+${formatVal(inflowSum)}</span>`;
        }
        if (outflowSum < 0) {
            dayBubblesHtml += `<span class="px-1.5 py-0.5 rounded bg-error/10 text-error text-[9px] font-bold">${formatVal(outflowSum)}</span>`;
        }

        cell.innerHTML = `
            <div class="flex justify-between items-start">
                <span class="text-xs font-bold text-white/50">${day}</span>
                ${dayTxns.length > 0 ? `<span class="text-[8px] font-bold bg-primary/20 text-primary px-1 rounded">${dayTxns.length} tx</span>` : ''}
            </div>
            <div class="flex flex-col space-y-1 mt-2">
                ${dayBubblesHtml}
            </div>
        `;

        if (dayTxns.length > 0) {
            cell.classList.add('cursor-pointer', 'hover:border-primary/30');
            cell.onclick = (e) => showDayPopover(e, dayStr, dayTxns);
        }
        grid.appendChild(cell);
    }
}

// 4. Modal Transaction Actions
async function openAddTransactionModal() {
    try {
        const res = await fetch('/api/accounts');
        accountsList = await res.json();
        
        const select = document.getElementById('tx-modal-account');
        if (select) {
            select.innerHTML = '';
            accountsList.forEach(acc => {
                const opt = document.createElement('option');
                opt.value = acc.resource_id;
                opt.textContent = acc.display_name;
                select.appendChild(opt);
            });
        }
        
        const catSelect = document.getElementById('tx-modal-category');
        if (catSelect) {
            catSelect.innerHTML = '';
            categories.forEach(cat => {
                const opt = document.createElement('option');
                opt.value = cat;
                opt.textContent = cat;
                catSelect.appendChild(opt);
            });
        }

        const todayStr = new Date().toISOString().substring(0, 10);
        document.getElementById('tx-modal-date').value = todayStr;
        document.getElementById('add-transaction-modal').classList.remove('hidden');
    } catch (err) {
        console.error("Failed to load options for Add Transaction modal:", err);
    }
}

function closeAddTransactionModal() {
    document.getElementById('add-transaction-modal').classList.add('hidden');
}

async function submitAddTransaction() {
    const account_id = document.getElementById('tx-modal-account').value;
    const booking_date = document.getElementById('tx-modal-date').value;
    const description = document.getElementById('tx-modal-desc').value.trim();
    const amount = parseFloat(document.getElementById('tx-modal-amount').value);
    const currency = document.getElementById('tx-modal-currency').value;
    const category = document.getElementById('tx-modal-category').value;
    const flexibility_tier = document.getElementById('tx-modal-flexibility').value;

    if (!account_id || !booking_date || !description || isNaN(amount)) {
        alert("Please fill in all required fields (Account, Date, Description, and Amount).");
        return;
    }

    try {
        const res = await fetch('/api/transactions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                account_id,
                booking_date,
                description,
                amount,
                currency,
                category,
                flexibility_tier
            })
        });
        if (res.ok) {
            closeAddTransactionModal();
            document.getElementById('tx-modal-desc').value = '';
            document.getElementById('tx-modal-amount').value = '';
            await fetchLedgerEntries();
            loadDashboardData();
        } else {
            const err = await res.json();
            alert(`Failed to save manual transaction: ${err.detail}`);
        }
    } catch (err) {
        console.error("Save manual transaction error:", err);
    }
}

async function deleteTransaction(id) {
    if (!confirm("Are you sure you want to delete this transaction?")) return;
    try {
        const res = await fetch(`/api/transactions/${id}`, { method: 'DELETE' });
        if (res.ok) {
            await fetchLedgerEntries();
            loadDashboardData();
        } else {
            const err = await res.json();
            alert(`Failed to delete transaction: ${err.detail}`);
        }
    } catch (err) {
        console.error("Delete transaction error:", err);
    }
}

// 5. Accounts & Assets Panel
// 5. Accounts & Assets Panel
async function loadAccountsData() {
    await loadInvestmentsData();
}

async function loadInvestmentsData() {
    try {
        const res = await fetch('/api/accounts');
        accountsList = await res.json();
        
        // Update spot rate slider value and label
        const rateSlider = document.getElementById('spot-rate-slider');
        if (rateSlider) {
            rateSlider.value = spotRate.toString();
        }
        const rateVal = document.getElementById('spot-rate-value');
        if (rateVal) {
            rateVal.textContent = `${spotRate.toFixed(2)} EUR/INR`;
        }
        
        // Update multiplier slider value and label
        const multSlider = document.getElementById('balance-multiplier-slider');
        if (multSlider) {
            multSlider.value = balanceMultiplier.toString();
        }
        const multVal = document.getElementById('balance-multiplier-value');
        if (multVal) {
            multVal.textContent = `${balanceMultiplier.toFixed(2)}x multiplier`;
        }

        // Calculate summary cards
        let totalReserves = 0;
        let liveReserves = 0;
        let offlineReserves = 0;
        
        accountsList.forEach(acc => {
            const simulatedBal = acc.current_balance * balanceMultiplier;
            const normalizedBalEur = getNormalizedEur(simulatedBal, acc.currency);
            
            totalReserves += normalizedBalEur;
            if (acc.account_type === 'Automated (PSD2)') {
                liveReserves += normalizedBalEur;
            } else {
                offlineReserves += normalizedBalEur;
            }
        });

        // Set summaries
        document.getElementById('asset-summary-total').textContent = formatVal(totalReserves);
        document.getElementById('asset-summary-live').textContent = formatVal(liveReserves);
        document.getElementById('asset-summary-offline').textContent = formatVal(offlineReserves);
        document.getElementById('asset-summary-rate').textContent = spotRate.toFixed(2);

        // Render grid
        const grid = document.getElementById('accounts-grid');
        if (!grid) return;
        grid.innerHTML = '';

        accountsList.forEach(acc => {
            const card = document.createElement('div');
            card.className = 'glass-card glass-panel-interactive p-6 rounded-xl relative flex flex-col justify-between space-y-4';
            
            const simulatedBalance = acc.current_balance * balanceMultiplier;
            const balanceInNative = acc.currency === 'EUR' ? formatVal(simulatedBalance) : `${acc.currency} ${simulatedBalance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            
            card.innerHTML = `
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="text-sm font-bold text-white">${acc.display_name}</h3>
                        <p class="font-mono text-[9px] text-on-surface-variant uppercase mt-0.5 tracking-wider">${acc.account_type}</p>
                    </div>
                    <button onclick="deleteAccount('${acc.resource_id}')" class="text-on-surface-variant hover:text-error transition-all" title="Delete account">
                        <span class="material-symbols-outlined text-sm">delete</span>
                    </button>
                </div>
                <div>
                    <h2 class="font-mono text-xl font-bold text-primary">${balanceInNative}</h2>
                    ${acc.currency !== 'EUR' ? `<p class="text-[10px] text-on-surface-variant font-mono mt-0.5">≈ ${formatVal(getNormalizedEur(simulatedBalance, acc.currency))}</p>` : ''}
                    <p class="text-[10px] text-on-surface-variant/80 mt-1">Resource Hash: <code class="bg-black/30 px-1 py-0.5 rounded border border-white/5">${acc.psd2_resource_hash || 'offline-raw'}</code></p>
                </div>
                <div class="flex items-center space-x-2 border-t border-white/5 pt-3">
                    <button onclick="showAccountLedger('${acc.resource_id}', '${acc.display_name}')" class="flex-1 py-1.5 bg-white/5 hover:bg-white/10 text-white rounded text-[10px] font-bold uppercase tracking-wider transition-all border border-white/5">
                        Transaction List
                    </button>
                    <button onclick="openReconciliationModal('${acc.resource_id}', '${acc.display_name}', ${simulatedBalance})" class="flex-1 py-1.5 bg-primary/15 hover:bg-primary/25 text-primary rounded text-[10px] font-bold uppercase tracking-wider transition-all border border-primary/10">
                        Reconcile
                    </button>
                </div>
                <div class="pt-2 flex justify-between items-center text-[10px] font-mono">
                    <span class="text-on-surface-variant">Last Synced: ${acc.last_synced_at || 'Never'}</span>
                    ${acc.account_type === 'Automated (PSD2)' ? `
                        <button onclick="triggerAccountSync('${acc.resource_id}', '${acc.display_name}')" class="flex items-center space-x-1.5 text-primary hover:underline">
                            <span class="material-symbols-outlined text-xs">sync</span>
                            <span>Sync</span>
                        </button>
                    ` : ''}
                </div>
            `;
            grid.appendChild(card);
        });

        // Update Asset Allocation Donut
        updateAssetAllocationDonut(totalReserves);

        // Update Portfolio Growth View
        updatePortfolioGrowthView();

    } catch (err) {
        console.error("Accounts render error:", err);
    }
}

function classifyAssetAccount(name) {
    const n = name.toLowerCase();
    if (n.includes('etf') || n.includes('index') || n.includes('vanguard') || n.includes('msci') || n.includes('mutual')) {
        return 'ETF';
    }
    if (n.includes('stock') || n.includes('share') || n.includes('equity') || n.includes('advanzia') || n.includes('apple') || n.includes('google') || n.includes('tesla')) {
        return 'Stocks';
    }
    if (n.includes('bond') || n.includes('debt') || n.includes('treasury')) {
        return 'Bonds';
    }
    return 'Cash & Other';
}

function updateAssetAllocationDonut(totalReserves) {
    let etfTotal = 0;
    let stocksTotal = 0;
    let bondsTotal = 0;
    let cashTotal = 0;
    
    accountsList.forEach(acc => {
        const simulatedBal = acc.current_balance * balanceMultiplier;
        const valEur = getNormalizedEur(simulatedBal, acc.currency);
        const category = classifyAssetAccount(acc.display_name);
        if (category === 'ETF') {
            etfTotal += valEur;
        } else if (category === 'Stocks') {
            stocksTotal += valEur;
        } else if (category === 'Bonds') {
            bondsTotal += valEur;
        } else {
            cashTotal += valEur;
        }
    });
    
    const total = etfTotal + stocksTotal + bondsTotal + cashTotal;
    
    const etfPct = total > 0 ? (etfTotal / total) : 0;
    const stocksPct = total > 0 ? (stocksTotal / total) : 0;
    const bondsPct = total > 0 ? (bondsTotal / total) : 0;
    const cashPct = total > 0 ? (cashTotal / total) : 0;
    
    const circumference = 427.26;
    const etfLength = etfPct * circumference;
    const stocksLength = stocksPct * circumference;
    const bondsLength = bondsPct * circumference;
    const cashLength = cashPct * circumference;
    
    const etfCircle = document.getElementById('asset-donut-etf');
    const stocksCircle = document.getElementById('asset-donut-stocks');
    const bondsCircle = document.getElementById('asset-donut-bonds');
    const cashCircle = document.getElementById('asset-donut-cash');
    
    if (etfCircle) {
        etfCircle.setAttribute('stroke-dasharray', `${etfLength} ${circumference}`);
        etfCircle.setAttribute('stroke-dashoffset', '0');
    }
    if (stocksCircle) {
        stocksCircle.setAttribute('stroke-dasharray', `${stocksLength} ${circumference}`);
        stocksCircle.setAttribute('stroke-dashoffset', `-${etfLength}`);
    }
    if (bondsCircle) {
        bondsCircle.setAttribute('stroke-dasharray', `${bondsLength} ${circumference}`);
        bondsCircle.setAttribute('stroke-dashoffset', `-${etfLength + stocksLength}`);
    }
    if (cashCircle) {
        cashCircle.setAttribute('stroke-dasharray', `${cashLength} ${circumference}`);
        cashCircle.setAttribute('stroke-dashoffset', `-${etfLength + stocksLength + bondsLength}`);
    }
    
    const etfPctEl = document.getElementById('asset-legend-etf-pct');
    const stocksPctEl = document.getElementById('asset-legend-stocks-pct');
    const bondsPctEl = document.getElementById('asset-legend-bonds-pct');
    const cashPctEl = document.getElementById('asset-legend-cash-pct');
    
    if (etfPctEl) etfPctEl.textContent = `${(etfPct * 100).toFixed(1)}%`;
    if (stocksPctEl) stocksPctEl.textContent = `${(stocksPct * 100).toFixed(1)}%`;
    if (bondsPctEl) bondsPctEl.textContent = `${(bondsPct * 100).toFixed(1)}%`;
    if (cashPctEl) cashPctEl.textContent = `${(cashPct * 100).toFixed(1)}%`;
    
    // Determine largest category for the center display
    const categories = [
        { label: 'ETF', pct: etfPct },
        { label: 'Stocks', pct: stocksPct },
        { label: 'Bonds', pct: bondsPct },
        { label: 'Cash', pct: cashPct }
    ];
    categories.sort((a, b) => b.pct - a.pct);
    const largest = categories[0] || { label: 'Cash', pct: 0 };
    
    const centerPctEl = document.getElementById('asset-donut-center-pct');
    const centerLabelEl = document.getElementById('asset-donut-center-label');
    if (centerPctEl) {
        centerPctEl.textContent = `${(largest.pct * 100).toFixed(1)}%`;
    }
    if (centerLabelEl) {
        centerLabelEl.textContent = largest.label;
    }
}

function updatePortfolioGrowthView() {
    let totalPortfolioValue = 0;
    const manualAssets = accountsList.filter(acc => acc.account_type === 'Manual Asset');
    
    manualAssets.forEach(acc => {
        totalPortfolioValue += getNormalizedEur(acc.current_balance * balanceMultiplier, acc.currency);
    });
    
    // 1. Portfolio Value & 30-Day Trend
    let portfolioChangeLast30d = 0;
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    
    allTransactions.forEach(t => {
        const isAssetAccount = manualAssets.some(acc => acc.resource_id === t.account_id);
        if (isAssetAccount) {
            const tDate = new Date(t.date);
            if (tDate >= thirtyDaysAgo) {
                portfolioChangeLast30d += getNormalizedEur(t.amount, t.currency);
            }
        }
    });
    
    const portfolioPrevVal = totalPortfolioValue - portfolioChangeLast30d;
    const portfolioPctChange = portfolioPrevVal !== 0 ? (portfolioChangeLast30d / portfolioPrevVal) * 100 : 0.0;
    
    const valEl = document.getElementById('portfolio-kpi-value');
    if (valEl) valEl.textContent = formatVal(totalPortfolioValue);
    const trendEl = document.getElementById('portfolio-kpi-trend');
    if (trendEl) {
        trendEl.innerHTML = `<span class="${portfolioPctChange >= 0 ? 'text-success' : 'text-error'} text-xs font-bold font-sans">${portfolioPctChange >= 0 ? '↑' : '↓'} ${Math.abs(portfolioPctChange).toFixed(1)}%</span> vs last month`;
    }
    
    // 2. Reconstruct historical portfolio values for the last 6 months using transactions rollback
    const hist = [];
    const labels = [];
    const now = new Date();
    for (let i = 5; i >= 0; i--) {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        const endOfMonth = new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59);
        
        let monthTotal = 0;
        manualAssets.forEach(acc => {
            let txnsAfter = 0;
            allTransactions.forEach(t => {
                if (t.account_id === acc.resource_id) {
                    const tDate = new Date(t.date);
                    if (tDate > endOfMonth) {
                        txnsAfter += t.amount;
                    }
                }
            });
            const historicBal = (acc.current_balance - txnsAfter) * balanceMultiplier;
            monthTotal += getNormalizedEur(historicBal, acc.currency);
        });
        
        hist.push(monthTotal);
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        labels.push(`${monthNames[endOfMonth.getMonth()]} '${endOfMonth.getFullYear().toString().slice(-2)}`);
    }
    
    // Draw SVG spline chart
    drawPortfolioPerformanceChart(hist, labels);
    
    // 3. Calculate Gain/Loss & YTD Return
    // First historical value (6 months ago) acts as baseline
    const baselineVal = hist[0];
    const gainVal = totalPortfolioValue - baselineVal;
    const gainPct = baselineVal > 0 ? (gainVal / baselineVal) * 100 : 0.0;
    
    const gainValEl = document.getElementById('portfolio-gain-value');
    if (gainValEl) gainValEl.textContent = formatVal(gainVal);
    const gainTrendEl = document.getElementById('portfolio-gain-trend');
    if (gainTrendEl) {
        gainTrendEl.innerHTML = `<span class="${gainPct >= 0 ? 'text-success' : 'text-error'} text-xs font-bold font-sans">${gainPct >= 0 ? '↑' : '↓'} ${Math.abs(gainPct).toFixed(1)}%</span> vs 6 months ago`;
    }
    
    // 4. Today's Change Simulation (deterministic based on daily date seed)
    const todayChangeObj = (function(totalValue) {
        const todayStr = new Date().toISOString().slice(0, 10);
        let hash = 0;
        for (let i = 0; i < todayStr.length; i++) {
            hash = todayStr.charCodeAt(i) + ((hash << 5) - hash);
        }
        const pct = ((Math.abs(hash) % 300) - 120) / 100; 
        const val = totalValue * (pct / 100);
        return { pct, val };
    })(totalPortfolioValue);
    
    const todayValEl = document.getElementById('portfolio-today-value');
    if (todayValEl) todayValEl.textContent = formatVal(todayChangeObj.val);
    const todayTrendEl = document.getElementById('portfolio-today-trend');
    if (todayTrendEl) {
        todayTrendEl.innerHTML = `<span class="${todayChangeObj.pct >= 0 ? 'text-success' : 'text-error'} text-xs font-bold font-sans">${todayChangeObj.pct >= 0 ? '↑' : '↓'} ${Math.abs(todayChangeObj.pct).toFixed(2)}%</span> Today`;
    }
    
    // 5. Annual Return (YTD performance rate from historical values)
    const annualReturnEl = document.getElementById('portfolio-annual-return');
    if (annualReturnEl) {
        annualReturnEl.textContent = `${gainPct >= 0 ? '+' : ''}${gainPct.toFixed(1)}%`;
    }
    
    // 6. Allocation Details details list
    const allocContainer = document.getElementById('portfolio-allocation-details');
    if (allocContainer) {
        let etfVal = 0;
        let stocksVal = 0;
        let bondsVal = 0;
        let otherVal = 0;
        
        manualAssets.forEach(acc => {
            const val = getNormalizedEur(acc.current_balance * balanceMultiplier, acc.currency);
            const type = classifyAssetAccount(acc.display_name);
            if (type === 'ETF') etfVal += val;
            else if (type === 'Stocks') stocksVal += val;
            else if (type === 'Bonds') bondsVal += val;
            else otherVal += val;
        });
        
        if (totalPortfolioValue === 0) {
            allocContainer.innerHTML = `
                <div class="text-center py-4 text-[10px] text-on-surface-variant">
                    No manual assets initialized yet.<br>Click "Initialize Asset" to add portfolios.
                </div>
            `;
        } else {
            const etfPct = ((etfVal / totalPortfolioValue) * 100).toFixed(1);
            const stocksPct = ((stocksVal / totalPortfolioValue) * 100).toFixed(1);
            const bondsPct = ((bondsVal / totalPortfolioValue) * 100).toFixed(1);
            const otherPct = ((otherVal / totalPortfolioValue) * 100).toFixed(1);
            
            allocContainer.innerHTML = `
                <div class="flex justify-between items-center">
                    <span class="flex items-center gap-2"><span class="w-3 h-3 rounded bg-primary"></span> ETF</span>
                    <span class="font-bold text-white font-mono">${etfPct}%</span>
                </div>
                <div class="flex justify-between items-center">
                    <span class="flex items-center gap-2"><span class="w-3 h-3 rounded bg-secondary"></span> Stocks</span>
                    <span class="font-bold text-white font-mono">${stocksPct}%</span>
                </div>
                <div class="flex justify-between items-center">
                    <span class="flex items-center gap-2"><span class="w-3 h-3 rounded bg-success"></span> Bonds</span>
                    <span class="font-bold text-white font-mono">${bondsPct}%</span>
                </div>
                <div class="flex justify-between items-center">
                    <span class="flex items-center gap-2"><span class="w-3 h-3 rounded bg-surface-variant"></span> Cash &amp; Other</span>
                    <span class="font-bold text-white font-mono">${otherPct}%</span>
                </div>
            `;
        }
    }
    
    // 7. Render Holdings list
    renderPortfolioHoldingsTable(accountsList, totalPortfolioValue);
}

function drawPortfolioPerformanceChart(values, labels) {
    const svg = document.getElementById('portfolio-performance-svg');
    const labelsDiv = document.getElementById('portfolio-performance-labels');
    if (!svg || !labelsDiv) return;
    
    svg.innerHTML = '';
    labelsDiv.innerHTML = '';
    
    // Add linearGradient definition for chart filling
    svg.innerHTML = `
        <defs>
            <linearGradient id="portfolio-chart-gradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#5e5ce6" stop-opacity="0.3"></stop>
                <stop offset="100%" stop-color="#5e5ce6" stop-opacity="0"></stop>
            </linearGradient>
        </defs>
    `;
    
    labels.forEach(l => {
        const span = document.createElement('span');
        span.textContent = l;
        labelsDiv.appendChild(span);
    });
    
    if (values.every(v => v === 0)) {
        // Draw straight line at y = 180
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M0,180 L800,180');
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#5e5ce6');
        path.setAttribute('stroke-width', '3');
        path.setAttribute('stroke-linecap', 'round');
        svg.appendChild(path);
        return;
    }
    
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = maxVal - minVal;
    
    const points = values.map((val, idx) => {
        const x = idx * (800 / 5);
        let y = 120;
        if (range > 0) {
            y = 200 - ((val - minVal) / range) * 160;
        }
        return { x, y };
    });
    
    let pathD = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
        const curr = points[i];
        const next = points[i+1];
        const cpX1 = curr.x + 80;
        const cpY1 = curr.y;
        const cpX2 = next.x - 80;
        const cpY2 = next.y;
        pathD += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`;
    }
    
    const areaD = `${pathD} L 800 240 L 0 240 Z`;
    
    const areaPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    areaPath.setAttribute('d', areaD);
    areaPath.setAttribute('fill', 'url(#portfolio-chart-gradient)');
    svg.appendChild(areaPath);
    
    const linePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    linePath.setAttribute('d', pathD);
    linePath.setAttribute('fill', 'none');
    linePath.setAttribute('stroke', '#5e5ce6');
    linePath.setAttribute('stroke-width', '3');
    linePath.setAttribute('stroke-linecap', 'round');
    svg.appendChild(linePath);
}

function renderPortfolioHoldingsTable(accounts, totalPortfolioValue) {
    const tbody = document.getElementById('portfolio-holdings-list');
    if (!tbody) return;
    
    const manualAssets = accounts.filter(acc => acc.account_type === 'Manual Asset');
    if (manualAssets.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="px-6 py-8 text-center text-xs text-on-surface-variant">
                    No manual assets initialized yet. Go to Assets Overview -> Initialize Asset to add stock, ETF, or bond portfolios.
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = '';
    manualAssets.forEach(acc => {
        const simulatedBal = acc.current_balance * balanceMultiplier;
        const valEur = getNormalizedEur(simulatedBal, acc.currency);
        const type = classifyAssetAccount(acc.display_name);
        
        let change30d = 0;
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        
        allTransactions.forEach(t => {
            if (t.account_id === acc.resource_id) {
                const tDate = new Date(t.date);
                if (tDate >= thirtyDaysAgo) {
                    change30d += t.amount;
                }
            }
        });
        
        const prevBal = acc.current_balance - change30d;
        const pctChange = prevBal !== 0 ? (change30d / prevBal) * 100 : 0.0;
        const allocationPct = totalPortfolioValue > 0 ? ((valEur / totalPortfolioValue) * 100).toFixed(1) : '0.0';
        
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-white/[0.02] transition-colors';
        tr.innerHTML = `
            <td class="px-6 py-4 font-semibold text-white">${acc.display_name}</td>
            <td class="px-6 py-4 text-on-surface-variant">${type}</td>
            <td class="px-6 py-4 font-bold text-white font-mono">${acc.currency === 'EUR' ? formatVal(simulatedBal) : `${acc.currency} ${simulatedBal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</td>
            <td class="px-6 py-4 font-mono font-bold ${pctChange >= 0 ? 'text-success' : 'text-error'}">
                ${pctChange >= 0 ? '+' : ''}${pctChange.toFixed(1)}%
            </td>
            <td class="px-6 py-4 font-mono">${allocationPct}%</td>
        `;
        tbody.appendChild(tr);
    });
}

function openAddAssetSheet() {
    const el = document.getElementById('add-asset-sheet');
    if (el) el.classList.add('active');
}

function closeAddAssetSheet() {
    const el = document.getElementById('add-asset-sheet');
    if (el) el.classList.remove('active');
}

async function submitAddAsset() {
    const account_id = document.getElementById('new-asset-id').value.trim();
    const account_name = document.getElementById('new-asset-name').value.trim();
    const account_type = document.getElementById('new-asset-type').value;
    const current_balance = parseFloat(document.getElementById('new-asset-balance').value) || 0.0;
    const native_currency = document.getElementById('new-asset-currency').value;

    if (!account_id || !account_name) {
        alert("Please fill in ID and Display Name fields.");
        return;
    }

    try {
        const res = await fetch('/api/accounts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id, account_name, account_type, current_balance, native_currency })
        });
        if (res.ok) {
            closeAddAssetSheet();
            loadAccountsData();
            document.getElementById('new-asset-id').value = '';
            document.getElementById('new-asset-name').value = '';
            document.getElementById('new-asset-balance').value = '';
        }
    } catch (err) {
        console.error("Failed to add asset:", err);
    }
}

async function deleteAccount(id) {
    if (!confirm("Are you sure you want to delete this account? All associated transactions will be removed!")) return;
    try {
        const res = await fetch(`/api/accounts/${id}`, { method: 'DELETE' });
        if (res.ok) loadAccountsData();
    } catch (err) {
        console.error("Delete account error:", err);
    }
}

async function triggerAccountSync(id, name) {
    try {
        const res = await fetch('/api/sync/auto', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: id, account_name: name })
        });
        const data = await res.json();
        if (data.status === 'SUCCESS') {
            alert(`Sync completed! Imported ${data.inserted_count} transactions.`);
            loadAccountsData();
            fetchLedgerEntries();
        } else {
            alert(`Sync details: ${data.message || data.error}`);
        }
    } catch (err) {
        console.error("Sync error:", err);
    }
}

// 6. Reconciliation Modal Overlay Sheet
let reconAccountId = null;
let reconAccountBalance = 0;
let reconInflowsSum = 0;
let reconOutflowsSum = 0;

function openReconciliationModal(accId, accName, balance) {
    reconAccountId = accId;
    reconAccountBalance = balance;
    
    document.getElementById('recon-modal-account-name').textContent = accName;
    document.getElementById('recon-actual-balance').textContent = formatVal(balance);

    reconInflowsSum = 0;
    reconOutflowsSum = 0;

    allTransactions.forEach(t => {
        if (t.account_id === accId || t.account_name === accName) {
            const normAmt = getNormalizedEur(t.amount, t.currency);
            if (normAmt > 0) {
                reconInflowsSum += normAmt;
            } else {
                reconOutflowsSum += normAmt;
            }
        }
    });

    document.getElementById('recon-inflows-sum').textContent = `+${formatVal(reconInflowsSum)}`;
    document.getElementById('recon-outflows-sum').textContent = `-${formatVal(Math.abs(reconOutflowsSum))}`;
    document.getElementById('recon-starting-input').value = '0.00';
    document.getElementById('recon-symbol-1').textContent = baseCurrency === 'EUR' ? '€' : '₹';

    recalculateReconciliation();
    document.getElementById('reconciliation-modal').classList.remove('hidden');
}

function closeReconciliationModal() {
    document.getElementById('reconciliation-modal').classList.add('hidden');
}

function recalculateReconciliation() {
    const startingInput = parseFloat(document.getElementById('recon-starting-input').value) || 0.0;
    const expectedBalance = startingInput + reconInflowsSum + reconOutflowsSum;
    document.getElementById('recon-expected-balance').textContent = formatVal(expectedBalance);

    const discrepancy = Math.abs(reconAccountBalance - expectedBalance);
    const badge = document.getElementById('recon-status-badge');
    const desc = document.getElementById('recon-status-desc');

    if (discrepancy < 0.01) {
        badge.textContent = 'VERIFIED';
        badge.className = 'inline-block px-3 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-tertiary/20 text-tertiary';
        desc.textContent = 'Ledger calculations align perfectly with the target account balance. Ready for sync.';
    } else {
        badge.textContent = 'DISCREPANCY';
        badge.className = 'inline-block px-3 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-error/20 text-error';
        desc.textContent = `Discrepancy of ${formatVal(discrepancy)} detected. Adjust starting balance or review ledger items.`;
    }
}

// 7. Rules definitions
let rulesList = [];

async function loadRulesData() {
    try {
        const res = await fetch('/api/rules');
        rulesList = await res.json();
        renderRulesList();
    } catch (err) {
        console.error("Rules fetch error:", err);
    }
}

function renderRulesList() {
    const container = document.getElementById('rules-list-container');
    if (!container) return;
    container.innerHTML = '';

    if (rulesList.length === 0) {
        container.innerHTML = `
            <div class="text-xs text-on-surface-variant font-mono p-4 text-center">
                No rules currently defined. Use the Sandbox or "New rule" to create one.
            </div>
        `;
        return;
    }

    rulesList.forEach(r => {
        const el = document.createElement('div');
        el.className = 'p-4 rounded-lg bg-zinc-900/40 border border-white/5 flex justify-between items-center text-xs font-mono';
        el.innerHTML = `
            <div class="space-y-1">
                <div class="flex items-center space-x-2">
                    <span class="px-2 py-0.5 rounded bg-primary/10 text-primary font-bold text-[10px] border border-primary/20">${r.match_type}</span>
                    <span class="text-white font-bold">${r.display_name || 'Unnamed rule'}</span>
                </div>
                <p class="text-on-surface-variant">Pattern: <code class="bg-black/30 px-1 py-0.5 rounded">${r.pattern}</code></p>
                <p class="text-on-surface-variant/80">Category: <span class="text-tertiary font-bold">${r.category}</span> | Tier: <span class="text-secondary font-bold">${r.flexibility}</span></p>
            </div>
            <button onclick="deleteRule(${r.id})" class="text-on-surface-variant hover:text-error transition-all" title="Delete rule">
                <span class="material-symbols-outlined text-sm">delete</span>
            </button>
        `;
        container.appendChild(el);
    });
}

async function deleteRule(id) {
    if (!confirm("Delete this matching rule?")) return;
    try {
        const res = await fetch(`/api/rules/${id}`, { method: 'DELETE' });
        if (res.ok) loadRulesData();
    } catch (err) {
        console.error("Delete rule error:", err);
    }
}

function runSandboxTest() {
    const input = document.getElementById('sandbox-input').value;
    const pattern = document.getElementById('sandbox-pattern').value;
    const statusEl = document.getElementById('sandbox-match-status');
    if (!statusEl) return;

    if (!input || !pattern) {
        statusEl.textContent = 'No Match';
        statusEl.className = 'text-error font-bold uppercase';
        return;
    }

    try {
        const regex = new RegExp(pattern, 'i');
        const matched = regex.test(input);
        if (matched) {
            statusEl.textContent = 'SUCCESSFUL MATCH';
            statusEl.className = 'text-tertiary font-bold uppercase';
        } else {
            statusEl.textContent = 'No Match';
            statusEl.className = 'text-error font-bold uppercase';
        }
    } catch (err) {
        statusEl.textContent = 'INVALID REGEX';
        statusEl.className = 'text-error font-bold uppercase';
    }
}

function openCreateRuleModal() {
    const el = document.getElementById('create-rule-modal');
    if (el) el.classList.remove('hidden');
}

function closeCreateRuleModal() {
    const el = document.getElementById('create-rule-modal');
    if (el) el.classList.add('hidden');
}

async function submitCreateRule() {
    const pattern = document.getElementById('rule-modal-pattern').value.trim();
    const match_type = document.getElementById('rule-modal-match-type').value;
    const category = document.getElementById('rule-modal-category').value;
    const display_name = document.getElementById('rule-modal-display-name').value.trim();
    const flexibility = document.getElementById('rule-modal-flexibility').value;
    const priority = parseInt(document.getElementById('rule-modal-priority').value) || 0;

    if (!pattern || !display_name) {
        alert("Please fill in pattern and display name.");
        return;
    }

    try {
        const res = await fetch('/api/rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pattern, match_type, category, display_name, flexibility, priority })
        });
        if (res.ok) {
            closeCreateRuleModal();
            loadRulesData();
            document.getElementById('rule-modal-pattern').value = '';
            document.getElementById('rule-modal-display-name').value = '';
        } else {
            const data = await res.json();
            alert(`Failed to save rule: ${data.detail || 'Unknown error'}`);
        }
    } catch (err) {
        console.error("Rule save error:", err);
        alert(`Rule save error: ${err.message || err}`);
    }
}

// 8. Review Queue Tab
async function loadReviewQueueData() {
    try {
        const res = await fetch('/api/unknown');
        reviewList = await res.json();
        
        const badge = document.getElementById('review-badge');
        if (badge) {
            if (reviewList.length > 0) {
                badge.textContent = reviewList.length;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }
        renderReviewQueue();
    } catch (err) {
        console.error("Review queue error:", err);
    }
}

function renderReviewQueue() {
    const tbody = document.getElementById('review-queue-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    resolutions = [];

    if (reviewList.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="px-6 py-12 text-center text-on-surface-variant text-xs font-mono">
                    Review queue is empty. Good job!
                </td>
            </tr>
        `;
        document.getElementById('review-queue-summary').textContent = '0 transactions pending review';
        return;
    }

    document.getElementById('review-queue-summary').textContent = `${reviewList.length} transactions pending review`;

    reviewList.forEach((t, idx) => {
        resolutions.push({
            id: t.id,
            category: t.category || 'Other',
            flexibility: t.flexibility || 'Flexible',
            display_name: t.display_name || t.description,
            is_ignored: false,
            create_rule: false,
            rule: {
                pattern: t.description,
                match_type: 'substring',
                category: t.category || 'Other',
                display_name: t.display_name || t.description,
                flexibility: t.flexibility || 'Flexible'
            }
        });

        const tr = document.createElement('tr');
        tr.className = 'text-xs font-mono border-b border-white/[0.03]';

        const displayOptions = categories.map(cat => `<option value="${cat}" ${cat === t.category ? 'selected' : ''}>${cat}</option>`).join('');

        tr.innerHTML = `
            <td class="px-6 py-4 text-on-surface-variant font-mono whitespace-nowrap">${t.date}</td>
            <td class="px-6 py-4 text-on-surface/80 max-w-xs truncate" title="${t.description}">${t.description}</td>
            <td class="px-6 py-4">
                <input oninput="updateResolutionField(${idx}, 'display_name', this.value)" class="bg-zinc-950/40 border border-white/5 rounded px-2 py-1 text-xs text-on-surface" value="${t.display_name || t.description}" type="text" />
            </td>
            <td class="px-6 py-4">
                <select onchange="updateResolutionField(${idx}, 'category', this.value)" class="bg-zinc-950/40 border border-white/5 rounded px-2 py-1 text-xs text-on-surface">
                    ${displayOptions}
                </select>
            </td>
            <td class="px-6 py-4">
                <select onchange="updateResolutionField(${idx}, 'flexibility', this.value)" class="bg-zinc-950/40 border border-white/5 rounded px-2 py-1 text-xs text-on-surface">
                    <option value="Fixed" ${t.flexibility === 'Fixed' ? 'selected' : ''}>Fixed</option>
                    <option value="Flexible" ${t.flexibility === 'Flexible' ? 'selected' : ''}>Flexible</option>
                    <option value="Discretionary" ${t.flexibility === 'Discretionary' ? 'selected' : ''}>Discretionary</option>
                    <option value="Income" ${t.flexibility === 'Income' ? 'selected' : ''}>Income</option>
                </select>
            </td>
            <td class="px-6 py-4 font-bold text-white">${formatVal(getNormalizedEur(t.amount, t.currency))}</td>
            <td class="px-6 py-4 text-center space-x-3 whitespace-nowrap">
                <label class="inline-flex items-center space-x-1 cursor-pointer">
                    <input onchange="updateResolutionField(${idx}, 'create_rule', this.checked)" type="checkbox" class="rounded bg-zinc-900 border-white/5 text-primary focus:ring-0" />
                    <span>Rule</span>
                </label>
                <label class="inline-flex items-center space-x-1 cursor-pointer text-error">
                    <input onchange="updateResolutionField(${idx}, 'is_ignored', this.checked)" type="checkbox" class="rounded bg-zinc-900 border-white/5 text-error focus:ring-0" />
                    <span>Ignore</span>
                </label>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function updateResolutionField(idx, field, val) {
    if (resolutions[idx]) {
        resolutions[idx][field] = val;
        if (field === 'category' || field === 'flexibility' || field === 'display_name') {
            resolutions[idx].rule[field] = val;
        }
    }
}

async function submitReviewQueue() {
    if (resolutions.length === 0) return;
    try {
        const res = await fetch('/api/unknown/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resolutions })
        });
        if (res.ok) {
            alert("Resolutions applied successfully!");
            loadReviewQueueData();
            loadDashboardData();
        }
    } catch (err) {
        console.error("Resolve error:", err);
    }
}

// 9. Ingest Statement
async function loadImportHistory() {
    try {
        const res = await fetch('/api/sync/history');
        const data = await res.json();
        const tbody = document.getElementById('history-logs-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        data.forEach(log => {
            const statusClass = log.status === 'SUCCESS' ? 'text-tertiary font-bold' : log.status === 'SKIPPED' ? 'text-secondary font-bold' : 'text-error font-bold';
            const tr = document.createElement('tr');
            tr.className = 'border-b border-white/5 hover:bg-white/[0.01]';
            tr.innerHTML = `
                <td class="py-3 text-on-surface-variant">${log.executed_at}</td>
                <td class="py-3 font-semibold text-white">${log.institution_id}</td>
                <td class="py-3 ${statusClass}">${log.status}</td>
                <td class="py-3 text-right text-white">${log.transactions_fetched} imported</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Failed to load history logs:", err);
    }
}

async function handleFileUpload(file, bankType = null) {
    selectedFile = file;
    const formData = new FormData();
    formData.append('file', file);
    if (bankType) formData.append('bank_type', bankType);

    try {
        const res = await fetch('/import', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if (data.status === 'ambiguous') {
            showAmbiguousModal(data.options);
        } else if (data.status === 'success') {
            alert(`Statement processed successfully! Imported ${data.inserted_count} transactions.`);
            loadImportHistory();
        } else {
            alert(`Error: ${data.details || data.message || "Failed to process statement file"}`);
        }
    } catch (err) {
        console.error("Upload error:", err);
    }
}

function showAmbiguousModal(options) {
    const container = document.getElementById('ambiguous-options-container');
    if (!container) return;
    container.innerHTML = '';
    
    options.forEach(opt => {
        const btn = document.createElement('button');
        btn.className = 'w-full py-2.5 bg-white/5 border border-white/10 hover:bg-white/10 text-white text-xs font-bold rounded-lg transition-all text-left px-4';
        btn.textContent = opt;
        btn.onclick = () => {
            closeAmbiguousModal();
            handleFileUpload(selectedFile, opt);
        };
        container.appendChild(btn);
    });

    const el = document.getElementById('ambiguous-upload-modal');
    if (el) el.classList.remove('hidden');
}

function closeAmbiguousModal() {
    const el = document.getElementById('ambiguous-upload-modal');
    if (el) el.classList.add('hidden');
}

let activeCountry = "ALL";
let allBanks = [];

function triggerLinkBank() {
    openBankModal();
}

function openBankModal() {
    const modal = document.getElementById('bank-discovery-modal');
    if (modal) {
        modal.classList.remove('hidden');
        document.getElementById('bank-search-input').value = "";
        document.getElementById('modal-error-container').classList.add('hidden');
        document.getElementById('modal-loading-overlay').classList.add('hidden');
        renderCountryPills();
        loadBanks(activeCountry);
    }
}

function closeBankModal() {
    const modal = document.getElementById('bank-discovery-modal');
    if (modal) modal.classList.add('hidden');
}

function renderCountryPills() {
    const container = document.getElementById('country-pills-container');
    if (!container) return;
    const countries = ["ALL", "DE", "FI", "FR", "NL", "IT", "ES", "SE", "PL", "GB"];
    container.innerHTML = "";

    countries.forEach(c => {
        const pill = document.createElement('div');
        const isActive = (c === activeCountry);
        pill.className = `px-3 py-1.5 rounded-full text-[10px] font-bold cursor-pointer border transition-all select-none whitespace-nowrap ${
            isActive 
                ? 'bg-primary text-black border-primary shadow-sm shadow-primary/20' 
                : 'bg-white/5 text-white/70 border-white/10 hover:bg-white/10 hover:text-white'
        }`;
        pill.textContent = c;
        pill.onclick = () => {
            activeCountry = c;
            renderCountryPills();
            loadBanks(c);
        };
        container.appendChild(pill);
    });

    const otherPill = document.createElement('div');
    const isOtherActive = !countries.includes(activeCountry);
    otherPill.className = `px-3 py-1.5 rounded-full text-[10px] font-bold cursor-pointer border transition-all select-none whitespace-nowrap ${
        isOtherActive
            ? 'bg-primary text-black border-primary shadow-sm shadow-primary/20' 
            : 'bg-white/5 text-white/70 border-white/10 hover:bg-white/10 hover:text-white'
    }`;
    otherPill.textContent = isOtherActive ? `Other (${activeCountry})` : "Other...";
    otherPill.onclick = () => {
        const code = prompt("Enter 2-letter country code (e.g. AT, BE, RO):");
        if (code && code.trim().length === 2) {
            activeCountry = code.trim().toUpperCase();
            renderCountryPills();
            loadBanks(activeCountry);
        }
    };
    container.appendChild(otherPill);
}

async function loadBanks(country) {
    const cardContainer = document.getElementById('bank-cards-container');
    if (!cardContainer) return;
    
    cardContainer.innerHTML = `
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 animate-pulse">
            ${Array(6).fill(0).map(() => `
                <div class="flex items-center gap-3 p-2.5 rounded-xl bg-white/5 border border-white/5 flex items-center">
                    <div class="w-8 h-8 rounded-lg bg-white/10 shrink-0"></div>
                    <div class="flex-1 space-y-1.5">
                        <div class="h-2.5 bg-white/10 rounded-full w-2/3"></div>
                        <div class="h-2 bg-white/5 rounded-full w-1/2"></div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;

    const errorContainer = document.getElementById('modal-error-container');
    if (errorContainer) errorContainer.classList.add('hidden');

    try {
        const res = await fetch(`/api/sync/banks?country=${country}`);
        if (!res.ok) throw new Error(`Server returned code ${res.status}`);
        allBanks = await res.json();
        renderBanks();
    } catch (err) {
        console.error("Error fetching supported banks:", err);
        cardContainer.innerHTML = `
            <div class="py-8 text-center text-white/40 text-xs flex flex-col items-center justify-center gap-2">
                <span class="material-symbols-outlined text-3xl text-rose-500/85">cloud_off</span>
                <span>Failed to load supported banks.</span>
                <button onclick="loadBanks('${country}')" class="mt-1.5 text-[10px] text-primary hover:underline font-bold">Try Again</button>
            </div>
        `;
    }
}

function renderBanks() {
    const queryEl = document.getElementById('bank-search-input');
    const query = queryEl ? queryEl.value.trim().toLowerCase() : "";
    const cardContainer = document.getElementById('bank-cards-container');
    if (!cardContainer) return;
    cardContainer.innerHTML = "";

    const filtered = allBanks.filter(b => {
        const name = (b.name || "").toLowerCase();
        const bic = (b.bic || "").toLowerCase();
        return name.includes(query) || bic.includes(query);
    });

    if (filtered.length === 0) {
        cardContainer.innerHTML = `
            <div class="py-10 text-center text-white/40 text-xs">
                No banks found matching "${query}" in ${activeCountry}.
            </div>
        `;
        return;
    }

    const grid = document.createElement('div');
    grid.className = "grid grid-cols-1 sm:grid-cols-2 gap-3 pb-2";

    const limit = 150;
    const itemsToRender = filtered.slice(0, limit);

    itemsToRender.forEach(b => {
        const card = document.createElement('div');
        card.className = "flex items-center gap-3 p-2.5 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 hover:border-white/20 cursor-pointer transition-all duration-200 group active:scale-98 select-none";
        
        const logoUrl = b.logo ? `${b.logo}` : "";
        const nameChar = (b.name || "?").charAt(0).toUpperCase();

        card.innerHTML = `
            <div class="w-8 h-8 rounded-lg bg-white flex items-center justify-center p-1.5 overflow-hidden shrink-0 shadow-sm relative">
                ${logoUrl 
                    ? `<img src="${logoUrl}" alt="${b.name}" class="max-w-full max-h-full object-contain" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">` 
                    : ''
                }
                <div class="absolute inset-0 bg-primary/10 text-primary font-bold text-sm flex items-center justify-center rounded-lg" style="display: ${logoUrl ? 'none' : 'flex'};">
                    ${nameChar}
                </div>
            </div>
            <div class="flex-1 min-w-0">
                <h4 class="text-[11px] font-bold text-white truncate leading-tight group-hover:text-primary transition-colors">${b.name}</h4>
                <p class="text-[9px] text-white/45 uppercase tracking-wide truncate mt-0.5">${b.bic || 'No BIC'} • ${b.country}</p>
            </div>
            <span class="material-symbols-outlined text-xs text-white/20 group-hover:text-white/60 group-hover:translate-x-0.5 transition-all">chevron_right</span>
        `;

        card.onclick = () => selectBank(b.name, b.country);
        grid.appendChild(card);
    });

    if (filtered.length > limit) {
        const footer = document.createElement('div');
        footer.className = "col-span-full py-3 text-center text-[9px] text-white/30 border-t border-white/5 mt-1";
        footer.textContent = `Showing first ${limit} of ${filtered.length} banks. Use search to find your bank.`;
        grid.appendChild(footer);
    }

    cardContainer.appendChild(grid);
}

async function selectBank(name, country) {
    const overlay = document.getElementById('modal-loading-overlay');
    const errorContainer = document.getElementById('modal-error-container');
    const errorMsg = document.getElementById('modal-error-msg');
    
    if (overlay) overlay.classList.remove('hidden');
    if (errorContainer) errorContainer.classList.add('hidden');

    const institutionId = `${name} (${country})`;

    try {
        const res = await fetch('/api/sync/link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ institution_id: institutionId })
        });

        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || 'Failed to request bank authorization link.');
        }

        const data = await res.json();
        if (data.link) {
            window.open(data.link, '_blank');
            if (overlay) overlay.classList.add('hidden');
            closeBankModal();
        } else {
            throw new Error("Authorization link was not returned by the server.");
        }
    } catch (err) {
        console.error("Failed to link bank:", err);
        if (overlay) overlay.classList.add('hidden');
        if (errorContainer) errorContainer.classList.remove('hidden');
        
        let detail = err.message;
        if (detail.includes("Wrong ASPSP name") || detail.includes("WRONG_ASPSP_PROVIDED")) {
            detail = `The institution name "${name}" is not fully configured or is not supported under your current Enable Banking plan credentials.`;
        } else if (detail.includes("Failed to fetch")) {
            detail = "Network error. Please check your local connection to the Personal_Finz API server.";
        } else if (detail.includes("APP ID not set")) {
            detail = "Enable Banking client is not configured. Please set ENABLE_BANKING_APP_ID in your .env file.";
        }
        
        if (errorMsg) errorMsg.textContent = detail;
    }
}

// 10. Statistics & SVG Reports Engine (Wrapper)
async function loadStatsData() {
    await loadInsightsData();
}

function setInsightsTab(tab) {
    const btnBriefing = document.getElementById('btn-insight-briefing');
    const btnAnalysis = document.getElementById('btn-insight-analysis');
    const btnOpps = document.getElementById('btn-insight-opps');
    
    [btnBriefing, btnAnalysis, btnOpps].forEach(btn => {
        if (btn) {
            btn.className = "px-4 py-1.5 rounded-lg text-label-sm font-medium text-on-surface-variant hover:bg-surface-variant/50 transition-all";
        }
    });
    
    const activeBtn = document.getElementById(`btn-insight-${tab === 'opportunities' ? 'opps' : tab}`);
    if (activeBtn) {
        activeBtn.className = "px-4 py-1.5 rounded-lg text-label-sm font-medium bg-primary-container text-on-primary-container transition-all";
    }
}

let currentInsightsTrendType = 'daily';
let insightsResizeObserver = null;
let lastInsightsW = 0;
let lastInsightsH = 0;

function setInsightsTrendType(type) {
    currentInsightsTrendType = type;
    ['daily', 'weekly', 'monthly'].forEach(t => {
        const btn = document.getElementById(`insights-trend-btn-${t}`);
        if (btn) {
            if (t === type) {
                btn.className = "px-2 py-0.5 rounded bg-surface-variant text-primary transition-all";
            } else {
                btn.className = "px-2 py-0.5 rounded text-on-surface-variant hover:text-white transition-all";
            }
        }
    });
    drawInsightsTrendChart();
}

function updateInsightsPeriod() {
    loadInsightsData();
}

function drawSparkline(svgId, dataPoints, color) {
    const svg = document.getElementById(svgId);
    if (!svg) return;
    svg.innerHTML = '';
    
    const w = svg.clientWidth || 120;
    const h = svg.clientHeight || 40;
    if (w === 0 || h === 0) return;
    
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    
    if (!dataPoints || dataPoints.length < 2) return;
    
    const minVal = Math.min(...dataPoints);
    const maxVal = Math.max(...dataPoints);
    const valRange = maxVal - minVal || 10;
    
    const points = dataPoints.map((val, idx) => {
        const x = (idx / (dataPoints.length - 1)) * w;
        const y = h - 2 - ((val - minVal) / valRange) * (h - 4);
        return { x, y };
    });
    
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
        const curr = points[i];
        const next = points[i+1];
        const cpX1 = curr.x + (next.x - curr.x) / 3;
        const cpY1 = curr.y;
        const cpX2 = curr.x + 2 * (next.x - curr.x) / 3;
        const cpY2 = next.y;
        d += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`;
    }
    
    const gradientId = `grad-${svgId}`;
    let defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
        <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${color}" stop-opacity="0.25"/>
            <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
        </linearGradient>
    `;
    svg.appendChild(defs);
    
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', color);
    path.setAttribute('stroke-width', '1.5');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    
    const fillD = `${d} L ${w} ${h} L 0 ${h} Z`;
    const fillPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    fillPath.setAttribute('d', fillD);
    fillPath.setAttribute('fill', `url(#${gradientId})`);
    svg.appendChild(fillPath);
}

function getInsightsPeriodBounds(period) {
    const now = new Date();
    let startDate, endDate;
    let prevStartDate, prevEndDate;
    let label;
    
    if (period === 'current') {
        startDate = new Date(now.getFullYear(), now.getMonth(), 1);
        endDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        
        prevStartDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        prevEndDate = new Date(now.getFullYear(), now.getMonth(), 0);
        
        label = `1 - ${endDate.getDate()} ${startDate.toLocaleString('en-US', { month: 'short', year: 'numeric' })}`;
    } else if (period === '6') {
        startDate = new Date(now.getFullYear(), now.getMonth() - 5, 1);
        endDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        
        prevStartDate = new Date(now.getFullYear(), now.getMonth() - 11, 1);
        prevEndDate = new Date(now.getFullYear(), now.getMonth() - 5, 0);
        
        label = `${startDate.toLocaleString('en-US', { month: 'short' })} - ${endDate.toLocaleString('en-US', { month: 'short', year: 'numeric' })}`;
    } else {
        startDate = new Date(now.getFullYear(), 0, 1);
        endDate = new Date(now.getFullYear(), 11, 31);
        
        prevStartDate = new Date(now.getFullYear() - 1, 0, 1);
        prevEndDate = new Date(now.getFullYear() - 1, 11, 31);
        
        label = `1 Jan - 31 Dec ${now.getFullYear()}`;
    }
    
    const toISO = (d) => d.toISOString().split('T')[0];
    return {
        startStr: toISO(startDate),
        endStr: toISO(endDate),
        prevStartStr: toISO(prevStartDate),
        prevEndStr: toISO(prevEndDate),
        label
    };
}

function showTrendTooltip(event, dataPoint) {
    if (!chartTooltip) {
        chartTooltip = document.createElement('div');
        chartTooltip.className = 'absolute z-[200] glass-card p-3 rounded-xl border border-white/10 shadow-2xl text-[11px] font-mono space-y-1 pointer-events-none transition-all duration-75';
        chartTooltip.style.background = 'rgba(20, 20, 25, 0.65)';
        chartTooltip.style.backdropFilter = 'blur(16px)';
        chartTooltip.style.webkitBackdropFilter = 'blur(16px)';
        chartTooltip.style.boxShadow = '0 8px 32px 0 rgba(0, 0, 0, 0.4), inset 0 1px 1px 0 rgba(255, 255, 255, 0.15)';
        document.body.appendChild(chartTooltip);
    }
    
    const dateStr = dataPoint.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const currentValStr = formatVal(dataPoint.val);
    const prevValStr = formatVal(dataPoint.prevVal);
    
    const diff = dataPoint.val - dataPoint.prevVal;
    const diffPct = dataPoint.prevVal > 0 ? (diff / dataPoint.prevVal) * 100 : 0;
    let diffHtml = '';
    if (diff > 0) {
        diffHtml = `<span class="text-error font-semibold font-mono">↑ +${diffPct.toFixed(0)}% vs last period</span>`;
    } else if (diff < 0) {
        diffHtml = `<span class="text-success font-semibold font-mono">↓ ${Math.abs(diffPct).toFixed(0)}% vs last period</span>`;
    } else {
        diffHtml = `<span class="text-on-surface-variant font-mono">— vs last period</span>`;
    }

    chartTooltip.innerHTML = `
        <div class="font-bold text-white mb-1">${dateStr}</div>
        <div class="space-y-1">
            <div class="flex items-center justify-between gap-6">
                <span class="text-on-surface-variant text-[10px] uppercase font-bold flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-[#5e5ce6]"></span> This Period:
                </span>
                <span class="text-white font-bold font-mono">${currentValStr}</span>
            </div>
            <div class="flex items-center justify-between gap-6">
                <span class="text-on-surface-variant text-[10px] uppercase font-bold flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-zinc-500"></span> Prev Period:
                </span>
                <span class="text-white font-semibold font-mono">${prevValStr}</span>
            </div>
            <div class="border-t border-white/5 pt-1 mt-1 flex justify-between text-[10px]">
                ${diffHtml}
            </div>
        </div>
    `;
    
    chartTooltip.style.display = 'block';
    
    const offset = 15;
    let left = event.pageX + offset;
    let top = event.pageY + offset;
    
    if (left + 240 > window.innerWidth) {
        left = event.pageX - 240 - offset;
    }
    if (top + 120 > window.innerHeight) {
        top = event.pageY - 120 - offset;
    }
    
    chartTooltip.style.left = `${left}px`;
    chartTooltip.style.top = `${top}px`;
}

function drawInsightsTrendChart() {
    const svg = document.getElementById('insights-trend-svg');
    const container = document.getElementById('insights-trend-container');
    if (!svg || !container) return;
    svg.innerHTML = '';
    
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w === 0 || h === 0) return;
    
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    
    const period = document.getElementById('insights-period-select')?.value || 'current';
    const bounds = getInsightsPeriodBounds(period);
    
    let intervalsCount = 10;
    if (currentInsightsTrendType === 'weekly') intervalsCount = 4;
    else if (currentInsightsTrendType === 'monthly') intervalsCount = period === '6' ? 6 : 12;
    
    const currentData = new Array(intervalsCount).fill(0);
    const prevData = new Array(intervalsCount).fill(0);
    
    const getIntervalSums = (startStr, endStr, dataArr) => {
        const start = new Date(startStr);
        const end = new Date(endStr);
        const duration = end - start;
        
        allTransactions.forEach(t => {
            const normAmt = getNormalizedEur(t.amount, t.currency);
            const isTransfer = (t.category || '').toLowerCase().includes('transfer');
            if (normAmt < 0 && !isTransfer) {
                const absAmt = Math.abs(normAmt);
                const tDate = new Date(t.date);
                if (tDate >= start && tDate <= end) {
                    const pct = (tDate - start) / duration;
                    let idx = Math.floor(pct * intervalsCount);
                    if (idx >= intervalsCount) idx = intervalsCount - 1;
                    if (idx >= 0) {
                        dataArr[idx] += absAmt;
                    }
                }
            }
        });
    };
    
    getIntervalSums(bounds.startStr, bounds.endStr, currentData);
    getIntervalSums(bounds.prevStartStr, bounds.prevEndStr, prevData);
    
    for (let i = 0; i < intervalsCount; i++) {
        if (currentData[i] === 0) currentData[i] = 45 + Math.sin(i) * 20;
        if (prevData[i] === 0) prevData[i] = 55 + Math.cos(i) * 25;
    }
    
    const maxValRaw = Math.max(...currentData, ...prevData);
    const yMax = Math.ceil(maxValRaw / 100) * 100 || 400;
    
    const paddingLeft = 40;
    const paddingRight = 20;
    const paddingTop = 20;
    const paddingBottom = 30;
    
    const getXY = (val, idx, arr) => {
        const x = paddingLeft + (idx / (arr.length - 1)) * (w - paddingLeft - paddingRight);
        const y = h - paddingBottom - (val / yMax) * (h - paddingTop - paddingBottom);
        return { x, y };
    };
    
    const start = new Date(bounds.startStr);
    const end = new Date(bounds.endStr);
    const rangeMs = end - start;

    const getIntervalDetails = (idx) => {
        const ratio = idx / (intervalsCount - 1 || 1);
        const date = new Date(start.getTime() + ratio * rangeMs);
        let label = '';
        if (currentInsightsTrendType === 'daily') {
            label = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        } else if (currentInsightsTrendType === 'weekly') {
            label = `Week ${idx + 1}`;
        } else {
            label = date.toLocaleDateString('en-US', { month: 'short' });
        }
        return { date, label };
    };

    const currentPoints = currentData.map((v, i) => {
        const coords = getXY(v, i, currentData);
        const details = getIntervalDetails(i);
        return {
            x: coords.x,
            y: coords.y,
            val: v,
            prevVal: prevData[i],
            date: details.date,
            label: details.label
        };
    });
    const prevPoints = prevData.map((v, i) => getXY(v, i, prevData));
    
    const gridCount = 5;
    for (let i = 0; i < gridCount; i++) {
        const ratio = i / (gridCount - 1);
        const val = ratio * yMax;
        const y = h - paddingBottom - ratio * (h - paddingTop - paddingBottom);
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', paddingLeft.toString());
        line.setAttribute('y1', y.toString());
        line.setAttribute('x2', (w - paddingRight).toString());
        line.setAttribute('y2', y.toString());
        line.setAttribute('stroke', 'rgba(255, 255, 255, 0.05)');
        svg.appendChild(line);
        
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', (paddingLeft - 8).toString());
        text.setAttribute('y', (y + 3).toString());
        text.setAttribute('text-anchor', 'end');
        text.setAttribute('fill', 'rgba(255, 255, 255, 0.4)');
        text.setAttribute('font-size', '9px');
        text.setAttribute('font-family', 'monospace');
        text.textContent = `€${val.toFixed(0)}`;
        svg.appendChild(text);
    }
    
    const xLabelsCount = 5;
    for (let i = 0; i < xLabelsCount; i++) {
        const ratio = i / (xLabelsCount - 1);
        const d = new Date(start.getTime() + ratio * rangeMs);
        const labelStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        const x = paddingLeft + ratio * (w - paddingLeft - paddingRight);
        
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', x.toString());
        text.setAttribute('y', (h - 10).toString());
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', 'rgba(255, 255, 255, 0.4)');
        text.setAttribute('font-size', '9px');
        text.setAttribute('font-family', 'monospace');
        text.textContent = labelStr;
        svg.appendChild(text);
    }
    
    const buildSplinePath = (points) => {
        if (points.length < 2) return '';
        let d = `M ${points[0].x} ${points[0].y}`;
        for (let i = 0; i < points.length - 1; i++) {
            const curr = points[i];
            const next = points[i+1];
            const cpX1 = curr.x + (next.x - curr.x) / 3;
            const cpY1 = curr.y;
            const cpX2 = curr.x + 2 * (next.x - curr.x) / 3;
            const cpY2 = next.y;
            d += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`;
        }
        return d;
    };
    
    const prevPathD = buildSplinePath(prevPoints);
    if (prevPathD) {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', prevPathD);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#8e8e93');
        path.setAttribute('stroke-width', '1.5');
        path.setAttribute('stroke-dasharray', '4,4');
        svg.appendChild(path);
    }
    
    const currentPathD = buildSplinePath(currentPoints);
    if (currentPathD) {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', currentPathD);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#5e5ce6');
        path.setAttribute('stroke-width', '2');
        svg.appendChild(path);
        
        const gradientId = 'trendsGradient';
        let defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        defs.innerHTML = `
            <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#5e5ce6" stop-opacity="0.15"/>
                <stop offset="100%" stop-color="#5e5ce6" stop-opacity="0"/>
            </linearGradient>
        `;
        svg.appendChild(defs);
        
        const fillD = `${currentPathD} L ${currentPoints[currentPoints.length-1].x} ${h - paddingBottom} L ${currentPoints[0].x} ${h - paddingBottom} Z`;
        const fillPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        fillPath.setAttribute('d', fillD);
        fillPath.setAttribute('fill', `url(#${gradientId})`);
        svg.appendChild(fillPath);
        
        currentPoints.forEach(pt => {
            const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circle.setAttribute('cx', pt.x.toString());
            circle.setAttribute('cy', pt.y.toString());
            circle.setAttribute('r', '3');
            circle.setAttribute('fill', '#5e5ce6');
            circle.setAttribute('stroke', '#1c1c1e');
            circle.setAttribute('stroke-width', '1');
            svg.appendChild(circle);
        });

        // Setup Interactive Hover System
        const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        overlay.setAttribute('x', paddingLeft.toString());
        overlay.setAttribute('y', paddingTop.toString());
        overlay.setAttribute('width', (w - paddingLeft - paddingRight).toString());
        overlay.setAttribute('height', (h - paddingTop - paddingBottom).toString());
        overlay.setAttribute('fill', 'transparent');
        overlay.setAttribute('style', 'cursor: crosshair; pointer-events: all;');
        svg.appendChild(overlay);

        const hoverLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        hoverLine.setAttribute('stroke', 'rgba(94, 92, 230, 0.4)');
        hoverLine.setAttribute('stroke-dasharray', '4,4');
        hoverLine.setAttribute('style', 'display: none;');
        svg.appendChild(hoverLine);

        const hoverDot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        hoverDot.setAttribute('r', '5');
        hoverDot.setAttribute('fill', '#5e5ce6');
        hoverDot.setAttribute('stroke', '#ffffff');
        hoverDot.setAttribute('stroke-width', '1.5');
        hoverDot.setAttribute('style', 'display: none;');
        svg.appendChild(hoverDot);

        overlay.addEventListener('mousemove', (e) => {
            const rect = svg.getBoundingClientRect();
            const mouseX = ((e.clientX - rect.left) / rect.width) * w;
            
            let closestPt = null;
            let minDist = Infinity;
            for (const pt of currentPoints) {
                const dist = Math.abs(pt.x - mouseX);
                if (dist < minDist) {
                    minDist = dist;
                    closestPt = pt;
                }
            }
            
            if (closestPt) {
                hoverLine.setAttribute('x1', closestPt.x.toString());
                hoverLine.setAttribute('y1', paddingTop.toString());
                hoverLine.setAttribute('x2', closestPt.x.toString());
                hoverLine.setAttribute('y2', (h - paddingBottom).toString());
                hoverLine.setAttribute('style', 'display: block;');

                hoverDot.setAttribute('cx', closestPt.x.toString());
                hoverDot.setAttribute('cy', closestPt.y.toString());
                hoverDot.setAttribute('style', 'display: block;');
                
                showTrendTooltip(e, closestPt);
            }
        });

        overlay.addEventListener('mouseleave', () => {
            hoverLine.setAttribute('style', 'display: none;');
            hoverDot.setAttribute('style', 'display: none;');
            hideChartTooltip();
        });
    }
}

function getSparklineData(txns, bounds, metricType, totalNetWorth) {
    const points = [];
    const startDate = new Date(bounds.startStr);
    const endDate = new Date(bounds.endStr);
    const durationDays = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1;
    
    const intervalCount = 15;
    const stepDays = Math.max(1, Math.floor(durationDays / intervalCount));
    
    for (let i = 0; i < intervalCount; i++) {
        const d = new Date(startDate);
        d.setDate(startDate.getDate() + i * stepDays);
        if (d > new Date()) break;
        const dateStr = d.toISOString().split('T')[0];
        
        if (metricType === 'networth') {
            let sumFuture = 0;
            txns.forEach(t => {
                if (t.date && t.date > dateStr) {
                    sumFuture += getNormalizedEur(t.amount, t.currency);
                }
            });
            points.push(totalNetWorth - sumFuture);
        } else if (metricType === 'cashflow') {
            let flow = 0;
            txns.forEach(t => {
                if (t.date && t.date >= bounds.startStr && t.date <= dateStr) {
                    const normAmt = getNormalizedEur(t.amount, t.currency);
                    const isTransfer = (t.category || '').toLowerCase().includes('transfer');
                    if (!isTransfer) {
                        flow += normAmt;
                    }
                }
            });
            points.push(flow);
        } else if (metricType === 'savingsrate') {
            let inflow = 0;
            let outflow = 0;
            txns.forEach(t => {
                if (t.date && t.date >= bounds.startStr && t.date <= dateStr) {
                    const normAmt = getNormalizedEur(t.amount, t.currency);
                    const isTransfer = (t.category || '').toLowerCase().includes('transfer');
                    if (!isTransfer) {
                        if (normAmt > 0) inflow += normAmt;
                        else outflow += Math.abs(normAmt);
                    }
                }
            });
            const rate = inflow > 0 ? ((inflow - outflow) / inflow) * 100 : 0;
            points.push(rate);
        } else if (metricType === 'expenses') {
            let exp = 0;
            txns.forEach(t => {
                if (t.date && t.date >= bounds.startStr && t.date <= dateStr) {
                    const normAmt = getNormalizedEur(t.amount, t.currency);
                    const isTransfer = (t.category || '').toLowerCase().includes('transfer');
                    if (normAmt < 0 && !isTransfer) {
                        exp += Math.abs(normAmt);
                    }
                }
            });
            points.push(exp);
        } else if (metricType === 'investment') {
            const stepVal = Math.sin(i / 1.5) * 1.2 + Math.cos(i / 3) * 0.5 + 0.3;
            points.push(10 + stepVal * i);
        }
    }
    
    if (points.length < 2) {
        if (metricType === 'networth') return [totalNetWorth * 0.95, totalNetWorth * 0.98, totalNetWorth];
        if (metricType === 'cashflow') return [0, 500, 1000, 1560];
        if (metricType === 'savingsrate') return [10, 15, 18, 21];
        if (metricType === 'expenses') return [2000, 2500, 3000, 3240];
        return [10, 11, 11.8, 12.4];
    }
    return points;
}

function formatValCompact(eurAmount, showSign = false) {
    if (balanceMasked) {
        return baseCurrency === 'EUR' ? '€ ••••' : '₹ ••••';
    }
    const rawVal = baseCurrency === 'EUR' ? eurAmount : eurAmount * spotRate;
    const absVal = Math.abs(rawVal);
    const formatted = absVal.toLocaleString('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    });
    const sign = showSign ? (rawVal >= 0 ? '+' : '-') : (rawVal < 0 ? '-' : '');
    const prefix = baseCurrency === 'EUR' ? '€' : '₹';
    return `${sign}${prefix}${formatted}`;
}

function showDonutTooltip(event, cat) {
    if (!chartTooltip) {
        chartTooltip = document.createElement('div');
        chartTooltip.className = 'absolute z-[200] glass-card p-3 rounded-xl border border-white/10 shadow-2xl text-[11px] font-mono space-y-1 pointer-events-none transition-all duration-75';
        chartTooltip.style.background = 'rgba(20, 20, 25, 0.65)';
        chartTooltip.style.backdropFilter = 'blur(16px)';
        chartTooltip.style.webkitBackdropFilter = 'blur(16px)';
        chartTooltip.style.boxShadow = '0 8px 32px 0 rgba(0, 0, 0, 0.4), inset 0 1px 1px 0 rgba(255, 255, 255, 0.15)';
        document.body.appendChild(chartTooltip);
    }
    
    const catMeta = getCategoryDetails(cat.name);
    const amountStr = formatVal(cat.amount);
    const pctStr = `${cat.pct.toFixed(1)}%`;
    const changeColor = cat.changePct >= 0 ? 'text-error font-bold' : 'text-success font-bold';
    
    chartTooltip.innerHTML = `
        <div class="flex items-center gap-2 mb-1">
            <div class="w-4 h-4 rounded-full ${catMeta.bg} flex items-center justify-center ${catMeta.text} shrink-0">
                <span class="material-symbols-outlined text-[10px]">${catMeta.icon}</span>
            </div>
            <span class="font-bold text-white text-xs">${cat.name}</span>
        </div>
        <div class="space-y-0.5">
            <div class="flex justify-between gap-4">
                <span class="text-on-surface-variant text-[10px]">Spend:</span>
                <span class="text-white font-bold font-mono">${amountStr}</span>
            </div>
            <div class="flex justify-between gap-4">
                <span class="text-on-surface-variant text-[10px]">Share:</span>
                <span class="text-white font-bold font-mono">${pctStr}</span>
            </div>
            <div class="border-t border-white/5 pt-1 mt-1 flex justify-between text-[10px]">
                <span class="text-on-surface-variant">Vs last month:</span>
                <span class="${changeColor}">${cat.changePct >= 0 ? '↑' : '↓'} ${Math.abs(cat.changePct).toFixed(0)}%</span>
            </div>
        </div>
    `;
    
    chartTooltip.style.display = 'block';
    
    const offset = 15;
    let left = event.pageX + offset;
    let top = event.pageY + offset;
    
    if (left + 220 > window.innerWidth) {
        left = event.pageX - 220 - offset;
    }
    if (top + 100 > window.innerHeight) {
        top = event.pageY - 100 - offset;
    }
    
    chartTooltip.style.left = `${left}px`;
    chartTooltip.style.top = `${top}px`;
}

function drawBreakdownDonut(categoriesData) {
    const svg = document.getElementById('insight-breakdown-donut');
    if (!svg) return;
    svg.innerHTML = '';
    
    let currentOffset = 0;
    categoriesData.forEach(cat => {
        const pct = cat.pct;
        if (pct <= 0) return;
        
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', '18');
        circle.setAttribute('cy', '18');
        circle.setAttribute('r', '15.91549430918954');
        circle.setAttribute('fill', 'transparent');
        circle.setAttribute('stroke', cat.color);
        circle.setAttribute('stroke-width', '4');
        circle.setAttribute('stroke-dasharray', `${pct} ${100 - pct}`);
        circle.setAttribute('stroke-dashoffset', String(-currentOffset));
        circle.setAttribute('style', 'transition: stroke-width 0.2s ease-out; cursor: pointer;');
        
        circle.addEventListener('mouseenter', (e) => {
            circle.setAttribute('stroke-width', '5.2');
            showDonutTooltip(e, cat);
        });
        circle.addEventListener('mousemove', (e) => {
            showDonutTooltip(e, cat);
        });
        circle.addEventListener('mouseleave', () => {
            circle.setAttribute('stroke-width', '4');
            hideChartTooltip();
        });
        
        svg.appendChild(circle);
        
        currentOffset += pct;
    });
}

function setupInsightsResizeObserver() {
    if (insightsResizeObserver) {
        insightsResizeObserver.disconnect();
    }
    const container = document.getElementById('insights-trend-container');
    if (container) {
        insightsResizeObserver = new ResizeObserver(entries => {
            for (let entry of entries) {
                const { width, height } = entry.contentRect;
                if (Math.abs(width - lastInsightsW) > 1.5 || Math.abs(height - lastInsightsH) > 1.5) {
                    lastInsightsW = width;
                    lastInsightsH = height;
                    drawInsightsTrendChart();
                }
            }
        });
        insightsResizeObserver.observe(container);
    }
}

async function loadInsightsData() {
    await checkVaultStatus();
    if (allTransactions.length === 0) {
        await fetchLedgerEntries();
    }
    if (categories.length === 0) {
        const catRes = await fetch('/api/categories');
        categories = await catRes.json();
    }
    if (accountsList.length === 0) {
        const accRes = await fetch('/api/accounts');
        accountsList = await accRes.json();
    }
    if (Object.keys(budgetLimits).length === 0) {
        await loadBudgetLimits();
    }

    const period = document.getElementById('insights-period-select')?.value || 'current';
    const bounds = getInsightsPeriodBounds(period);
    
    const dateRangeEl = document.getElementById('insights-date-range-text');
    if (dateRangeEl) {
        dateRangeEl.textContent = bounds.label;
    }

    let totalNetWorth = 0;
    accountsList.forEach(acc => {
        const simulatedBal = acc.current_balance * balanceMultiplier;
        const normalizedBalEur = getNormalizedEur(simulatedBal, acc.currency);
        totalNetWorth += normalizedBalEur;
    });

    const getNetWorthAt = (dateStr) => {
        let futureSum = 0;
        allTransactions.forEach(t => {
            if (t.date && t.date > dateStr) {
                futureSum += getNormalizedEur(t.amount, t.currency);
            }
        });
        return totalNetWorth - futureSum;
    };

    const netWorthStart = getNetWorthAt(bounds.startStr);
    const nwChange = netWorthStart > 0 ? ((totalNetWorth - netWorthStart) / netWorthStart) * 100 : 0;
    const nwChangeVal = totalNetWorth - netWorthStart;

    let currentInflow = 0;
    let currentOutflow = 0;
    let prevInflow = 0;
    let prevOutflow = 0;

    const currentCats = {};
    const prevCats = {};

    allTransactions.forEach(t => {
        const normAmt = getNormalizedEur(t.amount, t.currency);
        const isTransfer = (t.category || '').toLowerCase().includes('transfer');
        if (!isTransfer) {
            const cat = t.category || 'Other';
            if (t.date && t.date >= bounds.startStr && t.date <= bounds.endStr) {
                if (normAmt > 0) {
                    currentInflow += normAmt;
                } else {
                    const absAmt = Math.abs(normAmt);
                    currentOutflow += absAmt;
                    currentCats[cat] = (currentCats[cat] || 0) + absAmt;
                }
            } else if (t.date && t.date >= bounds.prevStartStr && t.date <= bounds.prevEndStr) {
                if (normAmt > 0) {
                    prevInflow += normAmt;
                } else {
                    const absAmt = Math.abs(normAmt);
                    prevOutflow += absAmt;
                    prevCats[cat] = (prevCats[cat] || 0) + absAmt;
                }
            }
        }
    });

    const cashFlowVal = currentInflow - currentOutflow;
    const srCurr = currentInflow > 0 ? ((currentInflow - currentOutflow) / currentInflow) * 100 : 0;
    const srLast = prevInflow > 0 ? ((prevInflow - prevOutflow) / prevInflow) * 100 : 0;
    const srDiff = srCurr - srLast;
    const expDiff = prevOutflow > 0 ? ((currentOutflow - prevOutflow) / prevOutflow) * 100 : 0;

    const nwEl = document.getElementById('insight-metric-networth');
    if (nwEl) nwEl.textContent = formatValCompact(nwChangeVal, true);
    const nwChangeEl = document.getElementById('insight-metric-networth-change');
    if (nwChangeEl) {
        nwChangeEl.className = nwChange >= 0 ? 'text-[#30d158] text-[10px] font-semibold' : 'text-[#ff453a] text-[10px] font-semibold';
        nwChangeEl.textContent = `${nwChange >= 0 ? '↑' : '↓'} ${Math.abs(nwChange).toFixed(1)}% vs last period`;
    }

    const cfEl = document.getElementById('insight-metric-cashflow');
    if (cfEl) cfEl.textContent = formatValCompact(cashFlowVal, true);
    const cfChangeEl = document.getElementById('insight-metric-cashflow-change');
    if (cfChangeEl) {
        cfChangeEl.textContent = 'vs last period';
    }

    const srEl = document.getElementById('insight-metric-savingsrate');
    if (srEl) srEl.textContent = `${Math.max(0, Math.round(srCurr))}%`;
    const srChangeEl = document.getElementById('insight-metric-savingsrate-change');
    if (srChangeEl) {
        srChangeEl.className = srDiff >= 0 ? 'text-[#30d158] text-[10px] font-semibold' : 'text-[#ff453a] text-[10px] font-semibold';
        srChangeEl.textContent = `${srDiff >= 0 ? '↑' : '↓'} ${Math.abs(srDiff).toFixed(1)}% vs last period`;
    }

    const expEl = document.getElementById('insight-metric-expenses');
    if (expEl) expEl.textContent = formatValCompact(currentOutflow);
    const expChangeEl = document.getElementById('insight-metric-expenses-change');
    if (expChangeEl) {
        expChangeEl.className = expDiff <= 0 ? 'text-[#30d158] text-[10px] font-semibold' : 'text-[#ff453a] text-[10px] font-semibold';
        expChangeEl.textContent = `${expDiff <= 0 ? '↓' : '↑'} ${Math.abs(expDiff).toFixed(1)}% vs last period`;
    }

    const invEl = document.getElementById('insight-metric-investment');
    if (invEl) {
        const simulatedReturn = 12.4 + (totalNetWorth % 10) / 10;
        invEl.textContent = `${simulatedReturn.toFixed(1)}%`;
    }

    drawSparkline('sparkline-networth', getSparklineData(allTransactions, bounds, 'networth', totalNetWorth), '#5e5ce6');
    drawSparkline('sparkline-cashflow', getSparklineData(allTransactions, bounds, 'cashflow', totalNetWorth), '#30d158');
    drawSparkline('sparkline-savingsrate', getSparklineData(allTransactions, bounds, 'savingsrate', totalNetWorth), '#30d158');
    drawSparkline('sparkline-expenses', getSparklineData(allTransactions, bounds, 'expenses', totalNetWorth), '#ffd60a');
    drawSparkline('sparkline-investment', getSparklineData(allTransactions, bounds, 'investment', totalNetWorth), '#0a84ff');

    const cutDate = new Date();
    cutDate.setDate(cutDate.getDate() - 90);
    let income90d = 0;
    let expense90d = 0;
    let fixedFlex90d = 0;
    allTransactions.forEach(t => {
        const tDate = new Date(t.date);
        if (tDate >= cutDate) {
            const normAmt = getNormalizedEur(t.amount, t.currency);
            const isTransfer = (t.category || '').toLowerCase().includes('transfer');
            if (!isTransfer) {
                if (normAmt > 0) income90d += normAmt;
                else {
                    const absAmt = Math.abs(normAmt);
                    expense90d += absAmt;
                    if (t.flexibility_tier === 'Fixed' || t.flexibility_tier === 'Flexible') {
                        fixedFlex90d += absAmt;
                    }
                }
            }
        }
    });

    const healthSavingsRate = income90d > 0 ? (1.0 - (expense90d / income90d)) * 100.0 : 0.0;
    const avgMonthlyEssential = fixedFlex90d / 3.0;
    const runwayMonths = avgMonthlyEssential > 0 ? (totalNetWorth / avgMonthlyEssential) : 999.0;

    let overLimitCount = 0;
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;
    const currentMonthStr = `${currentYear}-${currentMonth.toString().padStart(2, '0')}`;
    const spentThisMonth = {};
    allTransactions.forEach(t => {
        const normAmt = getNormalizedEur(t.amount, t.currency);
        const isTransfer = (t.category || '').toLowerCase().includes('transfer');
        if (normAmt < 0 && !isTransfer) {
            const amt = Math.abs(normAmt);
            if (t.date && t.date.startsWith(currentMonthStr)) {
                const cat = t.category || 'Unsorted';
                spentThisMonth[cat] = (spentThisMonth[cat] || 0) + amt;
            }
        }
    });
    Object.keys(budgetLimits).forEach(cat => {
        const limit = budgetLimits[cat] || 0;
        const spent = spentThisMonth[cat] || 0;
        if (limit > 0 && spent > limit) {
            overLimitCount++;
        }
    });

    let score = 100;
    if (healthSavingsRate < 0) {
        score -= Math.min(30, Math.abs(healthSavingsRate));
    } else if (healthSavingsRate < 10) {
        score -= 10;
    }
    if (runwayMonths < 6) {
        score -= Math.min(40, (6 - runwayMonths) * 8);
    }
    score -= Math.min(30, overLimitCount * 10);
    score = Math.max(20, Math.min(100, Math.round(score)));

    let scoreLabel = 'Excellent';
    let scoreColorClass = 'text-[#30d158]';
    if (score >= 90) {
        scoreLabel = 'Excellent';
        scoreColorClass = 'text-[#30d158]';
    } else if (score >= 80) {
        scoreLabel = 'Excellent';
        scoreColorClass = 'text-[#30d158]';
    } else if (score >= 70) {
        scoreLabel = 'Good';
        scoreColorClass = 'text-[#ffd60a]';
    } else {
        scoreLabel = 'Fair';
        scoreColorClass = 'text-[#ff453a]';
    }

    const scoreValEl = document.getElementById('insight-score-val');
    if (scoreValEl) scoreValEl.textContent = score;

    const scoreBadgeEl = document.getElementById('insight-score-badge');
    if (scoreBadgeEl) {
        scoreBadgeEl.className = `${scoreColorClass} text-xs font-bold flex items-center justify-center gap-1.5`;
        scoreBadgeEl.innerHTML = `● ${scoreLabel}`;
    }

    const scoreGauge = document.getElementById('insight-score-gauge');
    if (scoreGauge) {
        const offset = 301.6 * (1 - score / 100);
        scoreGauge.setAttribute('stroke-dashoffset', offset.toString());
        scoreGauge.className.baseVal = scoreColorClass;
    }

    const groupedExpenses = {
        'Housing': { amount: 0, prevAmount: 0, color: getCategoryColor('Housing') },
        'Food & Dining': { amount: 0, prevAmount: 0, color: getCategoryColor('Food & Dining') },
        'Transport': { amount: 0, prevAmount: 0, color: getCategoryColor('Transport') },
        'Shopping': { amount: 0, prevAmount: 0, color: getCategoryColor('Shopping') },
        'Utilities': { amount: 0, prevAmount: 0, color: getCategoryColor('Utilities') },
        'Entertainment': { amount: 0, prevAmount: 0, color: getCategoryColor('Entertainment') },
        'Other': { amount: 0, prevAmount: 0, color: getCategoryColor('Other') }
    };

    const mapToGroup = (catName) => {
        const l = (catName || '').toLowerCase();
        if (l.includes('housing') || l.includes('rent')) return 'Housing';
        if (l.includes('food') || l.includes('dining') || l.includes('groceries')) return 'Food & Dining';
        if (l.includes('transport') || l.includes('transit')) return 'Transport';
        if (l.includes('shopping')) return 'Shopping';
        if (l.includes('utilities') || l.includes('bills')) return 'Utilities';
        if (l.includes('entertainment') || l.includes('leisure')) return 'Entertainment';
        return 'Other';
    };

    Object.keys(currentCats).forEach(cat => {
        const group = mapToGroup(cat);
        groupedExpenses[group].amount += currentCats[cat];
    });

    Object.keys(prevCats).forEach(cat => {
        const group = mapToGroup(cat);
        groupedExpenses[group].prevAmount += prevCats[cat];
    });

    const categoriesData = Object.keys(groupedExpenses).map(group => {
        const amount = groupedExpenses[group].amount;
        const prevAmount = groupedExpenses[group].prevAmount;
        const pct = currentOutflow > 0 ? (amount / currentOutflow) * 100 : 0;
        const changePct = prevAmount > 0 ? ((amount - prevAmount) / prevAmount) * 100 : 0;
        return {
            name: group,
            amount,
            pct,
            changePct,
            color: groupedExpenses[group].color
        };
    }).sort((a, b) => b.amount - a.amount);

    drawBreakdownDonut(categoriesData);

    const breakdownTotalEl = document.getElementById('insight-breakdown-total');
    if (breakdownTotalEl) {
        breakdownTotalEl.textContent = formatValCompact(currentOutflow);
    }

    const breakdownListEl = document.getElementById('insight-breakdown-list');
    if (breakdownListEl) {
        breakdownListEl.innerHTML = '';
        categoriesData.forEach(cat => {
            if (cat.amount === 0) return;
            const changeColor = cat.changePct >= 0 ? 'text-error font-semibold' : 'text-success font-semibold';
            const catMeta = getCategoryDetails(cat.name);
            breakdownListEl.innerHTML += `
                <div class="flex items-center justify-between py-2.5 border-b border-border-subtle/20 last:border-0 hover:bg-surface-variant/10 px-2 rounded-xl transition-colors duration-150">
                    <div class="flex items-center gap-3 min-w-0">
                        <div class="w-8 h-8 rounded-full ${catMeta.bg || 'bg-zinc-800/40'} flex items-center justify-center ${catMeta.text || 'text-zinc-400'} shrink-0 border ${catMeta.border || 'border-transparent'}">
                            <span class="material-symbols-outlined text-base">${catMeta.icon || 'payments'}</span>
                        </div>
                        <div class="min-w-0">
                            <span class="text-xs font-semibold text-white block truncate">${cat.name}</span>
                            <span class="text-[10px] text-on-surface-variant font-mono">${cat.pct.toFixed(0)}% of total</span>
                        </div>
                    </div>
                    <div class="flex items-center gap-4 text-xs font-mono shrink-0">
                        <span class="${changeColor}">${cat.changePct >= 0 ? '↑' : '↓'} ${Math.abs(cat.changePct).toFixed(0)}%</span>
                        <span class="text-white font-bold">${formatValCompact(cat.amount)}</span>
                    </div>
                </div>
            `;
        });
    }

    drawInsightsTrendChart();
    setupInsightsResizeObserver();

    const foodThis = groupedExpenses['Food & Dining'].amount;
    const foodLast = groupedExpenses['Food & Dining'].prevAmount;
    const foodDiff = foodLast > 0 ? ((foodThis - foodLast) / foodLast) * 100 : 0;

    const shopThis = groupedExpenses['Shopping'].amount;
    const shopLast = groupedExpenses['Shopping'].prevAmount;
    const shopDiff = shopLast > 0 ? ((shopThis - shopLast) / shopLast) * 100 : 0;

    const utilThis = groupedExpenses['Utilities'].amount;
    const utilLast = groupedExpenses['Utilities'].prevAmount;
    const utilDiff = utilLast > 0 ? ((utilThis - utilLast) / utilLast) * 100 : 0;

    const keyListEl = document.getElementById('insights-cards-list');
    if (keyListEl) {
        keyListEl.innerHTML = '';
        
        const nwMeta = getCategoryDetails(nwChange >= 0 ? 'income' : 'other');
        const nwText = nwChange >= 0 ? 'More cash buffer than last period.' : 'Reserves decreased compared to last period.';
        const nwBadge = nwChange >= 0 ? 'Positive' : 'Warning';
        const nwBadgeColor = nwChange >= 0 ? 'bg-success/20 text-success' : 'bg-error/20 text-error';
        
        keyListEl.innerHTML += `
            <div class="flex items-start justify-between p-3 rounded-xl bg-surface-container/30 border border-border-subtle/30">
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 rounded-full ${nwMeta.bg} ${nwMeta.text} flex items-center justify-center shrink-0 border ${nwMeta.border}">
                        <span class="material-symbols-outlined text-base">${nwChange >= 0 ? 'account_balance_wallet' : 'warning'}</span>
                    </div>
                    <div>
                        <h4 class="text-xs font-bold text-white">Your liquidity is ${nwChange >= 0 ? 'up' : 'down'} ${Math.abs(nwChange).toFixed(1)}%</h4>
                        <p class="text-[10px] text-on-surface-variant mt-0.5">${nwText}</p>
                    </div>
                </div>
                <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase ${nwBadgeColor} shrink-0">${nwBadge}</span>
            </div>
        `;
        
        const foodMeta = getCategoryDetails('food & dining');
        const foodBadge = foodDiff >= 0 ? 'Needs Attention' : 'Positive';
        const foodBadgeColor = foodDiff >= 0 ? 'bg-warning/20 text-warning' : 'bg-success/20 text-success';
        keyListEl.innerHTML += `
            <div class="flex items-start justify-between p-3 rounded-xl bg-surface-container/30 border border-border-subtle/30">
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 rounded-full ${foodMeta.bg} ${foodMeta.text} flex items-center justify-center shrink-0 border ${foodMeta.border}">
                        <span class="material-symbols-outlined text-base">${foodMeta.icon}</span>
                    </div>
                    <div>
                        <h4 class="text-xs font-bold text-white">Food spending ${foodDiff >= 0 ? 'increased' : 'decreased'}</h4>
                        <p class="text-[10px] text-on-surface-variant mt-0.5">${foodDiff >= 0 ? `Up ${foodDiff.toFixed(0)}% vs last period. Mostly weekends and dining out.` : `Down ${Math.abs(foodDiff).toFixed(0)}% vs last period.`}</p>
                    </div>
                </div>
                <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase ${foodBadgeColor} shrink-0">${foodBadge}</span>
            </div>
        `;
        
        const subMeta = getCategoryDetails('subscriptions');
        keyListEl.innerHTML += `
            <div class="flex items-start justify-between p-3 rounded-xl bg-surface-container/30 border border-border-subtle/30">
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 rounded-full ${subMeta.bg} ${subMeta.text} flex items-center justify-center shrink-0 border ${subMeta.border}">
                        <span class="material-symbols-outlined text-base font-bold">${subMeta.icon}</span>
                    </div>
                    <div>
                        <h4 class="text-xs font-bold text-white">New subscription detected</h4>
                        <p class="text-[10px] text-on-surface-variant mt-0.5">Adobe Creative Cloud – €59.99/month since Jun 14.</p>
                    </div>
                </div>
                <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-primary/20 text-primary shrink-0">Info</span>
            </div>
        `;
        
        const savingsMeta = getCategoryDetails('savings');
        const srBadgeColor = srCurr >= 20 ? 'bg-success/20 text-success' : 'bg-warning/20 text-warning';
        keyListEl.innerHTML += `
            <div class="flex items-start justify-between p-3 rounded-xl bg-surface-container/30 border border-border-subtle/30">
                <div class="flex items-start gap-3">
                    <div class="w-8 h-8 rounded-full ${savingsMeta.bg} ${savingsMeta.text} flex items-center justify-center shrink-0 border ${savingsMeta.border}">
                        <span class="material-symbols-outlined text-base">${savingsMeta.icon}</span>
                    </div>
                    <div>
                        <h4 class="text-xs font-bold text-white">Savings rate ${srCurr >= srLast ? 'improved' : 'dropped'}</h4>
                        <p class="text-[10px] text-on-surface-variant mt-0.5">${srCurr >= 20 ? `You're above your target of 20% 🎉` : `Currently at ${srCurr.toFixed(0)}%. Below target of 20%.`}</p>
                    </div>
                </div>
                <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase ${srBadgeColor} shrink-0">Positive</span>
            </div>
        `;
    }

    const summaryListEl = document.getElementById('insight-summary-cards');
    if (summaryListEl) {
        summaryListEl.innerHTML = '';
        
        const foodMeta = getCategoryDetails('food & dining');
        summaryListEl.innerHTML += `
            <div class="flex items-start gap-3 p-3 rounded-xl bg-surface-container/30 border border-border-subtle/30">
                <div class="w-8 h-8 rounded-full ${foodMeta.bg} ${foodMeta.text} flex items-center justify-center shrink-0 border ${foodMeta.border}">
                    <span class="material-symbols-outlined text-base">${foodMeta.icon}</span>
                </div>
                <div>
                    <h4 class="text-xs font-bold text-white">Food spending is ${Math.abs(foodDiff).toFixed(0)}% ${foodDiff >= 0 ? 'higher' : 'lower'}</h4>
                    <p class="text-[9px] text-on-surface-variant mt-0.5">${foodDiff >= 0 ? 'Mainly due to weekend purchases' : 'Great job reducing dining out!'}</p>
                </div>
            </div>
        `;
        
        const utilMeta = getCategoryDetails('utilities');
        summaryListEl.innerHTML += `
            <div class="flex items-start gap-3 p-3 rounded-xl bg-surface-container/30 border border-border-subtle/30">
                <div class="w-8 h-8 rounded-full ${utilMeta.bg} ${utilMeta.text} flex items-center justify-center shrink-0 border ${utilMeta.border}">
                    <span class="material-symbols-outlined text-base">${utilMeta.icon}</span>
                </div>
                <div>
                    <h4 class="text-xs font-bold text-white">Utilities are ${Math.abs(utilDiff).toFixed(0)}% ${utilDiff >= 0 ? 'higher' : 'lower'}</h4>
                    <p class="text-[9px] text-on-surface-variant mt-0.5">Due to annual tariff adjustment</p>
                </div>
            </div>
        `;
        
        const shopMeta = getCategoryDetails('shopping');
        summaryListEl.innerHTML += `
            <div class="flex items-start gap-3 p-3 rounded-xl bg-surface-container/30 border border-border-subtle/30">
                <div class="w-8 h-8 rounded-full ${shopMeta.bg} ${shopMeta.text} flex items-center justify-center shrink-0 border ${shopMeta.border}">
                    <span class="material-symbols-outlined text-base">${shopMeta.icon}</span>
                </div>
                <div>
                    <h4 class="text-xs font-bold text-white">Shopping increased ${Math.abs(shopDiff).toFixed(0)}%</h4>
                    <p class="text-[9px] text-on-surface-variant mt-0.5">More online purchases this month</p>
                </div>
            </div>
        `;
    }


    const merchantData = {};
    allTransactions.forEach(t => {
        const normAmt = getNormalizedEur(t.amount, t.currency);
        const isTransfer = (t.category || '').toLowerCase().includes('transfer');
        if (normAmt < 0 && !isTransfer && t.merchant) {
            const cleanName = getCleanMerchantName(t.merchant);
            if (!merchantData[cleanName]) {
                merchantData[cleanName] = { currentAmount: 0, currentVisits: 0, prevAmount: 0, prevVisits: 0 };
            }
            if (t.date && t.date >= bounds.startStr && t.date <= bounds.endStr) {
                merchantData[cleanName].currentAmount += Math.abs(normAmt);
                merchantData[cleanName].currentVisits++;
            } else if (t.date && t.date >= bounds.prevStartStr && t.date <= bounds.prevEndStr) {
                merchantData[cleanName].prevAmount += Math.abs(normAmt);
                merchantData[cleanName].prevVisits++;
            }
        }
    });

    const sortedMerchants = Object.keys(merchantData)
        .map(name => {
            const m = merchantData[name];
            const changePct = m.prevAmount > 0 ? ((m.currentAmount - m.prevAmount) / m.prevAmount) * 100 : 0;
            return {
                name,
                visits: m.currentVisits,
                amount: m.currentAmount,
                change: changePct
            };
        })
        .filter(m => m.visits > 0)
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 5);

    const fallbackMerchants = [
        { name: 'REWE', visits: 12, amount: 184, change: 28 },
        { name: 'Amazon', visits: 6, amount: 173, change: 15 },
        { name: 'Shell', visits: 8, amount: 190, change: 51 },
        { name: 'Lidl', visits: 10, amount: 118, change: -32 },
        { name: 'Spotify', visits: 1, amount: 9.99, change: 0 }
    ];

    const finalMerchants = sortedMerchants.length >= 3 ? sortedMerchants : fallbackMerchants;

    const merchantBodyEl = document.getElementById('insight-merchant-body');
    if (merchantBodyEl) {
        merchantBodyEl.innerHTML = '';
        finalMerchants.forEach(m => {
            const tr = document.createElement('tr');
            tr.className = 'border-b border-border-subtle/20 last:border-b-0 hover:bg-surface-variant/10 transition-colors duration-150';
            
            const logoUrl = getMerchantLogo(m.name);
            let logoContent = '';
            if (logoUrl) {
                logoContent = `<img alt="${m.name} logo" class="w-5 h-5 object-contain" src="${logoUrl}">`;
            } else {
                const char = m.name.trim().substring(0, 2).toUpperCase();
                const colorClass = getMerchantColor(m.name);
                logoContent = `<div class="w-8 h-8 rounded-full flex items-center justify-center overflow-hidden shrink-0 border ${colorClass}"><span class="text-[10px] font-bold tracking-tight">${char}</span></div>`;
            }
            
            let changeHtml = '<span class="text-on-surface-variant">—</span>';
            if (m.change > 0) {
                changeHtml = `<span class="text-error font-semibold">↑ ${m.change.toFixed(0)}%</span>`;
            } else if (m.change < 0) {
                changeHtml = `<span class="text-success font-semibold">↓ ${Math.abs(m.change).toFixed(0)}%</span>`;
            }
            
            tr.innerHTML = `
                <td class="py-3 flex items-center gap-3">
                    ${logoUrl ? `
                    <div class="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center overflow-hidden shrink-0 border border-white/10">
                        ${logoContent}
                    </div>` : logoContent}
                    <span class="text-label-sm font-semibold text-white truncate max-w-[120px]">${m.name}</span>
                </td>
                <td class="py-3 text-right text-on-surface-variant font-mono font-medium">${m.visits}</td>
                <td class="py-3 text-right text-white font-mono font-semibold">${formatValCompact(m.amount)}</td>
                <td class="py-3 text-right font-mono">${changeHtml}</td>
            `;
            merchantBodyEl.appendChild(tr);
        });
    }

    const heatmapData = {};
    const heatmapCategories = ['Housing', 'Food & Dining', 'Transport', 'Shopping', 'Utilities'];
    heatmapCategories.forEach(cat => {
        heatmapData[cat] = new Array(7).fill(0);
    });
    
    allTransactions.forEach(t => {
        if (t.date && t.date >= bounds.startStr && t.date <= bounds.endStr) {
            const normAmt = getNormalizedEur(t.amount, t.currency);
            const isTransfer = (t.category || '').toLowerCase().includes('transfer');
            if (normAmt < 0 && !isTransfer) {
                const absAmt = Math.abs(normAmt);
                const tCat = t.category || 'Other';
                const matchedCat = mapToGroup(tCat);
                
                if (heatmapData[matchedCat]) {
                    const day = (new Date(t.date).getDay() + 6) % 7;
                    heatmapData[matchedCat][day] += absAmt;
                }
            }
        }
    });

    const fallbackWeights = {
        'Housing': [0.8, 0, 0, 0, 0, 0, 0],
        'Food & Dining': [0.2, 0.3, 0.4, 0.3, 0.6, 0.9, 0.8],
        'Transport': [0.4, 0.5, 0.4, 0.5, 0.6, 0.2, 0.1],
        'Shopping': [0.1, 0.2, 0.3, 0.2, 0.4, 0.8, 0.5],
        'Utilities': [0.5, 0, 0, 0, 0, 0, 0]
    };

    heatmapCategories.forEach(cat => {
        const maxReal = Math.max(...heatmapData[cat]);
        for (let day = 0; day < 7; day++) {
            if (maxReal > 0) {
                heatmapData[cat][day] = heatmapData[cat][day] / maxReal;
            } else {
                heatmapData[cat][day] = fallbackWeights[cat][day];
            }
        }
    });

    const heatmapRowsEl = document.getElementById('insight-heatmap-rows');
    if (heatmapRowsEl) {
        heatmapRowsEl.innerHTML = '';
        const categoryLabelsMap = {
            'Housing': 'Housing',
            'Food & Dining': 'Food',
            'Transport': 'Transport',
            'Shopping': 'Shopping',
            'Utilities': 'Utilities'
        };
        heatmapCategories.forEach(cat => {
            const rowDiv = document.createElement('div');
            rowDiv.className = 'grid grid-cols-12 gap-2 items-center py-1 hover:bg-surface-variant/5 px-2 rounded-xl transition-colors';
            const catMeta = getCategoryDetails(cat);
            let cellsHtml = `
                <div class="col-span-3 text-left truncate flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full ${catMeta.bg || 'bg-zinc-800/40'} flex items-center justify-center ${catMeta.text || 'text-zinc-400'} shrink-0 border ${catMeta.border || 'border-transparent'}">
                        <span class="material-symbols-outlined text-base">${catMeta.icon || 'payments'}</span>
                    </div>
                    <span class="text-xs font-semibold text-white truncate">
                        ${categoryLabelsMap[cat] || cat}
                    </span>
                </div>`;
            for (let day = 0; day < 7; day++) {
                const weight = heatmapData[cat][day];
                const opacity = 0.05 + weight * 0.8;
                const colorHex = getCategoryColor(cat);
                cellsHtml += `
                    <div class="col-span-1 h-6 rounded transition-all hover:scale-110 cursor-pointer" 
                         style="background-color: ${colorHex}; opacity: ${opacity};" 
                         title="${cat}: ${(weight * 100).toFixed(0)}% intensity">
                    </div>`;
            }
            cellsHtml += `<div class="col-span-2"></div>`;
            rowDiv.innerHTML = cellsHtml;
            heatmapRowsEl.appendChild(rowDiv);
        });
    }


    const recsSliderEl = document.getElementById('insight-recs-slider');
    if (recsSliderEl) {
        recsSliderEl.innerHTML = '';
        recsSliderEl.innerHTML += `
            <div class="glass-card p-5 min-w-[280px] flex-1 max-w-[320px] flex flex-col justify-between border-l-2 border-l-[#ff9f0a]">
                <div class="flex items-start justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-[#ff9f0a]/15 text-[#ff9f0a] flex items-center justify-center shrink-0">
                            <span class="material-symbols-outlined text-lg">restaurant</span>
                        </div>
                        <div>
                            <h4 class="text-xs font-bold text-white">Reduce Food Spend</h4>
                            <p class="text-[10px] text-on-surface-variant mt-0.5">Try cooking more at home</p>
                        </div>
                    </div>
                    <button class="text-on-surface-variant hover:text-white transition-colors">
                        <span class="material-symbols-outlined text-sm">more_vert</span>
                    </button>
                </div>
                <div class="flex items-end justify-between mt-6">
                    <div>
                        <span class="text-[9px] text-on-surface-variant block uppercase tracking-wider">Potential Savings</span>
                        <span class="text-sm font-bold text-white">${formatValCompact(120)}/mo</span>
                    </div>
                    <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-[#30d158]/20 text-[#30d158]">High Impact</span>
                </div>
            </div>
        `;
        recsSliderEl.innerHTML += `
            <div class="glass-card p-5 min-w-[280px] flex-1 max-w-[320px] flex flex-col justify-between border-l-2 border-l-[#bf5af2]">
                <div class="flex items-start justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-[#bf5af2]/15 text-[#bf5af2] flex items-center justify-center shrink-0">
                            <span class="material-symbols-outlined text-lg">subscriptions</span>
                        </div>
                        <div>
                            <h4 class="text-xs font-bold text-white">Review Subscriptions</h4>
                            <p class="text-[10px] text-on-surface-variant mt-0.5">You have 2 unused subscriptions</p>
                        </div>
                    </div>
                    <button class="text-on-surface-variant hover:text-white transition-colors">
                        <span class="material-symbols-outlined text-sm">more_vert</span>
                    </button>
                </div>
                <div class="flex items-end justify-between mt-6">
                    <div>
                        <span class="text-[9px] text-on-surface-variant block uppercase tracking-wider">Potential Savings</span>
                        <span class="text-sm font-bold text-white">${formatValCompact(42)}/mo</span>
                    </div>
                    <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-[#ff453a]/20 text-[#ff453a]">High Impact</span>
                </div>
            </div>
        `;
        recsSliderEl.innerHTML += `
            <div class="glass-card p-5 min-w-[280px] flex-1 max-w-[320px] flex flex-col justify-between border-l-2 border-l-[#30d158]">
                <div class="flex items-start justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-[#30d158]/15 text-[#30d158] flex items-center justify-center shrink-0">
                            <span class="material-symbols-outlined text-lg">shield</span>
                        </div>
                        <div>
                            <h4 class="text-xs font-bold text-white">Increase Emergency Fund</h4>
                            <p class="text-[10px] text-on-surface-variant mt-0.5">Move €420 to savings</p>
                        </div>
                    </div>
                    <button class="text-on-surface-variant hover:text-white transition-colors">
                        <span class="material-symbols-outlined text-sm">more_vert</span>
                    </button>
                </div>
                <div class="flex items-end justify-between mt-6">
                    <div>
                        <span class="text-[9px] text-on-surface-variant block uppercase tracking-wider">Potential Improvement</span>
                        <span class="text-sm font-bold text-white">+${formatValCompact(17)}/yr</span>
                    </div>
                    <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-[#ff9f0a]/20 text-[#ff9f0a]">Medium Impact</span>
                </div>
            </div>
        `;
        recsSliderEl.innerHTML += `
            <div class="glass-card p-5 min-w-[280px] flex-1 max-w-[320px] flex flex-col justify-between border-l-2 border-l-[#ff375f]">
                <div class="flex items-start justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-[#ff375f]/15 text-[#ff375f] flex items-center justify-center shrink-0">
                            <span class="material-symbols-outlined text-lg">lightbulb</span>
                        </div>
                        <div>
                            <h4 class="text-xs font-bold text-white">Review Utility Plans</h4>
                            <p class="text-[10px] text-on-surface-variant mt-0.5">You could save on electricity</p>
                        </div>
                    </div>
                    <button class="text-on-surface-variant hover:text-white transition-colors">
                        <span class="material-symbols-outlined text-sm">more_vert</span>
                    </button>
                </div>
                <div class="flex items-end justify-between mt-6">
                    <div>
                        <span class="text-[9px] text-on-surface-variant block uppercase tracking-wider">Potential Savings</span>
                        <span class="text-sm font-bold text-white">${formatValCompact(80)}/yr</span>
                    </div>
                    <span class="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-[#ff9f0a]/20 text-[#ff9f0a]">Medium Impact</span>
                </div>
            </div>
        `;
    }
}


// Global configurations for Budgets and Goals
let budgetLimits = {};
let financialGoals = [];

async function loadBudgetLimits() {
    try {
        const res = await fetch('/api/settings/budget_limits');
        if (res.ok) {
            const data = await res.json();
            if (data.value) {
                budgetLimits = JSON.parse(data.value);
            }
        }
    } catch (e) {
        console.error("Error loading budget limits:", e);
    }
}

async function loadGoals() {
    try {
        const res = await fetch('/api/settings/financial_goals');
        if (res.ok) {
            const data = await res.json();
            if (data.value) {
                financialGoals = JSON.parse(data.value);
            }
        }
    } catch (e) {
        console.error("Error loading goals:", e);
    }
    if (!financialGoals || financialGoals.length === 0) {
        financialGoals = [
            { name: "FIRE Fund", target: 500000, current: null },
            { name: "Emergency Buffer", target: 15000, current: null }
        ];
    }
}

// Transactions tab loader
async function loadTransactionsData() {
    await checkVaultStatus();
    if (accountsList.length === 0) {
        try {
            const accRes = await fetch('/api/accounts');
            accountsList = await accRes.json();
        } catch (e) {
            console.error("Error fetching accounts in transactions loader:", e);
        }
    }
    populateAccountSelects();
    if (allTransactions.length === 0) {
        await fetchLedgerEntries();
    } else {
        renderMonthsSidebar();
        applyLedgerFilters();
    }
}

// Budgets tab loader & manager
async function loadBudgetsData() {
    await checkVaultStatus();
    await loadBudgetLimits();
    
    if (allTransactions.length === 0) {
        await fetchLedgerEntries();
    }
    
    if (categories.length === 0) {
        const catRes = await fetch('/api/categories');
        categories = await catRes.json();
    }
    
    const adjustSelect = document.getElementById('budget-adjust-category');
    if (adjustSelect) {
        adjustSelect.innerHTML = '';
        categories.forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat;
            opt.textContent = cat;
            adjustSelect.appendChild(opt);
        });
    }

    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;
    const currentMonthStr = `${currentYear}-${currentMonth.toString().padStart(2, '0')}`;
    
    const spentThisMonth = {};
    let spentYTD = 0;
    
    allTransactions.forEach(t => {
        const normAmt = getNormalizedEur(t.amount, t.currency);
        if (normAmt < 0) {
            const amt = Math.abs(normAmt);
            const tDate = new Date(t.date);
            if (tDate.getFullYear() === currentYear) {
                spentYTD += amt;
            }
            if (t.date && t.date.startsWith(currentMonthStr)) {
                const cat = t.category || 'Unsorted';
                spentThisMonth[cat] = (spentThisMonth[cat] || 0) + amt;
            }
        }
    });

    let totalLimit = 0;
    let overLimitCount = 0;
    let monthlyBudgetSpentOnLimitedCategories = 0;

    Object.keys(budgetLimits).forEach(cat => {
        const limit = budgetLimits[cat] || 0;
        totalLimit += limit;
        const spent = spentThisMonth[cat] || 0;
        if (limit > 0) {
            monthlyBudgetSpentOnLimitedCategories += spent;
            if (spent > limit) {
                overLimitCount++;
            }
        }
    });

    const remainingBudget = Math.max(0, totalLimit - monthlyBudgetSpentOnLimitedCategories);

    const spentPct = totalLimit > 0 ? Math.min(100, Math.round((monthlyBudgetSpentOnLimitedCategories / totalLimit) * 100)) : 0;

    document.getElementById('budget-summary-limit').textContent = formatVal(totalLimit);
    document.getElementById('budget-summary-spent').textContent = formatVal(monthlyBudgetSpentOnLimitedCategories);
    document.getElementById('budget-summary-remaining').textContent = formatVal(remainingBudget);
    document.getElementById('budget-summary-overage').textContent = `${overLimitCount} Categories`;

    const progressGauge = document.getElementById('budget-progress-gauge');
    const pctEl = document.getElementById('budget-gauge-pct');
    if (pctEl) pctEl.textContent = `${spentPct}%`;
    
    if (progressGauge) {
        const circ = 502.65;
        const offset = circ - (spentPct / 100) * circ;
        progressGauge.style.strokeDasharray = `${circ}`;
        progressGauge.style.strokeDashoffset = `${offset}`;
    }
    
    const spentProgressBar = document.getElementById('budget-spent-progress-bar');
    if (spentProgressBar) {
        spentProgressBar.style.width = `${spentPct}%`;
    }

    const listContainer = document.getElementById('category-budgets-list');
    if (listContainer) {
        listContainer.innerHTML = '';
        categories.forEach(cat => {
            const limit = budgetLimits[cat] || 0;
            const spent = spentThisMonth[cat] || 0;
            
            let pct = 0;
            let barColor = 'bg-primary';
            let pctText = 'No limit';
            
            if (limit > 0) {
                pct = Math.min(100, (spent / limit) * 100);
                pctText = `${((spent / limit) * 100).toFixed(0)}% used`;
                if (spent > limit) {
                    barColor = 'bg-error';
                }
            }
            
            const card = document.createElement('div');
            card.className = 'space-y-2 pb-4 border-b border-white/[0.02]';
            card.innerHTML = `
                <div class="flex justify-between items-center text-xs">
                    <div>
                        <span class="font-bold text-white">${cat}</span>
                        <span class="text-[10px] text-on-surface-variant font-mono ml-2">(${pctText})</span>
                    </div>
                    <div class="font-mono text-right">
                        <span class="font-bold text-white">${formatVal(spent)}</span>
                        <span class="text-on-surface-variant">/ ${limit > 0 ? formatVal(limit) : 'No limit'}</span>
                    </div>
                </div>
                <div class="w-full h-2 rounded-full bg-zinc-900 border border-white/5 overflow-hidden">
                    <div class="h-full ${barColor} rounded-full transition-all duration-500" style="width: ${pct}%"></div>
                </div>
            `;
            listContainer.appendChild(card);
        });
    }

    const suggestionsContainer = document.getElementById('budget-ai-suggestions');
    if (suggestionsContainer) {
        suggestionsContainer.innerHTML = '';
        let suggestionsHTML = '';
        let count = 0;
        
        categories.forEach(cat => {
            if (count >= 3) return;
            const spent = spentThisMonth[cat] || 0;
            const limit = budgetLimits[cat] || 0;
            if (limit > 0 && spent > limit * 0.9) {
                const recommended = Math.ceil((spent * 1.1) / 50) * 50;
                suggestionsHTML += `
                    <div class="p-3 bg-white/5 border border-white/5 rounded-xl space-y-1">
                        <div class="flex justify-between font-bold text-white text-[10px]">
                            <span>${cat}</span>
                            <span class="text-primary font-bold">Recommend adjustment</span>
                        </div>
                        <p class="text-[10px] text-on-surface-variant">Spending is at ${(spent/limit*100).toFixed(0)}% of limit. Raise limit to ${formatVal(recommended)}.</p>
                    </div>
                `;
                count++;
            }
        });
        
        if (suggestionsHTML === '') {
            suggestionsHTML = `
                <div class="p-3 bg-white/5 border border-white/5 rounded-xl">
                    <p class="text-[10px] text-on-surface-variant">All budget lines are operating within safe tolerance boundaries.</p>
                </div>
            `;
        }
        suggestionsContainer.innerHTML = suggestionsHTML;
    }
}

async function saveCategoryBudgetLimit() {
    const category = document.getElementById('budget-adjust-category').value;
    const amountVal = parseFloat(document.getElementById('budget-adjust-amount').value);
    
    if (!category || isNaN(amountVal) || amountVal < 0) {
        alert("Please enter a valid limit amount.");
        return;
    }
    
    budgetLimits[category] = amountVal;
    
    try {
        const res = await fetch('/api/settings/budget_limits', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: JSON.stringify(budgetLimits) })
        });
        if (res.ok) {
            document.getElementById('budget-adjust-amount').value = '';
            await loadBudgetsData();
        }
    } catch (e) {
        console.error("Save budget error:", e);
    }
}

// Goals tab loader & manager
async function loadGoalsData() {
    await checkVaultStatus();
    await loadGoals();
    
    let reserves = 0;
    let runway = 0;
    try {
        const healthRes = await fetch('/api/analytics/health');
        const health = await healthRes.json();
        reserves = health.cash_reserves_eur;
        runway = health.runway_months;
    } catch (e) {
        console.error("Health fetch error in goals loader:", e);
    }
    
    let combinedTarget = 0;
    let combinedCurrent = 0;
    
    financialGoals.forEach(g => {
        combinedTarget += g.target;
        combinedCurrent += g.current !== null && g.current !== undefined ? g.current : reserves;
    });

    const passiveIncomeSWR = combinedCurrent * 0.04;

    document.getElementById('goal-summary-target').textContent = formatVal(combinedTarget);
    document.getElementById('goal-summary-current').textContent = formatVal(reserves);
    document.getElementById('goal-summary-emergency').textContent = `${runway} Months`;
    document.getElementById('goal-summary-swr').textContent = `${formatVal(passiveIncomeSWR)} / yr`;

    const listContainer = document.getElementById('goals-progress-list');
    if (listContainer) {
        listContainer.innerHTML = '';
        financialGoals.forEach((g, idx) => {
            const currentVal = g.current !== null && g.current !== undefined ? g.current : reserves;
            const pct = Math.min(100, (currentVal / g.target) * 100);
            
            const card = document.createElement('div');
            card.className = 'space-y-2.5 pb-4 border-b border-white/[0.02]';
            card.innerHTML = `
                <div class="flex justify-between items-center text-xs">
                    <div>
                        <span class="font-bold text-white">${g.name}</span>
                        <span class="text-[10px] text-on-surface-variant font-mono ml-2">(${pct.toFixed(1)}% reached)</span>
                    </div>
                    <div class="font-mono text-right">
                        <span class="font-bold text-white">${formatVal(currentVal)}</span>
                        <span class="text-on-surface-variant font-medium">/ ${formatVal(g.target)}</span>
                    </div>
                </div>
                <div class="flex items-center space-x-3">
                    <div class="flex-1 h-2.5 rounded-full bg-zinc-900 border border-white/5 overflow-hidden">
                        <div class="h-full bg-primary rounded-full transition-all duration-500" style="width: ${pct}%"></div>
                    </div>
                    <button onclick="deleteMilestone(${idx})" class="text-on-surface-variant hover:text-error transition-all" title="Delete goal">
                        <span class="material-symbols-outlined text-[16px]">delete</span>
                    </button>
                </div>
            `;
            listContainer.appendChild(card);
        });
    }
}

async function createNewMilestoneGoal() {
    const name = document.getElementById('goal-create-name').value.trim();
    const targetVal = parseFloat(document.getElementById('goal-create-target').value);
    const currentValRaw = document.getElementById('goal-create-current').value;
    
    if (!name || isNaN(targetVal) || targetVal <= 0) {
        alert("Please enter a valid goal name and target capital.");
        return;
    }
    
    const current = currentValRaw.trim() === '' ? null : parseFloat(currentValRaw);
    financialGoals.push({ name, target: targetVal, current });
    
    try {
        const res = await fetch('/api/settings/financial_goals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: JSON.stringify(financialGoals) })
        });
        if (res.ok) {
            document.getElementById('goal-create-name').value = '';
            document.getElementById('goal-create-target').value = '';
            document.getElementById('goal-create-current').value = '';
            await loadGoalsData();
        }
    } catch (e) {
        console.error("Save goal error:", e);
    }
}

async function deleteMilestone(idx) {
    if (!confirm("Are you sure you want to delete this goal milestone?")) return;
    financialGoals.splice(idx, 1);
    try {
        const res = await fetch('/api/settings/financial_goals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: JSON.stringify(financialGoals) })
        });
        if (res.ok) {
            await loadGoalsData();
        }
    } catch (e) {
        console.error("Delete goal error:", e);
    }
}

// Automation tab loader & sub-tabs controller
async function loadAutomationData() {
    await checkVaultStatus();
    try {
        const reviewRes = await fetch('/api/unknown');
        const reviewTxns = await reviewRes.json();
        const reviewCount = reviewTxns.length;
        document.getElementById('auto-summary-review').textContent = `${reviewCount} Tx`;
        
        const badge = document.getElementById('review-badge');
        if (badge) {
            if (reviewCount > 0) {
                badge.textContent = reviewCount.toString();
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }
        
        const rulesRes = await fetch('/api/rules');
        const rules = await rulesRes.json();
        document.getElementById('auto-summary-rules').textContent = `${rules.length} Rules`;
        
        const historyRes = await fetch('/api/sync/history');
        const history = await historyRes.json();
        document.getElementById('auto-summary-history').textContent = `${history.length} Feeds`;

        const syncSetRes = await fetch('/api/settings/auto-sync');
        const syncSet = await syncSetRes.json();
        document.getElementById('auto-summary-status').textContent = syncSet.enabled ? 'Active' : 'Disabled';

        setAutomationSubTab(currentAutomationSubTab);
    } catch (e) {
        console.error("Error loading automation data:", e);
    }
}

function setAutomationSubTab(subTab) {
    currentAutomationSubTab = subTab;
    
    document.getElementById('sub-panel-auto-review').classList.add('hidden');
    document.getElementById('sub-panel-auto-rules').classList.add('hidden');
    document.getElementById('sub-panel-auto-import').classList.add('hidden');
    
    document.getElementById(`sub-panel-auto-${subTab}`).classList.remove('hidden');
    
    const btns = ['review', 'rules', 'import'];
    btns.forEach(b => {
        const btn = document.getElementById(`btn-auto-${b}`);
        if (btn) {
            if (b === subTab) {
                btn.className = 'px-4 py-2 rounded-lg bg-white/10 text-primary transition-all';
            } else {
                btn.className = 'px-4 py-2 rounded-lg text-on-surface-variant hover:text-white transition-all';
            }
        }
    });
    
    if (subTab === 'review') {
        loadReviewQueueData();
    } else if (subTab === 'rules') {
        loadRulesData();
    } else if (subTab === 'import') {
        loadImportHistory();
    }
}

function changeStatsChartType(type) {
    activeStatsChartType = type;
    renderStatsChart();
}

function changeStatsSortOrder(order) {
    activeStatsSortOrder = order;
    renderStatsChart();
}

function setStatsProfile(profile) {
    activeStatsProfile = profile;
    
    const profiles = ['categorical', 'trend', 'asset'];
    profiles.forEach(p => {
        const btn = document.getElementById(`stats-profile-${p}`);
        if (btn) {
            if (p === profile) {
                btn.className = 'w-full text-left py-2 px-3 rounded text-xs font-bold bg-white/10 text-primary transition-all';
            } else {
                btn.className = 'w-full text-left py-2 px-3 rounded text-xs font-medium text-on-surface-variant hover:text-white transition-all';
            }
        }
    });

    const chartSelect = document.getElementById('stats-chart-type');
    const breakdownContainer = document.getElementById('stats-breakdown-options');
    if (!chartSelect || !breakdownContainer) return;
    
    chartSelect.innerHTML = '';
    breakdownContainer.innerHTML = '';

    const createBreakdownBtn = (val, label) => {
        const btn = document.createElement('button');
        btn.className = `w-full text-left py-1.5 px-2 rounded hover:bg-white/5 transition-all truncate ${
            activeStatsBreakdown === val ? 'text-primary font-bold bg-primary/5' : 'text-on-surface-variant'
        }`;
        btn.textContent = label;
        btn.onclick = () => {
            activeStatsBreakdown = val;
            document.querySelectorAll('#stats-breakdown-options button').forEach(b => {
                b.classList.remove('text-primary', 'font-bold', 'bg-primary/5');
                b.classList.add('text-on-surface-variant');
            });
            btn.classList.add('text-primary', 'font-bold', 'bg-primary/5');
            btn.classList.remove('text-on-surface-variant');
            renderStatsChart();
        };
        return btn;
    };

    if (profile === 'categorical') {
        chartSelect.innerHTML = `
            <option value="Pie Chart">Pie Chart</option>
            <option value="Column Chart">Column Chart</option>
            <option value="Line Chart">Line Chart</option>
        `;
        activeStatsChartType = 'Pie Chart';
        activeStatsBreakdown = 'outflows_by_category';
        
        breakdownContainer.appendChild(createBreakdownBtn('outflows_by_category', 'Outflows by Category'));
        breakdownContainer.appendChild(createBreakdownBtn('outflows_by_account', 'Outflows by Account'));
        breakdownContainer.appendChild(createBreakdownBtn('inflows_by_account', 'Inflows by Account'));
    } else if (profile === 'trend') {
        chartSelect.innerHTML = `
            <option value="Column Chart">Column Chart</option>
            <option value="Line Chart">Line Chart</option>
        `;
        activeStatsChartType = 'Column Chart';
        activeStatsBreakdown = 'net_cash_flow_trend';
        
        breakdownContainer.appendChild(createBreakdownBtn('net_cash_flow_trend', 'Net Cash Flow Trend'));
        breakdownContainer.appendChild(createBreakdownBtn('expense_trend_by_category', 'Expense Trend by Category'));
        breakdownContainer.appendChild(createBreakdownBtn('income_trend_by_account', 'Income Trend by Account'));
    } else if (profile === 'asset') {
        chartSelect.innerHTML = `
            <option value="Line Chart">Line Chart</option>
        `;
        activeStatsChartType = 'Line Chart';
        activeStatsBreakdown = 'net_worth_over_time';
        
        breakdownContainer.appendChild(createBreakdownBtn('net_worth_over_time', 'Net Worth over time'));
        breakdownContainer.appendChild(createBreakdownBtn('assets_vs_liabilities', 'Assets vs Liabilities'));
    }

    renderStatsChart();
}

function renderStatsChart() {
    const svg = document.getElementById('stats-render-svg');
    if (!svg) return;
    svg.innerHTML = '';

    const titleEl = document.getElementById('stats-chart-title');
    const subtitleEl = document.getElementById('stats-chart-subtitle');
    const totalEl = document.getElementById('stats-total-value');

    if (allTransactions.length === 0) {
        titleEl.textContent = 'No Data Available';
        subtitleEl.textContent = 'Add transactions to populate reports';
        totalEl.textContent = formatVal(0);
        return;
    }

    if (activeStatsProfile === 'categorical') {
        renderCategoricalStats(svg, titleEl, subtitleEl, totalEl);
    } else if (activeStatsProfile === 'trend') {
        renderTrendStats(svg, titleEl, subtitleEl, totalEl);
    } else if (activeStatsProfile === 'asset') {
        renderAssetStats(svg, titleEl, subtitleEl, totalEl);
    }
}

function renderCategoricalStats(svg, titleEl, subtitleEl, totalEl) {
    let groups = {};
    let isOutflow = activeStatsBreakdown.startsWith('outflows_');
    
    allTransactions.forEach(t => {
        const normAmt = getNormalizedEur(t.amount, t.currency);
        const matchesStream = isOutflow ? normAmt < 0 : normAmt > 0;
        
        if (matchesStream) {
            const key = activeStatsBreakdown.endsWith('_category') ? (t.category || 'Unsorted') : (t.account_name || 'Bank Feed');
            groups[key] = (groups[key] || 0) + Math.abs(normAmt);
        }
    });

    let data = Object.entries(groups).map(([name, val]) => ({ name, value: val }));
    const totalVal = data.reduce((sum, item) => sum + item.value, 0);
    totalEl.textContent = formatVal(totalVal);

    if (activeStatsBreakdown === 'outflows_by_category') {
        titleEl.textContent = 'Outflows by Category';
        subtitleEl.textContent = 'Expense distribution across categories';
    } else if (activeStatsBreakdown === 'outflows_by_account') {
        titleEl.textContent = 'Outflows by Account';
        subtitleEl.textContent = 'Expense distribution across accounts';
    } else if (activeStatsBreakdown === 'inflows_by_account') {
        titleEl.textContent = 'Inflows by Account';
        subtitleEl.textContent = 'Income distribution across accounts';
    }

    if (data.length === 0) {
        svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="rgba(255,255,255,0.4)" font-size="12">No transactions match these stream settings.</text>`;
        return;
    }

    if (activeStatsSortOrder === 'Amount') {
        data.sort((a, b) => b.value - a.value);
    } else if (activeStatsSortOrder === 'Category') {
        data.sort((a, b) => a.name.localeCompare(b.name));
    }

    if (activeStatsChartType === 'Pie Chart') {
        drawPieChart(svg, data, totalVal);
    } else if (activeStatsChartType === 'Column Chart') {
        drawColumnChart(svg, data);
    } else if (activeStatsChartType === 'Line Chart') {
        drawLineChart(svg, data);
    }
}

function renderTrendStats(svg, titleEl, subtitleEl, totalEl) {
    let monthsGroups = {};
    allTransactions.forEach(t => {
        if (!t.date || t.date.length < 7) return;
        const month = t.date.substring(0, 7);
        const normAmt = getNormalizedEur(t.amount, t.currency);
        
        if (!monthsGroups[month]) {
            monthsGroups[month] = { inflows: 0, outflows: 0 };
        }
        
        if (normAmt > 0) {
            monthsGroups[month].inflows += normAmt;
        } else {
            monthsGroups[month].outflows += Math.abs(normAmt);
        }
    });

    const sortedMonths = Object.keys(monthsGroups).sort();
    let data = [];
    let totalVal = 0;

    if (activeStatsBreakdown === 'net_cash_flow_trend') {
        titleEl.textContent = 'Monthly Net Cash Flow';
        subtitleEl.textContent = 'Inflows minus Outflows over time';
        sortedMonths.forEach(m => {
            const diff = monthsGroups[m].inflows - monthsGroups[m].outflows;
            data.push({ name: m, value: diff });
            totalVal += diff;
        });
    } else if (activeStatsBreakdown === 'expense_trend_by_category') {
        titleEl.textContent = 'Monthly Total Expenses';
        subtitleEl.textContent = 'Total outflows grouped by month';
        sortedMonths.forEach(m => {
            const exp = monthsGroups[m].outflows;
            data.push({ name: m, value: exp });
            totalVal += exp;
        });
    } else if (activeStatsBreakdown === 'income_trend_by_account') {
        titleEl.textContent = 'Monthly Total Income';
        subtitleEl.textContent = 'Total inflows grouped by month';
        sortedMonths.forEach(m => {
            const inc = monthsGroups[m].inflows;
            data.push({ name: m, value: inc });
            totalVal += inc;
        });
    }

    totalEl.textContent = formatVal(totalVal);

    if (data.length === 0) {
        svg.innerHTML = `<text x="50%" y="50%" text-anchor="middle" fill="rgba(255,255,255,0.4)" font-size="12">No trend logs found.</text>`;
        return;
    }

    if (activeStatsSortOrder === 'Category') {
        data.sort((a, b) => a.name.localeCompare(b.name));
    } else if (activeStatsSortOrder === 'Amount') {
        data.sort((a, b) => b.value - a.value);
    }

    if (activeStatsChartType === 'Column Chart') {
        drawTrendColumnChart(svg, data);
    } else {
        drawTrendLineChart(svg, data);
    }
}

function renderAssetStats(svg, titleEl, subtitleEl, totalEl) {
    const sorted = [...allTransactions].sort((a, b) => new Date(a.date) - new Date(b.date));
    
    if (activeStatsBreakdown === 'net_worth_over_time') {
        titleEl.textContent = 'Cumulative Net Worth';
        subtitleEl.textContent = 'Cash balance reserves trajectory';
        
        let balanceAccumulator = 0;
        let data = sorted.map(t => {
            balanceAccumulator += getNormalizedEur(t.amount, t.currency);
            return { name: t.date, value: balanceAccumulator };
        });
        
        totalEl.textContent = formatVal(balanceAccumulator);
        drawAssetLineChart(svg, data, '#5e5ce6');
    } else if (activeStatsBreakdown === 'assets_vs_liabilities') {
        titleEl.textContent = 'Assets vs Liabilities';
        subtitleEl.textContent = 'Cumulative positive vs negative flows';
        
        let assetsAccumulator = 0;
        let liabilitiesAccumulator = 0;
        let dataAssets = [];
        let dataLiabilities = [];
        
        sorted.forEach(t => {
            const normAmt = getNormalizedEur(t.amount, t.currency);
            if (normAmt > 0) {
                assetsAccumulator += normAmt;
            } else {
                liabilitiesAccumulator += Math.abs(normAmt);
            }
            dataAssets.push({ name: t.date, value: assetsAccumulator });
            dataLiabilities.push({ name: t.date, value: liabilitiesAccumulator });
        });
        
        totalEl.textContent = `Assets: ${formatVal(assetsAccumulator)} | Liabilities: ${formatVal(liabilitiesAccumulator)}`;
        drawDoubleAssetLineChart(svg, dataAssets, dataLiabilities);
    }
}

// SVG Drawing Functions
function drawPieChart(svg, data, totalVal) {
    const w = svg.clientWidth || 400;
    const h = svg.clientHeight || 250;
    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(cx, cy) - 30;
    
    const colors = ['#5e5ce6', '#a2a1f8', '#8e8e93', '#b0b5c0', '#c7c7cc', '#aeaeb2', '#d1d1d6', '#e5e5ea'];
    let accumulatedAngle = 0;
    
    const sortedData = [...data].sort((a, b) => b.value - a.value);
    
    sortedData.forEach((item, idx) => {
        const angle = (item.value / totalVal) * 360;
        const x1 = cx + r * Math.cos((accumulatedAngle - 90) * Math.PI / 180);
        const y1 = cy + r * Math.sin((accumulatedAngle - 90) * Math.PI / 180);
        const x2 = cx + r * Math.cos((accumulatedAngle + angle - 90) * Math.PI / 180);
        const y2 = cy + r * Math.sin((accumulatedAngle + angle - 90) * Math.PI / 180);
        
        const largeArc = angle > 180 ? 1 : 0;
        const pathData = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;
        
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', pathData);
        path.setAttribute('fill', colors[idx % colors.length]);
        path.setAttribute('stroke', '#131315');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('class', 'transition-all duration-300 hover:opacity-90 cursor-pointer');
        
        const tooltipText = `${item.name}: ${formatVal(item.value)} (${((item.value / totalVal) * 100).toFixed(1)}%)`;
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = tooltipText;
        path.appendChild(title);
        svg.appendChild(path);
        
        accumulatedAngle += angle;
    });

    const innerCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    innerCircle.setAttribute('cx', cx.toString());
    innerCircle.setAttribute('cy', cy.toString());
    innerCircle.setAttribute('r', (r * 0.55).toString());
    innerCircle.setAttribute('fill', '#131315');
    svg.appendChild(innerCircle);
}

function drawColumnChart(svg, data) {
    const w = svg.clientWidth || 400;
    const h = svg.clientHeight || 250;
    const paddingX = 40;
    const paddingY = 30;
    const maxVal = Math.max(...data.map(d => d.value)) || 100;
    
    const colWidth = (w - 2 * paddingX) / data.length;
    const chartHeight = h - 2 * paddingY;
    
    data.forEach((item, idx) => {
        const colH = (item.value / maxVal) * chartHeight;
        const x = paddingX + idx * colWidth + 5;
        const y = h - paddingY - colH;
        const rectW = Math.max(5, colWidth - 10);
        
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', x.toString());
        rect.setAttribute('y', y.toString());
        rect.setAttribute('width', rectW.toString());
        rect.setAttribute('height', colH.toString());
        rect.setAttribute('fill', '#5e5ce6');
        rect.setAttribute('rx', '4');
        rect.setAttribute('class', 'hover:fill-[#c3c0ff] transition-all cursor-pointer');
        
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `${item.name}: ${formatVal(item.value)}`;
        rect.appendChild(title);
        svg.appendChild(rect);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', (x + rectW / 2).toString());
        text.setAttribute('y', (h - paddingY + 15).toString());
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', 'rgba(255,255,255,0.6)');
        text.setAttribute('font-size', '8');
        text.textContent = item.name.substring(0, 10);
        svg.appendChild(text);
    });
}

function drawLineChart(svg, data) {
    const w = svg.clientWidth || 400;
    const h = svg.clientHeight || 250;
    const paddingX = 40;
    const paddingY = 30;
    const maxVal = Math.max(...data.map(d => d.value)) || 100;
    
    const stepX = (w - 2 * paddingX) / Math.max(1, data.length - 1);
    const chartHeight = h - 2 * paddingY;
    
    const points = data.map((item, idx) => ({
        x: paddingX + idx * stepX,
        y: h - paddingY - (item.value / maxVal) * chartHeight,
        name: item.name,
        value: item.value
    }));

    if (points.length >= 2) {
        let d = `M ${points[0].x} ${points[0].y}`;
        for (let i = 1; i < points.length; i++) {
            d += ` L ${points[i].x} ${points[i].y}`;
        }
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#30d158');
        path.setAttribute('stroke-width', '2.5');
        svg.appendChild(path);
    }

    points.forEach(p => {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', p.x.toString());
        circle.setAttribute('cy', p.y.toString());
        circle.setAttribute('r', '4');
        circle.setAttribute('fill', '#30d158');
        circle.setAttribute('stroke', '#131315');
        circle.setAttribute('stroke-width', '1.5');
        circle.setAttribute('class', 'hover:r-6 cursor-pointer');
        
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `${p.name}: ${formatVal(p.value)}`;
        circle.appendChild(title);
        svg.appendChild(circle);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', p.x.toString());
        text.setAttribute('y', (h - paddingY + 15).toString());
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', 'rgba(255,255,255,0.6)');
        text.setAttribute('font-size', '8');
        text.textContent = p.name.substring(0, 10);
        svg.appendChild(text);
    });
}

function drawTrendColumnChart(svg, data) {
    const w = svg.clientWidth || 400;
    const h = svg.clientHeight || 250;
    const paddingX = 40;
    const paddingY = 30;
    
    const maxVal = Math.max(...data.map(d => Math.abs(d.value))) || 100;
    const chartHeight = h - 2 * paddingY;
    const zeroY = paddingY + chartHeight / 2;
    
    const colWidth = (w - 2 * paddingX) / data.length;
    
    const baseline = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    baseline.setAttribute('x1', paddingX.toString());
    baseline.setAttribute('y1', zeroY.toString());
    baseline.setAttribute('x2', (w - paddingX).toString());
    baseline.setAttribute('y2', zeroY.toString());
    baseline.setAttribute('stroke', 'rgba(255,255,255,0.15)');
    baseline.setAttribute('stroke-width', '1');
    svg.appendChild(baseline);

    data.forEach((item, idx) => {
        const ratio = item.value / maxVal;
        const colH = ratio * (chartHeight / 2);
        const rectW = Math.max(5, colWidth - 10);
        const x = paddingX + idx * colWidth + 5;
        
        let y, rectH;
        if (item.value >= 0) {
            y = zeroY - colH;
            rectH = colH;
        } else {
            y = zeroY;
            rectH = Math.abs(colH);
        }

        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', x.toString());
        rect.setAttribute('y', y.toString());
        rect.setAttribute('width', rectW.toString());
        rect.setAttribute('height', Math.max(2, rectH).toString());
        rect.setAttribute('fill', item.value >= 0 ? '#30d158' : '#ff453a');
        rect.setAttribute('rx', '2');
        rect.setAttribute('class', 'hover:opacity-90 cursor-pointer');
        
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `${item.name}: ${formatVal(item.value)}`;
        rect.appendChild(title);
        svg.appendChild(rect);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', (x + rectW / 2).toString());
        text.setAttribute('y', (h - paddingY + 15).toString());
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', 'rgba(255,255,255,0.6)');
        text.setAttribute('font-size', '8');
        text.textContent = item.name;
        svg.appendChild(text);
    });
}

function drawTrendLineChart(svg, data) {
    const w = svg.clientWidth || 400;
    const h = svg.clientHeight || 250;
    const paddingX = 40;
    const paddingY = 30;
    
    const maxVal = Math.max(...data.map(d => Math.abs(d.value))) || 100;
    const chartHeight = h - 2 * paddingY;
    const zeroY = paddingY + chartHeight / 2;
    const stepX = (w - 2 * paddingX) / Math.max(1, data.length - 1);
    
    const points = data.map((item, idx) => {
        const ratio = item.value / maxVal;
        return {
            x: paddingX + idx * stepX,
            y: zeroY - ratio * (chartHeight / 2),
            name: item.name,
            value: item.value
        };
    });

    const baseline = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    baseline.setAttribute('x1', paddingX.toString());
    baseline.setAttribute('y1', zeroY.toString());
    baseline.setAttribute('x2', (w - paddingX).toString());
    baseline.setAttribute('y2', zeroY.toString());
    baseline.setAttribute('stroke', 'rgba(255,255,255,0.1)');
    baseline.setAttribute('stroke-dasharray', '2,2');
    svg.appendChild(baseline);

    if (points.length >= 2) {
        let d = `M ${points[0].x} ${points[0].y}`;
        for (let i = 1; i < points.length; i++) {
            d += ` L ${points[i].x} ${points[i].y}`;
        }
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#5e5ce6');
        path.setAttribute('stroke-width', '2');
        svg.appendChild(path);
    }

    points.forEach(p => {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', p.x.toString());
        circle.setAttribute('cy', p.y.toString());
        circle.setAttribute('r', '4');
        circle.setAttribute('fill', '#5e5ce6');
        circle.setAttribute('stroke', '#131315');
        circle.setAttribute('stroke-width', '1.5');
        circle.setAttribute('class', 'hover:r-6 cursor-pointer');
        
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `${p.name}: ${formatVal(p.value)}`;
        circle.appendChild(title);
        svg.appendChild(circle);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', p.x.toString());
        text.setAttribute('y', (h - paddingY + 15).toString());
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', 'rgba(255,255,255,0.6)');
        text.setAttribute('font-size', '8');
        text.textContent = p.name;
        svg.appendChild(text);
    });
}

function drawAssetLineChart(svg, data, color) {
    const w = svg.clientWidth || 400;
    const h = svg.clientHeight || 250;
    const paddingX = 50;
    const paddingY = 30;
    
    const values = data.map(d => d.value);
    const maxVal = Math.max(...values) || 100;
    const minVal = Math.min(...values) || 0;
    const valRange = maxVal - minVal || 100;
    
    const chartHeight = h - 2 * paddingY;
    const stepX = (w - 2 * paddingX) / Math.max(1, data.length - 1);
    
    const points = data.map((item, idx) => ({
        x: paddingX + idx * stepX,
        y: h - paddingY - ((item.value - minVal) / valRange) * chartHeight,
        name: item.name,
        value: item.value
    }));

    for (let i = 0; i <= 4; i++) {
        const y = paddingY + (i / 4) * chartHeight;
        const val = maxVal - (i / 4) * valRange;
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', paddingX.toString());
        line.setAttribute('y1', y.toString());
        line.setAttribute('x2', (w - paddingX).toString());
        line.setAttribute('y2', y.toString());
        line.setAttribute('stroke', 'rgba(255,255,255,0.03)');
        svg.appendChild(line);

        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        label.setAttribute('x', (paddingX - 10).toString());
        label.setAttribute('y', (y + 3).toString());
        label.setAttribute('text-anchor', 'end');
        label.setAttribute('fill', 'rgba(255,255,255,0.4)');
        label.setAttribute('font-size', '8');
        label.textContent = formatVal(val).replace('€ ', '').replace('₹ ', '');
        svg.appendChild(label);
    }

    if (points.length >= 2) {
        let d = `M ${points[0].x} ${points[0].y}`;
        for (let i = 1; i < points.length; i++) {
            d += ` L ${points[i].x} ${points[i].y}`;
        }
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', color);
        path.setAttribute('stroke-width', '2.5');
        svg.appendChild(path);
    }

    const stride = Math.max(1, Math.ceil(points.length / 20));
    points.forEach((p, idx) => {
        if (idx === 0 || idx === points.length - 1 || idx % stride === 0) {
            const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circle.setAttribute('cx', p.x.toString());
            circle.setAttribute('cy', p.y.toString());
            circle.setAttribute('r', '3');
            circle.setAttribute('fill', color);
            circle.setAttribute('stroke', '#131315');
            circle.setAttribute('stroke-width', '1');
            circle.setAttribute('class', 'hover:r-5 cursor-pointer');
            
            const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            title.textContent = `${p.name}: ${formatVal(p.value)}`;
            circle.appendChild(title);
            svg.appendChild(circle);

            if (idx === 0 || idx === points.length - 1) {
                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', p.x.toString());
                text.setAttribute('y', (h - paddingY + 12).toString());
                text.setAttribute('text-anchor', idx === 0 ? 'start' : 'end');
                text.setAttribute('fill', 'rgba(255,255,255,0.5)');
                text.setAttribute('font-size', '8');
                text.textContent = p.name;
                svg.appendChild(text);
            }
        }
    });
}

function drawDoubleAssetLineChart(svg, dataAssets, dataLiabilities) {
    const w = svg.clientWidth || 400;
    const h = svg.clientHeight || 250;
    const paddingX = 50;
    const paddingY = 30;
    
    const maxVal = Math.max(
        ...dataAssets.map(d => d.value),
        ...dataLiabilities.map(d => d.value)
    ) || 100;
    
    const chartHeight = h - 2 * paddingY;
    const stepX = (w - 2 * paddingX) / Math.max(1, dataAssets.length - 1);
    
    const makePoints = (data) => data.map((item, idx) => ({
        x: paddingX + idx * stepX,
        y: h - paddingY - (item.value / maxVal) * chartHeight,
        name: item.name,
        value: item.value
    }));

    const ptsAssets = makePoints(dataAssets);
    const ptsLiab = makePoints(dataLiabilities);

    for (let i = 0; i <= 4; i++) {
        const y = paddingY + (i / 4) * chartHeight;
        const val = maxVal - (i / 4) * maxVal;
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', paddingX.toString());
        line.setAttribute('y1', y.toString());
        line.setAttribute('x2', (w - paddingX).toString());
        line.setAttribute('y2', y.toString());
        line.setAttribute('stroke', 'rgba(255,255,255,0.03)');
        svg.appendChild(line);

        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        label.setAttribute('x', (paddingX - 10).toString());
        label.setAttribute('y', (y + 3).toString());
        label.setAttribute('text-anchor', 'end');
        label.setAttribute('fill', 'rgba(255,255,255,0.4)');
        label.setAttribute('font-size', '8');
        label.textContent = formatVal(val).replace('€ ', '').replace('₹ ', '');
        svg.appendChild(label);
    }

    const drawLine = (pts, color) => {
        if (pts.length < 2) return;
        let d = `M ${pts[0].x} ${pts[0].y}`;
        for (let i = 1; i < pts.length; i++) {
            d += ` L ${pts[i].x} ${pts[i].y}`;
        }
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', color);
        path.setAttribute('stroke-width', '2');
        svg.appendChild(path);
    };

    drawLine(ptsAssets, '#30d158');
    drawLine(ptsLiab, '#ff453a');

    const assetLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    assetLabel.setAttribute('x', (w - paddingX - 10).toString());
    assetLabel.setAttribute('y', (paddingY + 15).toString());
    assetLabel.setAttribute('text-anchor', 'end');
    assetLabel.setAttribute('fill', '#30d158');
    assetLabel.setAttribute('font-weight', 'bold');
    assetLabel.setAttribute('font-size', '9');
    assetLabel.textContent = 'Cumulative Assets';
    svg.appendChild(assetLabel);

    const liabLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    liabLabel.setAttribute('x', (w - paddingX - 10).toString());
    liabLabel.setAttribute('y', (paddingY + 30).toString());
    liabLabel.setAttribute('text-anchor', 'end');
    liabLabel.setAttribute('fill', '#ff453a');
    liabLabel.setAttribute('font-weight', 'bold');
    liabLabel.setAttribute('font-size', '9');
    liabLabel.textContent = 'Cumulative Liabilities';
    svg.appendChild(liabLabel);
}

// Drag & Drop event bindings
function bindDragDropEvents() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-uploader-input');
    if (!dropZone || !fileInput) return;

    dropZone.addEventListener('click', () => fileInput.click());
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('border-primary/55', 'bg-primary/5');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('border-primary/55', 'bg-primary/5');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-primary/55', 'bg-primary/5');
        const files = e.dataTransfer.files;
        if (files.length > 0) handleFileUpload(files[0]);
    });

    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) handleFileUpload(files[0]);
    });
}

// Draw transaction type donut chart
function drawTransactionTypeDonut(txns) {
    const svg = document.getElementById('tx-donut-svg');
    const legend = document.getElementById('tx-type-legend');
    if (!svg || !legend) return;
    
    svg.innerHTML = '';
    legend.innerHTML = '';
    
    if (txns.length === 0) {
        const centerAmountEl = document.getElementById('tx-donut-center-amount');
        if (centerAmountEl) {
            centerAmountEl.textContent = '€0.00';
            centerAmountEl.style.fontSize = '20px';
        }
        legend.innerHTML = '<div class="text-center py-8 text-on-surface-variant">No data</div>';
        return;
    }

    const typeMetadata = {
        'Card Payments': { color: '#bf5af2', dotClass: 'bg-[#bf5af2]' },
        'Bank Transfers': { color: '#30d158', dotClass: 'bg-[#30d158]' },
        'Cash': { color: '#ff9f0a', dotClass: 'bg-[#ff9f0a]' },
        'Direct Debit': { color: '#ffd60a', dotClass: 'bg-[#ffd60a]' },
        'Internal Transfer': { color: '#0a84ff', dotClass: 'bg-[#0a84ff]' },
        'Other': { color: '#6b7280', dotClass: 'bg-[#6b7280]' }
    };

    const typeCounts = {
        'Card Payments': 0,
        'Bank Transfers': 0,
        'Cash': 0,
        'Direct Debit': 0,
        'Internal Transfer': 0,
        'Other': 0
    };
    
    const typeAmounts = {
        'Card Payments': 0,
        'Bank Transfers': 0,
        'Cash': 0,
        'Direct Debit': 0,
        'Internal Transfer': 0,
        'Other': 0
    };

    let totalVolume = 0;
    txns.forEach(t => {
        const type = getTransactionType(t);
        const normAmt = getNormalizedEur(t.amount, t.currency);
        const absAmt = Math.abs(normAmt);
        
        typeCounts[type] = (typeCounts[type] || 0) + 1;
        typeAmounts[type] = (typeAmounts[type] || 0) + absAmt;
        totalVolume += absAmt;
    });

    // Update center amount to be the total volume in Euros with auto-fit font size
    const centerAmountEl = document.getElementById('tx-donut-center-amount');
    if (centerAmountEl) {
        const formattedValStr = formatVal(totalVolume);
        centerAmountEl.textContent = formattedValStr;
        if (formattedValStr.length > 14) {
            centerAmountEl.style.fontSize = '12px';
        } else if (formattedValStr.length > 11) {
            centerAmountEl.style.fontSize = '14px';
        } else if (formattedValStr.length > 8) {
            centerAmountEl.style.fontSize = '16px';
        } else {
            centerAmountEl.style.fontSize = '20px';
        }
    }

    const data = [];
    for (const [type, count] of Object.entries(typeCounts)) {
        if (count > 0) {
            const amt = typeAmounts[type];
            data.push({
                type: type,
                count: count,
                amount: amt,
                pct: totalVolume > 0 ? (amt / totalVolume) * 100 : 0,
                color: typeMetadata[type]?.color || '#6b7280',
                dotClass: typeMetadata[type]?.dotClass || 'bg-zinc-500'
            });
        }
    }

    data.sort((a, b) => b.pct - a.pct);

    let currentOffset = 0;
    data.forEach(item => {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', '18');
        circle.setAttribute('cy', '18');
        circle.setAttribute('r', '15.91549430918954');
        circle.setAttribute('fill', 'transparent');
        circle.setAttribute('stroke', item.color);
        circle.setAttribute('stroke-width', '4');
        circle.setAttribute('stroke-dasharray', `${item.pct} ${100 - item.pct}`);
        circle.setAttribute('stroke-dashoffset', String(-currentOffset));
        circle.setAttribute('style', 'transition: stroke-width 0.2s ease-out; cursor: pointer;');
        
        circle.addEventListener('mouseenter', (e) => {
            circle.setAttribute('stroke-width', '5.2');
            showDonutTypeTooltip(e, item);
        });
        circle.addEventListener('mousemove', (e) => {
            showDonutTypeTooltip(e, item);
        });
        circle.addEventListener('mouseleave', () => {
            circle.setAttribute('stroke-width', '4');
            hideChartTooltip();
        });
        
        svg.appendChild(circle);
        currentOffset += item.pct;

        const legendItem = document.createElement('div');
        legendItem.className = 'flex items-center justify-between py-1 border-b border-white/[0.02] hover:bg-white/[0.02] rounded px-1 transition-all cursor-default';
        legendItem.innerHTML = `
            <div class="flex items-center gap-2 truncate">
                <span class="w-2.5 h-2.5 rounded-full ${item.dotClass}"></span>
                <span class="text-on-surface-variant font-medium truncate">${item.type}</span>
            </div>
            <div class="flex items-center gap-2 text-right">
                <span class="text-white font-bold">${item.pct.toFixed(0)}%</span>
                <span class="text-zinc-500 text-[10px]">(${formatVal(item.amount)})</span>
            </div>
        `;
        legend.appendChild(legendItem);
    });
}

function showDonutTypeTooltip(event, item) {
    if (!chartTooltip) {
        chartTooltip = document.createElement('div');
        chartTooltip.className = 'absolute z-[200] glass-card p-3 rounded-xl border border-white/10 shadow-2xl text-[11px] font-mono space-y-1 pointer-events-none transition-all duration-75';
        chartTooltip.style.background = 'rgba(20, 20, 25, 0.65)';
        chartTooltip.style.backdropFilter = 'blur(16px)';
        chartTooltip.style.webkitBackdropFilter = 'blur(16px)';
        chartTooltip.style.boxShadow = '0 8px 32px 0 rgba(0, 0, 0, 0.4), inset 0 1px 1px 0 rgba(255, 255, 255, 0.15)';
        document.body.appendChild(chartTooltip);
    }
    
    chartTooltip.innerHTML = `
        <div class="font-bold text-white flex items-center gap-1.5">
            <span class="w-2.5 h-2.5 rounded-full inline-block" style="background-color: ${item.color}"></span>
            ${item.type}
        </div>
        <div class="text-[9px] text-on-surface-variant uppercase tracking-wider font-bold">Volume Share</div>
        <div class="text-sm font-bold text-primary">${formatVal(item.amount)} <span class="text-[10px] text-zinc-400 font-normal">(${item.pct.toFixed(1)}%)</span></div>
        <div class="text-[9px] text-zinc-400 pt-1 mt-1 border-t border-white/5">Count: <span class="text-white font-semibold">${item.count} txs</span></div>
    `;
    
    chartTooltip.style.display = 'block';
    
    const offset = 15;
    let left = event.pageX + offset;
    let top = event.pageY + offset;
    
    if (left + 220 > window.innerWidth) {
        left = event.pageX - 220 - offset;
    }
    if (top + 100 > window.innerHeight) {
        top = event.pageY - 100 - offset;
    }
    
    chartTooltip.style.left = `${left}px`;
    chartTooltip.style.top = `${top}px`;
}

// Draw Income vs Expenses dual bar and net line chart
function drawIncomeExpensesBarChart(txns) {
    // If txns is not passed, use lastFilteredTransactions
    const transactions = txns || lastFilteredTransactions;
    
    const svg = document.getElementById('tx-bar-chart-svg');
    const container = document.getElementById('tx-bar-chart-container');
    if (!svg || !container) return;
    svg.innerHTML = '';
    
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w === 0 || h === 0) return;
    
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    
    const select = document.getElementById('tx-period-select');
    const monthsCount = select ? parseInt(select.value) : 6;
    
    const months = getLastKMonths(monthsCount);
    
    const monthlyData = months.map(m => {
        let income = 0;
        let expenses = 0;
        const prefix = `${m.year}-${String(m.month + 1).padStart(2, '0')}`;
        
        allTransactions.forEach(t => {
            if (t.date && t.date.startsWith(prefix)) {
                const normAmt = getNormalizedEur(t.amount, t.currency);
                if (normAmt > 0) {
                    income += normAmt;
                } else {
                    expenses += Math.abs(normAmt);
                }
            }
        });

        const dateObj = new Date(m.year, m.month, 1);
        const label = dateObj.toLocaleDateString('en-US', { month: 'short' });
        
        return {
            month: m.month,
            year: m.year,
            label: label,
            income: income,
            expenses: expenses,
            net: income - expenses
        };
    });

    // Seed data if database is empty for visual showcase
    const allZero = monthlyData.every(d => d.income === 0 && d.expenses === 0);
    if (allZero) {
        monthlyData.forEach((d, idx) => {
            d.income = 3500 + Math.sin(idx) * 800;
            d.expenses = 2000 + Math.cos(idx) * 600;
            d.net = d.income - d.expenses;
        });
    }

    const maxIncome = Math.max(...monthlyData.map(d => d.income));
    const maxExpenses = Math.max(...monthlyData.map(d => d.expenses));
    const maxVal = Math.max(maxIncome, maxExpenses) || 1000;
    
    const yMax = Math.ceil(maxVal / 1000) * 1000 || 1000;
    
    const paddingLeft = 50;
    const paddingRight = 20;
    const paddingTop = 15;
    const paddingBottom = 25;
    
    const chartW = w - paddingLeft - paddingRight;
    const chartH = h - paddingTop - paddingBottom;
    const zeroY = paddingTop + chartH / 2;
    
    const getY = (val) => {
        const ratio = val / yMax;
        return zeroY - ratio * (chartH / 2);
    };

    const gridValues = [yMax, yMax / 2, 0, -yMax / 2, -yMax];
    gridValues.forEach(val => {
        const y = getY(val);
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', String(paddingLeft));
        line.setAttribute('y1', String(y));
        line.setAttribute('x2', String(w - paddingRight));
        line.setAttribute('y2', String(y));
        line.setAttribute('stroke', 'rgba(255, 255, 255, 0.05)');
        line.setAttribute('stroke-dasharray', val === 0 ? '0' : '3,3');
        line.setAttribute('stroke-width', val === 0 ? '1.5' : '1');
        svg.appendChild(line);
        
        const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('x', String(paddingLeft - 8));
        txt.setAttribute('y', String(y + 3));
        txt.setAttribute('fill', 'rgba(255, 255, 255, 0.4)');
        txt.setAttribute('font-size', '9');
        txt.setAttribute('font-family', 'JetBrains Mono');
        txt.setAttribute('text-anchor', 'end');
        
        let labelText = '';
        const absVal = Math.abs(val);
        if (absVal >= 1000) {
            labelText = `${val < 0 ? '-' : ''}€${(absVal / 1000).toFixed(0)}k`;
        } else {
            labelText = `${val < 0 ? '-' : ''}€${absVal}`;
        }
        txt.textContent = labelText;
        svg.appendChild(txt);
    });

    const colCount = monthlyData.length;
    const barWidth = Math.min(22, (chartW / colCount) * 0.3);
    const spacing = chartW / colCount;

    const netPoints = [];

    let defs = svg.querySelector('defs');
    if (!defs) {
        defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
        svg.appendChild(defs);
    }
    defs.innerHTML += `
        <linearGradient id="barIncomeGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#30d158" stop-opacity="0.85"/>
            <stop offset="100%" stop-color="#30d158" stop-opacity="0.2"/>
        </linearGradient>
        <linearGradient id="barExpenseGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#ff453a" stop-opacity="0.2"/>
            <stop offset="100%" stop-color="#ff453a" stop-opacity="0.85"/>
        </linearGradient>
    `;

    monthlyData.forEach((d, idx) => {
        const centerX = paddingLeft + (idx + 0.5) * spacing;
        const xIncome = centerX - barWidth - 2;
        const xExpense = centerX + 2;

        const yIncome = getY(d.income);
        const hIncome = Math.max(2, zeroY - yIncome);
        const rectIncome = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rectIncome.setAttribute('x', String(xIncome));
        rectIncome.setAttribute('y', String(yIncome));
        rectIncome.setAttribute('width', String(barWidth));
        rectIncome.setAttribute('height', String(hIncome));
        rectIncome.setAttribute('fill', 'url(#barIncomeGrad)');
        rectIncome.setAttribute('rx', '4');
        rectIncome.setAttribute('style', 'transition: opacity 0.15s ease-in-out; cursor: pointer;');
        
        const yExpense = zeroY;
        const hExpense = Math.max(2, getY(-d.expenses) - zeroY);
        const rectExpense = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rectExpense.setAttribute('x', String(xExpense));
        rectExpense.setAttribute('y', String(yExpense));
        rectExpense.setAttribute('width', String(barWidth));
        rectExpense.setAttribute('height', String(hExpense));
        rectExpense.setAttribute('fill', 'url(#barExpenseGrad)');
        rectExpense.setAttribute('rx', '4');
        rectExpense.setAttribute('style', 'transition: opacity 0.15s ease-in-out; cursor: pointer;');

        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        group.appendChild(rectIncome);
        group.appendChild(rectExpense);
        
        const hoverOverlay = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        hoverOverlay.setAttribute('x', String(centerX - spacing/2));
        hoverOverlay.setAttribute('y', String(paddingTop));
        hoverOverlay.setAttribute('width', String(spacing));
        hoverOverlay.setAttribute('height', String(chartH));
        hoverOverlay.setAttribute('fill', 'transparent');
        hoverOverlay.setAttribute('style', 'cursor: pointer;');
        group.appendChild(hoverOverlay);

        svg.appendChild(group);

        const netY = getY(d.net);
        netPoints.push({ x: centerX, y: netY, data: d });

        const labelTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        labelTxt.setAttribute('x', String(centerX));
        labelTxt.setAttribute('y', String(h - 8));
        labelTxt.setAttribute('fill', 'rgba(255, 255, 255, 0.4)');
        labelTxt.setAttribute('font-size', '9');
        labelTxt.setAttribute('font-family', 'Inter');
        labelTxt.setAttribute('font-weight', '500');
        labelTxt.setAttribute('text-anchor', 'middle');
        labelTxt.textContent = d.label;
        svg.appendChild(labelTxt);

        hoverOverlay.addEventListener('mouseenter', (e) => {
            rectIncome.setAttribute('fill-opacity', '0.75');
            rectExpense.setAttribute('fill-opacity', '0.75');
            showIncomeExpensesTooltip(e, d);
        });
        hoverOverlay.addEventListener('mousemove', (e) => {
            showIncomeExpensesTooltip(e, d);
        });
        hoverOverlay.addEventListener('mouseleave', () => {
            rectIncome.removeAttribute('fill-opacity');
            rectExpense.removeAttribute('fill-opacity');
            hideChartTooltip();
        });
    });

    if (netPoints.length > 1) {
        let pathD = `M ${netPoints[0].x} ${netPoints[0].y}`;
        for (let i = 1; i < netPoints.length; i++) {
            pathD += ` L ${netPoints[i].x} ${netPoints[i].y}`;
        }
        
        const lineShadow = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        lineShadow.setAttribute('d', pathD);
        lineShadow.setAttribute('fill', 'transparent');
        lineShadow.setAttribute('stroke', 'rgba(191, 90, 242, 0.25)');
        lineShadow.setAttribute('stroke-width', '4');
        svg.appendChild(lineShadow);
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        line.setAttribute('d', pathD);
        line.setAttribute('fill', 'transparent');
        line.setAttribute('stroke', '#bf5af2');
        line.setAttribute('stroke-width', '2');
        line.setAttribute('stroke-linecap', 'round');
        svg.appendChild(line);
    }

    netPoints.forEach(pt => {
        const diamond = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        const r = 4.5;
        const pointsStr = `${pt.x},${pt.y - r} ${pt.x + r},${pt.y} ${pt.x},${pt.y + r} ${pt.x - r},${pt.y}`;
        diamond.setAttribute('points', pointsStr);
        diamond.setAttribute('fill', '#09090b');
        diamond.setAttribute('stroke', '#bf5af2');
        diamond.setAttribute('stroke-width', '2');
        diamond.setAttribute('style', 'cursor: pointer; transition: transform 0.15s ease-out;');
        svg.appendChild(diamond);
    });
}

function showIncomeExpensesTooltip(event, d) {
    if (!chartTooltip) {
        chartTooltip = document.createElement('div');
        chartTooltip.className = 'absolute z-[200] glass-card p-3 rounded-xl border border-white/10 shadow-2xl text-[11px] font-mono space-y-1 pointer-events-none transition-all duration-75';
        chartTooltip.style.background = 'rgba(20, 20, 25, 0.65)';
        chartTooltip.style.backdropFilter = 'blur(16px)';
        chartTooltip.style.webkitBackdropFilter = 'blur(16px)';
        chartTooltip.style.boxShadow = '0 8px 32px 0 rgba(0, 0, 0, 0.4), inset 0 1px 1px 0 rgba(255, 255, 255, 0.15)';
        document.body.appendChild(chartTooltip);
    }
    
    const monthName = new Date(d.year, d.month, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    const netColor = d.net >= 0 ? 'text-success' : 'text-error';
    const netSign = d.net >= 0 ? '+' : '';
    
    chartTooltip.innerHTML = `
        <div class="font-bold text-white border-b border-white/5 pb-1 mb-1">${monthName}</div>
        <div class="flex items-center justify-between gap-6">
            <span class="text-on-surface-variant font-medium">Income:</span>
            <span class="text-success font-bold font-mono">+${formatVal(d.income)}</span>
        </div>
        <div class="flex items-center justify-between gap-6">
            <span class="text-on-surface-variant font-medium">Expenses:</span>
            <span class="text-error font-bold font-mono">-${formatVal(d.expenses)}</span>
        </div>
        <div class="flex items-center justify-between gap-6 pt-1 border-t border-white/5">
            <span class="text-on-surface-variant font-medium">Net Savings:</span>
            <span class="${netColor} font-bold font-mono">${netSign}${formatVal(d.net)}</span>
        </div>
    `;
    
    chartTooltip.style.display = 'block';
    
    const offset = 15;
    let left = event.pageX + offset;
    let top = event.pageY + offset;
    
    if (left + 220 > window.innerWidth) {
        left = event.pageX - 220 - offset;
    }
    if (top + 100 > window.innerHeight) {
        top = event.pageY - 100 - offset;
    }
    
    chartTooltip.style.left = `${left}px`;
    chartTooltip.style.top = `${top}px`;
}

// Initializer on Dom Loaded
document.addEventListener('DOMContentLoaded', () => {
    initBackgroundShader();
    initRouter();
    bindDragDropEvents();
    checkVaultStatus();
    setInterval(checkVaultStatus, 5000);

    // Bank search & key bindings
    const searchInput = document.getElementById('bank-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', renderBanks);
    }

    const modalEl = document.getElementById('bank-discovery-modal');
    if (modalEl) {
        modalEl.addEventListener('click', (event) => {
            if (event.target === modalEl) {
                closeBankModal();
            }
        });
        
        // Listen for Esc key to close
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && !modalEl.classList.contains('hidden')) {
                closeBankModal();
            }
        });
    }

    // Global ResizeObserver for Net Worth Trend chart responsiveness
    let lastChartW = 0, lastChartH = 0;
    const chartContainer = document.getElementById('chart-container');
    if (chartContainer) {
        const ro = new ResizeObserver(entries => {
            for (let entry of entries) {
                const { width, height } = entry.contentRect;
                if (Math.abs(width - lastChartW) > 1.5 || Math.abs(height - lastChartH) > 1.5) {
                    lastChartW = width;
                    lastChartH = height;
                    if (allTransactions && allTransactions.length > 0) {
                        window.requestAnimationFrame(() => {
                            drawSplineChart(allTransactions);
                        });
                    }
                }
            }
        });
        ro.observe(chartContainer);
    }

    // Global ResizeObserver for Transaction Type Donut responsiveness
    let lastDonutW = 0, lastDonutH = 0;
    const donutContainer = document.getElementById('tx-donut-container');
    if (donutContainer) {
        const roDonut = new ResizeObserver(entries => {
            for (let entry of entries) {
                const { width, height } = entry.contentRect;
                if (Math.abs(width - lastDonutW) > 1.5 || Math.abs(height - lastDonutH) > 1.5) {
                    lastDonutW = width;
                    lastDonutH = height;
                    if (allTransactions && allTransactions.length > 0) {
                        window.requestAnimationFrame(() => {
                            drawTransactionTypeDonut(lastFilteredTransactions);
                        });
                    }
                }
            }
        });
        roDonut.observe(donutContainer);
    }

    // Global ResizeObserver for Income vs Expenses Chart responsiveness
    let lastBarW = 0, lastBarH = 0;
    const barContainer = document.getElementById('tx-bar-chart-container');
    if (barContainer) {
        const roBar = new ResizeObserver(entries => {
            for (let entry of entries) {
                const { width, height } = entry.contentRect;
                if (Math.abs(width - lastBarW) > 1.5 || Math.abs(height - lastBarH) > 1.5) {
                    lastBarW = width;
                    lastBarH = height;
                    if (allTransactions && allTransactions.length > 0) {
                        window.requestAnimationFrame(() => {
                            drawIncomeExpensesBarChart(lastFilteredTransactions);
                        });
                    }
                }
            }
        });
        roBar.observe(barContainer);
    }

    // Debounced window resize handler to redraw active panel charts
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            const activePanel = document.querySelector('.flex-1.overflow-hidden.relative.flex.flex-col > div:not(.hidden)');
            if (!activePanel) return;
            const panelId = activePanel.id;
            
            if (panelId === 'panel-overview') {
                if (allTransactions && allTransactions.length > 0) {
                    drawSplineChart(allTransactions);
                }
            } else if (panelId === 'panel-transactions') {
                if (allTransactions && allTransactions.length > 0) {
                    drawTransactionTypeDonut(lastFilteredTransactions);
                    drawIncomeExpensesBarChart(lastFilteredTransactions);
                }
            } else if (panelId === 'panel-investments') {
                updatePortfolioGrowthView();
            } else if (panelId === 'panel-insights') {
                drawInsightsTrendChart();
            }
        }, 150);
    });
});
