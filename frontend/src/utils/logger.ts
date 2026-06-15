/**
 * Juno frontend logger.
 *
 * In development: pretty-prints structured log entries to the browser console.
 * In production: console output only (browser logs stay local).
 *
 * TODO: In a future iteration, add a `flush()` method that POSTs batched log
 * entries to a `/log` endpoint on the backend, or integrates with Firebase
 * Analytics for UX event tracking. The LogEntry interface is already structured
 * to support either approach without changes to call sites.
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  level: LogLevel;
  message: string;
  data?: Record<string, unknown>;
  sessionId?: string;
  timestamp: string;
}

const IS_DEV = import.meta.env.DEV;

// Console method mapping
const CONSOLE_METHODS: Record<LogLevel, (...args: unknown[]) => void> = {
  debug: console.debug,
  info: console.info,
  warn: console.warn,
  error: console.error,
};

class Logger {
  private sessionId: string | undefined;

  // ---------------------------------------------------------------------------
  // Session correlation
  // ---------------------------------------------------------------------------

  /**
   * Attach a session ID to all subsequent log entries.
   * Call this after receiving the X-Session-Id header from the backend.
   */
  setSessionId(id: string): void {
    this.sessionId = id;
  }

  // ---------------------------------------------------------------------------
  // Core log methods
  // ---------------------------------------------------------------------------

  debug(message: string, data?: Record<string, unknown>): void {
    this._emit('debug', message, data);
  }

  info(message: string, data?: Record<string, unknown>): void {
    this._emit('info', message, data);
  }

  warn(message: string, data?: Record<string, unknown>): void {
    this._emit('warn', message, data);
  }

  error(message: string, data?: Record<string, unknown>): void {
    this._emit('error', message, data);
  }

  // ---------------------------------------------------------------------------
  // Structured UX event helpers
  // ---------------------------------------------------------------------------

  /**
   * Log a page view. Call on route changes.
   *
   * @param page  Human-readable page name, e.g. "SimplifyPage", "HistoryPage".
   */
  logPageView(page: string): void {
    this._emit('info', 'page_view', { page });
  }

  /**
   * Log a user action (button click, form submit, etc.).
   *
   * @param action  Stable snake_case identifier, e.g. "upload_file", "submit_text".
   * @param data    Optional extra context (file type, input length, etc.).
   */
  logUserAction(action: string, data?: Record<string, unknown>): void {
    this._emit('info', 'user_action', { action, ...data });
  }

  // ---------------------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------------------

  private _emit(level: LogLevel, message: string, data?: Record<string, unknown>): void {
    const entry: LogEntry = {
      level,
      message,
      timestamp: new Date().toISOString(),
      ...(this.sessionId && { sessionId: this.sessionId }),
      ...(data && { data }),
    };

    if (IS_DEV) {
      // Pretty-print in development for readability
      const prefix = `[Juno/${entry.level.toUpperCase()}]`;
      if (data) {
        CONSOLE_METHODS[level](prefix, message, data);
      } else {
        CONSOLE_METHODS[level](prefix, message);
      }
    } else {
      // Production: emit as a single structured object so browser tools
      // (and any future log ingestion pipeline) can parse it cleanly.
      CONSOLE_METHODS[level](entry);
    }
  }
}

/** Singleton logger instance — import and use directly. */
export const logger = new Logger();

export type { LogEntry, LogLevel };
