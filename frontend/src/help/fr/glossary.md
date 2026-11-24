# Glossaire

Le glossaire recense les termes, expressions, citations et noms hébreux utilisés dans les cours. Chaque entrée est identifiée par sa forme hébraïque.

## Contenu d'une entrée

- **Hébreu** : la forme affichée, avec nikoud. Deux clés de recherche en sont calculées : une exacte (signes de cantillation retirés, guillemets normalisés) et une sans aucun nikoud.
- **Translittération** et **autres translittérations** : l'écriture du terme en lettres latines.
- **Traduction**, **type** (terme, expression, citation, nom propre, livre, auteur, fête, lieu) et règle de **casse**.
- **Titre / référence Sefaria** pour les livres, auteurs et citations.
- **Statut** (validé, automatique, rejeté) et **origine** (migration, LLM, manuelle).
- **Contexte** : le cours et le paragraphe où l'entrée a été trouvée.

Deux entrées ne peuvent pas avoir la même forme hébraïque (nikoud compris, signes de cantillation ignorés).

## Actions disponibles

- Rechercher par hébreu (avec ou sans nikoud), translittération ou traduction ; filtrer par type et statut
- Créer, modifier ou supprimer des entrées
- Exporter le glossaire en YAML et le réimporter (les entrées sont rapprochées par leur forme hébraïque)
- Exporter l'ancien glossaire en YAML

## Entrées automatiques et complétion par l'IA

Quand un cours est corrigé avec un prompt en mode hébreu **natif**, chaque nouveau mot ou expression en hébreu est ajouté avec le statut *automatique*, avec seulement sa forme hébraïque et son contexte. Une tâche de complétion est alors lancée automatiquement.

La complétion demande au LLM configuré dans **Préférences › Glossaire** (preset de modèle, prompt, tokens max) de remplir la translittération, les autres translittérations, le type, la casse, la traduction et les références Sefaria de chaque entrée sans translittération (les entrées rejetées sont ignorées). Les entrées restent *automatiques* jusqu'à leur validation. **Compléter par l'IA** lance la même tâche à la main.

## Ancien glossaire

L'ancien glossaire (translittération standard + variantes) est conservé en lecture seule. Il sert encore au pipeline pour normaliser l'orthographe, jusqu'à ce que ses entrées soient converties dans le nouveau glossaire.
