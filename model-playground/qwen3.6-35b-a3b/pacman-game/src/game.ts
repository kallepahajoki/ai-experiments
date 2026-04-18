import { GameState } from './types';
import { CANVAS_W, CANVAS_H, TILE_SIZE, isWalkable, isGhostDoor, MAP, MAP_H, MAP_W } from './map';
import { createGhosts, moveGhost, getGhostBodyColor } from './ghost';
import { createPacman, getMouthAngle, getPacmanPixelPos, resetPacman } from './pacman';
import { initDots, getDots, allDotsEaten } from './dot';

const canvas = document.getElementById('game') as HTMLCanvasElement;
const ctx = canvas.getContext('2d')!;
canvas.width = CANVAS_W;
canvas.height = CANVAS_H;

const scoreEl = document.getElementById('score') as HTMLTextAreaElement;
const highScoreEl = document.getElementById('highscore') as HTMLTextAreaElement;
const messageEl = document.getElementById('message') as HTMLTextAreaElement;

let gameState = GameState.READY;
let score = 0;
let highScore = parseInt(localStorage.getItem('pacman_highscore') || '0');
let frameCount = 0;
let frightenTimer = 0;
let lives = 3;
let combo = 0;

const pacman = createPacman();
const ghosts = createGhosts();
const dots = initDots();

scoreEl.value = 'SCORE: 0';
highScoreEl.value = `HIGH: ${highScore}`;
messageEl.value = 'PRESS ENTER TO START';

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    if (gameState === GameState.GAME_OVER || gameState === GameState.WON) {
      resetGame();
    }
    if (gameState === GameState.READY) {
      gameState = GameState.PLAYING;
      pacman.nextDirection = 'right';
      pacman.direction = 'right';
      messageEl.value = '';
    }
    return;
  }

  if (gameState !== GameState.PLAYING) return;

  let dir: 'up' | 'down' | 'left' | 'right' | null = null;
  switch (e.key) {
    case 'ArrowUp': case 'w': case 'W': dir = 'up'; break;
    case 'ArrowDown': case 's': case 'S': dir = 'down'; break;
    case 'ArrowLeft': case 'a': case 'A': dir = 'left'; break;
    case 'ArrowRight': case 'd': case 'D': dir = 'right'; break;
  }
  if (dir) {
    pacman.nextDirection = dir;
    e.preventDefault();
  }
});

function resetGame(): void {
  score = 0;
  lives = 3;
  frameCount = 0;
  frightenTimer = 0;
  combo = 0;
  resetPacman(pacman);
  for (let i = 0; i < ghosts.length; i++) {
    const g = ghosts[i];
    g.scared = false;
    g.eaten = false;
    g.spawnTimer = i * 60;
  }
  initDots();
  gameState = GameState.READY;
  messageEl.value = 'PRESS ENTER TO START';
  scoreEl.value = 'SCORE: 0';
  draw();
}

function killPacman(): void {
  gameState = GameState.DYING;
  lives--;
  setTimeout(() => {
    if (lives <= 0) {
      gameState = GameState.GAME_OVER;
      if (score > highScore) {
        highScore = score;
        localStorage.setItem('pacman_highscore', String(highScore));
        highScoreEl.value = `HIGH: ${highScore}`;
      }
      messageEl.value = 'GAME OVER - PRESS ENTER';
    } else {
      resetPacman(pacman);
      gameState = GameState.READY;
      messageEl.value = 'PRESS ENTER TO START';
    }
  }, 1000);
}

