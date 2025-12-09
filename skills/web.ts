#!/usr/bin/env npx -y tsx
/**
 * Playwright Web Skill
 *
 * Usage:
 *   # Execute JS directly
 *   npx -y tsx ~/.claude/clanker/skills/web.ts "await page.goto('https://example.com'); return await page.title()"
 *
 *   # Interactive REPL (starts browser, waits for commands)
 *   npx -y tsx ~/.claude/clanker/skills/web.ts --interactive
 *
 *   # Run with specific browser
 *   npx -y tsx ~/.claude/clanker/skills/web.ts --browser firefox "console.log('test')"
 */

import { chromium, firefox, webkit, Browser, Page, BrowserContext } from 'playwright';
import { execSync } from 'child_process';
import * as readline from 'readline';

interface Options {
  browser: 'chromium' | 'firefox' | 'webkit';
  headless: boolean;
  interactive: boolean;
}

// Auto-install browsers if needed
function ensureBrowsersInstalled() {
  try {
    // Try to launch chromium - if it fails, browsers aren't installed
    execSync('npx -y playwright install chromium --dry-run 2>&1', { stdio: 'ignore' });
  } catch {
    console.error('Installing Playwright browsers (one-time setup)...');
    execSync('npx -y playwright install', { stdio: 'inherit' });
    console.error('Browsers installed!');
  }
}

async function executeCode(code: string, page: Page, context: BrowserContext, browser: Browser): Promise<any> {
  // Create async function with playwright context available
  const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
  const fn = new AsyncFunction('page', 'context', 'browser', code);
  return await fn(page, context, browser);
}

async function startInteractiveMode(browser: Browser, page: Page, context: BrowserContext) {
  console.log('🌐 Playwright Interactive Mode');
  console.log('Available: page, context, browser');
  console.log('Type JavaScript commands (Ctrl+C to exit)\n');

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    prompt: '> '
  });

  rl.prompt();

  rl.on('line', async (line: string) => {
    if (!line.trim()) {
      rl.prompt();
      return;
    }

    try {
      const result = await executeCode(line, page, context, browser);
      if (result !== undefined) {
        console.log(result);
      }
    } catch (error: any) {
      console.error('Error:', error.message);
    }

    rl.prompt();
  });

  rl.on('close', () => {
    console.log('\nClosing browser...');
    process.exit(0);
  });

  // Keep process alive
  await new Promise(() => {});
}

async function main() {
  const args = process.argv.slice(2);

  const options: Options = {
    browser: 'chromium',
    headless: true,
    interactive: false
  };

  let code = '';

  // Parse arguments
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];

    if (arg === '--browser') {
      options.browser = args[++i] as any;
    } else if (arg === '--headed' || arg === '--no-headless') {
      options.headless = false;
    } else if (arg === '--interactive' || arg === '-i') {
      options.interactive = true;
    } else if (arg === '--help' || arg === '-h') {
      console.log(`
Usage: npx -y tsx web.ts [options] [code]

Options:
  --browser <browser>   chromium (default), firefox, or webkit
  --headed              Show browser window
  --interactive, -i     Start interactive REPL
  --help, -h            Show this help

Examples:
  # Get page title
  npx -y tsx web.ts "await page.goto('https://example.com'); return await page.title()"

  # Get text content
  npx -y tsx web.ts "await page.goto('https://news.ycombinator.com'); return await page.textContent('body')"

  # Take screenshot
  npx -y tsx web.ts "await page.goto('https://example.com'); await page.screenshot({ path: 'screenshot.png' })"

  # Interactive mode
  npx -y tsx web.ts --interactive
      `);
      process.exit(0);
    } else {
      code = arg;
    }
  }

  // Ensure browsers are installed
  ensureBrowsersInstalled();

  // Launch browser
  const browserEngine = options.browser === 'firefox' ? firefox : options.browser === 'webkit' ? webkit : chromium;
  const browser = await browserEngine.launch({ headless: options.headless });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    if (options.interactive) {
      await startInteractiveMode(browser, page, context);
    } else if (code) {
      const result = await executeCode(code, page, context, browser);
      if (result !== undefined) {
        console.log(JSON.stringify(result, null, 2));
      }
    } else {
      console.error('No code provided. Use --help for usage information.');
      process.exit(1);
    }
  } finally {
    if (!options.interactive) {
      await browser.close();
    }
  }
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
