# Guide Utilisateur (Editeur)

## Objectif de l'application

Cette application est un outil de gestion et de traitement de sessions audio (cours, conférences, etc.). Elle permet de :

- **Téléverser** des fichiers audio de sessions
- **Transcrire** automatiquement l'audio en texte grâce à l'IA
- **Corriger** la transcription à l'aide de modèles de langage (LLM)
- **Rédiger** une version rédigée et structurée de la transcription
- **Extraire** les sources et références citées dans le texte
- **Vérifier** les sources en les confrontant à des bases de données de textes (Sefaria)
- **Résumer** le contenu de chaque session
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
| **Parcours** | Gestion de l'arborescence des parcours | Tous (lecture), Éditeur en chef/Admin (modification) |
| **Thèmes** | Gestion des thèmes | Tous (lecture), Éditeur en chef/Admin (modification) |
| **Traitement** | Suivi des tâches en cours | Éditeur, Éditeur en chef, Admin |

---

## Page d'accueil — Sessions

![Page d'acceuil](./images/home.png)

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
- L'**année hébraïque** (si disponible)
- Le **chemin de parcours complet** (ex. `Talmud / Berakhot / Chapitre 1`)
- Le **résumé bref** (si saisi)

> Le statut, les éditeurs et les thèmes ne sont pas affichés sur la carte liste (ils sont visibles dans la page de détail).

### Filtres / facettes (liste des sessions)

Au-dessus de la liste des sessions, vous disposez de filtres combinables :

- **Recherche par titre** (champ texte)
- **Année hébraïque** (multi-sélection)
- **Statut de session** (multi-sélection)
- **Thèmes** (multi-sélection)
- **Filtre de parcours** via l'arborescence de gauche (inclut les sous-parcours)
- Boutons d'effacement :
  - Effacer un filtre individuel
  - **Effacer tous les filtres**

### Tri des sessions

Un bouton de tri en haut à droite du panneau permet de changer l'ordre d'affichage :

- **Plus récent** : tri par date décroissante (par défaut)
- **Plus ancien** : tri par date croissante
- **Par nom** : tri alphabétique par titre
- **Par statut** : tri par progression du statut (Brouillon → En cours → … → Validée)

Un compteur affiche aussi le nombre de sessions actuellement visibles après filtres/tri.

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

La page de détail d'une session affiche une **barre de progression** visuelle montrant l'avancement du pipeline de traitement : Transcription → Correction → Rédaction → Extraction → Vérification → Résumé → Résumé bref. Chaque étape est représentée par un indicateur coloré (vert si terminée, bleu si en cours, gris si non démarrée).

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

#### 7. Résumé bref

Génère un résumé court à partir du résumé détaillé, avec son propre prompt et son propre preset de modèle.

**Résultat** : Le champ **Résumé bref** de la session est rempli et affiché dans les vues liste/détail.

### Ordre des étapes

Les étapes sont dépendantes les unes des autres :

```
Transcrire → Corriger → Rédiger → Extraire les sources → Vérifier les sources
                                 → Résumer → Résumé bref
```

L'interface désactive automatiquement les étapes dont les prérequis ne sont pas remplis. Vous pouvez aussi cliquer sur **Sélectionner les étapes restantes** pour sélectionner toutes les étapes non encore effectuées.

### Suivi du traitement

Pendant le traitement, un bandeau indique l'étape en cours. Les modifications de la session sont désactivées tant que le traitement n'est pas terminé.

![Page d'acceuil](./images/in_progress.png)

Vous pouvez consulter l'historique de toutes les tâches dans la section **Traitement** du menu principal.

![Page d'acceuil](./images/tasks_list.png)

---

## Consultation d'une session

La page de détail d'une session s'organise en onglets, affichés dynamiquement selon les données disponibles :

- **Résumé**
- **Version rédigée**
- **Sources**
- **Transcription**
- **Journal d'audit (workflow)** (visible pour les utilisateurs pouvant modifier la session)

Les onglets de contenu n'apparaissent que si la donnée correspondante existe.

### Informations générales

En haut de la page de détail, sont affichés :

- Le **titre**, la **date**, la **durée**, le **nom de fichier**
- Le **parcours** (chemin complet)
- Le lecteur **audio natif** du fichier source
- Les **thèmes** associés (badges)
- Le **résumé bref** (si présent)
- Le panneau **Workflow** (colonne droite) avec :
  - Les **éditeurs** assignés
  - Le **statut de session** (modifiable selon rôle)
  - Le **statut de chaque étape** du pipeline (modifiable selon rôle)
  - Le bouton **Lancer les tâches**
- Un bandeau **traitement en cours** lorsque le pipeline tourne (édition temporairement bloquée)

![Page d'acceuil](./images/session.png)

### Onglet Résumé

- Affiche le résumé du cours en Markdown
- Possibilité de **modifier** le résumé (bouton crayon)
- Possibilité d'**exporter** le résumé (Markdown, Word, PDF)
- Possibilité d'**importer** un document (Markdown/Word) pour remplacer le contenu (si vous avez les droits d'édition)
- Bouton **Historique** pour consulter, comparer et restaurer les versions du résumé
- Option **Afficher la version rédigée** pour afficher l'alignement résumé ↔ version rédigée
- Bouton **Rafraîchir l'alignement** lorsque l'alignement est obsolète
- Bouton **Historique** disponible aussi sur le **Résumé bref** (en en-tête), pour le versioning du champ bref

![Page d'acceuil](./images/summary.png)

En cliquant sur le bouton Afficher la version rédigée:

![Page d'acceuil](./images/summary_show_edited.png)


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
- Possibilité d'**exporter/importer** la version rédigée (Markdown, Word, PDF en export)
- Bouton **Historique** pour consulter, comparer et restaurer les versions de la version rédigée
- Bouton **Rafraîchir l'alignement** si la version rédigée n'est plus alignée

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
- Possibilité d'**exporter/importer** la transcription (Markdown, Word, PDF en export)
- Bouton **Historique** pour consulter, comparer et restaurer les versions de transcription corrigée

### Onglet Journal d'audit (workflow)

- Onglet visible pour les utilisateurs pouvant modifier la session
- Affiche les événements de workflow de la session (horodatage, acteur, action, payload)
- Permet d'ouvrir/fermer le JSON de chaque événement pour inspection détaillée

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
- **Glisser-déposer** : vous pouvez aussi déplacer un parcours dans l'arborescence (y compris retour à la racine) par drag-and-drop
- **Mise à jour en masse des sessions (CSV)** :
  - **Exporter les sessions CSV** depuis l'entête de la page Parcours
  - Modifier le fichier, puis **Importer les sessions CSV**
  - Un bouton **Format CSV** rappelle les colonnes acceptées (`status`, `date`, `course`, `themes`, `editors`, etc.)

![Page d'acceuil](./images/courses.png)

---

## Gérer les thèmes

Dans la section **Thèmes** :

- **Créer un thème** : cliquez sur **Nouveau Thème** et saisissez un nom
- **Modifier un thème** : cliquez sur le bouton crayon
- **Supprimer un thème** : cliquez sur le bouton de suppression (les sessions associées perdront ce thème)

![Page d'acceuil](./images/themes.png)

---

## Raccourcis et astuces

- Le **glisser-déposer** fonctionne pour le téléversement de fichiers audio
- Les exports document existent en **PDF/Markdown/Word** pour plusieurs contenus (sessions/livrets)
- Le **panneau latéral** peut être réduit pour gagner de l'espace
- L'**arborescence des parcours** sur la page d'accueil permet de naviguer rapidement dans les sessions par parcours
- Les parcours et les éléments de livret peuvent être réordonnés (flèches et/ou glisser-déposer)
- La **barre de lecture collante** en haut des onglets Transcription et Version rédigée permet de contrôler facilement la lecture audio (pause/stop) sans avoir à défiler
- Le **défilement automatique** suit le paragraphe ou segment en cours de lecture
