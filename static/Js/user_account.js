const loadedTabs = {
            dashboard: true,
            tickets: true,
            profil: true,
            evenements: false,
            historique: false
        };

        async function switchSection(target) {
            // Nettoyage visuel global des classes actives
            document.querySelectorAll('.app-section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.nav-item-link').forEach(l => l.classList.remove('active'));
            
            // Allumage dynamique de la section et de l'icône cibles
            const targetSec = document.getElementById(`section-${target}`);
            const targetIcon = document.getElementById(`nav-${target}`);
            if(targetSec) targetSec.classList.add('active');
            if(targetIcon) targetIcon.classList.add('active');
            
            window.scrollTo(0, 0);

            // Lazy Loading intelligent si l'onglet n'a pas encore été appelé
            if (!loadedTabs[target]) {
                if (target === 'evenements') {
                    await loadEvenements();
                } else if (target === 'historique') {
                    await loadHistorique();
                }
            }
        }

async function loadEvenements() {
    try {
        // 1. Appel asynchrone direct de ton API FastAPI
        const response = await fetch("/user/list_events");
        if (!response.ok) throw new Error("Erreur de récupération (Statut HTTP non-200)");
        
        const data = await response.json();

        // ================= 1. RENDU DE LA SECTION "À LA UNE" =================
        const featuredContainer = document.getElementById("featured-events-container");
        
        if (featuredContainer) {
            if (!data.featured_events || data.featured_events.length === 0) {
                featuredContainer.innerHTML = `<p class="text-secondary small ps-1">Aucun événement à la une pour le moment.</p>`;
            } else {
                featuredContainer.innerHTML = data.featured_events.map(event => {
                    const headerStyle = event.event_photo_url 
                        ? `background-image: url('${event.event_photo_url}'); background-size: cover; background-position: center;`
                        : `background: linear-gradient(45deg, #1e3a8a, #3b82f6);`;

                    return `
                        <div class="card border-0 flex-shrink-0" style="width: 280px; background-color: #1E293B; border-radius: 12px; scroll-snap-align: start;">
                            <div class="p-3 text-center rounded-top d-flex align-items-center justify-content-center" style="${headerStyle} height: 100px;">
                                ${!event.event_photo_url ? '<i class="bi bi-laptop text-white-50 fs-1"></i>' : ''}
                            </div>
                            <div class="card-body p-3">
                                <span class="badge bg-danger mb-2" style="font-size: 0.65rem;">🔥 Reste ${event.remaining_seats || 0} places</span>
                                <h6 class="fw-bold text-white mb-1 text-truncate" title="${event.event_name}">${event.event_name}</h6>
                                <p class="text-secondary small mb-2"><i class="bi bi-calendar-event me-1"></i> ${event.event_date}</p>
                                <p class="text-secondary small mb-2 text-truncate"><i class="bi bi-geo-alt-fill me-1"></i> ${event.location || 'Lieu non spécifié'}</p>
                                <div class="d-flex justify-content-between align-items-center mt-3">
                                    <span class="fw-bold text-warning">Ticket</span>
                                    <a href="/api/event/detail/${event.event_id}" class="btn btn-warning btn-sm fw-bold px-3 py-1 text-dark" style="border-radius: 8px;">Réserver</a>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        // ================= 2. RENDU DE LA LISTE "À VENIR" (Lignes verticales) =================
        const upcomingContainer = document.getElementById("upcoming-events-container");
        
        if (upcomingContainer) {
            if (!data.upcoming_events || data.upcoming_events.length === 0) {
                upcomingContainer.innerHTML = `<p class="text-secondary small ps-1">Aucun événement à venir.</p>`;
            } else {
                upcomingContainer.innerHTML = data.upcoming_events.map(event => {
                    const imgStyle = event.event_photo_url 
                        ? `background-image: url('${event.event_photo_url}'); background-size: cover; background-position: center;`
                        : `background-color: #334155;`;

                    return `
                        <div class="card border-0 mb-3" style="background-color: #1E293B; border-radius: 12px;">
                            <div class="card-body p-3 d-flex align-items-center">
                                <div class="rounded-3 d-flex align-items-center justify-content-center text-white" 
                                     style="width: 60px; height: 60px; ${imgStyle} min-width: 60px;">
                                    ${!event.event_photo_url ? '<i class="bi bi-cup-straw fs-3"></i>' : ''}
                                </div>
                                
                                <div class="ms-3 flex-grow-1 text-truncate">
                                    <h6 class="fw-bold text-white mb-0 text-truncate">${event.event_name}</h6>
                                    <small class="text-secondary d-block text-truncate">
                                        <i class="bi bi-calendar-event me-1"></i> ${event.event_date}
                                    </small>
                                    <small class="text-secondary d-block text-truncate">
                                        <i class="bi bi-geo-alt-fill me-1"></i> ${event.location || 'Lieu non spécifié'}
                                    </small>
                                </div>
                                <a href="/api/event/detail/${event.event_id}" class="btn btn-sm btn-outline-light-custom ms-2">
                                    <i class="bi bi-chevron-right"></i>
                                </a>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        // 3. Validation sécurisée de l'état de l'onglet/composant
        if (typeof loadedTabs !== 'undefined') {
            loadedTabs.evenements = true;
        }

    } catch (error) {
        console.error("Erreur détaillée lors du rendu :", error);
        const fallbackContainer = document.getElementById('upcoming-events-container');
        if (fallbackContainer) {
            fallbackContainer.innerHTML = '<p class="text-danger text-center py-4">Erreur lors de la récupération des événements.</p>';
        }
    }
}

    async function loadHistorique() {
    // 1. Ciblage du conteneur HTML
    const container = document.getElementById('history-container');
    if (!container) {
        console.error("[PROD ERROR] Le conteneur 'history-container' est introuvable dans le DOM.");
        return;
    }

    try {
        // 2. Appel à l'API sécurisée
        const response = await fetch('/user/historique');
        
        // Sécurité Prod : Gestion des codes d'erreur HTTP (401, 403, 500, etc.)
        if (!response.ok) {
            throw new Error(`Erreur HTTP réseau : Statut ${response.status}`);
        }

        const history = await response.json();
        
        // 3. Gestion de l'état vide
        if (!Array.isArray(history) || history.length === 0) {
            container.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-archive text-secondary fs-1 d-block mb-2"></i>
                    <p class="text-secondary mb-0">Votre historique d'événements passés auquel vous avez assistés est vide.</p>
                </div>
            `;
            return;
        }

        // 4. Génération performante du HTML (Sécurisé contre les injections de texte vides)
        container.innerHTML = history.map(order => {
            const eventName = order.event_name || "Événement sans nom";
            const location = order.location || "Lieu non spécifié";
            const eventDate = order.event_date || "Date inconnue";

            return `
                <div class="card border-0 mb-3" style="background-color: #1E293B; border-radius: 14px; opacity: 0.85;">
                    <div class="card-body p-3">
                        <h6 class="fw-bold text-white mb-2">${eventName}</h6>
                        <div class="d-flex justify-content-between text-secondary" style="font-size: 0.85rem;">
                            <span class="text-truncate me-2" style="max-width: 60%;">
                                <i class="bi bi-geo-alt-fill me-1 text-danger"></i>${location}
                            </span>
                            <span class="text-nowrap">
                                <i class="bi bi-calendar-check me-1 text-info"></i>${eventDate}
                            </span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // 5. Validation du chargement du composant
        if (typeof loadedTabs !== 'undefined') {
            loadedTabs.historique = true;
        }

    } catch (error) {
        // Log discret en production pour la maintenance, sans effrayer l'utilisateur
        console.error("[PROD ERROR] Échec du chargement de l'historique :", error);
        
        container.innerHTML = `
            <div class="text-center py-4 text-danger">
                <i class="bi bi-exclamation-triangle-fill fs-2 d-block mb-2"></i>
                <p class="mb-0" style="font-size: 0.9rem;">
                    Une erreur est survenue lors de la récupération de votre historique. Veuillez réessayer plus tard.
                </p>
            </div>
        `;
    }
}

        // Écouteur pour forcer un onglet spécifique au rechargement (via ?tab=)
        window.addEventListener('DOMContentLoaded', () => {
            const urlParams = new URLSearchParams(window.location.search);
            const tab = urlParams.get('tab');
            if (tab && loadedTabs.hasOwnProperty(tab)) {
                switchSection(tab);
            }
        });