// level-gated console logger.
// Dev builds log everything; prod shows warnings+ unless VITE_LOG_LEVEL is set.
// Usage: logger.info('session restored', user.id)

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 }
const threshold =
  LEVELS[import.meta.env.VITE_LOG_LEVEL] ?? (import.meta.env.DEV ? LEVELS.debug : LEVELS.warn)

const log = (level, label, args) => {
  if (LEVELS[level] >= threshold) console[level](label, ...args)
}

export const logger = {
  debug: (...args) => log('debug', '[sm]', args),
  info: (...args) => log('info', '[sm]', args),
  warn: (...args) => log('warn', '[sm]', args),
  error: (...args) => log('error', '[sm]', args),
}
