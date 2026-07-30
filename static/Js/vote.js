// Fonction utilitaire pour afficher la modale Bootstrap personnalisée
function showVoteModal({ 
    title, 
    message, 
    iconClass = 'bi-exclamation-circle-fill text-gold', 
    confirmBtnText = "D'accord, j'ai compris", 
    btnClass = 'btn-gold', // Style par défaut du bouton
    onConfirm = null 
}) {
    const modalElement = document.getElementById('voteInfoModal');
    if (!modalElement) return;

    // 1. Mise à jour des textes et de l'icône
    document.getElementById('voteModalTitle').innerText = title;
    document.getElementById('voteModalMessage').innerText = message;

    const iconElement = document.getElementById('voteModalIcon');
    if (iconElement) {
        iconElement.className = `bi ${iconClass} fs-1`;
    }

    // 2. Mise à jour du bouton de confirmation
    const confirmBtn = document.getElementById('voteModalConfirmBtn');
    if (confirmBtn) {
        confirmBtn.innerText = confirmBtnText;
        
        // Applique dynamiquement la classe CSS du bouton (ex: btn-primary, btn-gold, btn-danger)
        confirmBtn.className = `btn ${btnClass} w-100 rounded-pill py-2`;

        // Nettoyage des événements précédents (remplacement du nœud)
        const newBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

        // Attachement du nouveau callback si présent (ex: redirection vers /login)
        if (onConfirm) {
            newBtn.addEventListener('click', onConfirm);
        }
    }

    // 3. Affichage de la modale via l'instance Bootstrap
    const voteModal = bootstrap.Modal.getOrCreateInstance(modalElement);
    voteModal.show();
}

// Fonction principale de vote
async function voter(eventId, candidateId, buttonElement) {
    if (buttonElement) {
        buttonElement.disabled = true;
        buttonElement.dataset.originalHtml = buttonElement.innerHTML;
        buttonElement.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Envoi...';
    }

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content 
            || document.querySelector('input[name="csrf_token"]')?.value;

        const headers = { 'Content-Type': 'application/json' };
        if (csrfToken) {
            headers['X-CSRF-Token'] = csrfToken;
        }

        const response = await fetch(`/api/events/${eventId}/vote/${candidateId}`, {
            method: 'POST',
            headers: headers,
            credentials: 'same-origin'
        });

        // 1. Authentification / Session expirée (HTTP 401, 403 ou Redirection)
        if (response.status === 401 || response.status === 403 || response.redirected) {
            showVoteModal({
                title: "Connexion requise",
                message: "Vous devez être connecté pour pouvoir exprimer votre vote.",
                iconClass: "bi-lock-fill text-primary", // Icône bleue
                btnClass: "btn-primary",               // Bouton bleu Bootstrap
                confirmBtnText: "Se connecter",
                onConfirm: () => {
                    window.location.href = `/auth/login?next=/api/event/detail/${eventId}`;
                }
            });

            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = buttonElement.dataset.originalHtml;
            }
            return;
        }

        // 2. Traitement du contenu JSON
        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
            throw new Error("Le serveur a renvoyé une réponse inattendue (non-JSON).");
        }

        const data = await response.json();

        // 3. Cas Succès (HTTP 200/201)
        if (response.ok) {
            const countElement = document.getElementById(`votes-count-${candidateId}`);
            if (countElement) {
                countElement.innerText = data.new_votes_count;
            }

            // Verrouiller tous les boutons de vote
            document.querySelectorAll('.btn-vote').forEach(btn => {
                btn.disabled = true;
                btn.classList.remove('btn-warning', 'btn-outline-warning');
                btn.classList.add('btn-secondary');
                btn.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> Voté';
            });

            showVoteModal({
                title: "Vote enregistré !",
                message: "Merci ! Votre vote a bien été pris en compte.",
                iconClass: "bi-check-circle-fill text-success",
                btnClass: "btn-success",
                confirmBtnText: "Super !"
            });
            return;
        }

        // 4. Cas Erreur Métier (Ex: HTTP 400 - Déjà voté)
        if (response.status === 400 && data.detail?.toLowerCase().includes("déjà")) {
            // Verrouiller les boutons car l'utilisateur a déjà voté
            document.querySelectorAll('.btn-vote').forEach(btn => {
                btn.disabled = true;
                btn.classList.remove('btn-warning', 'btn-outline-warning');
                btn.classList.add('btn-secondary');
                btn.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> Déjà voté';
            });

            showVoteModal({
                title: "Information",
                message: data.detail,
                iconClass: "bi-exclamation-circle-fill text-gold",
                btnClass: "btn-warning",
                confirmBtnText: "D'accord, j'ai compris"
            });
        } else {
            // Pour toute autre erreur 4xx/5xx avec message JSON
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = buttonElement.dataset.originalHtml;
            }

            showVoteModal({
                title: "Erreur",
                message: data.detail || "Une erreur est survenue lors du vote.",
                iconClass: "bi-x-circle-fill text-danger",
                btnClass: "btn-danger",
                confirmBtnText: "Fermer"
            });
        }

    } catch (error) {
        console.error("Erreur réseau/technique vote :", error);
        if (buttonElement) {
            buttonElement.disabled = false;
            buttonElement.innerHTML = buttonElement.dataset.originalHtml;
        }

        showVoteModal({
            title: "Problème de connexion",
            message: "Impossible de valider le vote. Vérifiez votre connexion internet ou réessayez.",
            iconClass: "bi-wifi-off text-danger",
            btnClass: "btn-secondary",
            confirmBtnText: "Fermer"
        });
    }
}