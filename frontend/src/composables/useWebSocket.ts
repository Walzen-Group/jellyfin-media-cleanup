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
  let reconnectDelay = 1000  // Start at 1s, double on each retry (capped at 30s)
  let stopped = false  // Flag to disable reconnection when intentionally disconnecting

  function getWsUrl(): string {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}/ws`
  }

  /**
   * Establish WebSocket connection. Invokes all registered handlers for each message.
   * Closes on error to trigger reconnection. Resets reconnect delay on successful open.
   */
  function connect() {
    if (stopped) return
    try {
      ws = new WebSocket(getWsUrl())
    } catch {
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      isConnected.value = true
      reconnectDelay = 1000  // Reset backoff on successful connection
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

    ws.onclose = () => {
      isConnected.value = false
      scheduleReconnect()  // Attempt to reconnect
    }

    ws.onerror = () => {
      // Close socket to trigger onclose handler and reconnection
      ws?.close()
    }
  }

  /**
   * Schedule a reconnection attempt with exponential backoff.
   * Delay doubles each attempt, capped at 30 seconds.
   */
  function scheduleReconnect() {
    if (stopped) return
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 30000)
      connect()
    }, reconnectDelay)
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
