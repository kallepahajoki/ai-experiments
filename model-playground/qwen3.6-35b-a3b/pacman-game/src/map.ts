// Map tiles: 0=empty, 1=wall, 2=dot, 3=power pellet, 4=ghost door
export const MAP: number[][] = [
  [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [1,2,2,2,2,2,2,2,2,1,2,2,2,2,2,2,2,2,1],
  [1,3,1,1,2,1,1,1,2,1,2,1,1,1,2,1,1,3,1],
  [1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1],
  [1,2,1,1,2,1,2,1,1,1,1,1,2,1,2,1,1,2,1],
  [1,2,2,2,2,1,2,2,2,1,2,2,2,1,2,2,2,2,1],
  [1,1,1,1,2,1,1,1,0,1,0,1,1,1,2,1,1,1,1],
  [0,0,0,1,2,1,0,0,0,0,0,0,0,1,2,1,0,0,0],
  [1,1,1,1,2,1,0,1,1,4,1,1,0,1,2,1,1,1,1],
  [0,0,0,0,2,0,0,1,0,0,0,1,0,0,2,0,0,0,0],
  [1,1,1,1,2,1,0,1,1,1,1,1,0,1,2,1,1,1,1],
  [0,0,0,1,2,1,0,0,0,0,0,0,0,1,2,1,0,0,0],
  [1,1,1,1,2,1,2,1,1,1,1,1,2,1,2,1,1,1,1],
  [1,2,2,2,2,2,2,2,2,1,2,2,2,2,2,2,2,2,1],
  [1,2,1,1,2,1,1,1,2,1,2,1,1,1,2,1,1,2,1],
  [1,3,2,1,2,2,2,2,2,0,2,2,2,2,2,1,2,3,1],
  [1,1,2,1,2,1,2,1,1,1,1,1,2,1,2,1,2,1,1],
  [1,2,2,2,2,1,2,2,2,1,2,2,2,1,2,2,2,2,1],
  [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
];

export const TILE_SIZE = 24;
export const MAP_W = MAP[0].length;
export const MAP_H = MAP.length;
export const CANVAS_W = MAP_W * TILE_SIZE;
export const CANVAS_H = MAP_H * TILE_SIZE;

export interface WallRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function getWalls(): WallRect[] {
  const walls: WallRect[] = [];
  for (let r = 0; r < MAP_H; r++) {
    for (let c = 0; c < MAP_W; c++) {
      if (MAP[r][c] === 1) {
        walls.push({ x: c * TILE_SIZE, y: r * TILE_SIZE, w: TILE_SIZE, h: TILE_SIZE });
      }
    }
  }
  return walls;
}

export function isWall(x: number, y: number): boolean {
  const c = Math.floor(x / TILE_SIZE);
  const r = Math.floor(y / TILE_SIZE);
  if (r < 0 || r >= MAP_H || c < 0 || c >= MAP_W) return false; // tunnel
  return MAP[r][c] === 1;
}

export function isWalkable(x: number, y: number): boolean {
  const c = Math.floor(x / TILE_SIZE);
  const r = Math.floor(y / TILE_SIZE);
  if (r < 0 || r >= MAP_H || c < 0 || c >= MAP_W) return true; // tunnel
  const tile = MAP[r][c];
  return tile !== 1;
}

export function isGhostDoor(x: number, y: number): boolean {
  const c = Math.floor(x / TILE_SIZE);
  const r = Math.floor(y / TILE_SIZE);
  if (r < 0 || r >= MAP_H || c < 0 || c >= MAP_W) return false;
  return MAP[r][c] === 4;
}
