// Dans ton fichier JS ou balise <script>
document.addEventListener('DOMContentLoaded', () => {
    const downloadBtn = document.querySelector('.btn-gold');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
            const toastEl = document.getElementById('downloadToast');
            const toast = new bootstrap.Toast(toastEl);
            toast.show();
        });
    }
});