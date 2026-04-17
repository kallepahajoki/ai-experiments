# Pac-Man Game

A fully functional Pac-Man clone built with HTML Canvas and TypeScript.

## Features

- Classic 19x19 tile map with walls, dots, and power pellets
- Four ghosts (Blinky, Pinky, Inky, Clyde) with distinct chase personalities
- Collision detection, tunnel wrapping, and ghost eating combo scoring
- Lives system, score tracking, and high score persistence (localStorage)
- Death animation and frightened ghost mode with flashing

## Controls

| Key | Action |
|-----|--------|
| Arrow Keys / WASD | Move Pac-Man |
| Enter | Start / Restart |

## Tech Stack

- **TypeScript** — typed game entities, state management, and modular architecture
- **HTML5 Canvas** — 2D rendering for walls, sprites, and animations
- **esbuild** — bundling to a single JS file

## Running

```bash
cd pacman-game
npm install
npx esbuild src/game.ts --bundle --format=esm --outfile=dist/bundle.js
python3 -m http.server 8080
# Open http://localhost:8080/pacman-game/dist/
```

## Project Context

This experiment lives in [model-playground](../../README.my) — a collection of hands-on coding tasks used to evaluate the agentic coding capabilities of various LLM models. See the parent directory for more.

## Prompt

> Create a HTML Canvas + typescript Pacman game
