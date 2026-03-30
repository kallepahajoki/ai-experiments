#!/usr/bin/env python3
"""
Generate training data for fine-tuning Qwen 3.5 27B to fix
Next.js server-side module resolution errors.

The target pattern:
- Next.js build fails with "Module not found: Can't resolve 'X'" for Node.js built-ins
- The fix: add webpack externals for server-side bundles in next.config
- Must include transitive dependencies (e.g. pg → pgpass, split2, net, dns, stream)

Output: JSONL file with chat-format training examples.
"""

import json
import random
import itertools
from pathlib import Path

# ---------------------------------------------------------------------------
# Building blocks for synthetic examples
# ---------------------------------------------------------------------------

# Node.js built-in modules that commonly cause this error
NODE_BUILTINS = [
    "crypto", "net", "fs", "fs/promises", "path", "events",
    "stream", "dns", "tls", "http", "https", "os", "child_process",
    "util", "zlib", "buffer", "querystring",
]

# npm packages that use Node built-ins internally and need externalizing
SERVER_NPM_PACKAGES = {
    "pg": {"transitive": ["pgpass", "split2", "pg-pool", "pg-protocol"], "uses": ["net", "dns", "stream", "tls", "crypto"]},
    "better-sqlite3": {"transitive": [], "uses": ["fs", "path"]},
    "bcrypt": {"transitive": [], "uses": ["crypto"]},
    "sharp": {"transitive": [], "uses": ["fs", "path", "stream"]},
    "nodemailer": {"transitive": [], "uses": ["net", "tls", "dns", "stream", "crypto"]},
    "mongoose": {"transitive": ["mongodb"], "uses": ["net", "dns", "tls", "stream", "crypto", "os", "zlib"]},
    "ioredis": {"transitive": [], "uses": ["net", "tls", "dns", "stream", "events"]},
    "ws": {"transitive": [], "uses": ["net", "tls", "http", "https", "stream", "events", "crypto"]},
    "ssh2": {"transitive": [], "uses": ["net", "tls", "dns", "stream", "crypto", "events"]},
    "knex": {"transitive": [], "uses": ["fs", "path", "stream", "events"]},
}

# Realistic source file scenarios that import Node built-ins
SOURCE_FILE_SCENARIOS = [
    {
        "filename": "lib/auth/tokens.ts",
        "imports": ["crypto"],
        "purpose": "JWT token signing and verification",
        "code_snippet": """import { createHmac, randomBytes } from 'crypto';

export function generateToken(payload: Record<string, unknown>): string {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const signature = createHmac('sha256', process.env.JWT_SECRET!)
    .update(`${header}.${body}`)
    .digest('base64url');
  return `${header}.${body}.${signature}`;
}""",
    },
    {
        "filename": "lib/socket/connection.ts",
        "imports": ["net", "events"],
        "purpose": "TCP socket connection manager",
        "code_snippet": """import { createConnection, Socket } from 'net';
import { EventEmitter } from 'events';

export class SocketManager extends EventEmitter {
  private socket: Socket | null = null;

  async connect(host: string, port: number): Promise<void> {
    this.socket = createConnection(port, host);
    this.socket.on('data', (data) => this.emit('data', data));
  }
}""",
    },
    {
        "filename": "lib/storage/files.ts",
        "imports": ["fs/promises", "path"],
        "purpose": "File storage utilities",
        "code_snippet": """import fs from 'fs/promises';
import path from 'path';

export async function saveUpload(filename: string, data: Buffer): Promise<string> {
  const uploadDir = path.join(process.cwd(), 'uploads');
  await fs.mkdir(uploadDir, { recursive: true });
  const filePath = path.join(uploadDir, filename);
  await fs.writeFile(filePath, data);
  return filePath;
}""",
    },
    {
        "filename": "lib/encryption/store.ts",
        "imports": ["crypto"],
        "purpose": "AES-256-GCM encrypted credential storage",
        "code_snippet": """import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from 'crypto';

export function encrypt(plaintext: string, key: Buffer): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, iv);
  const ct = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return [iv, tag, ct].map(b => b.toString('hex')).join(':');
}""",
    },
    {
        "filename": "lib/mailer/transport.ts",
        "imports": ["net", "tls", "dns"],
        "purpose": "SMTP email transport",
        "code_snippet": """import { connect, Socket } from 'net';
import { connect as tlsConnect } from 'tls';
import { resolve } from 'dns';

export class SMTPTransport {
  private socket: Socket | null = null;

  async connectToMX(domain: string): Promise<void> {
    const host = await this.resolveMX(domain);
    this.socket = connect(25, host);
  }

  private resolveMX(domain: string): Promise<string> {
    return new Promise((res, rej) =>
      resolve(domain, (err, addrs) => err ? rej(err) : res(addrs[0]))
    );
  }
}""",
    },
    {
        "filename": "lib/worker/process.ts",
        "imports": ["child_process", "events"],
        "purpose": "Background worker process manager",
        "code_snippet": """import { fork, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';

export class WorkerManager extends EventEmitter {
  private workers: Map<string, ChildProcess> = new Map();

  spawn(script: string, id: string): void {
    const child = fork(script);
    this.workers.set(id, child);
    child.on('message', (msg) => this.emit('result', { id, msg }));
  }
}""",
    },
    {
        "filename": "lib/compression/gzip.ts",
        "imports": ["zlib", "stream"],
        "purpose": "Response compression middleware",
        "code_snippet": """import { createGzip, createGunzip } from 'zlib';
import { pipeline, Readable } from 'stream';

export async function compressBuffer(input: Buffer): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    const gzip = createGzip();
    const source = Readable.from(input);
    pipeline(source, gzip, (err) => err ? reject(err) : resolve(Buffer.concat(chunks)));
    gzip.on('data', (chunk) => chunks.push(chunk));
  });
}""",
    },
    {
        "filename": "lib/db/pool.ts",
        "imports": ["events"],
        "purpose": "PostgreSQL connection pool with event-based health monitoring",
        "code_snippet": """import { Pool } from 'pg';
import { EventEmitter } from 'events';

export class DatabasePool extends EventEmitter {
  private pool: Pool;

  constructor(connectionString: string) {
    super();
    this.pool = new Pool({ connectionString });
    this.pool.on('error', (err) => this.emit('error', err));
    this.pool.on('connect', () => this.emit('ready'));
  }

  async query(sql: string, params?: unknown[]) {
    return this.pool.query(sql, params);
  }
}""",
    },
    {
        "filename": "lib/db/migrations.ts",
        "imports": ["fs/promises", "path", "crypto"],
        "purpose": "Database migration runner with checksum verification",
        "code_snippet": """import fs from 'fs/promises';
import path from 'path';
import { createHash } from 'crypto';
import { Pool } from 'pg';

export async function runMigrations(pool: Pool): Promise<void> {
  const migrationsDir = path.join(process.cwd(), 'migrations');
  const files = await fs.readdir(migrationsDir);
  for (const file of files.sort()) {
    const sql = await fs.readFile(path.join(migrationsDir, file), 'utf-8');
    const checksum = createHash('md5').update(sql).digest('hex');
    await pool.query(sql);
  }
}""",
    },
    {
        "filename": "lib/realtime/pubsub.ts",
        "imports": ["events", "crypto"],
        "purpose": "Pub/sub event bus for real-time updates",
        "code_snippet": """import { EventEmitter } from 'events';
import { randomUUID } from 'crypto';

export class PubSub extends EventEmitter {
  private subscriptions = new Map<string, Set<string>>();

  subscribe(channel: string): string {
    const id = randomUUID();
    if (!this.subscriptions.has(channel)) {
      this.subscriptions.set(channel, new Set());
    }
    this.subscriptions.get(channel)!.add(id);
    return id;
  }

  publish(channel: string, data: unknown): void {
    this.emit(channel, { id: randomUUID(), data, timestamp: Date.now() });
  }
}""",
    },
]

