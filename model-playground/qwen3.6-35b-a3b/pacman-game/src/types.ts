export type Direction = 'up' | 'down' | 'left' | 'right' | 'none'

export interface Point {
  x: number
  y: number
}

export interface GhostState {
  x: number
  y: number
  dir: Direction
  scared: boolean
  eaten: boolean
  spawnTimer: number
  scatterTarget: Point
  flashTimer: number
}

export enum GameState {
  READY = 'ready',
  PLAYING = 'playing',
  GAME_OVER = 'game_over',
  WON = 'won',
  DYING = 'dying',
}

export interface PacmanState {
  x: number
  y: number
  direction: Direction
  nextDirection: Direction
  angle: number
  mouthDir: number
}
