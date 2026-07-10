function openConfirmationModal() {
    const fullnameInput = document.getElementById('fullname-input')?.value;
    const phoneInput = document.getElementById('phone-input')?.value;

    if (!fullnameInput || !phoneInput) {
        alert("Veuillez remplir tous les champs du profil.");
        return;
    }

    // Réinitialise le champ mot de passe de la modale
    document.getElementById('confirm-password-input').value = "";
    
    const modalElement = document.getElementById('confirmProfileModal');

    // 💡 SÉCURITÉ PROD : Si Bootstrap est déjà chargé, on ouvre directement
    if (typeof bootstrap !== 'undefined') {
        const myModal = bootstrap.Modal.getOrCreateInstance(modalElement);
        myModal.show();
    } else {
        // Si Bootstrap n'est pas encore défini, on attend que toute la page (et ses scripts) soit prête
        console.warn("[PROD WARNING] Bootstrap n'est pas encore détecté. Attente du chargement complet...");
        window.addEventListener('load', () => {
            if (typeof bootstrap !== 'undefined') {
                const myModal = bootstrap.Modal.getOrCreateInstance(modalElement);
                myModal.show();
            } else {
                console.error("[PROD ERROR] Le script JavaScript de Bootstrap est complètement manquant dans le HTML.");
                alert("Erreur d'interface : impossible d'ouvrir la fenêtre de confirmation.");
            }
        });
    }
}

async function submitProfileForm() {
    const user_name = document.getElementById('fullname-input')?.value;
    const user_phone = document.getElementById('phone-input')?.value;
    const password = document.getElementById('confirm-password-input')?.value;

    if (!password) {
        alert("Veuillez saisir votre mot de passe pour confirmer.");
        return;
    }

    // Préparation des données au format Form (comme attendu par FastAPI Form(...))
    const formData = new FormData();
    formData.append('user_name', user_name);
    formData.append('user_phone', user_phone);
    formData.append('password', password);

    try {
        // Envoi des données à ta route FastAPI
        const response = await fetch('/user/update-profile', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            // Si le serveur renvoie une erreur (401, 409, 422, etc.)
            alert(data.error || "Une erreur est survenue lors de la modification.");
            return;
        }

        // Si tout s'est bien passé (Code 200 OK)
        alert(data.message || "Profil mis à jour avec succès !");
        
        // Optionnel : Fermer la modale et recharger la page pour voir les changements
        const modalElement = document.getElementById('confirmProfileModal');
        if (typeof bootstrap !== 'undefined') {
            const myModal = bootstrap.Modal.getOrCreateInstance(modalElement);
            myModal.hide();
        }
        window.location.reload();

    } catch (error) {
        console.error("[FETCH ERROR]", error);
        alert("Impossible de joindre le serveur. Vérifiez votre connexion.");
    }
}