# Import chain patterns (how the server file gets pulled into the webpack build)
IMPORT_CHAINS = [
    {
        "entry": "instrumentation.ts",
        "description": "Next.js instrumentation hook",
        "chain": ["instrumentation.ts", "{router}", "{source_file}"],
    },
    {
        "entry": "app/api/[route]/route.ts",
        "description": "API route handler",
        "chain": ["app/api/{name}/route.ts", "{source_file}"],
    },
    {
        "entry": "middleware.ts",
        "description": "Next.js middleware",
        "chain": ["middleware.ts", "lib/auth/middleware.ts", "{source_file}"],
    },
    {
        "entry": "app/layout.tsx",
        "description": "Root layout (Server Component)",
        "chain": ["app/layout.tsx", "lib/providers.tsx", "{source_file}"],
    },
]

# Config file variations - use $PLACEHOLDER$ style to avoid brace conflicts
CONFIG_TEMPLATES = {
    "js_basic": {
        "filename": "next.config.js",
        "before": """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: [$EXISTING_EXTERNALS$],
  },
};

module.exports = nextConfig;""",
        "after": """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: [$EXISTING_EXTERNALS$],
  },
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
$EXTERNALS_LIST$
      ];
    }
    return config;
  },
};

module.exports = nextConfig;""",
    },
    "js_instrumentation": {
        "filename": "next.config.js",
        "before": """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    instrumentationHook: true,
    serverComponentsExternalPackages: [$EXISTING_EXTERNALS$],
  },
};

module.exports = nextConfig;""",
        "after": """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    instrumentationHook: true,
    serverComponentsExternalPackages: [$EXISTING_EXTERNALS$],
  },
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
$EXTERNALS_LIST$
      ];
    }
    return config;
  },
};

module.exports = nextConfig;""",
    },
    "mjs_basic": {
        "filename": "next.config.mjs",
        "before": """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: [$EXISTING_EXTERNALS$],
  },
};

export default nextConfig;""",
        "after": """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: [$EXISTING_EXTERNALS$],
  },
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
$EXTERNALS_LIST$
      ];
    }
    return config;
  },
};

export default nextConfig;""",
    },
    "mjs_instrumentation": {
        "filename": "next.config.mjs",
        "before": """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    instrumentationHook: true,
    serverComponentsExternalPackages: [$EXISTING_EXTERNALS$],
  },
};

export default nextConfig;""",
        "after": """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    instrumentationHook: true,
    serverComponentsExternalPackages: [$EXISTING_EXTERNALS$],
  },
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
$EXTERNALS_LIST$
      ];
    }
    return config;
  },
};

export default nextConfig;""",
    },
}

