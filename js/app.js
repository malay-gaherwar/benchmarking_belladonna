/* EdgeCase Benchmark Explorer — Core (dynamic datasets) */

const App = {
    datasets: [],
    cache: {},
    summaryCache: null,
    masSummaryCache: null,
    scSummaryCache: null,
    chartInstances: [],

    state: {
        currentPage: 1,
        pageSize: 25,
        kindFilter: null
    }
};

function destroyCharts() {
    for (const c of App.chartInstances) {
        try { c.destroy(); } catch (_) {}
    }
    App.chartInstances = [];
}

/* --- Utilities --- */

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str ?? '';
    return div.innerHTML;
}

function formatNumber(n) {
    return Number(n || 0).toLocaleString();
}

function slugToTitle(slug) {
    return String(slug || '')
        .replace(/[_-]+/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase())
        .trim();
}

function uniq(arr) {
    return [...new Set(arr)];
}

/* --- Summary + dataset config loading --- */

async function loadSummary() {
    if (App.summaryCache) return App.summaryCache;

    const resp = await fetch('/results/summary.json');
    if (!resp.ok) throw new Error('Failed to load /results/summary.json');

    const data = await resp.json();
    App.summaryCache = data;
    return data;
}

function deriveDatasetsFromSummary(summary) {
    const byId = new Map();

    const models = Array.isArray(summary?.models) ? summary.models : [];
    const datasetOrder = Array.isArray(summary?.dataset_order) ? summary.dataset_order : [];

    for (const model of models) {
        const datasets = Array.isArray(model.datasets) ? model.datasets : [];
        for (const ds of datasets) {
            const id = ds.dataset_id;
            if (!id) continue;

            const existing = byId.get(id) || {
                id,
                name: ds.dataset_name || slugToTitle(id),
                source: ds.dataset_name || slugToTitle(id),
                sourceNote: '',
                license: '—',
                description: ds.dataset_name || slugToTitle(id),
                taskType: 'Multiple-choice benchmark',
                questionCount: ds.total || 0,
                categories: Array.isArray(ds.categories) ? ds.categories : [],
                file: null
            };

            existing.name = existing.name || ds.dataset_name || slugToTitle(id);
            existing.source = existing.source || ds.dataset_name || slugToTitle(id);
            existing.description = existing.description || ds.dataset_name || slugToTitle(id);
            existing.questionCount = Math.max(existing.questionCount || 0, ds.total || 0);
            existing.categories = uniq([...(existing.categories || []), ...((ds.categories || []))]);

            byId.set(id, existing);
        }
    }

    const FILE_MAP = {
        expert200: '/resources/benchmarks/expert/200expertquestions.json'
    };

    const ids = datasetOrder.length ? datasetOrder : [...byId.keys()];
    return ids
        .filter(id => byId.has(id))
        .map(id => {
            const ds = byId.get(id);
            ds.file = FILE_MAP[id] || ds.file || `/resources/benchmarks/${id}.json`;
            return ds;
        });
}

async function ensureDatasetsLoaded() {
    if (App.datasets.length) return App.datasets;

    const summary = await loadSummary();
    App.datasets = deriveDatasetsFromSummary(summary);

    // Preload dataset metadata from wrapped dataset files
    await Promise.all(App.datasets.map(async (config) => {
        try {
            const resp = await fetch(config.file);
            if (!resp.ok) return;

            const text = await resp.text();
            if (!text.trim()) return;

            const raw = JSON.parse(text);

            if (raw && raw.meta) {
                config.id = raw.meta.id ?? config.id;
                config.name = raw.meta.name ?? config.name;
                config.abbrev = raw.meta.abbrev ?? config.abbrev;
                config.source = raw.meta.source ?? config.source;
                config.sourceNote = raw.meta.sourceNote ?? config.sourceNote;
                config.license = raw.meta.license ?? config.license;
                config.description = raw.meta.description ?? config.description;
                config.taskType = raw.meta.taskType ?? config.taskType;
                config.questionCount = raw.meta.questionCount ?? config.questionCount;
                config.categories = raw.meta.categories ?? config.categories;
            }
        } catch (_) {
            // ignore metadata preload failures
        }
    }));

    return App.datasets;
}
/* --- Data loading --- */

