/* EdgeCase Benchmark Explorer — Explorer View */

const OPTION_LABELS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const MAX_KINDS_FOR_FILTER = 50;

function renderQuestionCard(q) {
    const optionsHtml = q.options.map((opt, i) => {
        const isCorrect = i === Number(q.target);
        const label = OPTION_LABELS[i] || String(i + 1);
        const cls = isCorrect ? 'option correct' : 'option';
        return `<div class="${cls}">
            <span class="option-label">${label}</span>
            <span class="option-text">${escapeHtml(opt)}</span>
        </div>`;
    }).join('');

    const kindHtml = q.kind
        ? `<span class="question-kind">${escapeHtml(q.kind)}</span>`
        : '';

    return `<div class="question-card">
        <div class="question-meta">
            <span class="question-id">#${q.id}</span>
            ${kindHtml}
        </div>
        <p class="question-text">${escapeHtml(q.question)}</p>
        <div class="options-list">${optionsHtml}</div>
    </div>`;
}

function getFilteredData(data) {
    if (!App.state.kindFilter) return data;
    return data.filter(q => q.kind === App.state.kindFilter);
}

function renderExplorerContent(container, config, data) {
    const filtered = getFilteredData(data);
    const totalPages = Math.max(1, Math.ceil(filtered.length / App.state.pageSize));
    if (App.state.currentPage > totalPages) App.state.currentPage = totalPages;

    const start = (App.state.currentPage - 1) * App.state.pageSize;
    const pageItems = filtered.slice(start, start + App.state.pageSize);

    // Kind filter
    const kinds = [...new Set(data.map(q => q.kind).filter(Boolean))].sort();
    const showFilter = kinds.length > 1 && kinds.length <= MAX_KINDS_FOR_FILTER;

    const filterHtml = showFilter ? `
        <div class="filter-bar">
            <select id="kind-filter">
                <option value="">All types (${formatNumber(data.length)})</option>
                ${kinds.map(k => {
                    const count = data.filter(q => q.kind === k).length;
                    const sel = App.state.kindFilter === k ? ' selected' : '';
                    return `<option value="${escapeHtml(k)}"${sel}>${escapeHtml(k)} (${count})</option>`;
                }).join('')}
            </select>
            <span class="filter-info">Showing ${formatNumber(filtered.length)} of ${formatNumber(data.length)} questions</span>
        </div>` : `
        <div class="filter-bar">
            <span class="filter-info">Showing ${formatNumber(filtered.length)} questions</span>
        </div>`;

    const questionsHtml = pageItems.map(renderQuestionCard).join('');

    const paginationHtml = totalPages > 1 ? `
        <div class="pagination">
            <button id="pg-first" ${App.state.currentPage <= 1 ? 'disabled' : ''}>First</button>
            <button id="pg-prev" ${App.state.currentPage <= 1 ? 'disabled' : ''}>Prev</button>
            <span class="page-info">Page ${App.state.currentPage} of ${totalPages}</span>
            <button id="pg-next" ${App.state.currentPage >= totalPages ? 'disabled' : ''}>Next</button>
            <button id="pg-last" ${App.state.currentPage >= totalPages ? 'disabled' : ''}>Last</button>
        </div>` : '';

    container.innerHTML = `
        <nav class="breadcrumb">
            <a href="#/">Datasets</a> <span>/</span> ${escapeHtml(config.name)}
        </nav>
        <div class="explorer-header">
            <h2>${escapeHtml(config.name)}</h2>
            <div class="explorer-meta">
                ${categoryBadges(config.categories)}
                <span>${escapeHtml(config.license)}</span>
                <span>${formatNumber(data.length)} questions</span>
            </div>
            <p class="explorer-description">${escapeHtml(config.description)}</p>
        </div>
        ${filterHtml}
        ${questionsHtml}
        ${paginationHtml}`;

    // Bind events
    if (showFilter) {
        document.getElementById('kind-filter').addEventListener('change', function () {
            App.state.kindFilter = this.value || null;
            App.state.currentPage = 1;
            renderExplorerContent(container, config, data);
        });
    }

    const bindPage = (id, page) => {
        const el = document.getElementById(id);
        if (el && !el.disabled) {
            el.addEventListener('click', () => {
                App.state.currentPage = page;
                renderExplorerContent(container, config, data);
                window.scrollTo(0, 0);
            });
        }
    };

    bindPage('pg-first', 1);
    bindPage('pg-prev', App.state.currentPage - 1);
    bindPage('pg-next', App.state.currentPage + 1);
    bindPage('pg-last', totalPages);
}

async function renderExplorerView(container, datasetId) {
    const config = App.datasets.find(d => d.id === datasetId);
    if (!config) {
        container.innerHTML = `
            <nav class="breadcrumb"><a href="#/">Datasets</a> <span>/</span> Not found</nav>
            <div class="error-state">
                <p>Dataset not found.</p>
                <a href="#/">Back to datasets</a>
            </div>`;
        return;
    }

    container.innerHTML = `
        <nav class="breadcrumb">
            <a href="#/">Datasets</a> <span>/</span> ${escapeHtml(config.name)}
        </nav>
        <p class="loading">Loading ${escapeHtml(config.name)} dataset\u2026</p>`;

    try {
        const data = await loadDataset(datasetId);
        if (data.length === 0) {
            container.innerHTML = `
                <nav class="breadcrumb"><a href="#/">Datasets</a> <span>/</span> ${escapeHtml(config.name)}</nav>
                <div class="empty-state">
                    <p>This dataset is currently empty or unavailable.</p>
                    <a href="#/">Back to datasets</a>
                </div>`;
            return;
        }
        renderExplorerContent(container, config, data);
    } catch (err) {
        container.innerHTML = `
            <nav class="breadcrumb"><a href="#/">Datasets</a> <span>/</span> ${escapeHtml(config.name)}</nav>
            <div class="error-state">
                <p>Failed to load dataset. Please try again later.</p>
                <a href="#/">Back to datasets</a>
            </div>`;
    }
}