# Wrong approaches the model should learn to avoid
WRONG_APPROACHES = [
    {
        "approach": "resolve.fallback",
        "explanation": "Setting resolve.fallback to false silences the build error but makes the modules undefined at runtime, causing crashes when the code actually runs.",
        "wrong_code": """webpack: (config, { isServer }) => {
    if (isServer) {
      config.resolve = config.resolve || {};
      config.resolve.fallback = {
        ...config.resolve.fallback,
        crypto: false,
        net: false,
      };
    }
    return config;
  },""",
    },
    {
        "approach": "resolve.fallback on client",
        "explanation": "Setting resolve.fallback on the client side (!isServer) is backwards - the modules need to be available on the server, and they're already unavailable on the client. The fix needs to externalize them from the server bundle.",
        "wrong_code": """webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        crypto: false,
        net: false,
        fs: false,
      };
    }
    return config;
  },""",
    },
    {
        "approach": "serverComponentsExternalPackages with builtins",
        "explanation": "serverComponentsExternalPackages is designed for npm packages, not Node.js built-in modules. It may not work correctly for built-ins and doesn't apply to all server contexts like instrumentation hooks.",
        "wrong_code": """experimental: {
    serverComponentsExternalPackages: ['crypto', 'net', 'fs', 'path', 'events'],
  },""",
    },
]

# ---------------------------------------------------------------------------
# No system prompt — agentic use doesn't have one. The model should learn
# to recognise the error pattern from build output alone.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Example generators
# ---------------------------------------------------------------------------

def generate_build_error(filename: str, module: str, line: int, code_lines: list[str], import_trace: list[str]) -> str:
    """Generate a realistic Next.js build error message."""
    # Show a few lines of context around the error
    ctx_start = max(0, line - 2)
    ctx_end = min(len(code_lines), line + 2)

    error_display = []
    for i in range(ctx_start, ctx_end):
        ln = i + 1
        marker = ">" if i == line - 1 else " "
        error_display.append(f"[0m{marker}[90m{ln:>3} |[39m {code_lines[i]}[0m")
        if i == line - 1:
            error_display.append(f"[0m [90m    |[39m [31m[1m^[22m[39m[0m")

    trace = "\n".join(f"./{t}" for t in import_trace)

    return f"""./{filename}:{line}:1
Module not found: Can't resolve '{module}'
{'chr(10)'.join(error_display)}

https://nextjs.org/docs/messages/module-not-found

Import trace for requested module:
{trace}"""


# Agentic user prompts — short directives an agent or user might give
AGENTIC_USER_PROMPTS = [
    "Fix the Next.js build error.",
    "The build is failing. Fix it.",
    "npm run build fails. Debug and fix.",
    "Build is broken, fix the webpack errors.",
    "Fix the Module not found errors in the build.",
    "The Next.js production build fails. Fix it.",
    "Debug and fix the build failure.",
]


