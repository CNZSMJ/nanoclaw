import fs from 'fs';
import path from 'path';
import pino from 'pino';

const LOG_DIR = path.join(process.cwd(), 'logs');
fs.mkdirSync(LOG_DIR, { recursive: true });

const level = process.env.LOG_LEVEL || 'info';

// Main logger — stdout with pino-pretty (general infrastructure logs)
export const logger = pino({
  level,
  transport: { target: 'pino-pretty', options: { colorize: true } },
});

// WhatsApp logger — logs/whatsapp.log (connection, sync, messaging, baileys output)
export const whatsappLogger = pino({
  level,
  transport: {
    target: 'pino-pretty',
    options: {
      colorize: false,
      destination: path.join(LOG_DIR, 'whatsapp.log'),
      mkdir: true,
    },
  },
});

// Agent logger — logs/agent.log (message processing, container lifecycle, agent output)
export const agentLogger = pino({
  level,
  transport: {
    target: 'pino-pretty',
    options: {
      colorize: false,
      destination: path.join(LOG_DIR, 'agent.log'),
      mkdir: true,
    },
  },
});

// Redirect console.log to whatsappLogger to capture baileys' raw output
// (e.g. "Closing session: SessionEntry {...}" which bypasses pino)
const originalConsoleLog = console.log;
console.log = (...args: unknown[]) => {
  whatsappLogger.debug({ source: 'console' }, args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
};

// Route uncaught errors through pino so they get timestamps in stderr
process.on('uncaughtException', (err) => {
  logger.fatal({ err }, 'Uncaught exception');
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  logger.error({ err: reason }, 'Unhandled rejection');
});
