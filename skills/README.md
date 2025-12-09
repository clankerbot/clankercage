# Clanker Skills

Reusable capabilities for Claude Code.

## Available Skills

### 🌐 Web (Playwright)

Browser automation and web scraping using Playwright.

**Features:**
- ✅ Auto-installs dependencies (npx handles it)
- ✅ Execute JavaScript with full Playwright API
- ✅ Interactive REPL mode
- ✅ Multiple browser engines (Chromium, Firefox, WebKit)
- ✅ Headless or headed mode

**Quick Examples:**

```bash
# Get page title
npx -y tsx ~/.claude/clanker/skills/web.ts \
  "await page.goto('https://example.com'); return await page.title()"

# Scrape HN headlines
npx -y tsx ~/.claude/clanker/skills/web.ts \
  "await page.goto('https://news.ycombinator.com'); \
   const titles = await page.$$eval('.titleline > a', els => els.map(e => e.textContent)); \
   return titles.slice(0, 10)"

# Take screenshot
npx -y tsx ~/.claude/clanker/skills/web.ts \
  "await page.goto('https://example.com'); \
   await page.screenshot({ path: '/tmp/screenshot.png' })"

# Get all links
npx -y tsx ~/.claude/clanker/skills/web.ts \
  "await page.goto('https://example.com'); \
   return await page.$$eval('a', links => links.map(a => ({ text: a.textContent, href: a.href })))"

# Interactive mode
npx -y tsx ~/.claude/clanker/skills/web.ts --interactive
> await page.goto('https://github.com')
> await page.title()
"GitHub: Let's build from here"
> await page.screenshot({ path: '/tmp/gh.png' })
```

**API Available in Code:**
- `page` - Playwright Page object
- `context` - Browser context
- `browser` - Browser instance

**Options:**
- `--browser <chromium|firefox|webkit>` - Choose browser
- `--headed` - Show browser window
- `--interactive` - Start REPL mode

**First Run:**
On first use, Playwright browsers will be installed automatically (one-time, ~200MB).

## Creating New Skills

Skills are executable scripts in this directory that provide reusable functionality.

**Guidelines:**
1. Use `npx -y` for dependencies (no permanent installs)
2. Make skills self-contained
3. Provide clear help text
4. Handle errors gracefully
5. Return structured output (JSON when possible)

**Template:**

```typescript
#!/usr/bin/env npx -y tsx
/**
 * Skill Name
 *
 * Usage: npx -y tsx ~/.claude/clanker/skills/my-skill.ts [args]
 */

async function main() {
  // Your skill logic here
}

main().catch(console.error);
```
