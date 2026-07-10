document.addEventListener("DOMContentLoaded", function () {
    
    if (typeof Html5QrcodeScanner !== "undefined") {
        
        // --- FONCTIONS D'AFFICHAGE ---
        function showMessage(text, color) {
            document.getElementById("result").innerHTML =
                `<div class="alert alert-${color} mt-3">${text}</div>`;
        }

        // Affichage pour les invitations
        function showLink(name, guest) {
            document.getElementById("result").innerHTML = `
                <div class="alert alert-info mt-3">📩 Invitation détectée</div>
                <a href="/invite/result/${guest}" class="result-link bg-success text-white d-block text-center p-3 mt-2 font-weight-bold text-uppercase text-decoration-none rounded">
                    Vérifier l'invitation de : ${name}
                </a>
            `;
        }

        // Affichage dynamique pour les billets (S'adapte selon l'état d'utilisation)
        function showLinkTicket(name, ticketId, ticket_type, isScanned, message) {
            let alertClass = "alert-info";
            let btnClass = "bg-success"; // Vert par défaut (Valide)
            let prefixIcon = "🎟️ Billet Valide";

            // Si le serveur indique que le billet a déjà été validé/scanné
            if (isScanned) {
                alertClass = "alert-warning";
                btnClass = "bg-warning text-dark"; // Orange (Déjà utilisé)
                prefixIcon = "⚠️ Billet Déjà Utilisé";
            }

            document.getElementById("result").innerHTML = `
                <div class="alert ${alertClass} mt-3">${prefixIcon} (${ticket_type})</div>
                <p class="text-center small text-muted my-1">${message || ""}</p>
                <a href="/ticket/view/${ticketId}" class="result-link ${btnClass} d-block text-center p-3 mt-2 font-weight-bold text-uppercase text-decoration-none rounded">
                    Voir le detail
                </a>
            `;
        }

        // --- VERROU DU SCAN ---
        let scanEnCours = false;

        // --- FONCTION DE DETECTION UNIFIÉE ---
        async function onScanSuccess(decodedText) {
            if (scanEnCours) return; // Bloque les lectures en rafale
            
            scanEnCours = true; // Enclenche le verrou
            
            try {
                // Envoi de la requête de vérification sécurisée à FastAPI
                const response = await fetch(`/scan-ticket-secure?qr_data=${encodeURIComponent(decodedText)}`);
                const result = await response.json();
                
                // Si le serveur valide la structure et le jeton TOTP
                if (result.valid) {
                    if (result.type === "invitation") {
                        showLink(result.name, result.guest_id);
                    } else {
                        // On passe le booléen 'is_scanned' et le message pour appliquer la bonne couleur
                        showLinkTicket(
                            result.name, 
                            result.ticket_id, 
                            result.ticket_type, 
                            result.is_scanned, 
                            result.message
                        );
                    }
                } else {
                    // Code TOTP expiré ou mauvais QR code (Écran Rouge)
                    showMessage(`❌ ${result.message || "Code invalide ou expiré."}`, "danger");
                }
            } catch (error) {
                console.error("Erreur réseau :", error);
                showMessage("❌ Erreur de communication avec le serveur.", "danger");
            } finally {
                // Maintien du blocage pendant 2,5 secondes
                setTimeout(() => {
                    scanEnCours = false;
                }, 2500);
            }
        }

        // Initialisation du scanner
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

        // Traduction de l'interface en français
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