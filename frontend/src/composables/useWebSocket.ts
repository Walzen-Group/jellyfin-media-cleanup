import { ref, onUnmounted } from 'vue'
import type { WebSocketMessage } from '../types/api'

/**
 * Composable for WebSocket connection with exponential backoff reconnection.
 * Automatically connects on creation, cleans up on component unmount.
 * Allows multiple handlers to listen to the same stream (one-to-many).
 */
export function useWebSocket() {
  const isConnected = ref(false)
  const handlers: Array<(msg: WebSocketMessage) => void> = []
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let connectTimeoutTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 2000  // Initial retry interval during grace period
  let stopped = false  // Flag to disable reconnection when intentionally disconnecting
  const startTime = Date.now()
  const GRACE_PERIOD = 10_000  // 10s: retry every 2s without backoff
  const CONNECT_TIMEOUT = 5_000  // 5s: if handshake doesn't complete, abort and retry
  let attemptCount = 0

  function getWsUrl(): string {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}/ws`
  }

  /**
   * Establish WebSocket connection. Invokes all registered handlers for each message.
   * Closes on error to trigger reconnection. Resets reconnect delay on successful open.
   */
  function connect() {
    if (stopped) {
      console.warn('[WS] connect() called but stopped=true, skipping')
      return
    }
    attemptCount++
    const url = getWsUrl()
    console.info(`[WS] Connecting to ${url} (attempt ${attemptCount})...`)

    try {
      ws = new WebSocket(url)
    } catch (e) {
      console.warn(`[WS] Failed to create WebSocket (attempt ${attemptCount}):`, e)
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      if (connectTimeoutTimer) { clearTimeout(connectTimeoutTimer); connectTimeoutTimer = null }
      console.info(`[WS] Connected to ${url}`)
      isConnected.value = true
      reconnectDelay = 2000  // Reset for future reconnections
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WebSocketMessage
        // Dispatch to all registered handlers
        handlers.forEach((h) => h(msg))
      } catch {
        // Ignore malformed JSON messages silently
      }
    }

    ws.onclose = (ev) => {
      console.warn(`[WS] onclose (code=${ev.code}, reason=${ev.reason || 'none'}, wasClean=${ev.wasClean})`)
      isConnected.value = false
      scheduleReconnect()
    }

    ws.onerror = (ev) => {
      if (connectTimeoutTimer) { clearTimeout(connectTimeoutTimer); connectTimeoutTimer = null }
      console.warn('[WS] onerror:', ev)
      // Close socket to trigger onclose handler and reconnection
      ws?.close()
    }

    // If the handshake doesn't complete within CONNECT_TIMEOUT, abort and retry.
    // Some environments (Docker on Windows) can cause the handshake to hang.
    connectTimeoutTimer = setTimeout(() => {
      if (ws && ws.readyState === WebSocket.CONNECTING) {
        console.warn(`[WS] Connection timeout after ${CONNECT_TIMEOUT / 1000}s, aborting`)
        ws.close()
      }
    }, CONNECT_TIMEOUT)
  }

  /**
   * Schedule a reconnection attempt.
   * During the grace period (first 10s), retries every 2s without backoff.
   * After the grace period, uses exponential backoff (doubling, capped at 30s).
   */
  function scheduleReconnect() {
    if (stopped) return

    const inGracePeriod = (Date.now() - startTime) < GRACE_PERIOD
    if (inGracePeriod) {
      reconnectDelay = 2000
    } else {
      reconnectDelay = Math.min(reconnectDelay * 2, 30000)
    }

    console.warn(
      `[WS] Disconnected. Retrying in ${(reconnectDelay / 1000).toFixed(0)}s` +
      `${inGracePeriod ? ' (grace period)' : ' (backoff)'}` +
      ` (attempt ${attemptCount})`
    )

    reconnectTimer = setTimeout(connect, reconnectDelay)
  }

  /**
   * Register a message handler. Called for every incoming WebSocket message.
   * Multiple handlers can be registered and will all be called.
   */
  function onMessage(handler: (msg: WebSocketMessage) => void) {
    handlers.push(handler)
  }

  /**
   * Disconnect and stop attempting to reconnect.
   * Called automatically on component unmount.
   */
  function disconnect() {
    console.warn('[WS] disconnect() called, stopping reconnection')
    stopped = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
    ws = null
  }

  // Start connection immediately on creation
  connect()

  // Cleanup on component unmount
  onUnmounted(() => {
    disconnect()
  })

  return { isConnected, onMessage, disconnect }
}
