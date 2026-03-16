
document.addEventListener("DOMContentLoaded", function() {
    const event_type = document.querySelector("#event_type");
    const couple_field = document.querySelector(".couple_name");
    const couple_input_field = document.querySelector(".couple_name input");
    const img_field = document.querySelector(".event_img");
    const present_field = document.querySelector(".form-check");
    function toggleCoupleField() {
        if(event_type.value === "Concours") {
            couple_field.style.display = "None";
            img_field.style.display = "None";
            present_field.style.display = "None";
            couple_input_field.required =  false;
        } else {
            couple_field.style.display = "block";
            img_field.style.display = "block";
            present_field.style.display = "block";
            couple_input_field.required =  true;
        }
    }

    // Vérification initiale au chargement
    toggleCoupleField();

    // Vérification à chaque changement
    event_type.addEventListener("change", toggleCoupleField);
});

