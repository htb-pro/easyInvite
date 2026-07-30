async function apiRequest(url, options = {}) {
    const defaultOptions = {
        credentials: 'same-origin',
        ...options,
        headers: {
            ...options.headers
        }
    };

    try {
        const response = await fetch(url, defaultOptions);

        // 🎯 1. On intercepte le 401 (Non authentifié)
        if (response.status === 401) {
            const currentPath = window.location.pathname + window.location.search;
            
            // 🎯 2. Correction du test : On vérifie bien "/auth/login"
            if (!window.location.pathname.startsWith('/auth/login')) {
                console.log("Session expirée, redirection vers le login...");
                window.location.href = `/auth/login?next=${encodeURIComponent(currentPath)}`;
            }
            return null;
        }

        return response;

    } catch (error) {
        console.error("🚨 [Network Error] Impossible de joindre le serveur :", error);
        throw error;
    }
}