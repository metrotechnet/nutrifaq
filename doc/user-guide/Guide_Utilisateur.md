# NutriFAQ-Chat — Guide de l'utilisateur

**Version du document :** 1.0  
**Date de génération :** 2026-11-03  
**Entreprise :** IMX Technologie inc.

---

## 1. Introduction

NutriFAQ-Chat est une application web qui permet de :

- gérer les fichiers de connaissances (section **Indexer**);
- lancer l’indexation de la base documentaire;
- valider la qualité des réponses dans la section **Valider**;
- publier une version mise à jour (section **Publier**);
- suivre l’historique des conversations et des publications;
- administrer les utilisateurs (pour les administrateurs).

Ce guide s’adresse aux utilisateurs opérationnels et administrateurs.

---

## 2. Premiers pas

### 2.1 Accéder à l’application

1. Ouvrez la page de connexion (`/login.html`).
2. Entrez votre **Courriel** et votre **Mot de passe**.
3. Cliquez sur **Se connecter**.

> [Capture d'écran à insérer : page Connexion avec champs Courriel, Mot de passe et bouton Se connecter]

### 2.2 Changement du mot de passe à la première connexion

Si votre compte a été créé ou réinitialisé par un administrateur, une fenêtre vous demandera :

1. votre **mot de passe temporaire**;
2. un **nouveau mot de passe**;
3. la **confirmation** du nouveau mot de passe.

Le nouveau mot de passe doit contenir au moins 8 caractères.

> [Capture d'écran à insérer : fenêtre « Changer votre mot de passe » avec 3 champs]

### 2.3 Déconnexion

1. Ouvrez le **Menu du compte** (en bas de la barre latérale).
2. Cliquez sur **Déconnecter**.

### 2.4 Navigation principale

La barre latérale donne accès à :

- **Instructions**
- **Indexer**
- **Valider**
- **Publier**

Et dans le menu du compte :

- **Gérer les utilisateurs** (admin seulement)
- **Journal de logs** (admin)
- **Déconnecter**

---

## 3. Utilisation des fonctionnalités

### 3.1 Section Indexer — téléversement et gestion des fichiers

**Description**  
Permet d’ajouter, consulter, rechercher, télécharger et supprimer des fichiers utilisés pour l’indexation.

**Quand l’utiliser**  
Avant une nouvelle indexation ou pour mettre à jour les documents.

**Procédure**

1. Ouvrez **Indexer**.
2. Ajoutez vos fichiers :
   1. glisser-déposer dans la zone prévue, ou
   2. cliquer sur **Choisir un fichier**.
3. Vérifiez la table **Fichiers** :
   - nom,
   - taille,
   - date de modification.
4. Utilisez la recherche pour filtrer la liste.
5. Au besoin :
   - téléchargez un fichier;
   - sélectionnez plusieurs fichiers et téléchargez en ZIP;
   - supprimez un fichier;
   - supprimez une sélection.

**Résultat attendu**

- un message de succès indique le nombre de fichiers téléversés;
- la table se met à jour;
- un indicateur de chargement central apparaît pendant les opérations longues.

**Conseils pratiques**

- validez le nom des fichiers avant l’envoi;
- pour les envois multiples, attendez le message final de lot.

> [Capture d'écran à insérer : section Indexer avec zone de glisser-déposer, table Fichiers et actions Télécharger/Supprimer]

### 3.2 Lancer une indexation

**Description**  
Démarre la pipeline d’indexation de la base documentaire.

**Quand l’utiliser**  
Après ajout/modification/suppression de documents.

**Procédure**

1. Dans **Indexer**, cliquez **Démarrer un indexage**.
2. Confirmez l’action.
3. Suivez la barre de progression.
4. Si nécessaire, cliquez **Annuler**.

**Résultat attendu**

- l’état passe à *Indexation en cours*;
- la progression (%) est mise à jour;
- un message final indique la fin ou l’annulation.

> [Capture d'écran à insérer : barre de progression d’indexation avec bouton Annuler]

### 3.3 Section Valider — poser des questions

**Description**  
Permet de tester les réponses générées à partir de la base indexée.

**Quand l’utiliser**  
Après une indexation, avant publication.

**Procédure**

1. Ouvrez **Valider**.
2. Entrez une question dans la zone de texte.
3. Cliquez sur l’icône **Envoyer**.
4. Attendez la réponse en flux continu.
5. (Optionnel) Utilisez les **Questions suggérées**.

**Résultat attendu**

- la réponse s’affiche progressivement;
- les actions de rétroaction (vote/commentaire) deviennent disponibles à la fin.

> [Capture d'écran à insérer : section Valider avec zone de saisie, réponse et panneau Questions suggérées]

### 3.4 Rétroaction sur les réponses (vote/commentaire)

**Description**  
Permet de qualifier une réponse et d’ajouter un commentaire.

**Quand l’utiliser**  
Pendant la validation qualité des réponses.

**Procédure**

1. Après une réponse, cliquez **Like** ou **Dislike**.
2. Cliquez sur l’icône de commentaire pour ouvrir la fenêtre de saisie.
3. Entrez le commentaire et enregistrez.

**Résultat attendu**

- la rétroaction est enregistrée dans les journaux de conversations.

### 3.5 Lecture audio (TTS) d’une réponse

**Description**  
Permet de faire lire la réponse par synthèse vocale.

**Quand l’utiliser**  
Pour validation orale ou accessibilité.

**Procédure**

1. Sur une réponse affichée, cliquez l’icône audio.
2. Cliquez de nouveau pour arrêter la lecture.

**Résultat attendu**

- le texte est envoyé au service TTS;
- la lecture audio démarre dans le navigateur.

### 3.6 Section Publier — publication immédiate

**Description**  
Permet de publier la base validée.

**Quand l’utiliser**  
Quand les tests en section **Valider** sont satisfaisants.

**Procédure**

1. Ouvrez **Publier**.
2. Vérifiez le **Modèle IA** dans la barre latérale.
3. Cliquez **Publier**.
4. Confirmez l’action.
5. Suivez l’état de publication.

**Résultat attendu**

- progression et messages d’état affichés;
- message final *Publication terminée* avec nombre de fichiers.

> [Capture d'écran à insérer : section Publier avec bouton Publier et état de progression]

### 3.7 Planifier une publication

**Description**  
Permet de programmer une publication immédiate, unique, quotidienne ou hebdomadaire.

**Quand l’utiliser**  
Pour automatiser les mises en production.

**Procédure**

1. Dans **Planifier la publication**, choisissez :
   - **Fréquence**;
   - **Date** (si *Une fois*);
   - **Heure**;
   - **Jour** (si *Chaque semaine*).
2. Cliquez **Publier**.
3. Confirmez.
4. Vérifiez l’entrée dans **Planifications actives**.
5. Pour annuler : cliquez **Annuler** sur la planification.

**Résultat attendu**

- la planification active est affichée avec sa prochaine exécution;
- l’annulation retire la planification active.

### 3.8 Historique d’activité (Conversations/Publications)

**Description**  
Affiche l’historique dans deux onglets :

- **Conversations**
- **Publications**

**Quand l’utiliser**  
Pour audit, suivi qualité et diagnostic.

**Procédure**

1. Ouvrez la section **Publier**.
2. Dans **Historique d’activité**, choisissez l’onglet.
3. Utilisez :
   - **Rafraîchir**
   - **Exporter** (PDF)
   - **Réinitialiser** (actif sur l’onglet Conversations)

**Résultat attendu**

- Conversations : question, réponse, vote, commentaires;
- Publications : date, fournisseur, modèle, nombre de fichiers, statut, détail d’erreur si présent.

> [Capture d'écran à insérer : onglets Conversations/Publications avec actions Rafraîchir, Réinitialiser, Exporter]

### 3.9 Gestion des utilisateurs (administrateur)

**Description**  
Permet d’administrer les comptes, rôles et réinitialisations de mot de passe.

**Quand l’utiliser**  
Pour gérer les accès applicatifs.

**Procédure**

1. Ouvrez **Menu du compte** > **Gérer les utilisateurs**.
2. Actions disponibles :
   1. **Ajouter un utilisateur** (courriel + rôle);
   2. **Modifier le rôle** (collaborateur/admin);
   3. **Forcer la réinitialisation du mot de passe**;
   4. **Supprimer l’utilisateur**.
3. Transmettez le mot de passe temporaire à l’utilisateur concerné.

**Résultat attendu**

- la liste est mise à jour;
- un message confirme chaque opération.

**Conseils pratiques**

- vous ne pouvez pas supprimer votre propre compte;
- vérifiez le rôle attribué avant de fermer la fenêtre.

> [Capture d'écran à insérer : page Gestion des utilisateurs avec table et actions]

### 3.10 Journal de logs (administrateur)

**Description**  
Affiche le journal applicatif en lecture directe.

**Quand l’utiliser**  
Pour diagnostiquer une erreur de traitement ou de publication.

**Procédure**

1. Ouvrez **Journal de logs** depuis le menu du compte.
2. Utilisez :
   - **Refresh**
   - **Auto** (rafraîchissement automatique)
   - **Clear log**
   - **Download .txt**

**Résultat attendu**

- le contenu du log s’affiche;
- le statut indique Loaded/Empty/Error selon le cas.

---

## 4. Processus de travail complets

### 4.1 Parcours standard : de l’import à la publication

1. Se connecter.
2. Ouvrir **Indexer**.
3. Téléverser les fichiers.
4. Cliquer **Démarrer un indexage** et attendre la fin.
5. Ouvrir **Valider** et tester plusieurs questions.
6. Ouvrir **Publier** et lancer la publication.
7. Vérifier **Historique d’activité > Publications**.

### 4.2 Parcours planifié : publication automatique

1. Se connecter (admin).
2. Ouvrir **Publier**.
3. Configurer fréquence/date/heure/jour.
4. Confirmer la planification.
5. Vérifier **Planifications actives**.
6. Surveiller les résultats dans l’historique des publications.

### 4.3 Parcours administratif : création d’un compte

1. Ouvrir **Gérer les utilisateurs**.
2. Ajouter un utilisateur (courriel + rôle).
3. Copier le mot de passe temporaire affiché.
4. Communiquer le mot de passe temporaire à l’utilisateur.
5. Demander à l’utilisateur de se connecter et changer son mot de passe.

---

## 5. Paramètres et gestion du compte

### 5.1 Paramètres disponibles

- **Langue** : Français / English.
- **Modèle IA** : sélection dans la barre latérale (liste chargée depuis le backend).
- **Bannière cookies** : acceptation/refus.

### 5.2 Gestion du compte

- Déconnexion via **Déconnecter**.
- Changement obligatoire du mot de passe au premier accès si requis.

### 5.3 Rôles et autorisations (résumé)

- **Collaborateur** : opérations de consultation/interaction.
- **Admin** : accès complet, y compris indexation, publication, journaux et gestion des utilisateurs.

---

## 6. Résolution des problèmes

### 6.1 Problèmes fréquents et solutions

1. **« Session expirée » / redirection vers connexion**
   - Cause possible : token expiré.
   - Solution : reconnectez-vous.

2. **Impossible d’ouvrir Gestion des utilisateurs**
   - Cause possible : rôle non administrateur.
   - Solution : demander une élévation de rôle à un administrateur.

3. **Échec de connexion**
   - Cause possible : mauvais courriel/mot de passe.
   - Solution : vérifier les identifiants; utiliser une réinitialisation de mot de passe si nécessaire.

4. **Échec de téléversement/suppression/téléchargement de fichier**
   - Cause possible : erreur serveur ou permission insuffisante.
   - Solution : rafraîchir la liste; réessayer; vérifier les droits.

5. **Indexation déjà en cours**
   - Cause possible : un autre traitement est actif.
   - Solution : attendre la fin ou utiliser **Annuler**.

6. **Publication en erreur**
   - Cause possible : problème technique pendant le traitement.
   - Solution : consulter **Historique d’activité > Publications** (colonne statut + détail d’erreur), puis le **Journal de logs**.

7. **Mot de passe temporaire refusé**
   - Cause possible : valeur erronée.
   - Solution : demander un nouveau mot de passe temporaire à un administrateur.

---

## 7. Questions fréquentes (FAQ)

**Q1. Puis-je créer mon propre compte ?**  
Non. La création de compte est une action administrateur.

**Q2. Pourquoi je dois changer mon mot de passe à la connexion ?**  
Parce que votre compte est marqué *mot de passe temporaire*.

**Q3. Où voir les erreurs de publication ?**  
Dans **Publier > Historique d’activité > Publications**, puis au besoin dans **Journal de logs**.

**Q4. Puis-je annuler une indexation ?**  
Oui, via le bouton **Annuler** pendant l’indexation.

**Q5. Puis-je exporter l’historique ?**  
Oui, bouton **Exporter** (PDF) dans l’historique d’activité.

---

## 8. Glossaire

- **Indexation** : transformation des documents en données consultables par l’IA.
- **Publication** : transfert de la base validée vers l’environnement de production.
- **Planification** : exécution automatique d’une publication selon une fréquence.
- **Mot de passe temporaire** : mot de passe initial/provisoire qui doit être changé à la connexion.
- **Historique des publications** : journal des opérations de publication, avec statut et erreurs.
- **Rôle administrateur** : rôle autorisé à gérer les utilisateurs et les opérations sensibles.

---

## Annexe — Emplacements de captures d’écran recommandés

1. Page **Connexion**.
2. Fenêtre **Changer votre mot de passe** (première connexion).
3. Vue **Indexer** (zone de dépôt + table).
4. Progression d’**indexation**.
5. Vue **Valider** (question/réponse).
6. Actions de rétroaction (like/dislike/commentaire).
7. Vue **Publier** (publication immédiate).
8. Bloc **Planifier la publication**.
9. **Historique d’activité** (onglets Conversations/Publications).
10. Page **Gestion des utilisateurs**.
11. Page **Journal de logs**.

