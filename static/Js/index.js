if (typeof Html5QrcodeScanner !== "undefined"){
function showMessage(text,color){
    document.getElementById("result").innerHTML =
        `<div class="alert alert-${color} mt-3">${text}</div>`;
}

function showLink(name,guest){

    document.getElementById("result").innerHTML = `
        <a href="/result/${guest}" class="result-link bg-success text-white">
            Voir résultat de ${name}
        </a>
    `;
}

function onScanSuccess(decodedText){

    fetch(`/scan?guest_id=${decodedText}`)
    .then(res=>res.json())
    .then(data=>{

        if(!data.valid){
            showMessage("QR Code invalide","danger");
            return;
        }

        showLink(data.name,data.guest_id);

        // vibration mobile
        if(navigator.vibrate){
            navigator.vibrate(200);
        }

    })
    .catch(()=>showMessage("le qr_code est invalid","danger"));
}

const scanner = new Html5QrcodeScanner(
    "reader",
    { fps:10, qrbox:250}
);

scanner.render(onScanSuccess);
//faire apparaitre et disparaitre le formulaire
const form = document.querySelector(".form-section");
const show_form = document.querySelector("#show-form");

form.style.display ="none"
show_form.addEventListener("click",()=>{
    form.style.display= form.style.display ==="none" ? "block":"none";
})
//----------------modifier le nom de la fonctionalite de "en scan an image en fr scanner une image"
const scan_text = document.querySelector("#html5-qrcode-anchor-scan-type-change");
const scan_camera_permission = document.querySelector("#reader__dashboard_section_csr button");//changer le text en fr
const select_image_to_scan = document.querySelector("#html5-qrcode-button-file-selection");
scan_text.innerHTML = "Choisir le qr_code a scanner";
scan_camera_permission.innerHTML = "Demander la permission de la camera";
select_image_to_scan.innerHTML = "selectionner l'image - aucune image selectionné";
}

