//scripte pour le wizard de l'easyevent suivant/precedent
     let currentStep = 1;
const totalSteps = 5; // Changement ici : on passe à 5 étapes

// Configuration des textes de la barre de progression
const stepTexts = [
    "Type d'événement",
    "Cadre du lieu",         // Étape 2
    "Taille & Logistique",   // Étape 3
    "Prestations requises",  // Étape 4
    "Informations de contact"// Étape 5
];

// Initialisation au chargement de la page
document.addEventListener("DOMContentLoaded", () => {
    // Activer la carte par défaut de l'Étape 1
    const defaultTypeRadio = document.querySelector('input[name="event_type"]:checked');
    if(defaultTypeRadio) defaultTypeRadio.closest('.wizard-card').classList.add('active');

    // Activer la carte par défaut du Cadre (Étape 2) si pré-cochée lors d'un retour en arrière
    const defaultCadreRadio = document.querySelector('input[name="cadre_lieu"]:checked');
    if(defaultCadreRadio) defaultCadreRadio.closest('.wizard-card').classList.add('active');
});

// Rend visuellement active la carte cliquée (Boutons Radio)
function toggleCardActive(radioElement) {
    const allCards = radioElement.closest('.row').querySelectorAll('.wizard-card');
    allCards.forEach(card => card.classList.remove('active'));
    if (radioElement.checked) {
        radioElement.closest('.wizard-card').classList.add('active');
    }
}

// Gestion spécifique du bouton clé en main (Saut magique direct vers la fin)
function handleFullOrga(radioElement) {
    toggleCardActive(radioElement);
    
    if (radioElement.checked) {
        const nextBtn = document.getElementById('nextBtn');
        
        nextBtn.onclick = function() {
            document.getElementById(`step-${currentStep}`).classList.add('d-none');
            currentStep = 5; // Saut direct vers l'étape finale du numéro de téléphone
            document.getElementById(`step-${currentStep}`).classList.remove('d-none');
            updateWizardUI();
            
            // On réinitialise le comportement normal du bouton pour après
            nextBtn.onclick = function() { changeStep(1); };
        };
    }
}

// Rend visuellement active la carte cliquée (Cases à cocher / Prestations)
function toggleCheckboxActive(checkboxElement) {
    if (checkboxElement.checked) {
        checkboxElement.closest('.wizard-card').classList.add('active');
    } else {
        checkboxElement.closest('.wizard-card').classList.remove('active');
    }
}

// Gestion classique de navigation Suivant / Précédent
function changeStep(direction) {
    if (direction === 1 && !validateCurrentStep()) return;

    document.getElementById(`step-${currentStep}`).classList.add('d-none');
    currentStep += direction;
    document.getElementById(`step-${currentStep}`).classList.remove('d-none');

    updateWizardUI();
}

// Validation basique des champs obligatoires
function validateCurrentStep() {
    const currentStepEl = document.getElementById(`step-${currentStep}`);
    const inputs = currentStepEl.querySelectorAll('[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('is-invalid');
            isValid = false;
        } else {
            input.classList.remove('is-invalid');
        }
    });
    return isValid;
}

// Synchronisation complète des éléments de l'interface graphique
function updateWizardUI() {
    // Bouton Précédent visible uniquement après l'étape 1
    if (currentStep === 1) {
        document.getElementById('prevBtn').classList.add('d-none');
    } else {
        document.getElementById('prevBtn').classList.remove('d-none');
    }

    // Affichage alternatif entre le bouton Suivant et le bouton Soumettre à la fin
    if (currentStep === totalSteps) {
        document.getElementById('nextBtn').classList.add('d-none');
        document.getElementById('submitBtn').classList.remove('d-none');
    } else {
        document.getElementById('nextBtn').classList.remove('d-none');
        document.getElementById('submitBtn').classList.add('d-none');
    }

    // Ajustement de la largeur de la barre de progression Bootstrap
    const progressPercentage = (currentStep / totalSteps) * 100;
    document.getElementById('wizardProgress').style.width = `${progressPercentage}%`;
    
    // Remplacement textuel des indications d'étapes
    document.querySelector('.progress-bar').parentNode.nextElementSibling.children[0].innerText = `Étape ${currentStep}/${totalSteps}`;
    document.getElementById('progressText').innerText = stepTexts[currentStep - 1];
}