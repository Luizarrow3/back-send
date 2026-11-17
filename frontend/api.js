export function getToken() {
    return localStorage.getItem("censo-token");
}

export async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (options.body && !(options.body instanceof FormData)) {
        headers.set("Content-Type", "application/json");
    }

    const response = await fetch(path, { ...options, headers });
    if (response.status === 401) {
        window.dispatchEvent(new Event("censo:session-expired"));
    }
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Falha na requisição (${response.status})`);
    }
    return response;
}

export async function json(path, options = {}) {
    const response = await api(path, options);
    if (response.status === 204) return null;
    return response.json();
}

export async function exportCsv(filters = {}) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
        if (value) query.set(key, value);
    }
    const response = await api(`/relatorios/pessoas.csv?${query}`);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = "recenseados.csv";
    link.click();
    URL.revokeObjectURL(url);
}
