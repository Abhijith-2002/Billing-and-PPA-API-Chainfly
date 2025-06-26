document.addEventListener('DOMContentLoaded', function() {
let jwtToken = '';

function showResult(msg, id) {
    document.getElementById(id).innerHTML = '<pre>' + (typeof msg === 'string' ? msg : JSON.stringify(msg, null, 2)) + '</pre>';
}

document.getElementById('auth-form').onsubmit = async function(e) {
    e.preventDefault();
    const email = document.getElementById('auth-email').value;
    const password = document.getElementById('auth-password').value;
    showResult('Authenticating...', 'results-auth');
    const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (res.ok && data.idToken) {
        jwtToken = data.idToken;
        showResult('Authentication successful. Token set.', 'results-auth');
    } else {
        showResult(data, 'results-auth');
    }
};

document.getElementById('customer-form').onsubmit = async function(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    const payload = {
        name: data.name,
        email: data.email,
        address: data.address,
        customerType: data.customerType,
        gstNumber: data.gstNumber || undefined,
        linkedPPAs: []
    };
    const res = await fetch('/customers', {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload)
    });
    showResult(await res.json(), 'results-customer');
};

document.getElementById('list-customers-btn').onclick = async function(e) {
    e.preventDefault();
    const res = await fetch('/customers', {
        method: 'GET',
        headers: getHeaders()
    });
    showResult(await res.json(), 'results-customer');
};

// --- Dynamic Slabs, ToU Rates, Signatories ---
function createSlabRow(slab = {}) {
    const div = document.createElement('div');
    div.className = 'slab-row';
    div.innerHTML = `
        <input type="number" step="0.01" placeholder="Min" class="slab-min" value="${slab.min ?? ''}" required>
        <input type="number" step="0.01" placeholder="Max" class="slab-max" value="${slab.max ?? ''}" required>
        <input type="number" step="0.01" placeholder="Rate" class="slab-rate" value="${slab.rate ?? ''}" required>
        <input type="text" placeholder="Unit" class="slab-unit" value="${slab.unit ?? 'kWh'}" required>
        <button type="button" class="remove-slab-btn">Remove</button>
    `;
    div.querySelector('.remove-slab-btn').onclick = () => div.remove();
    return div;
}
function createToURow(tou = {}) {
    const div = document.createElement('div');
    div.className = 'tou-row';
    div.innerHTML = `
        <input type="text" placeholder="Time Range (e.g. 22:00-06:00)" class="tou-timeRange" value="${tou.timeRange ?? ''}" required>
        <input type="number" step="0.01" placeholder="Rate" class="tou-rate" value="${tou.rate ?? ''}" required>
        <input type="text" placeholder="Unit" class="tou-unit" value="${tou.unit ?? 'kWh'}" required>
        <button type="button" class="remove-tou-btn">Remove</button>
    `;
    div.querySelector('.remove-tou-btn').onclick = () => div.remove();
    return div;
}
function createSignatoryRow(signatory = {}) {
    const div = document.createElement('div');
    div.className = 'signatory-row';
    div.innerHTML = `
        <input type="text" placeholder="Name" class="signatory-name" value="${signatory.name ?? ''}" required>
        <input type="text" placeholder="Role" class="signatory-role" value="${signatory.role ?? ''}" required>
        <input type="datetime-local" placeholder="Signed At (optional)" class="signatory-signedAt" value="${signatory.signedAt ? signatory.signedAt.substring(0,16) : ''}">
        <button type="button" class="remove-signatory-btn">Remove</button>
    `;
    div.querySelector('.remove-signatory-btn').onclick = () => div.remove();
    return div;
}
if (document.getElementById('add-slab-btn')) {
    document.getElementById('add-slab-btn').onclick = function() {
        document.getElementById('slabs-list').appendChild(createSlabRow());
    };
    // Add one row by default
    if (!document.getElementById('slabs-list').hasChildNodes()) {
        document.getElementById('slabs-list').appendChild(createSlabRow());
    }
}
if (document.getElementById('add-tou-btn')) {
    document.getElementById('add-tou-btn').onclick = function() {
        document.getElementById('tou-list').appendChild(createToURow());
    };
    if (!document.getElementById('tou-list').hasChildNodes()) {
        document.getElementById('tou-list').appendChild(createToURow());
    }
}
if (document.getElementById('add-signatory-btn')) {
    document.getElementById('add-signatory-btn').onclick = function() {
        document.getElementById('signatories-list').appendChild(createSignatoryRow());
    };
    if (!document.getElementById('signatories-list').hasChildNodes()) {
        document.getElementById('signatories-list').appendChild(createSignatoryRow());
    }
}
// --- END Dynamic fields ---

document.getElementById('ppa-form').onsubmit = async function(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    // Collect slabs
    const slabs = Array.from(document.querySelectorAll('#slabs-list .slab-row')).map(row => ({
        min: parseFloat(row.querySelector('.slab-min').value),
        max: parseFloat(row.querySelector('.slab-max').value),
        rate: parseFloat(row.querySelector('.slab-rate').value),
        unit: row.querySelector('.slab-unit').value
    })).filter(s => !isNaN(s.min) && !isNaN(s.max) && !isNaN(s.rate) && s.unit);
    // Collect ToU rates
    const touRates = Array.from(document.querySelectorAll('#tou-list .tou-row')).map(row => ({
        timeRange: row.querySelector('.tou-timeRange').value,
        rate: parseFloat(row.querySelector('.tou-rate').value),
        unit: row.querySelector('.tou-unit').value
    })).filter(t => t.timeRange && !isNaN(t.rate) && t.unit);
    // Collect signatories
    const signatories = Array.from(document.querySelectorAll('#signatories-list .signatory-row')).map(row => {
        const signedAtVal = row.querySelector('.signatory-signedAt').value;
        return {
            name: row.querySelector('.signatory-name').value,
            role: row.querySelector('.signatory-role').value,
            signedAt: signedAtVal ? new Date(signedAtVal).toISOString() : undefined
        };
    }).filter(s => s.name && s.role);
    // Parse nested/optional fields
    let systemLocation = undefined;
    if (data.lat && data.long) {
        systemLocation = {
            lat: parseFloat(data.lat),
            long: parseFloat(data.long)
        };
    }
    const payload = {
        customer_id: data.customer_id,
        start_date: data.start_date,
        end_date: data.end_date,
        system_specs: {
            capacity_kw: parseFloat(data.capacity_kw),
            panel_type: data.panel_type,
            inverter_type: data.inverter_type,
            installation_date: data.installation_date,
            estimated_annual_production: parseFloat(data.estimated_annual_production),
            systemLocation,
            moduleManufacturer: data.moduleManufacturer || undefined,
            inverterBrand: data.inverterBrand || undefined,
            expectedGeneration: data.expectedGeneration ? parseFloat(data.expectedGeneration) : undefined,
            actualGeneration: data.actualGeneration ? parseFloat(data.actualGeneration) : undefined,
            systemAgeInMonths: data.systemAgeInMonths ? parseInt(data.systemAgeInMonths) : undefined
        },
        billing_terms: {
            tariff_rate: parseFloat(data.tariff_rate),
            escalation_rate: parseFloat(data.escalation_rate),
            billing_cycle: data.billing_cycle,
            payment_terms: data.payment_terms,
            slabs: slabs.length ? slabs : undefined,
            touRates: touRates.length ? touRates : undefined,
            taxRate: data.taxRate ? parseFloat(data.taxRate) : undefined,
            latePaymentPenaltyRate: data.latePaymentPenaltyRate ? parseFloat(data.latePaymentPenaltyRate) : undefined,
            currency: data.currency || 'INR',
            subsidySchemeId: data.subsidySchemeId || undefined,
            autoInvoice: data.autoInvoice === 'on',
            gracePeriodDays: data.gracePeriodDays ? parseInt(data.gracePeriodDays) : undefined
        },
        contractType: data.contractType || 'net_metering',
        signatories: signatories.length ? signatories : undefined,
        terminationClause: data.terminationClause || undefined,
        paymentTerms: data.paymentTerms || undefined,
        curtailmentClauses: data.curtailmentClauses || undefined,
        generationGuarantees: data.generationGuarantees || undefined,
        createdBy: data.createdBy || undefined
    };
    const res = await fetch('/ppas', {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload)
    });
    showResult(await res.json(), 'results-ppa');
};

