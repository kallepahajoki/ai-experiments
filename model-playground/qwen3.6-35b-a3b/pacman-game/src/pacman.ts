import { Direction, PacmanState, Point } from './types';
import { isWall, TILE_SIZE } from './map';

function dirVector(d: Direction): Point {
  return { x: d === 'left' ? -1 : d === 'right' ? 1 : 0, y: d === 'up' ? -1 : d === 'down' ? 1 : 0 };
}

const PACMAN_SPEED = 2;

export function createPacman(): PacmanState {
  return { x: 9 * TILE_SIZE, y: 15 * TILE_SIZE, direction: 'none', nextDirection: 'none', angle: 0.2, mouthDir: 1 };
}

export function movePacman(pacman: PacmanState): void {
  const dir = pacman.direction === 'none' ? pacman.nextDirection : pacman.direction;
  if (dir === 'none') return;

  const v = dirVector(dir);
  const nx = (pacman.x ?? TILE_SIZE * 9) + v.x * PACMAN_SPEED;
  const ny = (pacman.y ?? TILE_SIZE * 15) + v.y * PACMAN_SPEED;

  if (!isWall(nx, ny)) {
    pacman.x = nx;
    pacman.y = ny;
    pacman.direction = dir;
  }

  // Tunnel wrap
  if ((pacman.x ?? 0) < -TILE_SIZE) pacman.x = 18 * TILE_SIZE;
  if ((pacman.x ?? 0) > 18 * TILE_SIZE) pacman.x = 0;
}

export function updatePacmanAnimation(pacman: PacmanState, frame: number): void {
  // Animate mouth
  const mouthSpeed = 6;
  pacman.angle += pacman.mouthDir * 0.05;
  if (pacman.angle > 0.8) pacman.mouthDir = -1;
  if (pacman.angle < 0.05) pacman.mouthDir = 1;
}

export function getMouthAngle(pacman: PacmanState, frame: number): number {
  const wave = Math.sin(frame * 0.15) * 0.3 + 0.3;
  return Math.max(0.05, wave);
}

export function getPacmanCenter(pacman: PacmanState): Point {
  return {
    x: (pacman.x ?? TILE_SIZE * 9) / TILE_SIZE,
    y: (pacman.y ?? TILE_SIZE * 15) / TILE_SIZE,
  };
}

export function getPacmanPixelPos(pacman: PacmanState): Point {
  return {
    x: pacman.x ?? TILE_SIZE * 9,
    y: pacman.y ?? TILE_SIZE * 15,
  };
}

export function getPacmanRotation(pacman: PacmanState): number {
  switch (pacman.direction) {
    case 'right': return 0;
    case 'down': return Math.PI / 2;
    case 'left': return Math.PI;
    case 'up': return -Math.PI / 2;
    default: return 0;
  }
}

export function resetPacman(pacman: PacmanState): void {
  pacman.x = 9 * TILE_SIZE;
  pacman.y = 15 * TILE_SIZE;
  pacman.direction = 'none';
  pacman.nextDirection = 'none';
  pacman.angle = 0.2;
  pacman.mouthDir = 1;
}
