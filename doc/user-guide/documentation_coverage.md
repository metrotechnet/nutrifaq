# Couverture de documentation — NutriFAQ-Chat

| Fonctionnalité identifiée | Fichier/composant source | Section du guide | État de documentation | Capture d’écran nécessaire |
|---|---|---|---|---|
| Connexion locale (courriel/mot de passe) | `templates/login.html`, `static/js/login-page.js` | 2. Premiers pas | Documenté | Oui |
| Changement de mot de passe à la première connexion | `static/js/login-page.js`, `api/routes/users.py` | 2.2, 5.2 | Documenté | Oui |
| Redirection si session invalide | `templates/index.html`, `static/js/login-page.js`, `static/js/users-page.js` | 6.1 | Documenté | Non |
| Navigation latérale (Instructions / Indexer / Valider / Publier) | `templates/index.html`, `static/js/download-manager.js` | 2.4 | Documenté | Oui |
| Sélection de langue | `templates/index.html`, `static/js/config.js`, `static/locales/fr.json` | 5.1 | Documenté | Oui |
| Sélection du modèle IA | `templates/index.html`, `static/js/main.js`, `api/routes/config.py` | 5.1, 3.6 | Documenté | Oui |
| Téléversement fichiers (drag-and-drop + bouton) | `templates/index.html`, `static/js/download-manager.js`, `api/routes/blob.py` | 3.1 | Documenté | Oui |
| Chargement de la liste des fichiers | `static/js/download-manager.js`, `api/routes/blob.py` | 3.1 | Documenté | Oui |
| Recherche/filtrage des fichiers | `templates/index.html`, `static/js/download-manager.js` | 3.1 | Documenté | Oui |
| Téléchargement fichier unique | `static/js/download-manager.js`, `api/routes/blob.py` | 3.1 | Documenté | Oui |
| Téléchargement multi-fichiers ZIP | `static/js/download-manager.js`, `api/routes/blob.py` | 3.1 | Documenté | Oui |
| Suppression fichier unique | `static/js/download-manager.js`, `api/routes/blob.py` | 3.1 | Documenté | Oui |
| Suppression multi-sélection | `static/js/download-manager.js` | 3.1 | Documenté | Oui |
| Spinner central lors des actions d’indexation (load/download/delete/upload lot) | `templates/index.html`, `static/js/download-manager.js` | 3.1 | Documenté | Oui |
| Démarrage de l’indexation | `templates/index.html`, `static/js/download-manager.js`, `api/routes/indexing.py` | 3.2 | Documenté | Oui |
| Annulation de l’indexation | `templates/index.html`, `static/js/download-manager.js`, `api/routes/indexing.py` | 3.2 | Documenté | Oui |
| Barre de progression d’indexation | `templates/index.html`, `static/js/download-manager.js`, `api/routes/indexing.py` | 3.2 | Documenté | Oui |
| Questions suggérées | `templates/index.html`, `static/js/chat.js`, `api/routes/query.py` (`/api/generated-questions`) | 3.3 | Documenté | Oui |
| Envoi de question / réponse en flux | `static/js/chat.js`, `api/routes/query.py` | 3.3 | Documenté | Oui |
| Vote Like/Dislike | `static/js/chat.js`, `api/routes/report.py` (`/api/like_answer`) | 3.4 | Documenté | Oui |
| Commentaire sur réponse | `static/js/chat.js`, `api/routes/report.py` (`/api/add_comment`) | 3.4 | Documenté | Oui |
| Lecture audio TTS d’une réponse | `static/js/tts.js`, `api/routes/tts.py` | 3.5 | Documenté | Oui |
| Publication immédiate | `templates/index.html`, `static/js/download-manager.js`, `api/routes/publish.py` | 3.6 | Documenté | Oui |
| Planification de publication (immédiat/once/daily/weekly) | `templates/index.html`, `static/js/download-manager.js`, `api/routes/publish.py` | 3.7 | Documenté | Oui |
| Annulation d’une planification active | `static/js/download-manager.js`, `api/routes/publish.py` | 3.7 | Documenté | Oui |
| Historique d’activité — onglet Conversations | `templates/index.html`, `static/js/download-manager.js`, `api/routes/report.py` (`/api/download_log`) | 3.8 | Documenté | Oui |
| Historique d’activité — onglet Publications | `templates/index.html`, `static/js/download-manager.js`, `api/routes/publish.py` (`/api/publish/log`) | 3.8 | Documenté | Oui |
| Export PDF de l’historique | `static/js/download-manager.js` | 3.8 | Documenté | Oui |
| Réinitialisation du journal des questions | `static/js/download-manager.js`, `api/routes/report.py` (`/api/reset_question_log`) | 3.8 | Documenté | Oui |
| Gestion des utilisateurs (accès admin) | `templates/users.html`, `static/js/users-page.js`, `api/routes/users.py` | 3.9, 5.3 | Documenté | Oui |
| Création d’utilisateur + mot de passe temporaire | `static/js/users-page.js`, `api/routes/users.py` | 3.9, 4.3 | Documenté | Oui |
| Changement de rôle utilisateur | `static/js/users-page.js`, `api/routes/users.py` | 3.9 | Documenté | Oui |
| Forcer réinitialisation mot de passe d’un utilisateur | `static/js/users-page.js`, `api/routes/users.py` | 3.9 | Documenté | Oui |
| Suppression utilisateur (avec interdiction auto-suppression) | `static/js/users-page.js`, `api/routes/users.py` | 3.9, 6.1 | Documenté | Oui |
| Journal de logs (viewer) | `templates/log_report.html`, `api/routes/report.py`, `static/js/azure-auth.js` | 3.10 | Documenté | Oui |
| Bouton Réinitialiser du journal de publication (API existe, action UI non branchée pour onglet Publications) | `api/routes/publish.py`, `static/js/download-manager.js` | Mentionné implicitement (limitation) | Partiellement documenté (comportement réel conservé) | Non |
| Fonctions de traduction (`/api/translate`, `/api/translate_audio`) | `api/routes/translation.py`, `static/js/agents.js` | Non incluses (pas d’entrée UI visible confirmée) | Explicitement exclu (non confirmé côté interface actuelle) | Non |

