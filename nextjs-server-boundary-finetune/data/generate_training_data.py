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
# System prompt for training
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert software engineer. When given a coding task, analyze the problem carefully, explain your reasoning, then provide the fix. Focus on correctness - use the right mechanism for the problem, not just something that silences the error."""

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


def generate_example(
    source_files: list[dict],
    npm_packages: list[str],
    config_template_key: str,
    import_chain_template: dict,
    include_wrong_approach: bool = False,
    existing_externals: list[str] | None = None,
) -> dict:
    """Generate one training example."""

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

    # Build the source file listing
    source_listings = []
    for sf in source_files:
        source_listings.append(f"File: {sf['filename']}\n```typescript\n{sf['code_snippet'].strip()}\n```")

    # Build user message
    user_parts = [
        f"I'm getting build errors in my Next.js project. Here's the output of `npm run build`:\n\n```\n{build_output}\n```",
        f"\nHere's my current {config_template['filename']}:\n```javascript\n{config_before}\n```",
    ]
    for listing in source_listings:
        user_parts.append(f"\n{listing}")

    user_msg = "\n".join(user_parts)

    # Build assistant response
    # Explain the problem
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
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
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

    user_msg = f"""I'm getting build errors in my Next.js project. The project uses an instrumentation hook to start a Signal messenger adapter as a background process. The signal adapter and calendar integration use Node.js built-in modules. Here's the output of `npm run build`:

```
{build_output}
```

Here's my current next.config.js:
```javascript
{config_before}
```

The project also has `pg` (PostgreSQL) as a dependency, used in `lib/calendar/token-store.ts` and a shared database module. The `token-store.ts` imports both `crypto` and `pg`.

How do I fix this?"""

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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_negative_example_fallback() -> dict:
    """Generate an example where the model should NOT use resolve.fallback."""

    user_msg = """My Next.js app fails to build:

```
./lib/db/connection.ts:1:1
Module not found: Can't resolve 'net'
> 1 | import { createConnection } from 'net';
    | ^

Import trace for requested module:
./lib/db/connection.ts
./instrumentation.ts
```

I tried this fix but the app crashes at runtime:
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
```

The build passes now but I get `TypeError: Cannot read properties of undefined (reading 'createConnection')` when the code runs. What's going on?"""

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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_negative_example_client_side() -> dict:
    """Example where someone applies the fix to the wrong side."""

    user_msg = """Next.js build error:

```
./lib/crypto/hash.ts:1:1
Module not found: Can't resolve 'crypto'
> 1 | import { createHash } from 'crypto';
    | ^

Import trace for requested module:
./app/api/auth/route.ts
```

My current next.config.js:
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
```

Why isn't this working?"""

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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def generate_transitive_deps_example() -> dict:
    """Example focusing on the need to externalize transitive dependencies."""

    user_msg = """I fixed the direct Node.js built-in errors in my Next.js build by adding webpack externals:

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
```

But now I get a new error:

```
./node_modules/pg/lib/connection.js
Module not found: Can't resolve 'net'

Import trace for requested module:
./node_modules/pg/lib/client.js
./node_modules/pg/lib/index.js
./lib/db.ts
./instrumentation.ts
```

The `crypto` and `net` errors in my own code are gone, but `pg` still can't find `net`. Do I need to add `node:` prefix to pg's source code?"""

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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]
    }


def main():
    random.seed(42)
    examples = []

    # 1. Negative examples (wrong approaches)
    # NOTE: The real ai-toolkit example is deliberately excluded from training
    # so we can use it as a held-out eval to test generalization.
    examples.append(generate_negative_example_fallback())
    examples.append(generate_negative_example_client_side())
    examples.append(generate_transitive_deps_example())

    # 3. Synthetic variations
    config_keys = list(CONFIG_TEMPLATES.keys())
    chain_templates = IMPORT_CHAINS

    # Generate combinations of source files and config templates
    for i in range(40):
        # Pick 1-3 source files
        num_files = random.randint(1, 3)
        files = random.sample(SOURCE_FILE_SCENARIOS, min(num_files, len(SOURCE_FILE_SCENARIOS)))

        # Maybe include an npm package
        npm_pkgs = []
        if random.random() > 0.4:
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

        example = generate_example(
            source_files=files,
            npm_packages=npm_pkgs,
            config_template_key=config_key,
            import_chain_template=chain,
            include_wrong_approach=include_wrong,
            existing_externals=existing,
        )
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
