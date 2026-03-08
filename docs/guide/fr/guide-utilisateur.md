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

Au fil du traitement, une session peut contenir :

- La **transcription brute** (résultat de la reconnaissance vocale)
- La **transcription corrigée** (après correction par IA)
- La **version rédigée** (réécriture structurée du cours)
- Les **sources** extraites et vérifiées
- Un **résumé** détaillé généré par IA

### Cours (Courses)

Un **cours** est un regroupement logique de sessions. Par exemple : « Cours sur la Genèse », « Traité de Berakhot », etc.

- Chaque session peut être rattachée à un seul cours
- Les cours permettent de filtrer les sessions dans la liste et la recherche

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
| **Sessions** | Liste de toutes les sessions | Tous |
| **Rechercher** | Recherche plein texte dans les transcriptions | Tous |
| **Cours** | Gestion des cours | Tous (lecture), Éditeur en chef/Admin (modification) |
| **Thèmes** | Gestion des thèmes | Tous (lecture), Éditeur en chef/Admin (modification) |
| **Traitement** | Suivi des tâches en cours | Éditeur en chef, Admin |
| **Utilisateurs** | Gestion des utilisateurs | Éditeur en chef, Admin |
| **Préférences** | Configuration de l'application | Éditeur en chef, Admin |

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
3. Cliquez sur **Créer**

La session est créée et une tâche de **transcription** est automatiquement lancée.

---

## Pipeline de traitement

Le traitement d'une session se fait par étapes successives. Chaque étape est une **tâche** qui peut être lancée manuellement depuis la page de détail d'une session.

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

**Résultat** : Les segments corrigés remplacent les segments originaux dans l'onglet **Transcription**. Les différences entre l'original et le corrigé sont mises en évidence en vert.

#### 3. Rédiger

Réécrit la transcription corrigée sous forme d'un texte rédigé et structuré, avec des paragraphes, des indications de timing et un style écrit.

**Résultat** : Le texte rédigé apparaît dans l'onglet **Version rédigée**.

#### 4. Extraire les sources

Analyse le texte rédigé pour identifier les sources et références citées (Tanakh, Mishnah, Talmud, Midrash, etc.).

**Résultat** : Les sources extraites sont listées dans l'onglet **Sources**, classées par type.

#### 5. Vérifier les sources

Confronte chaque source extraite à la base de données Sefaria pour vérifier la référence, récupérer le texte original en hébreu et sa traduction, et évaluer la correspondance avec le texte cité.

**Résultat** : Chaque source dans l'onglet **Sources** est enrichie de son statut de vérification et du texte retrouvé.

#### 6. Résumer

Génère un résumé détaillé du cours à partir du texte rédigé, selon un modèle de prompt configurable.

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
   - Le **résumé bref**
4. Cliquez sur **Enregistrer**

![Page d'acceuil](./images/modify.png)

---

## Gérer les cours

Dans la section **Cours** :

- **Créer un cours** : cliquez sur **Nouveau Cours**, saisissez un nom et une description optionnelle
- **Modifier un cours** : cliquez sur le bouton crayon à côté du cours
- **Supprimer un cours** : cliquez sur le bouton de suppression (les sessions associées seront désassignées, mais pas supprimées)

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
| **Lecteur** | Peut consulter les sessions, cours, thèmes et sources |
| **Éditeur** | Peut modifier les sessions (transcription, texte rédigé, résumé) |
| **Éditeur en chef** | Peut créer/supprimer des sessions, cours, thèmes, gérer les tâches et les utilisateurs |
| **Admin** | Accès complet à toutes les fonctionnalités et la configuration |

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
- Prompt de correction

### Rédaction

- Fournisseur LLM
- Modèle à utiliser
- Température
- Tokens max
- Prompt de rédaction

### Sources

- Configuration de l'extraction de sources (prompt, types de sources)
- Configuration de la vérification de sources (prompt)
- Référentiel des types de sources (Tanakh, Mishnah, Talmud, etc.)

### Résumé

- Fournisseur LLM
- Modèle à utiliser
- Modèles de prompts multiples (permettant différents styles de résumé)
- Longueur maximale

---

## Raccourcis et astuces

- **Entrée** dans le champ de recherche lance la recherche
- Le **glisser-déposer** fonctionne pour le téléversement de fichiers audio
- Les **PDF** peuvent être générés pour le résumé, la transcription, la version rédigée et les sources
- Le **panneau latéral** peut être réduit pour gagner de l'espace
- La **barre de lecture collante** en haut des onglets Transcription et Version rédigée permet de contrôler facilement la lecture audio (pause/stop) sans avoir à défiler
- Le **défilement automatique** suit le paragraphe ou segment en cours de lecture
