# AGENTS

Ce dépôt contient une interface TUI (Textual) pour piloter WPScan. Ce document sert d’aide rapide et de référence pour les contributrices/teurs et les agents automatisés.

## Mission du projet
- Fournir une UI terminal “lazy*-style” pour lancer des scans WPScan avec des presets utiles.
- Tenir compte des spécificités Arch/PEP 668 (environnements gérés) et faciliter l’installation via pipx.
- Historiser les scans dans la session uniquement (fichier supprimé à la fermeture) et permettre une relecture rapide.

## Structure des fichiers
- `pyproject.toml` : packaging, dépendances (Textual), entrée console `wpscan-tui`.
- `src/wpscan_tui/app.py` : application Textual complète (UI, logique WPScan, historique).
- `src/wpscan_tui/__init__.py` : export `run`, `WPScanTUI`.
- `README.md` : usages, installation, dépannage, développement.
- (Historique runtime) `~/.local/state/wpscan-tui/history.json` : créé à l’exécution, supprimé à la sortie.

## Installation locale
1) Pré-requis : `wpscan` dans le `PATH` (Arch : `paru -S wpscan` ou `yay -S wpscan`).
2) Recommandé : `pipx install .`
3) Alternatives : `python -m venv .venv && source .venv/bin/activate && pip install .` ou `pip install --break-system-packages .` (déconseillé).

## Commandes utiles
- Lancer l’app : `wpscan-tui`
- Dev live reload : `textual run --dev wpscan_tui.app:WPScanTUI`
- Rebuild pipx après changement : `pipx install . --force`

## Raccourcis et UI
- `Ctrl+S` : démarrer le scan courant.
- `Ctrl+C` : arrêter le scan en cours.
- `Ctrl+Q` : quitter l’app (purge l’historique et supprime le fichier history).
- Historique : sélection + Entrée ou bouton “View” pour recharger un ancien log de la session ; bouton “Clear” pour tout effacer manuellement.

## Options prises en charge
- Cible + token API.
- Enumérations : users/plugins/themes.
- Flags : random UA, verbose, ignore-main-redirect, no-update (défaut), ignore TLS, force, plain output.
- Champ “Extra arguments” pour passer n’importe quel flag WPScan.

## Notes techniques
- Textual version attendue ~0.69 (certaines classes comme `TextLog` n’existent pas ; on utilise `RichLog` et `OptionList` avec `Option` sans paramètre `value`).
- Couleurs : pas de fond imposé, bordures grises ; couleurs fixes neutres pour rester lisible sur la plupart des thèmes. (Textual n’accepte pas `color: inherit` ni `border: tall greyN` → utiliser valeurs hex et noms de couleurs valides.)
- L’historique est volatile : `clear_history_storage()` supprime le fichier et vide la liste sur “Clear” et à `on_exit`.

## Dépannage rapide
- Erreur CSS Textual : vérifier que les couleurs sont des hex ou noms valides et que les bordures sont de la forme `border: <type> <couleur>`.
- Import errors : Textual 0.69 nécessite `Option` depuis `textual.widgets.option_list`.
- PEP 668 / “externally managed” : installer via pipx ou venv, pas en global.
- WPScan manquant : installer le paquet, vérifier PATH.

## Checklist avant push
- `python -m py_compile src/wpscan_tui/app.py`
- Tester un scan fictif ou réel (avec autorisation) pour valider le flux et l’historique.
- `git status` doit être clean; `pipx install . --force && wpscan-tui` si possible.

## Licence
MIT (conserver la notice si redistribution).

## Contacts / Remote
- Origin : `git@github.com:Chaos-Tic/WPscan-TUI.git`

