# Art

Aseprite sources live here. Never edit the exported PNGs in `game/assets/`; run `tools\export-art.cmd` instead.

## Conventions

- **Base resolution:** the game renders at 640×360 and scales up by whole numbers, so 1 art pixel is always a whole number of screen pixels.
- **Palette:** one shared palette (`palette.aseprite`, created with the first sprite). Start from the brand colours: background `#141518`, panel `#1D1F23`, ink `#F1EFEA`, red `#E8352B`, yellow `#F2C230`.
- **Animation:** use Aseprite tags for animation names (`idle`, `pit`, `race`). The export writes them into the JSON so Godot can read them.
- **Naming:** lowercase with hyphens, one sprite per file, folders by category (`cars/`, `drivers/`, `tracks/`, `ui/`).
- **Placeholder first:** until M2's exit (see `docs/PLAN.md`), art is placeholder. Polish only screens that survived playtests.
