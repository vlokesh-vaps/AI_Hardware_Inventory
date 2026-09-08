/**
 * Hardware Inventory Dashboard - Vanilla JavaScript
 * Provides live filtering, table searches, drag-and-drop file upload, and UI interactions.
 */

document.addEventListener('DOMContentLoaded', () => {
    initPcTableFilters();
    initUsbFilter();
    initSoftwareFilter();
    initDropzone();
    initClickableRows();
    initToastAutoDismiss();
});

/**
 * Live search and status filter for the PC Inventory table
 */
function initPcTableFilters() {
    const searchInput = document.getElementById('pc-search-input');
    const filterButtons = document.querySelectorAll('#health-filter-buttons .btn-filter');
    const table = document.getElementById('pc-inventory-table');
    if (!table) return;

    const rows = table.querySelectorAll('tbody tr.clickable-row');
    const badge = document.getElementById('pc-count-badge');
    let currentHealthFilter = 'all';

    function applyFilters() {
        const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
        let visibleCount = 0;

        rows.forEach(row => {
            const searchData = (row.getAttribute('data-search') || '').toLowerCase();
            const health = (row.getAttribute('data-health') || '').toUpperCase();

            const matchesSearch = !query || searchData.includes(query);
            const matchesHealth = (currentHealthFilter === 'all') || (health === currentHealthFilter);

            if (matchesSearch && matchesHealth) {
                row.style.display = '';
                visibleCount++;
            } else {
                row.style.display = 'none';
            }
        });

        if (badge) {
            badge.textContent = `${visibleCount} systems`;
        }
    }

    if (searchInput) {
        searchInput.addEventListener('input', applyFilters);
    }

    filterButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentHealthFilter = btn.getAttribute('data-filter').toUpperCase();
            applyFilters();
        });
    });
}

/**
 * Filter USB devices table
 */
function initUsbFilter() {
    const searchInput = document.getElementById('usb-search-input');
    const table = document.getElementById('usb-table');
    const countBadge = document.getElementById('usb-count-badge');
    if (!searchInput || !table) return;

    const rows = table.querySelectorAll('tbody tr');

    searchInput.addEventListener('input', () => {
        const query = searchInput.value.toLowerCase().trim();
        let count = 0;
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            if (!query || text.includes(query)) {
                row.style.display = '';
                count++;
            } else {
                row.style.display = 'none';
            }
        });
        if (countBadge) {
            countBadge.textContent = `${count} Connected`;
        }
    });
}

/**
 * Filter Installed Software table
 */
function initSoftwareFilter() {
    const searchInput = document.getElementById('software-search-input');
    const table = document.getElementById('software-table');
    if (!searchInput || !table) return;

    const rows = table.querySelectorAll('tbody tr');

    searchInput.addEventListener('input', () => {
        const query = searchInput.value.toLowerCase().trim();
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            if (!query || text.includes(query)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    });
}

/**
 * Toggle collapsible accordion (e.g. Installed Software)
 */
function toggleSection(sectionId) {
    const el = document.getElementById(sectionId);
    const btn = document.getElementById('btn-toggle-software');
    if (!el) return;

    if (el.style.display === 'none' || !el.style.display) {
        el.style.display = 'block';
        if (btn) btn.innerHTML = 'Hide Applications &uarr;';
    } else {
        el.style.display = 'none';
        if (btn) btn.innerHTML = 'Show Applications &darr;';
    }
}

/**
 * Clickable table rows for fast navigation
 */
function initClickableRows() {
    const rows = document.querySelectorAll('tr.clickable-row');
    rows.forEach(row => {
        row.style.cursor = 'pointer';
        row.addEventListener('click', (e) => {
            // Avoid navigating if user clicked a direct link or button inside the row
            if (e.target.tagName.toLowerCase() === 'a' || e.target.tagName.toLowerCase() === 'button') {
                return;
            }
            const href = row.getAttribute('data-href');
            if (href) {
                window.location.href = href;
            }
        });
    });
}

/**
 * Drag and Drop File Upload
 */
function initDropzone() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const container = document.getElementById('selected-files-container');
    const list = document.getElementById('selected-files-list');

    if (!dropzone || !fileInput) return;

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');
        });
    });

    dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        if (dt && dt.files && dt.files.length > 0) {
            fileInput.files = dt.files;
            updateSelectedFilesList(dt.files);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files.length > 0) {
            updateSelectedFilesList(fileInput.files);
        }
    });
}

function updateSelectedFilesList(files) {
    const container = document.getElementById('selected-files-container');
    const list = document.getElementById('selected-files-list');
    if (!container || !list) return;

    list.innerHTML = '';
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const li = document.createElement('li');
        li.className = 'file-list-item';
        
        const sizeKb = (file.size / 1024).toFixed(1);
        li.innerHTML = `
            <span>📄 <strong>${file.name}</strong></span>
            <span class="text-muted text-sm">${sizeKb} KB</span>
        `;
        list.appendChild(li);
    }
    container.style.display = 'block';
}

function clearSelectedFiles() {
    const fileInput = document.getElementById('file-input');
    const container = document.getElementById('selected-files-container');
    const list = document.getElementById('selected-files-list');
    if (fileInput) fileInput.value = '';
    if (list) list.innerHTML = '';
    if (container) container.style.display = 'none';
}

/**
 * Automatically dismiss flash toast alerts after 6 seconds
 */
function initToastAutoDismiss() {
    const toasts = document.querySelectorAll('.toast');
    toasts.forEach(toast => {
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.5s ease';
            setTimeout(() => toast.remove(), 500);
        }, 6000);
    });
}
