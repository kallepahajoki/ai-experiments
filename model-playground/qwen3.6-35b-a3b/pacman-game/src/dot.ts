import { Point } from './types';
import { MAP, MAP_W, MAP_H, TILE_SIZE } from './map';

export interface Dot {
  x: number;
  y: number;
  eaten: boolean;
  isPower: boolean;
}

let dots: Dot[] = [];

export function initDots(): Dot[] {
  dots = [];
  for (let r = 0; r < MAP_H; r++) {
    for (let c = 0; c < MAP_W; c++) {
      if (MAP[r][c] === 2) {
        dots.push({ x: c * TILE_SIZE + TILE_SIZE / 2, y: r * TILE_SIZE + TILE_SIZE / 2, eaten: false, isPower: false });
      } else if (MAP[r][c] === 3) {
        dots.push({ x: c * TILE_SIZE + TILE_SIZE / 2, y: r * TILE_SIZE + TILE_SIZE / 2, eaten: false, isPower: true });
      }
    }
  }
  return dots;
}

export function getDots(): Dot[] {
  return dots;
}

export function eatDot(dot: Dot, pacmanCx: number, pacmanCy: number): boolean {
  if (dot.eaten) return false;
  const dist = Math.sqrt((dot.x - pacmanCx * TILE_SIZE) ** 2 + (dot.y - pacmanCy * TILE_SIZE) ** 2);
  if (dist < TILE_SIZE * 0.6) {
    dot.eaten = true;
    return true;
  }
  return false;
}

export function allDotsEaten(): boolean {
  return dots.every(d => d.eaten);
}

export function remainingDots(): number {
  return dots.filter(d => !d.eaten).length;
}

export function resetDots(): Dot[] {
  return initDots();
}