def _build_example_data(
    source_files: list[dict],
    npm_packages: list[str],
    config_template_key: str,
    import_chain_template: dict,
    include_wrong_approach: bool = False,
    existing_externals: list[str] | None = None,
) -> dict:
    """Build the raw data for a training example (build output, config, fix, explanation).

    Returns a dict with keys: build_output, config_before, config_after,
    config_filename, assistant_msg.
    """

    existing_externals = existing_externals or []
    config_template = CONFIG_TEMPLATES[config_template_key]

    # Collect all modules that will fail
    failing_modules = []
    for sf in source_files:
        for imp in sf["imports"]:
            if imp not in failing_modules:
                failing_modules.append(imp)

    # Collect all modules that need externalizing (including transitive)
    all_externals = list(failing_modules)
    for pkg_name in npm_packages:
        if pkg_name not in all_externals:
            all_externals.append(pkg_name)
        pkg_info = SERVER_NPM_PACKAGES.get(pkg_name, {})
        for trans in pkg_info.get("transitive", []):
            if trans not in all_externals:
                all_externals.append(trans)

    # Build error messages
    errors = []
    for sf in source_files:
        code_lines = sf["code_snippet"].strip().split("\n")
        for imp in sf["imports"]:
            # Find the line that imports this module
            import_line = 1
            for i, line in enumerate(code_lines):
                if f"'{imp}'" in line or f'"{imp}"' in line:
                    import_line = i + 1
                    break

            # Build import trace
            chain = list(import_chain_template["chain"])
            chain = [c.replace("{source_file}", sf["filename"]) for c in chain]
            chain = [c.replace("{router}", sf.get("router_file", "lib/router.ts")) for c in chain]
            chain = [c.replace("{name}", "webhook") for c in chain]
            # Reverse so the source file is last
            trace = list(reversed(chain))

            errors.append(generate_build_error(
                sf["filename"], imp, import_line, code_lines, trace
            ))

    build_output = f"""  ▲ Next.js 14.2.15

   Creating an optimized production build ...
Failed to compile.

{"".join(errors)}

> Build failed because of webpack errors"""

    # Build the config file content
    existing_ext_str = ", ".join(f"'{e}'" for e in existing_externals)
    config_before = config_template["before"].replace("$EXISTING_EXTERNALS$", existing_ext_str)

    # Build externals list for the fix
    externals_entries = []
    for ext in all_externals:
        externals_entries.append(f"        '{ext}',")
    externals_list = "\n".join(externals_entries)

    config_after = config_template["after"].replace(
        "$EXISTING_EXTERNALS$", existing_ext_str
    ).replace("$EXTERNALS_LIST$", externals_list)

    # Build assistant response
    file_descriptions = []
    for sf in source_files:
        mods = ", ".join(f"`{m}`" for m in sf["imports"])
        file_descriptions.append(f"- `{sf['filename']}` imports {mods} ({sf['purpose']})")

    pkg_descriptions = []
    for pkg_name in npm_packages:
        pkg_info = SERVER_NPM_PACKAGES.get(pkg_name, {})
        uses = ", ".join(f"`{u}`" for u in pkg_info.get("uses", []))
        trans = pkg_info.get("transitive", [])
        trans_str = f" (which pulls in {', '.join(f'`{t}`' for t in trans)})" if trans else ""
        pkg_descriptions.append(f"- `{pkg_name}`{trans_str} internally uses {uses}")

    explanation_parts = [
        "The build fails because webpack is trying to bundle Node.js built-in modules that are only available at runtime on the server. The import trace shows these server-only files are being pulled into the webpack bundle.",
        "",
        "**Affected files:**",
        *file_descriptions,
    ]

    if pkg_descriptions:
        explanation_parts.extend([
            "",
            "**Server-only npm packages also need externalizing:**",
            *pkg_descriptions,
        ])

    explanation_parts.extend([
        "",
        "**The fix:** Add a webpack configuration that externalizes these modules from the server bundle. This tells webpack \"these modules exist at runtime, don't try to bundle them.\"",
        "",
        "**Important:** Don't use `resolve.fallback: { module: false }` — that silences the error but makes the modules `undefined` at runtime, causing crashes.",
        "",
        f"Update `{config_template['filename']}`:",
        f"```javascript\n{config_after}\n```",
    ])

    assistant_msg = "\n".join(explanation_parts)

    # Optionally prepend a wrong approach discussion
    if include_wrong_approach:
        wrong = random.choice(WRONG_APPROACHES)
        wrong_discussion = f"""I see this pattern sometimes attempted but it's incorrect:

```javascript
{wrong['wrong_code']}
```

This won't work because: {wrong['explanation']}

The correct approach is to use webpack `externals`:

"""
        assistant_msg = wrong_discussion + assistant_msg

    return {
        "build_output": build_output,
        "config_before": config_before,
        "config_after": config_after,
        "config_filename": config_template["filename"],
        "assistant_msg": assistant_msg,
    }


def generate_example(
    source_files: list[dict],
    npm_packages: list[str],
    config_template_key: str,
    import_chain_template: dict,
    include_wrong_approach: bool = False,
    existing_externals: list[str] | None = None,
) -> dict:
    """Generate one plain-format training example (user/assistant)."""

    data = _build_example_data(
        source_files, npm_packages, config_template_key,
        import_chain_template, include_wrong_approach, existing_externals,
    )

    user_msg = f"""`npm run build` output:

```
{data['build_output']}
```

{data['config_filename']}:
```javascript
{data['config_before']}
```"""

    return {
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": data["assistant_msg"]},
        ]
    }


def generate_tool_use_example(
    source_files: list[dict],
    npm_packages: list[str],
    config_template_key: str,
    import_chain_template: dict,
    include_wrong_approach: bool = False,
    existing_externals: list[str] | None = None,
) -> dict:
    """Generate a tool-use formatted training example.

    Simulates an agentic flow where build output and config arrive as tool
    results (role: "tool"), matching the <tool_response> wrapper that Qwen 3.5's
    chat template renders at inference time.
    """

    data = _build_example_data(
        source_files, npm_packages, config_template_key,
        import_chain_template, include_wrong_approach, existing_externals,
    )

    user_prompt = random.choice(AGENTIC_USER_PROMPTS)

    return {
        "messages": [
            # User asks to fix the build
            {"role": "user", "content": user_prompt},
            # Assistant runs the build
            {
                "role": "assistant",
                "content": "Let me run the build to see the errors.",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": {"command": "npm run build"},
                        },
                    }
                ],
            },
            # Build output arrives as tool result
            {"role": "tool", "content": data["build_output"]},
            # Assistant reads the config
            {
                "role": "assistant",
                "content": f"The build has Module not found errors for Node.js built-ins. Let me check the webpack config.",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": {"path": data["config_filename"]},
                        },
                    }
                ],
            },
            # Config arrives as tool result
            {"role": "tool", "content": data["config_before"]},
            # Assistant provides the fix
            {"role": "assistant", "content": data["assistant_msg"]},
        ]
    }