document.getElementById('list-ppas-btn').onclick = async function(e) {
    e.preventDefault();
    const res = await fetch('/ppas', {
        method: 'GET',
        headers: getHeaders()
    });
    showResult(await res.json(), 'results-ppa');
};

document.getElementById('ppa-pdf-form').onsubmit = async function(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    const url = `/ppas/${data.ppa_id}/pdf`;
    showResult('Downloading PPA PDF...', 'results-ppa-pdf');
    const res = await fetch(url, {
        method: 'GET',
        headers: getHeaders()
    });
    if (!res.ok) {
        showResult(await res.json(), 'results-ppa-pdf');
        return;
    }
    const blob = await res.blob();
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.download = `ppa_${data.ppa_id}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showResult('PPA PDF download started.', 'results-ppa-pdf');
};

document.getElementById('usage-form').onsubmit = async function(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    const payload = {
        ppa_id: data.ppa_id,
        kwh_used: parseFloat(data.kwh_used),
        reading_date: new Date(data.reading_date).toISOString(),
        source: data.source || undefined,
        unit: data.unit || 'kWh',
        timestampStart: data.timestampStart ? new Date(data.timestampStart).toISOString() : undefined,
        timestampEnd: data.timestampEnd ? new Date(data.timestampEnd).toISOString() : undefined,
        importEnergy: data.importEnergy ? parseFloat(data.importEnergy) : undefined,
        exportEnergy: data.exportEnergy ? parseFloat(data.exportEnergy) : undefined
    };
    const res = await fetch(`/ppas/${data.ppa_id}/energy-usage`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload)
    });
    showResult(await res.json(), 'results-usage');
};

document.getElementById('invoice-form').onsubmit = async function(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    const payload = {
        ppa_id: data.ppa_id,
        kwh_used: parseFloat(data.kwh_used),
        reading_date: new Date(data.reading_date).toISOString()
    };
    const res = await fetch(`/ppas/${data.ppa_id}/invoices/generate`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload)
    });
    showResult(await res.json(), 'results-invoice');
};

document.getElementById('list-invoices-btn').onclick = async function(e) {
    e.preventDefault();
    const ppaId = prompt('Enter PPA ID to list invoices for:');
    if (!ppaId) return;
    const res = await fetch(`/ppas/${ppaId}/invoices`, {
        method: 'GET',
        headers: getHeaders()
    });
    showResult(await res.json(), 'results-invoice');
};

document.getElementById('pdf-form').onsubmit = async function(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    const url = `/ppas/${data.ppa_id}/invoices/${data.invoice_id}/pdf`;
    showResult('Downloading PDF...', 'results-pdf');
    const res = await fetch(url, {
        method: 'GET',
        headers: getHeaders()
    });
    if (!res.ok) {
        showResult(await res.json(), 'results-pdf');
        return;
    }
    const blob = await res.blob();
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.download = `invoice_${data.invoice_id}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showResult('PDF download started.', 'results-pdf');
};

