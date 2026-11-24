# Glossary

The Glossary lists Hebrew terms, expressions, quotations and names used in the lessons. Each entry is identified by its Hebrew form.

## What an entry contains

- **Hebrew**: the form shown to readers, with niqqud. Two search keys are computed from it: an exact one (cantillation marks removed, quotation marks standardized) and one without any niqqud.
- **Transliteration** and **other transliterations**: how the term is written in Latin letters.
- **Translation**, **type** (term, expression, quotation, proper name, book, author, holiday, place) and **capitalization** rule.
- **Sefaria title / reference** for books, authors and quotations.
- **Status** (validated, automatic, rejected) and **origin** (migration, LLM, manual).
- **Context**: the lesson and paragraph where the entry was first found.

Two entries cannot have the same Hebrew form (niqqud included, cantillation marks ignored).

## Available actions

- Search by Hebrew (with or without niqqud), transliteration or translation; filter by type and status
- Create, edit or delete entries
- Export the glossary as YAML, and import it back (entries are matched by their Hebrew form)
- Export the legacy glossary as YAML

## Automatic entries and AI completion

When a lesson is corrected with a prompt in **native** Hebrew mode, every new Hebrew word or expression is added with status *automatic*, with only its Hebrew form and context. A completion task is then queued automatically.

The completion asks the LLM configured in **Preferences › Glossary** (model preset, prompt, max tokens) to fill in the transliteration, other transliterations, type, capitalization, translation and Sefaria references of every entry without a transliteration (rejected entries are skipped). Entries stay *automatic* until you validate them. **Complete with AI** starts the same task by hand.

## Legacy glossary

The previous glossary (standard transliteration + variant spellings) is kept read-only. It is still used by the processing pipeline to normalize spellings until its entries are converted to the new glossary.
