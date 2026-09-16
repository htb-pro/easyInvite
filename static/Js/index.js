document.addEventListener("DOMContentLoaded", function () {
    
    if (typeof Html5QrcodeScanner !== "undefined") {
        
        // --- DONNÉES DU DERNIER SCAN ---
        let lastScanData = null;

        // --- ÉLÉMENTS DU DOM ---
        const showResultBtn = document.getElementById("show-result-btn");
        const modal = document.getElementById("scan-modal");
        const closeModalBtn = document.getElementById("close-modal-btn");
        const scanNextBtn = document.getElementById("scan-next-btn");

        function showMessage(text, color) {
            document.getElementById("result").innerHTML =
                `<div class="alert alert-${color} mt-3">${text}</div>`;
        }

        // --- PRÉPARATION DU BOUTON POUR INVITATION ---
       function prepareGuestResult(result) {
    lastScanData = result;

    if (showResultBtn) {
        showResultBtn.disabled = false;
        showResultBtn.classList.add("active");
        
        const btnText = document.getElementById("btn-text");
        const guestName = result.name ? result.name.toUpperCase() : "INVITÉ";

        // Détection dynamique du type
        const isInvitation = result.type === "invitation";
        const labelType = isInvitation ? "INVITATION" : "BILLET";

        if (btnText) {
            if (result.is_scanned) {
                showResultBtn.style.backgroundColor = "#eab308"; // Jaune
                showResultBtn.style.color = "#000000";
                btnText.innerText = `⚠️ ${labelType} DÉJÀ UTILISÉ(E) - ${guestName}`;
            } else {
                showResultBtn.style.backgroundColor = "#22c55e"; // Vert
                showResultBtn.style.color = "#ffffff";
                btnText.innerText = `📩 ${labelType} VALIDE - ${guestName}`;
            }
        }
    }

    if (navigator.vibrate) {
        navigator.vibrate(result.is_scanned ? [100, 50, 100] : [150]);
    }
}

        // --- OUVERTURE DU MODAL AU CLIC ---
        if (showResultBtn) {
            showResultBtn.addEventListener("click", function () {
                if (!lastScanData) return;

                const isSuccess = !lastScanData.is_scanned;

                // Remplissage dynamique pour un INVITÉ
                document.getElementById("modal-status-icon").innerText = isSuccess ? "📩" : "⚠️";
                document.getElementById("modal-status-title").innerText = isSuccess ? "Invitation Valide" : "Invitation Déjà Utilisée";
                document.getElementById("modal-status-title").style.color = isSuccess ? "#4ade80" : "#facc15";

                // Type d'invité (ex: VIP, Regular) avec fallback propre
                const guestType = lastScanData.guest_type || lastScanData.ticket_type || lastScanData.type_invite || " ";
                const guestTypeElement = document.getElementById("modal-guest-type") || document.getElementById("modal-ticket-type");
                if (guestTypeElement) guestTypeElement.innerText = guestType ;

                // 1. Nom
                document.getElementById("modal-guest-name").innerText = lastScanData.name || "Invité Anonyme";

                // 2. Token / Code unique
                const guestTokenElement = document.getElementById("modal-guest-token") || document.getElementById("modal-ticket-code");
                if (guestTokenElement) {
                    guestTokenElement.innerText = lastScanData.get_pass || lastScanData.guest_token || lastScanData.ticket_id || "#----";
                }

                // 3. Téléphone (Sécurisé avec alternatives de clés)
                const guestPhoneElement = document.getElementById("modal-guest-phone");
                if (guestPhoneElement) {
                    guestPhoneElement.innerText = lastScanData.telephone || lastScanData.phone || lastScanData.guest_phone || "non renseigné";
                }

                // 4. Table / Place (CORRECTION DU BUG ICI)
                const guestTableElement = document.getElementById("modal-guest-table");
                if (guestTableElement) {
                    // Utilise bien guestTableElement ici !
                    guestTableElement.innerText = lastScanData.place || lastScanData.table || lastScanData.seat || "non assignée";
                }

                // Message d'information
                const msgElement = document.getElementById("modal-message");
                msgElement.innerText = lastScanData.message || (isSuccess ? "Accès autorisé. Bienvenue !" : "Attention : cet invité a déjà été enregistré !");
                msgElement.style.color = isSuccess ? "#4ade80" : "#facc15";

                // Redirection optionnelle vers la fiche complète si un lien existe
                const guestLink = document.getElementById("modal-guest-link");
                if (guestLink && (lastScanData.guest_id || lastScanData.id)) {
                    guestLink.href = `/invite/result/${lastScanData.guest_id || lastScanData.id}`;
                    guestLink.style.display = "inline-block";
                }

                // Affichage du modal
                if (modal) modal.classList.remove("hidden");
            });
        }

        // --- RESET ET FERMETURE DU MODAL ---
        function resetScannerUI() {
            if (modal) modal.classList.add("hidden");

            if (showResultBtn) {
                showResultBtn.disabled = true;
                showResultBtn.classList.remove("active");
                showResultBtn.style.backgroundColor = "";
                showResultBtn.style.color = "";
                
                const btnText = document.getElementById("btn-text");
                if (btnText) btnText.innerText = "SCANNEZ UNE INVITATION";
            }

            lastScanData = null;
        }

        if (closeModalBtn) closeModalBtn.addEventListener("click", resetScannerUI);
        if (scanNextBtn) scanNextBtn.addEventListener("click", resetScannerUI);

        // --- VERROU DE SCAN ---
        let scanEnCours = false;

        // --- DÉTECTION DU QR CODE ---
        async function onScanSuccess(decodedText) {
            if (scanEnCours) return;
            
            scanEnCours = true;
            
            try {
                // Endpoint sécurisé pour les invitations
                const response = await fetch(`/scan-ticket-secure?qr_data=${encodeURIComponent(decodedText)}`);
                const result = await response.json();
                
                if (result.valid) {
                    // Préparation des données d'invitation pour le modal
                    prepareGuestResult(result);
                } else {
                    showMessage(`❌ ${result.message || "Invitation invalide ou expirée."}`, "danger");
                }
            } catch (error) {
                console.error("Erreur réseau :", error);
                showMessage("❌ Erreur de communication avec le serveur.", "danger");
            } finally {
                setTimeout(() => {
                    scanEnCours = false;
                }, 2500);
            }
        }

        // Initialisation de la caméra
        const scanner = new Html5QrcodeScanner(
            "reader",
            { fps: 10, qrbox: 250 }
        );
        scanner.render(onScanSuccess);

        // Gestion du formulaire manuel
        const form = document.querySelector(".form-section");
        const show_form = document.querySelector("#show-form");

        if (form && show_form) {
            form.style.display = "none";
            show_form.addEventListener("click", () => {
                form.style.display = form.style.display === "none" ? "block" : "none";
            });
        }

        // Traduction des textes de la bibliothèque
        setTimeout(() => {
            const scan_text = document.querySelector("#html5-qrcode-anchor-scan-type-change");
            const scan_camera_permission = document.querySelector("#reader__dashboard_section_csr button");
            const select_image_to_scan = document.querySelector("#html5-qrcode-button-file-selection");
            
            if (scan_text) scan_text.innerHTML = "Choisir le QR Code à scanner";
            if (scan_camera_permission) scan_camera_permission.innerHTML = "Demander la permission de la caméra";
            if (select_image_to_scan) select_image_to_scan.innerHTML = "Sélectionner une image";
        }, 500);
    }
});