function drawWalls(): void {
  ctx.fillStyle = '#1a1aa0';
  // Draw walls as filled rectangles from the MAP
  const MAP = [
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
  for (let r = 0; r < MAP.length; r++) {
    for (let c = 0; c < MAP[r].length; c++) {
      if (MAP[r][c] === 1) {
        ctx.fillRect(c * TILE_SIZE, r * TILE_SIZE, TILE_SIZE, TILE_SIZE);
        ctx.strokeStyle = '#3333ff';
        ctx.lineWidth = 0.5;
        ctx.strokeRect(c * TILE_SIZE + 0.5, r * TILE_SIZE + 0.5, TILE_SIZE - 1, TILE_SIZE - 1);
      }
    }
  }
}

function drawDot(dot: { x: number; y: number; eaten: boolean; isPower: boolean }): void {
  if (dot.eaten) return;
  ctx.fillStyle = '#FFB8ae';
  ctx.beginPath();
  const r = dot.isPower ? 4 + Math.sin(frameCount * 0.1) * 1.5 : 2;
  ctx.arc(dot.x, dot.y, Math.max(1, r), 0, Math.PI * 2);
  ctx.fill();
}

function drawPacman(): void {
  const pos = getPacmanPixelPos(pacman);
  const cx = pos.x + TILE_SIZE / 2;
  const cy = pos.y + TILE_SIZE / 2;
  const r = TILE_SIZE / 2 - 2;
  const angle = getMouthAngle(pacman, frameCount);

  let rotation = 0;
  switch (pacman.direction) {
    case 'right': rotation = 0; break;
    case 'down': rotation = Math.PI / 2; break;
    case 'left': rotation = Math.PI; break;
    case 'up': rotation = -Math.PI / 2; break;
  }

  ctx.fillStyle = '#FFFF00';
  ctx.beginPath();
  ctx.arc(cx, cy, r, rotation + angle, rotation + Math.PI * 2 - angle);
  ctx.lineTo(cx, cy);
  ctx.closePath();
  ctx.fill();

  // Eye
  const eyeOffX = Math.cos(rotation - 0.5) * r * 0.4;
  const eyeOffY = Math.sin(rotation - 0.5) * r * 0.4;
  ctx.fillStyle = '#000';
  ctx.beginPath();
  ctx.arc(cx + eyeOffX, cy + eyeOffY, 2, 0, Math.PI * 2);
  ctx.fill();
}

function drawGhost(ghost: typeof ghosts[0], idx: number): void {
  if (ghost.spawnTimer > 0 && (ghost.spawnTimer % 10) < 5) return;

  const cx = ghost.x + TILE_SIZE / 2;
  const cy = ghost.y + TILE_SIZE / 2;
  const r = TILE_SIZE / 2 - 2;
  const color = getGhostBodyColor(ghost.scared, frightenTimer, idx);

  // Body - dome + wavy bottom
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(cx, cy - 2, r, Math.PI, 0);
  ctx.lineTo(cx + r, cy + r);
  const wave = Math.sin(frameCount * 0.2) * 2;
  for (let i = 0; i < 3; i++) {
    const wx = cx + r - (i + 1) * (r * 2 / 3);
    ctx.quadraticCurveTo(wx + r / 3, cy + r + wave, wx, cy + r);
  }
  ctx.closePath();
  ctx.fill();

  if (ghost.scared) {
    ctx.fillStyle = '#FFFFFF';
    ctx.beginPath();
    ctx.arc(cx - 3, cy - 3, 2, 0, Math.PI * 2);
    ctx.arc(cx + 3, cy - 3, 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 5, cy + 3);
    for (let i = 0; i < 4; i++) {
      ctx.lineTo(cx - 5 + i * 3, cy + (i % 2 === 0 ? 3 : 6));
    }
    ctx.stroke();
  } else {
    // White eyes
    ctx.fillStyle = '#FFFFFF';
    ctx.beginPath();
    ctx.ellipse(cx - 4, cy - 3, 4, 5, 0, 0, Math.PI * 2);
    ctx.ellipse(cx + 4, cy - 3, 4, 5, 0, 0, Math.PI * 2);
    ctx.fill();

    // Pupils looking at pacman
    const pp = getPacmanPixelPos(pacman);
    const dx = pp.x - ghost.x;
    const dy = pp.y - ghost.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const px = cx + (dx / dist) * 2;
    const py = cy + (dy / dist) * 2;
    ctx.fillStyle = '#0000CC';
    ctx.beginPath();
    ctx.arc(px - 4, py, 2, 0, Math.PI * 2);
    ctx.arc(px + 4, py, 2, 0, Math.PI * 2);
    ctx.fill();
  }
}

function draw(): void {
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

  drawWalls();

  // Ghost door
  ctx.fillStyle = '#FFB8FF';
  ctx.fillRect(9 * TILE_SIZE, 8 * TILE_SIZE + 10, TILE_SIZE, 4);

  for (const d of dots) drawDot(d);

  for (let i = 0; i < ghosts.length; i++) drawGhost(ghosts[i], i);

  if (gameState !== GameState.DYING) {
    drawPacman();
  } else {
    // Death animation
    const pos = getPacmanPixelPos(pacman);
    const cx = pos.x + TILE_SIZE / 2;
    const cy = pos.y + TILE_SIZE / 2;
    const shrink = Math.max(0, Math.sin(frameCount * 0.3) * TILE_SIZE / 2);
    ctx.fillStyle = '#FFFF00';
    ctx.beginPath();
    ctx.arc(cx, cy, shrink, 0, Math.PI * 2);
    ctx.fill();
  }

  // Lives
  ctx.fillStyle = '#FFFF00';
  for (let i = 0; i < lives; i++) {
    ctx.beginPath();
    const lx = 20 + i * 24;
    const ly = CANVAS_H - 12;
    ctx.arc(lx, ly, 8, 0.3 + 0.1, Math.PI * 2 - 0.3 - 0.1);
    ctx.lineTo(lx, ly);
    ctx.closePath();
    ctx.fill();
  }
}

function update(): void {
  if (gameState !== GameState.PLAYING) {
    frameCount++;
    draw();
    requestAnimationFrame(update);
    return;
  }

  frameCount++;

  // Move pacman — always step-by-step at constant speed
  const px = pacman.x ?? TILE_SIZE * 9;
  const py = pacman.y ?? TILE_SIZE * 15;

  if (pacman.direction === 'none') return;

  // Check if near grid center (tolerance of 4px)
  const gridX = Math.round(px / TILE_SIZE) * TILE_SIZE;
  const gridY = Math.round(py / TILE_SIZE) * TILE_SIZE;
  const atCenter = Math.abs(px - gridX) <= 4 && Math.abs(py - gridY) <= 4;

  if (atCenter) {
    // Try buffered turn at intersection — snap to grid only when a turn is applied
    const intentDir = pacman.nextDirection;
    if (intentDir !== pacman.direction && intentDir !== 'none') {
      const dv = { x: intentDir === 'left' ? -1 : intentDir === 'right' ? 1 : 0,
                   y: intentDir === 'up' ? -1 : intentDir === 'down' ? 1 : 0 };
      const tx = Math.floor(gridX / TILE_SIZE) + dv.x;
      const ty = Math.floor(gridY / TILE_SIZE) + dv.y;
      const walkable = (ty < 0 || ty >= MAP_H) ? false : (tx < 0 || tx >= MAP_W) ? true : MAP[ty][tx] !== 1;
      if (walkable) {
        pacman.x = gridX;
        pacman.y = gridY;
        pacman.direction = intentDir;
        pacman.nextDirection = 'none';
      }
    }
  }

  // Move one step (2px) in current direction
  const dv = { x: pacman.direction === 'left' ? -1 : pacman.direction === 'right' ? 1 : 0,
               y: pacman.direction === 'up' ? -1 : pacman.direction === 'down' ? 1 : 0 };
  const nx = (pacman.x ?? 0) + dv.x * 2;
  const ny = (pacman.y ?? 0) + dv.y * 2;
  // Check the tile at the new position (incremental 2px movement, so this catches walls correctly).
  const tx = Math.floor(nx / TILE_SIZE);
  const ty = Math.floor(ny / TILE_SIZE);
  const walkable = (ty < 0 || ty >= MAP_H) ? false : (tx < 0 || tx >= MAP_W) ? true : MAP[ty][tx] !== 1;
  if (walkable) {
    pacman.x = nx;
    pacman.y = ny;
  }

  // Tunnel wrap
  if ((pacman.x ?? 0) < -TILE_SIZE) pacman.x = 18 * TILE_SIZE;
  if ((pacman.x ?? 0) > 18 * TILE_SIZE) pacman.x = 0;

  // Eat dots
  const pPx = pacman.x ?? TILE_SIZE * 9;
  const pPy = pacman.y ?? TILE_SIZE * 15;
  for (const d of dots) {
    if (d.eaten) continue;
    const dist = Math.sqrt((d.x - pPx - TILE_SIZE / 2) ** 2 + (d.y - pPy - TILE_SIZE / 2) ** 2);
    if (dist < TILE_SIZE * 0.7) {
      d.eaten = true;
      score += d.isPower ? 50 : 10;
      scoreEl.value = `SCORE: ${score}`;
      if (d.isPower) {
        frightenTimer = 480;
        combo = 0;
        for (const g of ghosts) {
          if (g.spawnTimer <= 0) g.scared = true;
        }
      }
    }
  }

  // Frighten timer
  if (frightenTimer > 0) {
    frightenTimer--;
    if (frightenTimer === 0) {
      for (const g of ghosts) g.scared = false;
    }
  }

  // Move ghosts & check collisions
  for (let i = 0; i < ghosts.length; i++) {
    const g = ghosts[i];
    const inHouse = g.spawnTimer > 0;
    moveGhost(g, i, (pPx / TILE_SIZE) | 0, (pPy / TILE_SIZE) | 0, g.scatterTarget, inHouse);

    const dist = Math.sqrt((g.x - pPx) ** 2 + (g.y - pPy) ** 2);
    if (dist < TILE_SIZE * 0.7) {
      if (g.scared && !g.eaten) {
        g.eaten = true;
        g.scared = false;
        combo++;
        score += 200 * combo;
        scoreEl.value = `SCORE: ${score}`;
      } else if (!g.eaten && g.spawnTimer <= 0) {
        killPacman();
        return;
      }
    }
  }

  // Win check
  if (allDotsEaten()) {
    gameState = GameState.WON;
    if (score > highScore) {
      highScore = score;
      localStorage.setItem('pacman_highscore', String(highScore));
      highScoreEl.value = `HIGH: ${highScore}`;
    }
    messageEl.value = 'YOU WIN - PRESS ENTER';
  }

  draw();
  requestAnimationFrame(update);
}

highScoreEl.value = `HIGH: ${highScore}`;
draw();
requestAnimationFrame(update);
