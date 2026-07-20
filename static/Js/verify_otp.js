document.addEventListener("DOMContentLoaded", function () {
    const otpForm = document.getElementById('otpForm');
    const alertZone = document.getElementById('alertZone');
    const alertText = document.getElementById('alertText');
    const btnSubmit = document.getElementById('btnSubmit');
    const btnText = document.getElementById('btnText');
    
    const btnResend = document.getElementById('btnResend');
    const messageBox = document.getElementById('messageBox');
    
    let timerInterval = null;

    // Fonction pour extraire un message texte lisible
    function extractErrorMessage(detail, defaultMsg = "Une erreur est survenue.") {
        if (!detail) return defaultMsg;
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail)) {
            // Si detail est une liste d'erreurs (ex: validation FastAPI)
            return detail.map(err => err.msg || JSON.stringify(err)).join(", ");
        }
        if (typeof detail === "object") {
            return detail.msg || detail.message || JSON.stringify(detail);
        }
        return String(detail);
    }

    // 1. VÉRIFICATION DU CODE OTP
    otpForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        btnSubmit.disabled = true;
        btnText.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Vérification...`;
        alertZone.classList.add('d-none');

        const formData = new FormData(otpForm);

        try {
            const response = await fetch('/auth/verify-otp', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok && data.status === "SUCCESS") {
                window.location.href = `/user/reset_password?token=${data.reset_token}`;
            } else {
                alertText.textContent = extractErrorMessage(data.detail, "Code invalide.");
                alertZone.classList.remove('d-none');
                
                if (data.status === "INVALID_CODE") {
                    const inputField = document.getElementById('otp_entered');
                    if (inputField) {
                        inputField.value = '';
                        inputField.focus();
                    }
                }
            }
        } catch (error) {
            alertText.textContent = "Une erreur réseau est survenue. Veuillez réessayer.";
            alertZone.classList.remove('d-none');
        } finally {
            btnSubmit.disabled = false;
            btnText.textContent = "Valider";
        }
    });

    // 2. RENVOI DE L'OTP + COMPTE À REBOURS
    function startCountdown(seconds) {
        let timeLeft = seconds;
        btnResend.disabled = true;

        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            btnResend.textContent = `Renvoyer le code (${timeLeft}s)`;
            timeLeft--;

            if (timeLeft < 0) {
                clearInterval(timerInterval);
                btnResend.disabled = false;
                btnResend.textContent = "Renvoyer le code";
            }
        }, 1000);
    }

    btnResend.addEventListener("click", async function () {
        const formData = new FormData(otpForm);

        btnResend.disabled = true;
        btnResend.textContent = "Envoi en cours...";

        try {
            const response = await fetch("/auth/send_otp", {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            messageBox.classList.remove('d-none', 'alert-success', 'alert-warning', 'alert-danger');

            const errorMessage = extractErrorMessage(data.detail || data.message, "Erreur lors du renvoi.");

            if (response.ok) {
                messageBox.classList.add('alert-success');
                messageBox.textContent = data.message || "Un nouveau code a été envoyé.";
                startCountdown(60);

            } else if (response.status === 429) {
                messageBox.classList.add('alert-warning');
                messageBox.textContent = errorMessage;

                // Extraire le temps restant dans le message (ex: "Attendez 45s")
                const match = errorMessage.match(/\d+/);
                const secondsLeft = match ? parseInt(match[0], 10) : 60;
                startCountdown(secondsLeft);

            } else {
                messageBox.classList.add('alert-danger');
                messageBox.textContent = errorMessage;
                btnResend.disabled = false;
                btnResend.textContent = "Renvoyer le code";
            }

        } catch (error) {
            messageBox.classList.remove('d-none');
            messageBox.classList.add('alert-danger');
            messageBox.textContent = "Impossible de contacter le serveur.";
            btnResend.disabled = false;
            btnResend.textContent = "Renvoyer le code";
        }
    });
});