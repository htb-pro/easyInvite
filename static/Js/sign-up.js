// 📄 static/js/sign-up.js
document.addEventListener("DOMContentLoaded", function () {
    const registerForm = document.getElementById("form-register");
    const errorAlert = document.getElementById("error-alert");

    if (registerForm) {
        registerForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            if (errorAlert) {
                errorAlert.classList.add("d-none");
                errorAlert.innerHTML = "";
            }
            document.querySelectorAll(".form-control").forEach(input => {
                input.classList.remove("is-invalid");
            });

            try {
                const csrfTokenElement = document.getElementById("csrf_token");
                if (!csrfTokenElement) {
                    throw new Error("Le jeton de sécurité CSRF est introuvable.");
                }

                const formData = new FormData(registerForm);
                formData.set("csrf_token", csrfTokenElement.value);

                const response = await fetch("/organizer/register", {
                    method: "POST",
                    body: formData
                });

                const data = await response.json();

                if (!response.ok) {
                    if (errorAlert) {
                        errorAlert.classList.remove("d-none");

                        if (typeof data.detail === "string") {
                            errorAlert.textContent = data.detail;
                        } 
                        else if (Array.isArray(data.detail)) {
                            const traductions = {
                                "company_name": "Nom de l'entreprise / organisation",
                                "email": "Adresse email",
                                "phone": "Numéro de téléphone",
                                "password": "Mot de passe"
                            };

                            let messagesErreur = [];
                            data.detail.forEach(err => {
                                const nomTechnique = err.loc[1];
                                const nomPropre = traductions[nomTechnique] || nomTechnique;
                                
                                messagesErreur.push(`Le champ <strong>${nomPropre}</strong> est obligatoire ou mal rempli.`);

                                const inputElement = document.querySelector(`[name="${nomTechnique}"]`);
                                if (inputElement) {
                                    inputElement.classList.add("is-invalid");
                                }
                            });
                            errorAlert.innerHTML = messagesErreur.join("<br>");
                        }
                    }
                    return;
                }

                alert(data.message || "Votre compte a été créé avec succès !");
                window.location.href = "/organizer/sign-in";

            } catch (networkError) {
                console.error("Erreur réseau :", networkError);
                if (errorAlert) {
                    errorAlert.classList.remove("d-none");
                    errorAlert.textContent = "Impossible de joindre le serveur.";
                }
            }
        });
    }
});