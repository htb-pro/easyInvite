
document.addEventListener("DOMContentLoaded", function() {
    const event_type = document.querySelector("#event_type");
    const couple_field = document.querySelector(".couple_name");
    const couple_input_field = document.querySelector(".couple_name input");
    const couple_number = document.querySelector(".couple_number label");
    const img_field = document.querySelector(".event_img");
    const present_field = document.querySelector(".form-check");

    const organizer = document.querySelector(".organizer");
    const organizer_input_field = document.querySelector(".organizer input");
    const greetings = document.querySelector(".greetings");
    const description = document.querySelector(".description");
    function toggleCoupleField() {
        if (!couple_field || !img_field || !present_field || !greetings || !description) return;
        else if(event_type.value === "concours") {
            couple_field.style.display = "none";
            img_field.style.display = "none";
            present_field.style.display = "none";
            couple_input_field.required =  false;
            couple_number.textContent = "numero organisateur"
            greetings.style.display = "none"
            description.style.display = "block"
        } 
        else if(event_type.value === "conference") {
            couple_field.style.display = "none";
            present_field.style.display = "none";
            description.style.display = "none";
            couple_input_field.required =  false;
            couple_number.textContent = "numero organisateur"
            description.style.display = "none"
            greetings.style.display = "block"
        }
        else if(event_type.value === "birth_day") {
            couple_field.style.display = "none";
            present_field.style.display = "block";
            description.style.display = "none";
            couple_input_field.required =  false;
            couple_number.textContent = "numero organisateur"
            description.style.display = "none"
            greetings.style.display = "block"
        } 
         else {
            couple_field.style.display = "block";
            img_field.style.display = "block";
            present_field.style.display = "block";
            description.style.display = "block";
            couple_input_field.required =  true;
            couple_number.textContent = "Numéro de téléphone du couple (Couple's phone number)"
            greetings.style.display = "none"
            organizer.style.display = "none"
            organizer_input_field.required = false
        }
    }

    // Vérification initiale au chargement
    toggleCoupleField();
    // Vérification à chaque changement
    event_type.addEventListener("change",()=>{
        toggleCoupleField();
    } );
});

