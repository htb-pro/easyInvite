document.addEventListener("DOMContentLoaded", function() {
    const event_type = document.querySelector("#event_type");
    
    // Si le sélecteur principal n'existe pas sur la page, on arrête
    if (!event_type) return;

    // Récupération des conteneurs de champs
    const couple_field = document.querySelector(".couple_name");
    const couple_input_field = document.querySelector(".couple_name input");
    
    // Ciblage précis du label associé au numéro de téléphone
    const couple_number_label = document.querySelector(".couple_number .form-label");
    
    const img_field = document.querySelector(".event_img");
    
    // CORRECTION : Ciblage de la nouvelle classe des conteneurs de cases à cocher
    const checkboxes_divs = document.querySelectorAll(".check-container");
    // Le premier est généralement "A la une", le second "Cadeau en espèce"
    const present_field = checkboxes_divs[1] || document.querySelector(".form-check"); 
    const is_featured_box = checkboxes_divs[0] || document.querySelector(".is_featured");

    const organizer = document.querySelector(".organizer");
    const organizer_input_field = document.querySelector(".organizer input");
    const greetings = document.querySelector(".greetings");
    const description = document.querySelector(".description");
    const place_field = document.querySelector(".total_place");

    function toggleCoupleField() {
        const val = event_type.value;

        // Réinitialisation par défaut des requis pour éviter les blocages fantômes
        if (couple_input_field) couple_input_field.required = false;
        if (organizer_input_field) organizer_input_field.required = false;
        if (place_field) {
            const pInput = place_field.querySelector("input");
            if (pInput) pInput.required = false;
        }

        // Affichage de base (On affiche tout par défaut, on masquera au cas par cas)
        if (couple_field) couple_field.style.display = "block";
        if (img_field) img_field.style.display = "block";
        if (present_field) present_field.style.display = "flex"; // Style flex pour l'alignement du nouveau design
        if (is_featured_box) is_featured_box.style.display = "flex";
        if (organizer) organizer.style.display = "block";
        if (greetings) greetings.style.display = "block";
        if (description) description.style.display = "block";
        if (place_field) place_field.style.display = "block";

        if (val === "concours") {
            if (couple_field) couple_field.style.display = "none";
            if (img_field) img_field.style.display = "none";
            if (present_field) present_field.style.display = "none";
            if (greetings) greetings.style.display = "none";
            if (couple_number_label) couple_number_label.textContent = "Numéro de l'organisateur";
        } 
        else if (val === "conference") {
            if (couple_field) couple_field.style.display = "none";
            if (present_field) present_field.style.display = "none";
            if (description) description.style.display = "none";
            if (couple_number_label) couple_number_label.textContent = "Numéro de l'organisateur";
        }
        else if (val === "birth_day") {
            if (couple_field) couple_field.style.display = "none";
            if (description) description.style.display = "none";
            if (couple_number_label) couple_number_label.textContent = "Numéro de l'organisateur";
        } 
        else if (val === "other") {
            if (couple_field) couple_field.style.display = "none";
            if (present_field) present_field.style.display = "none";
            if (organizer_input_field) organizer_input_field.required = true;
            if (couple_number_label) couple_number_label.textContent = "Numéro de l'organisateur";
            if (place_field) {
                const pInput = place_field.querySelector("input");
                if (pInput) pInput.required = true;
            }
        } 
        else {
            // Mode par défaut (Mariage / Wedding)
            if (greetings) greetings.style.display = "none";
            if (organizer) organizer.style.display = "none";
            if (place_field) place_field.style.display = "none";
            if (is_featured_box) is_featured_box.style.display = "none";
            if (couple_input_field) couple_input_field.required = true;
            if (couple_number_label) couple_number_label.textContent = "Numéro de téléphone du couple (Couple's phone number)";
        }
    }

    // Vérification initiale au chargement
    toggleCoupleField();
    
    // Écouteur de changement
    event_type.addEventListener("change", toggleCoupleField);
});