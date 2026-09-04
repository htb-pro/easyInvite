import random
from locust import HttpUser, task, between

class QRScannerUser(HttpUser):
    # Temps d'attente entre deux scans par un utilisateur (entre 1 et 3 secondes)
    wait_time = between(1, 3)

    # Données de test (Remplacez par des données valides de votre base si nécessaire)
    TICKET_IDS = ["8b0c-ticket-1", "9c1d-ticket-2", "10e2-ticket-3"]
    GUEST_URLS = [
        "http://localhost:8000/invite/941b984a-443d-4d53-9c87-e36ae0e9c226/4928aecb-2dd5-44b7-91f6-6808cd570524/create",
        "http://localhost:8000/invite/941b984a-443d-4d53-9c87-e36ae0e9c226/0f41b195-bb0c-45a8-aea8-ad3889aa7a77/create",
        #"https://app.easyevent-rdc.com/invite/event123/guest003/create",
    ]

    @task(3)
    def test_scan_billet_payant(self):
        """Simule le scan d'un billet payant (TOTP) avec préfixe EI~"""
        ticket_id = random.choice(self.TICKET_IDS)
        fake_token = "123456"  # Token TOTP fictif ou réel
        qr_data = f"EI~{ticket_id}~{fake_token}"

        # Envoi de la requête GET sur l'endpoint
        self.client.get(
            f"/scan-ticket-secure?qr_data={qr_data}",
            name="/scan-ticket-secure [Billet EI~]"
        )

    @task(3)
    def test_scan_invitation(self):
        """Simule le scan d'une invitation via URL"""
        qr_data = random.choice(self.GUEST_URLS)

        self.client.get(
            f"/scan-ticket-secure?qr_data={qr_data}",
            name="/scan-ticket-secure [Invitation URL]"
        )

    @task(1)
    def test_scan_invalide(self):
        """Simule un scan avec un format corrompu ou inconnu"""
        qr_data = "CODE_INVALID_123456"

        self.client.get(
            f"/scan-ticket-secure?qr_data={qr_data}",
            name="/scan-ticket-secure [Format Invalide]"
        )