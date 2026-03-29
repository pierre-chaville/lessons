# Guide Utilisateur

## Objectif de l'application

Cette application est un outil de gestion et de traitement de sessions audio (cours, conférences, etc.). Elle permet de :

- **Téléverser** des fichiers audio de sessions
- **Transcrire** automatiquement l'audio en texte grâce à l'IA
- **Corriger** la transcription à l'aide de modèles de langage (LLM)
- **Rédiger** une version rédigée et structurée de la transcription
- **Extraire** les sources et références citées dans le texte
- **Vérifier** les sources en les confrontant à des bases de données de textes (Sefaria)
- **Résumer** le contenu de chaque session
- **Rechercher** dans l'ensemble des transcriptions

L'application est conçue pour faciliter le travail d'étude et de diffusion de cours, en automatisant les tâches fastidieuses de transcription, mise en forme et vérification des sources.

---

## Ergonomie et paramètres d'interface

![Page d'acceuil](./images/home.png)

### Langue de l'interface

![Page d'acceuil](./images/language.png)

L'application est disponible en **français** et en **anglais**. Pour changer la langue :

1. En haut à droite de la page, cliquez sur le sélecteur de langue (icône de globe)
2. Choisissez **English** ou **Français**

Le changement est immédiat et s'applique à toute l'interface.

### Mode sombre / mode clair

L'application prend en charge un **mode sombre** et un **mode clair**. Pour basculer :

1. En haut à droite de la page, cliquez sur l'icône de soleil (☀️) ou de lune (🌙)
2. Le mode est mémorisé dans votre navigateur pour les prochaines visites

Par défaut, l'application respecte les préférences système de votre navigateur.

---

## Concepts clés

### Sessions (Lessons)

Une **session** est l'unité principale de l'application. Elle représente un enregistrement audio d'un cours ou d'une conférence. Chaque session comporte :

- Un **titre**
- Une **date**
- Un **fichier audio**
- Une **durée** (calculée automatiquement)
- Un **cours** associé (optionnel)
- Un ou plusieurs **thèmes** (optionnels)
- Un **résumé bref** (optionnel, saisi manuellement)
- Un **statut** de workflow (voir ci-dessous)
- Des **éditeurs** assignés (optionnels)

Au fil du traitement, une session peut contenir :

- La **transcription brute** (résultat de la reconnaissance vocale)
- La **transcription corrigée** (après correction par IA)
- La **version rédigée** (réécriture structurée du cours)
- Les **sources** extraites et vérifiées
- Un **résumé** détaillé généré par IA

### Statut d'une session

Chaque session dispose d'un **statut de workflow** qui permet de suivre son avancement éditorial :

| Statut | Description |
|---|---|
| **Brouillon** | Session nouvellement créée, pas encore en cours de traitement |
| **En cours** | Session en cours de travail par un éditeur |
| **Relecture demandée** | L'éditeur a terminé et demande une relecture |
| **Révision demandée** | Le relecteur demande des corrections supplémentaires |
| **Validée** | Session validée et prête à la publication |

Les transitions de statut sont contrôlées par les rôles :

- **Éditeur / Admin** : Brouillon → En cours, En cours → Relecture demandée, Révision demandée → En cours
- **Éditeur en chef / Admin** : Relecture demandée → Validée, Relecture demandée → Révision demandée
- **Admin uniquement** : Validée → En cours (réouverture)

### Éditeurs assignés

Chaque session peut avoir un ou plusieurs **éditeurs assignés**. Un éditeur ayant le rôle « Éditeur » ne peut modifier que les sessions auxquelles il est explicitement assigné. Les rôles « Éditeur en chef » et « Admin » peuvent modifier n'importe quelle session.

### Parcours (Courses)

Un **parcours** est un regroupement hiérarchique de sessions. Les parcours sont organisés en **arborescence** : chaque parcours peut avoir un parcours parent, permettant de créer des structures imbriquées (par exemple : Talmud > Berakhot > Chapitre 1).

- Chaque session peut être rattachée à un seul parcours
- Les parcours permettent de filtrer les sessions sur la page d'accueil via l'arborescence
- L'ordre d'affichage des parcours est personnalisable via des boutons de déplacement haut/bas

### Thèmes (Themes)

Un **thème** est une étiquette transversale. Par exemple : « Éthique », « Halakha », « Pensée juive », etc.

- Chaque session peut être rattachée à plusieurs thèmes
- Les thèmes permettent également de filtrer les sessions

---

## Navigation

Le menu de navigation se trouve dans le panneau latéral gauche. Il peut être réduit en cliquant sur la flèche de réduction.

![Page d'acceuil](./images/menu.png)

Les sections disponibles sont :

| Section | Description | Rôles requis |
|---|---|---|
| **Sessions** | Page d'accueil avec arborescence des parcours et liste des sessions | Tous |
| **Rechercher** | Recherche plein texte dans les transcriptions | Tous |
| **Parcours** | Gestion de l'arborescence des parcours | Tous (lecture), Éditeur en chef/Admin (modification) |
| **Thèmes** | Gestion des thèmes | Tous (lecture), Éditeur en chef/Admin (modification) |
| **Traitement** | Suivi des tâches en cours | Éditeur, Éditeur en chef, Admin |
| **Utilisateurs** | Gestion des utilisateurs | Éditeur en chef, Admin |
| **Préférences** | Configuration de l'application | Éditeur en chef, Admin |

---

## Page d'accueil — Sessions

La page d'accueil affiche les sessions dans un **agencement à deux panneaux** :

### Panneau gauche — Arborescence des parcours

Le panneau gauche affiche l'arborescence complète des parcours, avec pour chaque nœud :

- Une **icône de dossier** (ouvert/fermé) pour les parcours ayant des sous-parcours, ou une icône de document pour les parcours feuilles
- Le **nombre total de sessions** (incluant les sous-parcours) affiché dans un badge à droite
- Un bouton **chevron** pour déplier/replier les sous-parcours

En haut de l'arborescence, l'entrée **« Toutes les sessions »** permet d'afficher l'ensemble des sessions sans filtre.

Cliquez sur un parcours pour filtrer la liste des sessions à droite : seules les sessions appartenant à ce parcours ou à ses sous-parcours sont affichées. Cliquez à nouveau pour désélectionner.

### Panneau droit — Liste des sessions

Les sessions sont affichées sous forme de **cartes** dans une grille responsive. Chaque carte affiche :

- Le **titre** de la session
- La **date** et la **durée**
- Le **résumé bref** (si saisi)
- Le **statut** de workflow (badge coloré : gris pour Brouillon, bleu pour En cours, ambre pour Relecture demandée, orange pour Révision demandée, vert pour Validée)
- Les **éditeurs assignés** (affichés par nom, uniquement si le statut n'est pas « Validée »)
- Le **parcours** associé (badge gris)
- Les **thèmes** associés (badges indigo)

### Tri des sessions

Un bouton de tri en haut à droite du panneau permet de changer l'ordre d'affichage :

- **Plus récent** : tri par date décroissante (par défaut)
- **Plus ancien** : tri par date croissante
- **Par nom** : tri alphabétique par titre
- **Par statut** : tri par progression du statut (Brouillon → En cours → … → Validée)

---

## Créer une session

![Page d'acceuil](./images/new_session.png)

1. Dans la section **Sessions**, cliquez sur le bouton **Nouvelle Session**
2. Une fenêtre modale s'ouvre avec les champs suivants :
   - **Fichier Audio** : cliquez ou glissez-déposez un fichier audio (MP3, WAV, etc.)
   - **Titre** : le titre de la session (pré-rempli automatiquement à partir du nom du fichier si possible)
   - **Date** : la date du cours (pré-remplie à partir du nom du fichier si le format est reconnu)
   - **Cours** : sélectionnez un cours existant (optionnel)
   - **Thèmes** : sélectionnez un ou plusieurs thèmes (optionnel)
   - **Éditeurs** : assignez un ou plusieurs éditeurs à la session (optionnel)
3. Cliquez sur **Créer**

La session est créée et une tâche de **transcription** est automatiquement lancée.

---

## Pipeline de traitement

Le traitement d'une session se fait par étapes successives. Chaque étape est une **tâche** qui peut être lancée manuellement depuis la page de détail d'une session.

### Progression du pipeline

La page de détail d'une session affiche une **barre de progression** visuelle montrant l'avancement du pipeline de traitement : Transcription → Correction → Rédaction → Extraction → Vérification → Résumé. Chaque étape est représentée par un indicateur coloré (vert si terminée, bleu si en cours, gris si non démarrée).

### Lancer les tâches

![Page d'acceuil](./images/tasks.png)

1. Ouvrez une session en cliquant dessus dans la liste
2. Cliquez sur le bouton **Lancer les tâches** (icône d'engrenage)
3. Sélectionnez les étapes souhaitées :

#### 1. Transcrire

Convertit le fichier audio en texte brut à l'aide d'un moteur de reconnaissance vocale (Whisper/Deepgram).

**Résultat** : La transcription apparaît dans l'onglet **Transcription**, découpée en segments horodatés.

#### 2. Corriger

Utilise un modèle de langage (LLM) pour corriger les erreurs de transcription : noms propres, termes techniques, ponctuation, etc.

Lors du lancement, vous pouvez **choisir un prompt de correction** parmi ceux définis dans les préférences (voir section Préférences).

**Résultat** : Les segments corrigés remplacent les segments originaux dans l'onglet **Transcription**. Les différences entre l'original et le corrigé sont mises en évidence en vert.

#### 3. Rédiger

Réécrit la transcription corrigée sous forme d'un texte rédigé et structuré, avec des paragraphes, des indications de timing et un style écrit.

Lors du lancement, vous pouvez **choisir un prompt de rédaction** parmi ceux définis dans les préférences.

**Résultat** : Le texte rédigé apparaît dans l'onglet **Version rédigée**.

#### 4. Extraire les sources

Analyse le texte rédigé pour identifier les sources et références citées (Tanakh, Mishnah, Talmud, Midrash, etc.).

Lors du lancement, vous pouvez **choisir un prompt d'extraction** parmi ceux définis dans les préférences.

**Résultat** : Les sources extraites sont listées dans l'onglet **Sources**, classées par type.

#### 5. Vérifier les sources

Confronte chaque source extraite à la base de données Sefaria pour vérifier la référence, récupérer le texte original en hébreu et sa traduction, et évaluer la correspondance avec le texte cité.

Lors du lancement, vous pouvez **choisir un prompt de vérification** parmi ceux définis dans les préférences.

**Résultat** : Chaque source dans l'onglet **Sources** est enrichie de son statut de vérification et du texte retrouvé.

#### 6. Résumer

Génère un résumé détaillé du cours à partir du texte rédigé, selon un modèle de prompt configurable.

Lors du lancement, vous pouvez **choisir un prompt de résumé** parmi ceux définis dans les préférences.

**Résultat** : Le résumé apparaît dans l'onglet **Résumé**, formaté en Markdown.

### Ordre des étapes

Les étapes sont dépendantes les unes des autres :

```
Transcrire → Corriger → Rédiger → Extraire les sources → Vérifier les sources
                                 → Résumer
```

L'interface désactive automatiquement les étapes dont les prérequis ne sont pas remplis. Vous pouvez aussi cliquer sur **Sélectionner les étapes restantes** pour sélectionner toutes les étapes non encore effectuées.

### Suivi du traitement

Pendant le traitement, un bandeau indique l'étape en cours. Les modifications de la session sont désactivées tant que le traitement n'est pas terminé.

![Page d'acceuil](./images/in_progress.png)

Vous pouvez consulter l'historique de toutes les tâches dans la section **Traitement** du menu principal.

![Page d'acceuil](./images/tasks_list.png)

---

## Consultation d'une session

La page de détail d'une session s'organise en onglets, affichés en fonction des données disponibles :

### Informations générales

En haut de la page de détail, sont affichés :

- Le **titre**, la **date**, la **durée**, le **nom de fichier**
- La **progression du pipeline** (indicateurs visuels des étapes terminées/en cours)
- Le **statut** actuel avec les transitions possibles selon votre rôle
- Les **éditeurs** assignés (avec possibilité de les modifier en mode édition)

### Onglet Résumé

- Affiche le résumé du cours en Markdown
- Possibilité de **modifier** le résumé (bouton crayon)
- Possibilité de **télécharger en PDF**

![Page d'acceuil](./images/summary.png)

### Onglet Version rédigée

- Affiche le texte rédigé, découpé en paragraphes horodatés
- Chaque paragraphe peut être :
  - **Écouté** : cliquez sur le bouton lecture (▶) pour écouter l'audio correspondant
  - **Modifié** : cliquez sur le bouton crayon pour éditer le texte du paragraphe
- Les sources référencées dans chaque paragraphe sont affichées sous forme de badges cliquables
- En cliquant sur une source, une fenêtre modale affiche les détails de la source et le texte retrouvé sur Sefaria (en hébreu, anglais, ou les deux)
- Option **Afficher la transcription** : affiche la transcription originale en parallèle pour comparaison
- **Défilement automatique** : lorsque l'audio est en lecture, le paragraphe actif défile automatiquement à l'écran
- **Barre de lecture** : lorsque l'audio est en cours, une barre collante en haut affiche le temps, et les boutons pause et stop

![Page d'acceuil](./images/edited.png)

En cliquant sur le bouton Afficher la transcription:

![Page d'acceuil](./images/edited_show_transcript.png)

Les sources sont affichées en dessous du paragraphe correspondant:

![Page d'acceuil](./images/edited_show_sources.png)

### Onglet Sources

- Liste toutes les sources extraites, regroupées par type (Tanakh, Talmud, Mishnah, etc.)
- Chaque source affiche : la référence, le texte cité, le statut de vérification

![Page d'acceuil](./images/sources.png)

- Cliquez sur une source pour afficher le texte complet depuis Sefaria

![Page d'acceuil](./images/sources_detail.png)

![Page d'acceuil](./images/sources_sefaria.png)

- **Statistiques** : bouton pour afficher les statistiques de vérification des sources

![Page d'acceuil](./images/stats.png)

- **Téléchargement PDF** :
  - PDF des sources
  - PDF de la revue détaillée des sources

### Onglet Transcription

![Page d'acceuil](./images/transcript.png)

- Affiche la transcription segment par segment avec les horodatages
- Chaque segment peut être :
  - **Écouté** : cliquez sur le bouton lecture (▶)
  - **Modifié** : cliquez sur le bouton crayon pour corriger le texte
- Les différences entre la transcription initiale et la transcription corrigée sont mises en évidence (fond vert)
- **Défilement automatique** : le segment actif défile automatiquement pendant la lecture
- **Barre de lecture** : barre collante en haut pour contrôler la lecture (pause/stop)
- Possibilité de **télécharger en PDF**

---

## Modifier les informations d'une session

1. Ouvrez la session
2. Cliquez sur le bouton **Modifier** à côté du titre
3. Vous pouvez modifier :
   - Le **titre**
   - La **date**
   - Le **cours** associé
   - Les **thèmes**
   - Les **éditeurs** assignés
   - Le **résumé bref**
4. Cliquez sur **Enregistrer**

![Page d'acceuil](./images/modify.png)

---

## Gérer les parcours

Dans la section **Parcours** :

Les parcours sont affichés sous forme d'**arborescence repliable**, identique à celle de la page d'accueil. Chaque parcours affiche le nombre total de sessions (y compris celles des sous-parcours).

- **Créer un parcours** : cliquez sur **Nouveau Cours**, saisissez un nom, une description optionnelle et un parcours parent (ou laissez à « Aucun (racine) » pour un parcours de premier niveau)
- **Modifier un parcours** : survolez le parcours et cliquez sur le bouton crayon. Vous pouvez modifier le nom, la description et le parcours parent
- **Supprimer un parcours** : survolez le parcours et cliquez sur le bouton de suppression. Les sous-parcours sont automatiquement rattachés au parcours parent du parcours supprimé. Les sessions associées sont désassignées
- **Réordonner les parcours** : survolez un parcours et utilisez les flèches **haut** (▲) et **bas** (▼) pour le déplacer par rapport à ses voisins au même niveau. L'ordre est mémorisé

![Page d'acceuil](./images/courses.png)

---

## Gérer les thèmes

Dans la section **Thèmes** :

- **Créer un thème** : cliquez sur **Nouveau Thème** et saisissez un nom
- **Modifier un thème** : cliquez sur le bouton crayon
- **Supprimer un thème** : cliquez sur le bouton de suppression (les sessions associées perdront ce thème)

![Page d'acceuil](./images/themes.png)

---

## Rechercher dans les sessions

La section **Rechercher** permet de faire une recherche plein texte dans les transcriptions corrigées :

1. Saisissez votre requête dans le champ de recherche
2. Utilisez les filtres optionnels par **cours** et **thème**
3. Les résultats affichent les sessions correspondantes avec les extraits pertinents et les horodatages
4. Cliquez sur un résultat pour ouvrir la session
5. Cliquez sur le bouton lecture (▶) à côté d'un extrait pour écouter directement le passage correspondant

*ATTENTION: Cette partie est uniquement en phase prototype*

![Page d'acceuil](./images/search.png)

---

## Gestion des utilisateurs

La section **Utilisateurs** (accessible aux rôles Éditeur en chef et Admin) permet de :

- **Voir** la liste de tous les utilisateurs et leurs rôles
- **Inviter un utilisateur** : envoyer un email d'invitation
- **Créer un utilisateur** : créer un compte directement avec un mot de passe
- **Modifier le rôle** d'un utilisateur
- **Supprimer un utilisateur**

![Page d'acceuil](./images/users.png)

### Rôles disponibles

| Rôle | Description |
|---|---|
| **Lecteur** | Peut consulter les sessions, parcours, thèmes et sources |
| **Éditeur** | Peut modifier les sessions auxquelles il est assigné comme éditeur (transcription, texte rédigé, résumé), lancer des tâches sur ces sessions et changer le statut |
| **Éditeur en chef** | Peut créer/supprimer des sessions, parcours, thèmes, gérer les tâches et les utilisateurs. Peut valider ou demander des révisions |
| **Admin** | Accès complet à toutes les fonctionnalités et la configuration, y compris la réouverture de sessions validées |

> **Note** : Un Éditeur en chef ne peut pas attribuer le rôle Admin, ni modifier les utilisateurs ayant le rôle Admin.

![Page d'acceuil](./images/new_user.png)

---

## Préférences

La section **Préférences** (accessible aux rôles Éditeur en chef en lecture, Admin en modification) permet de configurer :

### Transcription

- Taille du modèle Whisper
- Périphérique (CPU/GPU)
- Type de calcul
- Langue de transcription
- Prompt initial pour guider la transcription

### Correction

- Fournisseur LLM (OpenAI / Anthropic)
- Modèle à utiliser
- Température
- Tokens max
- **Prompts de correction multiples** : définissez plusieurs prompts nommés (par exemple : « Standard », « Halakha », « Moussar »). Lors du lancement d'une tâche de correction, le prompt à utiliser peut être sélectionné dans la modale de lancement

### Rédaction

- Fournisseur LLM
- Modèle à utiliser
- Température
- Tokens max
- **Prompts de rédaction multiples** : définissez plusieurs prompts nommés pour différents styles de rédaction. Le prompt est sélectionnable au lancement de la tâche

### Sources

- **Extraction des sources** :
  - Fournisseur LLM, modèle, température, tokens max
  - **Prompts d'extraction multiples** : plusieurs prompts nommés pour l'extraction de sources
- **Vérification des sources** :
  - Fournisseur LLM, modèle, température, tokens max
  - **Prompts de vérification multiples** : plusieurs prompts nommés pour la vérification
- Référentiel des types de sources (Tanakh, Mishnah, Talmud, etc.)

### Résumé

- Fournisseur LLM
- Modèle à utiliser
- **Prompts de résumé multiples** : définissez plusieurs prompts nommés (permettant différents styles de résumé). Le prompt est sélectionnable au lancement de la tâche
- Longueur maximale

---

## Raccourcis et astuces

- **Entrée** dans le champ de recherche lance la recherche
- Le **glisser-déposer** fonctionne pour le téléversement de fichiers audio
- Les **PDF** peuvent être générés pour le résumé, la transcription, la version rédigée et les sources
- Le **panneau latéral** peut être réduit pour gagner de l'espace
- L'**arborescence des parcours** sur la page d'accueil permet de naviguer rapidement dans les sessions par parcours
- Les **flèches haut/bas** dans la gestion des parcours permettent de personnaliser l'ordre d'affichage
- La **barre de lecture collante** en haut des onglets Transcription et Version rédigée permet de contrôler facilement la lecture audio (pause/stop) sans avoir à défiler
- Le **défilement automatique** suit le paragraphe ou segment en cours de lecture
