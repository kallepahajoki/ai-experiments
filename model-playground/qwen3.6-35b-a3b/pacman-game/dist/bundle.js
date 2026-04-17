// src/map.ts
var MAP = [
  [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
  [1, 2, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 2, 2, 1],
  [1, 3, 1, 1, 2, 1, 1, 1, 2, 1, 2, 1, 1, 1, 2, 1, 1, 3, 1],
  [1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1],
  [1, 2, 1, 1, 2, 1, 2, 1, 1, 1, 1, 1, 2, 1, 2, 1, 1, 2, 1],
  [1, 2, 2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 2, 1],
  [1, 1, 1, 1, 2, 1, 1, 1, 0, 1, 0, 1, 1, 1, 2, 1, 1, 1, 1],
  [0, 0, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0],
  [1, 1, 1, 1, 2, 1, 0, 1, 1, 4, 1, 1, 0, 1, 2, 1, 1, 1, 1],
  [0, 0, 0, 0, 2, 0, 0, 1, 0, 0, 0, 1, 0, 0, 2, 0, 0, 0, 0],
  [1, 1, 1, 1, 2, 1, 0, 1, 1, 1, 1, 1, 0, 1, 2, 1, 1, 1, 1],
  [0, 0, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0],
  [1, 1, 1, 1, 2, 1, 2, 1, 1, 1, 1, 1, 2, 1, 2, 1, 1, 1, 1],
  [1, 2, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 2, 2, 1],
  [1, 2, 1, 1, 2, 1, 1, 1, 2, 1, 2, 1, 1, 1, 2, 1, 1, 2, 1],
  [1, 3, 2, 1, 2, 2, 2, 2, 2, 0, 2, 2, 2, 2, 2, 1, 2, 3, 1],
  [1, 1, 2, 1, 2, 1, 2, 1, 1, 1, 1, 1, 2, 1, 2, 1, 2, 1, 1],
  [1, 2, 2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 2, 1],
  [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
];
var TILE_SIZE = 24;
var MAP_W = MAP[0].length;
var MAP_H = MAP.length;
var CANVAS_W = MAP_W * TILE_SIZE;
var CANVAS_H = MAP_H * TILE_SIZE;
function isWall(x, y) {
  const c = Math.floor(x / TILE_SIZE);
  const r = Math.floor(y / TILE_SIZE);
  if (r < 0 || r >= MAP_H || c < 0 || c >= MAP_W) return false;
  return MAP[r][c] === 1;
}
function isGhostDoor(x, y) {
  const c = Math.floor(x / TILE_SIZE);
  const r = Math.floor(y / TILE_SIZE);
  if (r < 0 || r >= MAP_H || c < 0 || c >= MAP_W) return false;
  return MAP[r][c] === 4;
}

// src/ghost.ts
var SPEED = 2;
var SCARED_SPEED = 1.2;
var FRIGHTEN_FLASH_THRESHOLD = 120;
function opposite(d) {
  return { up: "down", down: "up", left: "right", right: "left", none: "none" }[d];
}
function dirVector(d) {
  return { x: d === "left" ? -1 : d === "right" ? 1 : 0, y: d === "up" ? -1 : d === "down" ? 1 : 0 };
}
function manhattan(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}
function snapToGrid(val) {
  return Math.round(val / TILE_SIZE) * TILE_SIZE;
}
function createGhosts() {
  return [
    { x: 9 * TILE_SIZE, y: 8 * TILE_SIZE, dir: "left", scared: false, eaten: false, spawnTimer: 0, scatterTarget: { x: 17, y: 0 }, flashTimer: 0 },
    { x: 8 * TILE_SIZE, y: 9 * TILE_SIZE, dir: "up", scared: false, eaten: false, spawnTimer: 60, scatterTarget: { x: 1, y: 0 }, flashTimer: 0 },
    { x: 9 * TILE_SIZE, y: 9 * TILE_SIZE, dir: "up", scared: false, eaten: false, spawnTimer: 120, scatterTarget: { x: 17, y: 18 }, flashTimer: 0 },
    { x: 10 * TILE_SIZE, y: 9 * TILE_SIZE, dir: "up", scared: false, eaten: false, spawnTimer: 180, scatterTarget: { x: 1, y: 18 }, flashTimer: 0 }
  ];
}
function getGhostBodyColor(scared, flashTimer, idx) {
  if (scared) {
    if (flashTimer > 0 && flashTimer < FRIGHTEN_FLASH_THRESHOLD && flashTimer % 20 < 10) {
      return "#FFFFFF";
    }
    return "#2121DE";
  }
  const colors = ["#FF0000", "#FFB8FF", "#00FFFF", "#FFB852"];
  return colors[idx % colors.length];
}
function moveGhost(ghost, ghostIdx, pacmanCx, pacmanCy, scatterTarget, inHouse) {
  if (ghost.spawnTimer > 0 && !inHouse) {
    ghost.spawnTimer--;
    return;
  }
  if (ghost.eaten && inHouse) {
    ghost.eaten = false;
    ghost.scared = false;
    ghost.x = 9 * TILE_SIZE;
    ghost.y = 9 * TILE_SIZE;
    ghost.spawnTimer = 0;
    ghost.dir = "up";
    return;
  }
  const speed = ghost.scared ? SCARED_SPEED : SPEED;
  const cx = snapToGrid(ghost.x + TILE_SIZE / 2);
  const cy = snapToGrid(ghost.y + TILE_SIZE / 2);
  if (ghost.x !== cx || ghost.y !== cy) return;
  const tileX = Math.floor((ghost.x + TILE_SIZE / 2) / TILE_SIZE);
  const tileY = Math.floor((ghost.y + TILE_SIZE / 2) / TILE_SIZE);
  let target;
  if (ghost.eaten) {
    target = { x: 9, y: 9 };
  } else if (ghost.scared) {
    const dirs = ["up", "down", "left", "right"];
    target = { x: Math.floor(Math.random() * 19), y: Math.floor(Math.random() * 19) };
  } else {
    const chaseTargets = [
      { x: pacmanCx, y: pacmanCy },
      // Blinky: exact pacman pos
      { x: pacmanCx + 4, y: pacmanCy },
      // Pinky: 4 tiles ahead (simplified)
      { x: pacmanCx + 2, y: pacmanCy - 2 },
      // Inky: offset
      { x: pacmanCx, y: pacmanCy }
      // Clyde: pacman pos
    ];
    if (ghostIdx === 3 && manhattan({ x: tileX, y: tileY }, { x: pacmanCx, y: pacmanCy }) < 8) {
      target = scatterTarget;
    } else {
      target = chaseTargets[ghostIdx % chaseTargets.length];
    }
  }
  const candidates = ["up", "down", "left", "right"];
  let bestDir = ghost.dir;
  let bestScore = ghost.scared ? -1 : Infinity;
  for (const d of candidates) {
    if (ghost.scared && !ghost.eaten && d === opposite(ghost.dir)) continue;
    const v2 = dirVector(d);
    const nx = (tileX + v2.x) * TILE_SIZE + TILE_SIZE / 2;
    const ny = (tileY + v2.y) * TILE_SIZE + TILE_SIZE / 2;
    if (isGhostDoor(nx, ny)) {
      if (!ghost.eaten) continue;
    }
    if (isWall(nx, ny)) continue;
    const dist = manhattan({ x: nx / TILE_SIZE, y: ny / TILE_SIZE }, target);
    if (ghost.scared && !ghost.eaten) {
      if (dist > bestScore) {
        bestScore = dist;
        bestDir = d;
      }
    } else {
      if (dist < bestScore) {
        bestScore = dist;
        bestDir = d;
      }
    }
  }
  if (bestDir === ghost.dir) {
    const fallback = opposite(ghost.dir);
    const v2 = dirVector(fallback);
    const nx = (tileX + v2.x) * TILE_SIZE + TILE_SIZE / 2;
    const ny = (tileY + v2.y) * TILE_SIZE + TILE_SIZE / 2;
    if (!isWall(nx, ny)) {
      bestDir = fallback;
    } else {
      return;
    }
  }
  ghost.dir = bestDir;
  const v = dirVector(ghost.dir);
  ghost.x += v.x * speed;
  ghost.y += v.y * speed;
  if (ghost.x < -TILE_SIZE) ghost.x = CANVAS_W;
  if (ghost.x > CANVAS_W) ghost.x = -TILE_SIZE;
}

// src/pacman.ts
function createPacman() {
  return { x: 9 * TILE_SIZE, y: 15 * TILE_SIZE, direction: "none", nextDirection: "none", angle: 0.2, mouthDir: 1 };
}
function getMouthAngle(pacman2, frame) {
  const wave = Math.sin(frame * 0.15) * 0.3 + 0.3;
  return Math.max(0.05, wave);
}
function getPacmanPixelPos(pacman2) {
  return {
    x: pacman2.x ?? TILE_SIZE * 9,
    y: pacman2.y ?? TILE_SIZE * 15
  };
}
function resetPacman(pacman2) {
  pacman2.x = 9 * TILE_SIZE;
  pacman2.y = 15 * TILE_SIZE;
  pacman2.direction = "none";
  pacman2.nextDirection = "none";
  pacman2.angle = 0.2;
  pacman2.mouthDir = 1;
}

// src/dot.ts
var dots = [];
function initDots() {
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
function allDotsEaten() {
  return dots.every((d) => d.eaten);
}

// src/game.ts
var canvas = document.getElementById("game");
var ctx = canvas.getContext("2d");
canvas.width = CANVAS_W;
canvas.height = CANVAS_H;
var scoreEl = document.getElementById("score");
var highScoreEl = document.getElementById("highscore");
var messageEl = document.getElementById("message");
var gameState = "ready" /* READY */;
var score = 0;
var highScore = parseInt(localStorage.getItem("pacman_highscore") || "0");
var frameCount = 0;
var frightenTimer = 0;
var lives = 3;
var combo = 0;
var pacman = createPacman();
var ghosts = createGhosts();
var dots2 = initDots();
scoreEl.value = "SCORE: 0";
highScoreEl.value = `HIGH: ${highScore}`;
messageEl.value = "PRESS ENTER TO START";
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    if (gameState === "game_over" /* GAME_OVER */ || gameState === "won" /* WON */) {
      resetGame();
    }
    if (gameState === "ready" /* READY */) {
      gameState = "playing" /* PLAYING */;
      pacman.nextDirection = "right";
      pacman.direction = "right";
      messageEl.value = "";
    }
    return;
  }
  if (gameState !== "playing" /* PLAYING */) return;
  let dir = null;
  switch (e.key) {
    case "ArrowUp":
    case "w":
    case "W":
      dir = "up";
      break;
    case "ArrowDown":
    case "s":
    case "S":
      dir = "down";
      break;
    case "ArrowLeft":
    case "a":
    case "A":
      dir = "left";
      break;
    case "ArrowRight":
    case "d":
    case "D":
      dir = "right";
      break;
  }
  if (dir) {
    pacman.nextDirection = dir;
    e.preventDefault();
  }
});
function resetGame() {
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
  gameState = "ready" /* READY */;
  messageEl.value = "PRESS ENTER TO START";
  scoreEl.value = "SCORE: 0";
  draw();
}
function killPacman() {
  gameState = "dying" /* DYING */;
  lives--;
  setTimeout(() => {
    if (lives <= 0) {
      gameState = "game_over" /* GAME_OVER */;
      if (score > highScore) {
        highScore = score;
        localStorage.setItem("pacman_highscore", String(highScore));
        highScoreEl.value = `HIGH: ${highScore}`;
      }
      messageEl.value = "GAME OVER - PRESS ENTER";
    } else {
      resetPacman(pacman);
      gameState = "ready" /* READY */;
      messageEl.value = "PRESS ENTER TO START";
    }
  }, 1e3);
}
function drawWalls() {
  ctx.fillStyle = "#1a1aa0";
  const MAP2 = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 2, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 2, 2, 1],
    [1, 3, 1, 1, 2, 1, 1, 1, 2, 1, 2, 1, 1, 1, 2, 1, 1, 3, 1],
    [1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1],
    [1, 2, 1, 1, 2, 1, 2, 1, 1, 1, 1, 1, 2, 1, 2, 1, 1, 2, 1],
    [1, 2, 2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 2, 1],
    [1, 1, 1, 1, 2, 1, 1, 1, 0, 1, 0, 1, 1, 1, 2, 1, 1, 1, 1],
    [0, 0, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0],
    [1, 1, 1, 1, 2, 1, 0, 1, 1, 4, 1, 1, 0, 1, 2, 1, 1, 1, 1],
    [0, 0, 0, 0, 2, 0, 0, 1, 0, 0, 0, 1, 0, 0, 2, 0, 0, 0, 0],
    [1, 1, 1, 1, 2, 1, 0, 1, 1, 1, 1, 1, 0, 1, 2, 1, 1, 1, 1],
    [0, 0, 0, 1, 2, 1, 0, 0, 0, 0, 0, 0, 0, 1, 2, 1, 0, 0, 0],
    [1, 1, 1, 1, 2, 1, 2, 1, 1, 1, 1, 1, 2, 1, 2, 1, 1, 1, 1],
    [1, 2, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 2, 2, 1],
    [1, 2, 1, 1, 2, 1, 1, 1, 2, 1, 2, 1, 1, 1, 2, 1, 1, 2, 1],
    [1, 3, 2, 1, 2, 2, 2, 2, 2, 0, 2, 2, 2, 2, 2, 1, 2, 3, 1],
    [1, 1, 2, 1, 2, 1, 2, 1, 1, 1, 1, 1, 2, 1, 2, 1, 2, 1, 1],
    [1, 2, 2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 1, 2, 2, 2, 2, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
  ];
  for (let r = 0; r < MAP2.length; r++) {
    for (let c = 0; c < MAP2[r].length; c++) {
      if (MAP2[r][c] === 1) {
        ctx.fillRect(c * TILE_SIZE, r * TILE_SIZE, TILE_SIZE, TILE_SIZE);
        ctx.strokeStyle = "#3333ff";
        ctx.lineWidth = 0.5;
        ctx.strokeRect(c * TILE_SIZE + 0.5, r * TILE_SIZE + 0.5, TILE_SIZE - 1, TILE_SIZE - 1);
      }
    }
  }
}
function drawDot(dot) {
  if (dot.eaten) return;
  ctx.fillStyle = "#FFB8ae";
  ctx.beginPath();
  const r = dot.isPower ? 4 + Math.sin(frameCount * 0.1) * 1.5 : 2;
  ctx.arc(dot.x, dot.y, Math.max(1, r), 0, Math.PI * 2);
  ctx.fill();
}
function drawPacman() {
  const pos = getPacmanPixelPos(pacman);
  const cx = pos.x + TILE_SIZE / 2;
  const cy = pos.y + TILE_SIZE / 2;
  const r = TILE_SIZE / 2 - 2;
  const angle = getMouthAngle(pacman, frameCount);
  let rotation = 0;
  switch (pacman.direction) {
    case "right":
      rotation = 0;
      break;
    case "down":
      rotation = Math.PI / 2;
      break;
    case "left":
      rotation = Math.PI;
      break;
    case "up":
      rotation = -Math.PI / 2;
      break;
  }
  ctx.fillStyle = "#FFFF00";
  ctx.beginPath();
  ctx.arc(cx, cy, r, rotation + angle, rotation + Math.PI * 2 - angle);
  ctx.lineTo(cx, cy);
  ctx.closePath();
  ctx.fill();
  const eyeOffX = Math.cos(rotation - 0.5) * r * 0.4;
  const eyeOffY = Math.sin(rotation - 0.5) * r * 0.4;
  ctx.fillStyle = "#000";
  ctx.beginPath();
  ctx.arc(cx + eyeOffX, cy + eyeOffY, 2, 0, Math.PI * 2);
  ctx.fill();
}
function drawGhost(ghost, idx) {
  if (ghost.spawnTimer > 0 && ghost.spawnTimer % 10 < 5) return;
  const cx = ghost.x + TILE_SIZE / 2;
  const cy = ghost.y + TILE_SIZE / 2;
  const r = TILE_SIZE / 2 - 2;
  const color = getGhostBodyColor(ghost.scared, frightenTimer, idx);
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
    ctx.fillStyle = "#FFFFFF";
    ctx.beginPath();
    ctx.arc(cx - 3, cy - 3, 2, 0, Math.PI * 2);
    ctx.arc(cx + 3, cy - 3, 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#FFFFFF";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 5, cy + 3);
    for (let i = 0; i < 4; i++) {
      ctx.lineTo(cx - 5 + i * 3, cy + (i % 2 === 0 ? 3 : 6));
    }
    ctx.stroke();
  } else {
    ctx.fillStyle = "#FFFFFF";
    ctx.beginPath();
    ctx.ellipse(cx - 4, cy - 3, 4, 5, 0, 0, Math.PI * 2);
    ctx.ellipse(cx + 4, cy - 3, 4, 5, 0, 0, Math.PI * 2);
    ctx.fill();
    const pp = getPacmanPixelPos(pacman);
    const dx = pp.x - ghost.x;
    const dy = pp.y - ghost.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const px = cx + dx / dist * 2;
    const py = cy + dy / dist * 2;
    ctx.fillStyle = "#0000CC";
    ctx.beginPath();
    ctx.arc(px - 4, py, 2, 0, Math.PI * 2);
    ctx.arc(px + 4, py, 2, 0, Math.PI * 2);
    ctx.fill();
  }
}
function draw() {
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
  drawWalls();
  ctx.fillStyle = "#FFB8FF";
  ctx.fillRect(9 * TILE_SIZE, 8 * TILE_SIZE + 10, TILE_SIZE, 4);
  for (const d of dots2) drawDot(d);
  for (let i = 0; i < ghosts.length; i++) drawGhost(ghosts[i], i);
  if (gameState !== "dying" /* DYING */) {
    drawPacman();
  } else {
    const pos = getPacmanPixelPos(pacman);
    const cx = pos.x + TILE_SIZE / 2;
    const cy = pos.y + TILE_SIZE / 2;
    const shrink = Math.max(0, Math.sin(frameCount * 0.3) * TILE_SIZE / 2);
    ctx.fillStyle = "#FFFF00";
    ctx.beginPath();
    ctx.arc(cx, cy, shrink, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = "#FFFF00";
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
function update() {
  if (gameState !== "playing" /* PLAYING */) {
    frameCount++;
    draw();
    requestAnimationFrame(update);
    return;
  }
  frameCount++;
  const moveDir = pacman.nextDirection;
  const mv = {
    x: moveDir === "left" ? -1 : moveDir === "right" ? 1 : 0,
    y: moveDir === "up" ? -1 : moveDir === "down" ? 1 : 0
  };
  if (mv.x !== 0 || mv.y !== 0) {
    const nx = (pacman.x ?? TILE_SIZE * 9) + mv.x * 2;
    const ny = (pacman.y ?? TILE_SIZE * 15) + mv.y * 2;
    if (!isWall(nx, ny)) {
      pacman.x = nx;
      pacman.y = ny;
      pacman.direction = moveDir;
    }
  }
  if ((pacman.x ?? 0) < -TILE_SIZE) pacman.x = 18 * TILE_SIZE;
  if ((pacman.x ?? 0) > 18 * TILE_SIZE) pacman.x = 0;
  const pPx = pacman.x ?? TILE_SIZE * 9;
  const pPy = pacman.y ?? TILE_SIZE * 15;
  for (const d of dots2) {
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
  if (frightenTimer > 0) {
    frightenTimer--;
    if (frightenTimer === 0) {
      for (const g of ghosts) g.scared = false;
    }
  }
  for (let i = 0; i < ghosts.length; i++) {
    const g = ghosts[i];
    const inHouse = g.spawnTimer > 0;
    moveGhost(g, i, pPx / TILE_SIZE | 0, pPy / TILE_SIZE | 0, g.scatterTarget, inHouse);
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
  if (allDotsEaten()) {
    gameState = "won" /* WON */;
    if (score > highScore) {
      highScore = score;
      localStorage.setItem("pacman_highscore", String(highScore));
      highScoreEl.value = `HIGH: ${highScore}`;
    }
    messageEl.value = "YOU WIN - PRESS ENTER";
  }
  draw();
  requestAnimationFrame(update);
}
highScoreEl.value = `HIGH: ${highScore}`;
draw();
requestAnimationFrame(update);
