const referenceName = document.querySelector('.referenceName');// recuperer la div
const selection = document.querySelector('.selectInput');// recuperer le champ


selection.addEventListener("change",desabledReferenceName)// si on selectionne une valeur dans la selection on execute la fonction

function desabledReferenceName(){
    if (selection.value == "couple"){
        referenceName.style.display = "block"; // une fois que la valeur selectionner est couple on affiche le champ nom de reference
    }
    else{
        referenceName.style.display = "none";
    }
    
    
}
