document.addEventListener("DOMContentLoaded", function () {
    
    if (typeof Html5QrcodeScanner !== "undefined") {
        
        function showMessage(text, color) {
            document.getElementById("result").innerHTML =
                `<div class="alert alert-${color} mt-3">${text}</div>`;
        }

        function showLink(name, guest) {
            document.getElementById("result").innerHTML = `
                <a href="/invite/result/${guest}" class="result-link bg-success text-white">
                    Voir résultat de ${name}
                </a>
            `;
        }

        function showLinkTicket(name, ticketId,ticket_type) {
            document.getElementById("result").innerHTML = `
                <div class="alert alert-success mt-3">✅ Billet ${ticket_type} Validé !</div>
                <a href="/ticket/view/${ticketId}" class="result-link bg-primary text-white d-block text-center p-2 mt-2" target="_blank">
                    Voir le Ticket de ${name}
                </a>
            `;
        }

        // Fonction principale de détection et d'analyse du scan
// Fonction principale de détection et d'analyse du scan
function onScanSuccess(decodedText) {
    console.log("Donnée scannée : ", decodedText);

    // Désormais, on ne cherche plus à deviner le type via l'URL.
    // On envoie systématiquement la donnée au serveur.
    // Le serveur, lui, saura décrypter et vérifier si c'est un ticket ou une invitation.
    
    fetch(`/scan-ticket-secure?qr_data=${encodeURIComponent(decodedText)}`)
    .then(res => res.json())
    .then(data => {
            // 1. Vérification si le code est invalide (n'existe pas dans la DB)
            if (!data.valid) {
                showMessage(data.message || "Code invalide ou inconnu", "danger");
                return;
            }
            
            // 2. Vérification si le code a déjà été utilisé (state === true)
            if (data.state === true) {
                showMessage("⚠️ Attention : Ce QR code a déjà été utilisé.", "warning");
                return;
            }
            
            // 3. Traitement des cas valides
            if (data.type === 'ticket') {
                showLinkTicket(data.name || "Billet", data.ticket_id,data.ticket_type);
            } else {
                showLink(data.name || "Invité", data.guest_id);
            }
            
            if (navigator.vibrate) navigator.vibrate(200);
        })
    .catch(() => showMessage("Erreur réseau lors de la validation", "danger"));
}

        // Initialisation du scanner sur l'élément HTML 'reader'
        const scanner = new Html5QrcodeScanner(
            "reader",
            { fps: 10, qrbox: 250 }
        );
        scanner.render(onScanSuccess);

        // Gestion de l'affichage du formulaire manuel
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