async function loadDataset(datasetId) {
    if (App.cache[datasetId]) return App.cache[datasetId];

    await ensureDatasetsLoaded();

    const config = App.datasets.find(d => d.id === datasetId);
    if (!config) throw new Error('Unknown dataset: ' + datasetId);

    const resp = await fetch(config.file);
    if (!resp.ok) throw new Error('Failed to load ' + config.file);

    const text = await resp.text();
    if (!text.trim()) {
        App.cache[datasetId] = [];
        return [];
    }

    const raw = JSON.parse(text);

    if (Array.isArray(raw)) {
        App.cache[datasetId] = raw;
        return raw;
    }

    if (raw && Array.isArray(raw.questions)) {
        if (config && raw.meta) {
            config.id = raw.meta.id ?? config.id;
            config.name = raw.meta.name ?? config.name;
            config.abbrev = raw.meta.abbrev ?? config.abbrev;
            config.source = raw.meta.source ?? config.source;
            config.sourceNote = raw.meta.sourceNote ?? config.sourceNote;
            config.license = raw.meta.license ?? config.license;
            config.description = raw.meta.description ?? config.description;
            config.taskType = raw.meta.taskType ?? config.taskType;
            config.questionCount = raw.meta.questionCount ?? raw.questions.length;
            config.categories = raw.meta.categories ?? config.categories;
        }

        App.cache[datasetId] = raw.questions;
        return raw.questions;
    }

    throw new Error('Unsupported dataset format in ' + config.file);
}

/* --- Tabs --- */

function updateTabs(activeTab) {
    document.querySelectorAll('.tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === activeTab);
    });
}

/* --- Router --- */

async function route() {
    const hash = location.hash || '#/';
    const appEl = document.getElementById('app');

    destroyCharts();
    window.scrollTo(0, 0);

    try {
        await ensureDatasetsLoaded();
    } catch (err) {
        appEl.innerHTML = `
            <div class="error-state">
                <h2>Failed to load dashboard data</h2>
                <p>Could not load <code>/results/summary.json</code>.</p>
                <p>${escapeHtml(err.message || String(err))}</p>
            </div>`;
        return;
    }

    if (hash.startsWith('#/explore/')) {
        const datasetId = hash.replace('#/explore/', '').split('?')[0];
        App.state.currentPage = 1;
        App.state.kindFilter = null;
        updateTabs('datasets');
        renderExplorerView(appEl, datasetId);
    } else if (hash.match(/^#\/sc-results\/(.+)/)) {
        const slug = hash.replace('#/sc-results/', '');
        updateTabs('sc-results');
        renderScDetailView(appEl, slug);
    } else if (hash.startsWith('#/sc-results')) {
        updateTabs('sc-results');
        renderScResultsView(appEl);
    } else if (hash.match(/^#\/mas-results\/(.+)/)) {
        const slug = hash.replace('#/mas-results/', '');
        updateTabs('mas-results');
        renderMasDetailView(appEl, slug);
    } else if (hash.startsWith('#/mas-results')) {
        updateTabs('mas-results');
        renderMasResultsView(appEl);
    } else if (hash.match(/^#\/results\/(.+)/)) {
        const slug = hash.replace('#/results/', '');
        updateTabs('results');
        renderResultsDetailView(appEl, slug);
    } else if (hash.startsWith('#/results')) {
        updateTabs('results');
        renderResultsView(appEl);
    } else {
        updateTabs('datasets');
        renderTableView(appEl);
    }
}

window.addEventListener('hashchange', () => {
    route();
});

window.addEventListener('DOMContentLoaded', () => {
    route();
});