document.getElementById('pay-invoice-form').onsubmit = async function(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    const url = `/ppas/${data.ppa_id}/invoices/${data.invoice_id}/pay`;
    const res = await fetch(url, {
        method: 'POST',
        headers: getHeaders()
    });
    showResult(await res.json(), 'results-pdf');
};

// List PPAs with optional customer_id filter
if (document.getElementById('list-ppas-form')) {
    document.getElementById('list-ppas-form').onsubmit = async function(e) {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        let url = '/ppas';
        if (data.customer_id) {
            url += `?customer_id=${encodeURIComponent(data.customer_id)}`;
        }
        const res = await fetch(url, {
            method: 'GET',
            headers: getHeaders()
        });
        showResult(await res.json(), 'results-list-ppas');
    };
}
// Get PPA by ID
if (document.getElementById('get-ppa-form')) {
    document.getElementById('get-ppa-form').onsubmit = async function(e) {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        const url = `/ppas/${encodeURIComponent(data.ppa_id)}`;
        const res = await fetch(url, {
            method: 'GET',
            headers: getHeaders()
        });
        showResult(await res.json(), 'results-get-ppa');
    };
}
// Sign PPA
if (document.getElementById('sign-ppa-form')) {
    document.getElementById('sign-ppa-form').onsubmit = async function(e) {
        e.preventDefault();
        const data = Object.fromEntries(new FormData(e.target));
        const url = `/ppas/${encodeURIComponent(data.ppa_id)}/sign`;
        const res = await fetch(url, {
            method: 'POST',
            headers: getHeaders()
        });
        showResult(await res.json(), 'results-sign-ppa');
    };
}

function getHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (jwtToken) headers['Authorization'] = 'Bearer ' + jwtToken;
    return headers;
}
}); 