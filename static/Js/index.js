//   function confirmYes() {
//     const msg = document.getElementById('guestMessage').value;
//     // Ici tu enverras la réponse à ton backend via fetch ou form

//     document.getElementById('message-section').style.display = 'none';
//     document.getElementById('confirmation-msg').style.display = 'block';
//   }

//   function confirmNo() {
//     const msg = document.getElementById('guestMessage').value;
//     document.getElementById('message-section').style.display = 'none';
//     document.getElementById('confirmation-msg').style.display = 'block';
//   }

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
    .catch(()=>showMessage("Erreur serveur","danger"));
}

const scanner = new Html5QrcodeScanner(
    "reader",
    { fps:10, qrbox:250}
);

scanner.render(onScanSuccess);
