#!/usr/bin/env node

/**
 * Lightweight stdout filter for Azure MCP server processes.
 *
 * The Azure MCP CLI occasionally emits human-readable status messages that
 * break JSON-only protocols. This wrapper spawns the requested command and
 * forwards only stdout lines that parse as JSON while redirecting any other
 * output to stderr so the client can stay in a clean JSON mode.
 */

const { spawn } = require('child_process');

const childArgs = process.argv.slice(2);

if (childArgs.length === 0) {
  console.error('Usage: node json_stdout_filter.js <command> [args...]');
  process.exit(1);
}

const [command, ...commandArgs] = childArgs;

const child = spawn(command, commandArgs, {
  stdio: ['inherit', 'pipe', 'pipe'],
});

let stdoutBuffer = '';

const isJsonLine = (line) => {
  const trimmed = line.trim();
  if (trimmed.length === 0) {
    return false;
  }

  const firstChar = trimmed[0];
  if (firstChar !== '{' && firstChar !== '[') {
    return false;
  }

  try {
    JSON.parse(trimmed);
    return true;
  } catch (_err) {
    return false;
  }
};

const flushLine = (line) => {
  if (isJsonLine(line)) {
    process.stdout.write(`${line}\n`);
  } else if (line.trim().length > 0) {
    process.stderr.write(`[mcp-json-filter] filtered non-JSON stdout: ${line}\n`);
  }
};

child.stdout.on('data', (data) => {
  stdoutBuffer += data.toString('utf8');
  const lines = stdoutBuffer.split(/\r?\n/);
  stdoutBuffer = lines.pop() ?? '';
  lines.forEach(flushLine);
});

child.stdout.on('end', () => {
  if (stdoutBuffer.length > 0) {
    flushLine(stdoutBuffer);
  }
});

child.stderr.on('data', (data) => {
  process.stderr.write(data);
});

child.on('error', (error) => {
  console.error(`[mcp-json-filter] failed to spawn child process: ${error.message}`);
  process.exit(1);
});

child.on('close', (code, signal) => {
  if (signal) {
    console.error(`[mcp-json-filter] child process terminated due to signal ${signal}`);
    process.exit(1);
  }

  process.exit(code ?? 0);
});