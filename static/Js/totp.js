// --- CONVERTISSEUR BASE32 VERS TABLEAU D'OCTETS (STANDARD RFC 4648) ---
function base32ToUint8Array(base32) {
    let alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    let sb32 = base32.toUpperCase().replace(/=+$/, "").replace(/\s/g, "");
    let len = sb32.length;
    let length = Math.floor(len * 5 / 8);
    let view = new Uint8Array(length);
    let bits = 0;
    let value = 0;
    let index = 0;

    for (let i = 0; i < len; i++) {
        let val = alphabet.indexOf(sb32.charAt(i));
        if (val === -1) continue;
        value = (value << 5) | val;
        bits += 5;
        if (bits >= 8) {
            bits -= 8;
            view[index++] = (value >> bits) & 255;
        }
    }
    return view;
}

// --- ALGORITHME TOTP SÉCURISÉ ET COMPATIBLE PYTHON (WEB CRYPTO API) ---
async function generateTOTP(secret) {
    try {
        if (!secret) return "000000";

        let keyBytes = base32ToUint8Array(secret);
        let epoch = Math.floor(Date.now() / 1000);
        let counter = Math.floor(epoch / 30);
        
        // Préparation du compteur sur 8 octets (64-bit integer) sans perte de précision JS
        let counterBytes = new Uint8Array(8);
        for (let i = 7; i >= 0; i--) {
            counterBytes[i] = counter & 0xff;
            counter = Math.floor(counter / 256);
        }

        let cryptoKey = await window.crypto.subtle.importKey(
            "raw", keyBytes, { name: "HMAC", hash: { name: "SHA-1" } }, false, ["sign"]
        );
        
        let signature = await window.crypto.subtle.sign("HMAC", cryptoKey, counterBytes);
        let hmac = new Uint8Array(signature);
        
        let offset = hmac[hmac.length - 1] & 0x0f;
        let binary = ((hmac[offset] & 0x7f) << 24) |
                     ((hmac[offset + 1] & 0xff) << 16) |
                     ((hmac[offset + 2] & 0xff) << 8) |
                     (hmac[offset + 3] & 0xff);

        return (binary % 1000000).toString().padStart(6, "0");
    } catch (e) {
        console.error("Erreur TOTP:", e);
        return "000000";
    }
}

document.addEventListener("DOMContentLoaded", function() {
    const ticketElement = document.getElementById("ticket-data");
    
    // 1. Déclaration en dehors du bloc pour assurer la portée globale
    let ticketId = "";
    let ticketSecret = "";

    if (ticketElement) {
        ticketId = ticketElement.dataset.ticketId || "";
        const rawSecret = ticketElement.dataset.ticketSecret || "";

        ticketSecret = rawSecret
            .toUpperCase()
            .trim()
            .replace(/0/g, 'O')
            .replace(/1/g, 'I');


    }

    const qrcodeElement = document.getElementById("qrcode-container");
    if (!qrcodeElement) return;

    const qr = new QRCode(qrcodeElement, {
        width: 200,
        height: 200,
        correctLevel: QRCode.CorrectLevel.M,
        colorDark : "#FFFFFF",
        colorLight : "#000000"
    });

    async function mettreAJourQRCode() {
        // Génération du token TOTP
        const token = await generateTOTP(ticketSecret);
        
        const maintenant = Math.floor(Date.now() / 1000);
        const secondesRestantes = 30 - (maintenant % 30);
        const dataString = `EI~${ticketId}~${token}`;

        qr.clear();
        qr.makeCode(dataString);

        const timerBar = document.getElementById("timer-bar");
        if (timerBar) {
            timerBar.style.width = (secondesRestantes / 30) * 100 + "%";
        }
    }

    mettreAJourQRCode();
    setInterval(mettreAJourQRCode, 1000);
});