def generate_tool_response_only_example(
    source_files: list[dict],
    npm_packages: list[str],
    config_template_key: str,
    import_chain_template: dict,
    include_wrong_approach: bool = False,
    existing_externals: list[str] | None = None,
) -> dict:
    """Generate a minimal example: just the build error as a lone tool result.

    The model must recognise the pattern from the <tool_response> alone —
    no user request, no config read.  This forces the LoRA to activate on
    the error text itself rather than relying on surrounding context.
    """

    data = _build_example_data(
        source_files, npm_packages, config_template_key,
        import_chain_template, include_wrong_approach, existing_externals,
    )

    user_prompt = random.choice(AGENTIC_USER_PROMPTS)

    return {
        "messages": [
            # Brief user request — required by Qwen's chat template
            {"role": "user", "content": user_prompt},
            # Assistant runs the build — no config read step
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": {"command": "npm run build"},
                        },
                    }
                ],
            },
            # Just the build error — nothing else
            {"role": "tool", "content": data["build_output"]},
            # Model must identify the problem and provide the fix
            {"role": "assistant", "content": data["assistant_msg"]},
        ]
    }


def generate_real_ai_toolkit_example() -> dict:
    """Generate the training example based on the actual ai-toolkit project."""

    build_output = """  ▲ Next.js 14.2.15
  - Environments: .env.local
  - Experiments (use with caution):
    · instrumentationHook

   Creating an optimized production build ...
Failed to compile.

./lib/calendar/caldav.ts:9:1
Module not found: Can't resolve 'crypto'
  7 | import { createDAVClient, DAVClient, DAVCalendar, DAVCalendarObject } from 'tsdav';
  8 | import ICAL from 'ical.js';
> 9 | import { randomUUID } from 'crypto';
    | ^
 10 | import { CalendarProvider, CalendarEvent, FreeBusyQuery } from './types';

https://nextjs.org/docs/messages/module-not-found

Import trace for requested module:
./lib/calendar/unified.ts
./lib/signal/router.ts
./instrumentation.ts

./lib/calendar/token-store.ts:12:1
Module not found: Can't resolve 'crypto'
 10 | */
 11 |
> 12 | import {
    | ^
 13 |   createCipheriv,
 14 |   createDecipheriv,
 15 |   randomBytes,

https://nextjs.org/docs/messages/module-not-found

Import trace for requested module:
./lib/calendar/unified.ts
./lib/signal/router.ts
./instrumentation.ts

./lib/signal/adapter.ts:1:1
Module not found: Can't resolve 'net'
> 1 | import { createConnection, connect, Socket } from 'net';
    | ^
  2 | import { EventEmitter } from 'events';
  3 | import { SignalConfig } from './config';

https://nextjs.org/docs/messages/module-not-found

Import trace for requested module:
./instrumentation.ts

./lib/signal/clients.ts:9:1
Module not found: Can't resolve 'fs/promises'
  7 | */
  8 |
> 9 | import fs from 'fs/promises';
    | ^
 10 | import path from 'path';

https://nextjs.org/docs/messages/module-not-found

Import trace for requested module:
./lib/signal/router.ts
./instrumentation.ts

./lib/signal/clients.ts:10:1
Module not found: Can't resolve 'path'
  9 | import fs from 'fs/promises';
> 10 | import path from 'path';
    | ^
 11 |
 12 | const FORGE_SECRET = process.env.FORGE_SECRET || 'anvil-internal';

https://nextjs.org/docs/messages/module-not-found

Import trace for requested module:
./lib/signal/router.ts
./instrumentation.ts


> Build failed because of webpack errors"""

    config_before = """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    instrumentationHook: true,
    serverComponentsExternalPackages: ['crypto', 'net', 'fs', 'path'],
  },
};

module.exports = nextConfig;"""

    config_after = """/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    instrumentationHook: true,
  },
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'crypto',
        'net',
        'fs',
        'fs/promises',
        'path',
        'stream',
        'dns',
        'events',
        'pg',
        'pgpass',
        'split2',
      ];
    }
    return config;
  },
};

module.exports = nextConfig;"""

    user_msg = f"""`npm run build` output:

```
{build_output}
```

next.config.js:
```javascript
{config_before}
```

The project also has `pg` (PostgreSQL) as a dependency, used in `lib/calendar/token-store.ts`."""

    assistant_msg = f"""The build fails because webpack is trying to bundle Node.js built-in modules that are only available at runtime on the server. The import trace shows these files are pulled in through `instrumentation.ts` → signal/calendar modules.

**Root cause:** The `serverComponentsExternalPackages` config only applies to Server Components, not to all server contexts like the instrumentation hook. And it's designed for npm packages, not Node.js built-in modules.

**Affected modules:**
- `crypto` — used in `caldav.ts` (UUID generation) and `token-store.ts` (AES-256-GCM encryption)
- `net`, `events` — used in `adapter.ts` (TCP socket to signal-cli)
- `fs/promises`, `path` — used in `clients.ts` (file I/O for attachments)

**Transitive dependencies that also need externalizing:**
- `pg` (PostgreSQL driver) — used in `token-store.ts`, internally uses `net`, `dns`, `stream`
- `pgpass`, `split2` — pulled in by `pg`

**The fix:** Use webpack `externals` to tell webpack these modules exist at runtime and shouldn't be bundled. Remove the built-ins from `serverComponentsExternalPackages` since that's not the right mechanism here.

**Important:** Don't use `resolve.fallback: {{ crypto: false }}` — that silences the build error but makes the modules `undefined` at runtime, causing crashes when the encryption or socket code actually runs.

Update `next.config.js`:
```javascript
{config_after}
```

This tells webpack to skip bundling these modules for the server — they'll be resolved from Node.js at runtime, which is exactly what you want for built-in modules and native npm packages."""

    return {
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_negative_example_fallback() -> dict:
    """Generate an example where the model should NOT use resolve.fallback."""

    user_msg = """`npm run build` output:

```
./lib/db/connection.ts:1:1
Module not found: Can't resolve 'net'
> 1 | import { createConnection } from 'net';
    | ^

Import trace for requested module:
./lib/db/connection.ts
./instrumentation.ts
```

Current webpack config uses resolve.fallback — build passes but runtime crashes with `TypeError: Cannot read properties of undefined (reading 'createConnection')`:
```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.resolve = config.resolve || {};
      config.resolve.fallback = {
        ...config.resolve.fallback,
        net: false,
        dns: false,
      };
    }
    return config;
  },
```"""

    assistant_msg = """The issue is that `resolve.fallback: { net: false }` tells webpack "don't provide a polyfill and resolve to `undefined`." The build succeeds because webpack no longer tries to find the module, but at runtime `net` is `undefined`, so `createConnection` fails.

**The correct approach is `externals`, not `resolve.fallback`:**

`externals` tells webpack "this module exists at runtime, don't bundle it — just leave the `require('net')` call as-is." Node.js will then resolve it normally when the server starts.

```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'net',
        'dns',
      ];
    }
    return config;
  },
```

The key distinction:
- `resolve.fallback: { net: false }` → module becomes `undefined` (build passes, runtime crashes)
- `externals: ['net']` → module resolved from Node.js at runtime (build passes, runtime works)"""

    return {
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_negative_example_client_side() -> dict:
    """Example where someone applies the fix to the wrong side."""

    user_msg = """`npm run build` output:

```
./lib/crypto/hash.ts:1:1
Module not found: Can't resolve 'crypto'
> 1 | import { createHash } from 'crypto';
    | ^

Import trace for requested module:
./app/api/auth/route.ts
```

next.config.js:
```javascript
const nextConfig = {
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        crypto: false,
      };
    }
    return config;
  },
};
module.exports = nextConfig;
```"""

    assistant_msg = """Two problems:

1. **Wrong side:** Your config only runs for `!isServer` (client bundle). The error is in a server-side API route (`app/api/auth/route.ts`), so you need to configure the server bundle.

2. **Wrong mechanism:** `resolve.fallback: { crypto: false }` makes the module `undefined`, not available. You need `externals` which tells webpack to leave the import as a runtime require.

Fix:
```javascript
const nextConfig = {
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'crypto',
      ];
    }
    return config;
  },
};
module.exports = nextConfig;
```

This tells webpack: "when building the server bundle, don't try to bundle `crypto` — it's available from Node.js at runtime.\""""

    return {
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_transitive_deps_example() -> dict:
    """Example focusing on the need to externalize transitive dependencies."""

    user_msg = """`npm run build` output:

```
./node_modules/pg/lib/connection.js
Module not found: Can't resolve 'net'

Import trace for requested module:
./node_modules/pg/lib/client.js
./node_modules/pg/lib/index.js
./lib/db.ts
./instrumentation.ts
```

Current webpack config already externalizes direct builtins:
```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'crypto',
        'net',
      ];
    }
    return config;
  },
```"""

    assistant_msg = """No — you can't modify code inside `node_modules`. The issue is that `pg` (the PostgreSQL driver) internally imports Node.js built-ins like `net`, `dns`, `stream`, `tls`, and `crypto`. When webpack processes `pg` for the server bundle, it tries to bundle those too.

The fix is to externalize `pg` itself (and its dependencies that also use Node built-ins) so webpack doesn't try to bundle any of it:

```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'crypto',
        'net',
        'stream',
        'dns',
        'tls',
        'pg',
        'pgpass',
        'split2',
        'pg-pool',
        'pg-protocol',
      ];
    }
    return config;
  },
```

**Why externalize `pg` instead of just its Node.js imports?**
When you externalize `pg`, webpack emits `require('pg')` as-is. Node.js then loads `pg` from `node_modules` at runtime, and `pg` naturally resolves its own `net`/`dns`/etc. imports through Node's module system. This is cleaner and more reliable than trying to externalize every transitive built-in.

`pgpass` and `split2` are direct dependencies of `pg` that may also trigger bundling issues, so include them too."""

    return {
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_pg_progressive_fix_example() -> dict:
    """Example where user fixes builtins first, then discovers pg transitive deps."""

    user_msg = """`npm run build` output:

```
./node_modules/pgpass/lib/index.js
Module not found: Can't resolve 'fs'

Import trace for requested module:
./node_modules/pgpass/lib/index.js
./node_modules/pg/lib/client.js
./lib/db.ts
./instrumentation.ts

./node_modules/split2/index.js
Module not found: Can't resolve 'stream'

Import trace for requested module:
./node_modules/split2/index.js
./node_modules/pgpass/lib/index.js
./node_modules/pg/lib/client.js
./lib/db.ts
./instrumentation.ts
```

Current webpack config:
```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'crypto',
        'net',
        'fs',
        'path',
        'events',
        'pg',
      ];
    }
    return config;
  },
```"""

    assistant_msg = """Externalizing `pg` tells webpack not to bundle `pg` itself, but webpack still processes `pg`'s dependencies (`pgpass`, `split2`, `pg-pool`, `pg-protocol`) because they're separate packages in `node_modules`.

You need to externalize these transitive dependencies too:

```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'crypto',
        'net',
        'fs',
        'path',
        'events',
        'stream',
        'pg',
        'pgpass',
        'split2',
        'pg-pool',
        'pg-protocol',
      ];
    }
    return config;
  },
```

**Why this happens:** `pg` has dependencies like `pgpass` (reads ~/.pgpass files using `fs`) and `split2` (stream splitter using `stream`). These are separate npm packages, so externalizing `pg` alone doesn't cover them. Each package that uses Node.js built-ins needs to be externalized individually, or you externalize the entire dependency chain.

A good rule of thumb: if you see errors from `node_modules/X/...`, add `X` to externals."""

    return {
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_mongoose_transitive_example() -> dict:
    """Example with mongoose transitive deps to reinforce the pattern."""

    user_msg = """`npm run build` output:

```
./node_modules/mongodb/lib/cmap/connect.js
Module not found: Can't resolve 'net'

Import trace for requested module:
./node_modules/mongodb/lib/index.js
./node_modules/mongoose/lib/index.js
./lib/models/user.ts
./app/api/users/route.ts
```

Current webpack config:
```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'mongoose',
      ];
    }
    return config;
  },
```"""

    assistant_msg = """Same pattern as other database drivers — `mongoose` depends on `mongodb`, which is a separate package in `node_modules`. Externalizing `mongoose` doesn't cover `mongodb`.

You need to externalize the full dependency chain plus the Node.js built-ins they use:

```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'net',
        'dns',
        'tls',
        'stream',
        'crypto',
        'os',
        'zlib',
        'events',
        'mongoose',
        'mongodb',
      ];
    }
    return config;
  },
```

**The pattern:** When you see a build error from `node_modules/X/...` where X is a dependency of a package you already externalized, add X to externals too. Database drivers (`pg`, `mongoose`, `ioredis`) are the most common case because they have deep dependency trees that use many Node.js built-ins.

`mongodb` internally uses `net`, `dns`, `tls`, `stream`, `crypto`, `os`, and `zlib` — all of which need to be available at runtime. Externalizing both `mongoose` and `mongodb` ensures webpack leaves the entire chain for Node.js to resolve."""

    return {
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_events_focused_example() -> dict:
    """Example specifically highlighting events as a commonly missed module."""

    user_msg = """`npm run build` output:

```
./lib/queue/worker.ts:2:1
Module not found: Can't resolve 'events'
  1 | import { Pool } from 'pg';
> 2 | import { EventEmitter } from 'events';
    | ^
  3 |
  4 | export class JobWorker extends EventEmitter {

Import trace for requested module:
./lib/queue/worker.ts
./instrumentation.ts
```

Current webpack config:
```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'crypto',
        'net',
        'fs',
        'path',
        'pg',
        'pgpass',
        'split2',
      ];
    }
    return config;
  },
```"""

    assistant_msg = """Add `events` and review all Node.js built-ins your code uses. A good practice is to include all the common ones upfront rather than playing whack-a-mole:

```javascript
webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [
        ...(config.externals || []),
        'crypto',
        'net',
        'fs',
        'fs/promises',
        'path',
        'events',
        'stream',
        'dns',
        'tls',
        'pg',
        'pgpass',
        'split2',
      ];
    }
    return config;
  },
```

**Commonly missed modules:**
- `events` — used by any class extending `EventEmitter` (very common in Node.js code)
- `stream` — used by database drivers, compression, file processing
- `dns` — used by database drivers and email libraries for hostname resolution
- `tls` — used by anything making secure connections
- `fs/promises` — the promise-based fs API, separate from `fs`

Since your code uses `pg`, make sure to include its transitive dependencies (`pgpass`, `split2`, `pg-pool`, `pg-protocol`) too, as they're separate npm packages that webpack will try to bundle independently."""

    return {
        "messages": [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def wrap_as_tool_use(plain_example: dict) -> dict:
    """Convert a plain user/assistant example into tool-use format.

    Splits the user message into build output and config, then wraps them
    as tool results so they appear inside <tool_response> tags at inference.
    Works for handcrafted examples that have build output and a config block
    in the user message.
    """
    user_msg = plain_example["messages"][0]["content"]
    assistant_msg = plain_example["messages"][1]["content"]

    # Try to split into build output and config
    # Look for the config section (either "Current webpack config:" or "next.config" or similar)
    config_markers = [
        "Current webpack config",
        "next.config.js:",
        "next.config.mjs:",
        "Current webpack config:",
    ]

    build_part = user_msg
    config_part = ""

    for marker in config_markers:
        idx = user_msg.find(marker)
        if idx != -1:
            build_part = user_msg[:idx].strip()
            config_part = user_msg[idx:].strip()
            break

    # Strip markdown code fences from build_part for raw tool output
    build_content = build_part
    for prefix in ["`npm run build` output:", "```", "`"]:
        build_content = build_content.replace(prefix, "")
    build_content = build_content.strip()

    # Strip markdown fences from config_part
    config_content = config_part
    for prefix in ["```javascript", "```"]:
        config_content = config_content.replace(prefix, "")
    # Extract just the config filename for the tool call
    config_filename = "next.config.js"
    if "next.config.mjs" in config_part:
        config_filename = "next.config.mjs"
    # Get just the JS content
    for marker in config_markers:
        config_content = config_content.replace(marker, "")
    config_content = config_content.strip()

    user_prompt = random.choice(AGENTIC_USER_PROMPTS)

    messages = [
        {"role": "user", "content": user_prompt},
        {
            "role": "assistant",
            "content": "Let me run the build to see the errors.",
            "tool_calls": [{"type": "function", "function": {"name": "bash", "arguments": {"command": "npm run build"}}}],
        },
        {"role": "tool", "content": build_content},
    ]

    if config_content:
        messages.extend([
            {
                "role": "assistant",
                "content": "Let me check the webpack config.",
                "tool_calls": [{"type": "function", "function": {"name": "read_file", "arguments": {"path": config_filename}}}],
            },
            {"role": "tool", "content": config_content},
        ])

    messages.append({"role": "assistant", "content": assistant_msg})

    return {"messages": messages}


def main():
    random.seed(42)
    examples = []

    # 1. Negative examples (wrong approaches) — plain format
    # NOTE: The real ai-toolkit example is deliberately excluded from training
    # so we can use it as a held-out eval to test generalization.
    examples.append(generate_negative_example_fallback())
    examples.append(generate_negative_example_client_side())
    examples.append(generate_transitive_deps_example())

    # 2. Additional focused examples for transitive deps and events — plain
    examples.append(generate_pg_progressive_fix_example())
    examples.append(generate_mongoose_transitive_example())
    examples.append(generate_events_focused_example())

    # 2b. Tool-use variants of the handcrafted examples
    examples.append(wrap_as_tool_use(generate_negative_example_fallback()))
    examples.append(wrap_as_tool_use(generate_negative_example_client_side()))
    examples.append(wrap_as_tool_use(generate_transitive_deps_example()))
    examples.append(wrap_as_tool_use(generate_pg_progressive_fix_example()))
    examples.append(wrap_as_tool_use(generate_mongoose_transitive_example()))
    examples.append(wrap_as_tool_use(generate_events_focused_example()))

    # 3. Synthetic variations — mix of plain and tool-use format
    config_keys = list(CONFIG_TEMPLATES.keys())
    chain_templates = IMPORT_CHAINS

    # Generate combinations of source files and config templates
    for i in range(40):
        # Pick 1-3 source files
        num_files = random.randint(1, 3)
        files = random.sample(SOURCE_FILE_SCENARIOS, min(num_files, len(SOURCE_FILE_SCENARIOS)))

        # Maybe include an npm package — bias toward pg to boost transitive dep coverage
        npm_pkgs = []
        if random.random() > 0.4:
            if random.random() < 0.5:
                # 50% chance: always include pg, maybe with another package
                npm_pkgs = ["pg"]
                if random.random() > 0.5:
                    other = random.choice([k for k in SERVER_NPM_PACKAGES if k != "pg"])
                    npm_pkgs.append(other)
            else:
                npm_pkgs = random.sample(list(SERVER_NPM_PACKAGES.keys()), random.randint(1, 2))

        # Pick config template and import chain
        config_key = random.choice(config_keys)
        chain = random.choice(chain_templates)

        # Maybe include existing externals in config
        existing = []
        if random.random() > 0.6:
            existing = random.sample(NODE_BUILTINS[:6], random.randint(1, 3))

        # Maybe include wrong approach discussion
        include_wrong = random.random() > 0.7

        # Mix of formats: ~1/3 plain, ~1/3 full tool-use, ~1/3 minimal tool-response-only
        fmt_roll = random.random()

        gen_kwargs = dict(
            source_files=files,
            npm_packages=npm_pkgs,
            config_template_key=config_key,
            import_chain_template=chain,
            include_wrong_approach=include_wrong,
            existing_externals=existing,
        )

        if fmt_roll < 0.33:
            example = generate_example(**gen_kwargs)
        elif fmt_roll < 0.66:
            example = generate_tool_use_example(**gen_kwargs)
        else:
            example = generate_tool_response_only_example(**gen_kwargs)

        examples.append(example)

    # Real ai-toolkit example is held out for eval — not included in training

    # Shuffle
    random.shuffle(examples)

    # Write output
    output_dir = Path(__file__).parent
    output_file = output_dir / "train.jsonl"

    with open(output_file, "w") as f:
        for example in examples:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    print(f"Generated {len(examples)} training examples → {output_file}")

    # Also write a small validation split
    val_examples = [
        examples.pop(0),
        examples.pop(0),
        examples.pop(0),
    ]

    val_file = output_dir / "val.jsonl"
    with open(val_file, "w") as f:
        for example in val_examples:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    print(f"Split off {len(val_examples)} validation examples → {val_file}")


if __name__ == "__main__":
    main()
