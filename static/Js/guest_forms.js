document.addEventListener("DOMContentLoaded",function(){//au chargement de la page de la tu fais
    const event_type = document.querySelector(".event_type");
    const guest_type_div = document.querySelector(".guest_type_div");
    const guest_table_div = document.querySelector(".guest_table_div");
    const guest_table_input = document.querySelector(".guest_table_div > input");
    const ticket_type = document.querySelector(".ticket_type_div");
    function toggle_field(){
        if (event_type.value ==="Concours"){
            guest_type_div.style.display = "None";
            guest_table_div.style.display = "None";
            guest_table_input.required = false;
        }
        else{

            guest_type_div.style.display = "block";
            guest_table_div.style.display = "block";
            ticket_type.style.display = "None";
            guest_table_input.required = true;
        }
    }

    toggle_field()
})

