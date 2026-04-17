import { Direction, Point, GhostState } from './types';
import { isWall, isGhostDoor, CANVAS_W, TILE_SIZE } from './map';

const SPEED = 2;
const SCARED_SPEED = 1.2;
const FRIGHTEN_FLASH_THRESHOLD = 120;

function opposite(d: Direction): Direction {
  return ({ up: 'down', down: 'up', left: 'right', right: 'left', none: 'none' } as Record<Direction, Direction>)[d];
}

function dirVector(d: Direction): Point {
  return { x: d === 'left' ? -1 : d === 'right' ? 1 : 0, y: d === 'up' ? -1 : d === 'down' ? 1 : 0 };
}

function manhattan(a: Point, b: Point): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function snapToGrid(val: number): number {
  return Math.round(val / TILE_SIZE) * TILE_SIZE;
}

// Ghost personality targets (chase mode)
const CHASE_TARGETS: Point[] = [
  { x: 14, y: 4 },   // Blinky: pacman position
  { x: 10, y: 4 },   // Pinky: 4 tiles ahead of pacman
  { x: 12, y: 2 },   // Inky: 2 tiles ahead + blinky offset
  { x: 5, y: 17 },   // Clyde: pacman position when far
];

export function createGhosts(): GhostState[] {
  return [
    { x: 9 * TILE_SIZE, y: 8 * TILE_SIZE, dir: 'left',  scared: false, eaten: false, spawnTimer: 0,    scatterTarget: { x: 17, y: 0 },    flashTimer: 0 },
    { x: 8 * TILE_SIZE, y: 9 * TILE_SIZE, dir: 'up',    scared: false, eaten: false, spawnTimer: 60,   scatterTarget: { x: 1, y: 0 },     flashTimer: 0 },
    { x: 9 * TILE_SIZE, y: 9 * TILE_SIZE, dir: 'up',    scared: false, eaten: false, spawnTimer: 120,  scatterTarget: { x: 17, y: 18 },   flashTimer: 0 },
    { x: 10 * TILE_SIZE, y: 9 * TILE_SIZE, dir: 'up',   scared: false, eaten: false, spawnTimer: 180,  scatterTarget: { x: 1, y: 18 },    flashTimer: 0 },
  ];
}

export function getGhostBodyColor(scared: boolean, flashTimer: number, idx: number): string {
  if (scared) {
    if (flashTimer > 0 && flashTimer < FRIGHTEN_FLASH_THRESHOLD && flashTimer % 20 < 10) {
      return '#FFFFFF';
    }
    return '#2121DE';
  }
  // Classic ghost colors
  const colors = ['#FF0000', '#FFB8FF', '#00FFFF', '#FFB852'];
  return colors[idx % colors.length];
}

export function moveGhost(ghost: GhostState, ghostIdx: number, pacmanCx: number, pacmanCy: number, scatterTarget: Point, inHouse: boolean): void {
  if (ghost.spawnTimer > 0 && !inHouse) {
    ghost.spawnTimer--;
    return;
  }

  // Eaten ghost returning to house
  if (ghost.eaten && inHouse) {
    ghost.eaten = false;
    ghost.scared = false;
    ghost.x = 9 * TILE_SIZE;
    ghost.y = 9 * TILE_SIZE;
    ghost.spawnTimer = 0;
    ghost.dir = 'up';
    return;
  }

  const speed = ghost.scared ? SCARED_SPEED : SPEED;
  const cx = snapToGrid(ghost.x + TILE_SIZE / 2);
  const cy = snapToGrid(ghost.y + TILE_SIZE / 2);

  if (ghost.x !== cx || ghost.y !== cy) return; // Only turn at grid centers

  const tileX = Math.floor((ghost.x + TILE_SIZE / 2) / TILE_SIZE);
  const tileY = Math.floor((ghost.y + TILE_SIZE / 2) / TILE_SIZE);

  // Choose target tile
  let target: Point;
  if (ghost.eaten) {
    target = { x: 9, y: 9 };
  } else if (ghost.scared) {
    // Random movement
    const dirs: Direction[] = ['up', 'down', 'left', 'right'];
    target = { x: Math.floor(Math.random() * 19), y: Math.floor(Math.random() * 19) };
  } else {
    // Chase or scatter
    const chaseTargets: Point[] = [
      { x: pacmanCx, y: pacmanCy },                    // Blinky: exact pacman pos
      { x: pacmanCx + 4, y: pacmanCy },              // Pinky: 4 tiles ahead (simplified)
      { x: pacmanCx + 2, y: pacmanCy - 2 },          // Inky: offset
      { x: pacmanCx, y: pacmanCy },                  // Clyde: pacman pos
    ];

    // Clyde scatters when close
    if (ghostIdx === 3 && manhattan({ x: tileX, y: tileY }, { x: pacmanCx, y: pacmanCy }) < 8) {
      target = scatterTarget;
    } else {
      target = chaseTargets[ghostIdx % chaseTargets.length];
    }
  }

  // Evaluate possible directions
  const candidates: Direction[] = ['up', 'down', 'left', 'right'];
  let bestDir: Direction = ghost.dir;
  let bestScore = ghost.scared ? -1 : Infinity;

  for (const d of candidates) {
    if (ghost.scared && !ghost.eaten && d === opposite(ghost.dir)) continue; // No U-turn when scared
    const v = dirVector(d);
    const nx = (tileX + v.x) * TILE_SIZE + TILE_SIZE / 2;
    const ny = (tileY + v.y) * TILE_SIZE + TILE_SIZE / 2;

    // Ghost door only for eaten ghosts going home
    if (isGhostDoor(nx, ny)) {
      if (!ghost.eaten) continue;
    }
    if (isWall(nx, ny)) continue;

    const dist = manhattan({ x: nx / TILE_SIZE, y: ny / TILE_SIZE }, target);

    if (ghost.scared && !ghost.eaten) {
      // Maximize distance (flee)
      if (dist > bestScore) { bestScore = dist; bestDir = d; }
    } else {
      // Minimize distance (chase)
      if (dist < bestScore) { bestScore = dist; bestDir = d; }
    }
  }

  // Fallback: allow U-turn if no other option
  if (bestDir === ghost.dir) {
    const fallback = opposite(ghost.dir);
    const v = dirVector(fallback);
    const nx = (tileX + v.x) * TILE_SIZE + TILE_SIZE / 2;
    const ny = (tileY + v.y) * TILE_SIZE + TILE_SIZE / 2;
    if (!isWall(nx, ny)) {
      bestDir = fallback;
    } else {
      return; // Truly stuck
    }
  }

  ghost.dir = bestDir;
  const v = dirVector(ghost.dir);
  ghost.x += v.x * speed;
  ghost.y += v.y * speed;

  // Tunnel wrap
  if (ghost.x < -TILE_SIZE) ghost.x = CANVAS_W;
  if (ghost.x > CANVAS_W) ghost.x = -TILE_SIZE;
}
