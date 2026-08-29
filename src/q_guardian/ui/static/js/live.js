/* Q-Guardian Console — live scan WebSocket client.
 * Connects to /api/v1/ws/scans/{scan_id} on the same origin and streams
 * the real scan lifecycle events published by the backend (scan.started,
 * scan.completed / scan.failed). Because scans are synchronous the client
 * connects *after* a scan is submitted and requests the retained completed
 * snapshot with a __replay__ control message; live events still fan out
 * while the socket is open.
 *
 * Connection state (CONNECTING / CONNECTED / RECONNECTING / DISCONNECTED)
 * is exposed through a state-change listener, and messages through an
 * event listener. Reconnects are bounded with a small backoff; the socket
 * self-closes cleanly via close() (no reconnect).
 */
(function () {
  "use strict";

  var QG = window.QG || (window.QG = {});
  var live = {};

  var STATES = {
    CONNECTING: "CONNECTING",
    CONNECTED: "CONNECTED",
    RECONNECTING: "RECONNECTING",
    DISCONNECTED: "DISCONNECTED",
  };

  var MAX_RETRIES = 5;
  var RETRY_DELAY = 800;
  var PING_INTERVAL = 25000;

  var socket = null;
  var state = STATES.DISCONNECTED;
  var scanId = null;
  var retries = 0;
  var retryTimer = null;
  var pingTimer = null;
  var manualClose = false;
  var stateListeners = [];
  var eventListeners = [];

  function notifyState(name) {
    state = name;
    stateListeners.slice().forEach(function (handler) {
      try {
        handler(name, scanId);
      } catch (e) {
        /* listener errors must not break the client */
      }
    });
  }

  function notifyEvent(event) {
    if (!event || typeof event !== "object") return;
    eventListeners.slice().forEach(function (handler) {
      try {
        handler(event);
      } catch (e) {
        /* listener errors must not break the client */
      }
    });
  }

  function wsUrl() {
    var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return (
      proto + "//" + window.location.host + "/api/v1/ws/scans/" + encodeURIComponent(scanId)
    );
  }

  function startPing() {
    stopPing();
    pingTimer = setInterval(function () {
      if (socket && socket.readyState === WebSocket.OPEN) {
        try {
          socket.send("__ping__");
        } catch (e) {
          /* ignore, socket close will surface */
        }
      }
    }, PING_INTERVAL);
  }

  function stopPing() {
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
  }

  function scheduleReconnect() {
    if (manualClose) return;
    retries += 1;
    if (retries > MAX_RETRIES) {
      notifyState(STATES.DISCONNECTED);
      return;
    }
    notifyState(STATES.RECONNECTING);
    var delay = RETRY_DELAY * retries;
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = setTimeout(open, delay);
  }

  function open() {
    if (manualClose) return;
    notifyState(STATES.CONNECTING);
    var ws;
    try {
      ws = new WebSocket(wsUrl());
    } catch (e) {
      scheduleReconnect();
      return;
    }
    socket = ws;

    ws.onopen = function () {
      retries = 0;
      notifyState(STATES.CONNECTED);
      startPing();
      try {
        ws.send("__replay__");
      } catch (e) {
        /* ignore, socket close will surface */
      }
    };

    ws.onmessage = function (event) {
      var data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (data && data.type === "pong") return;
      notifyEvent(data);
    };

    ws.onclose = function () {
      stopPing();
      if (ws !== socket) return;
      socket = null;
      if (!manualClose) {
        scheduleReconnect();
      } else {
        notifyState(STATES.DISCONNECTED);
      }
    };

    ws.onerror = function () {
      /* onclose follows and handles reconnect */
    };
  }

  function connect(id) {
    manualClose = true;
    if (retryTimer) clearTimeout(retryTimer);
    if (socket) {
      socket.onclose = null;
      try {
        socket.close();
      } catch (e) {
        /* ignore */
      }
      socket = null;
    }
    stopPing();
    scanId = id;
    manualClose = false;
    retries = 0;
    open();
  }

  function close() {
    manualClose = true;
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = null;
    stopPing();
    if (socket) {
      socket.onclose = null;
      try {
        socket.close();
      } catch (e) {
        /* ignore */
      }
      socket = null;
    }
    notifyState(STATES.DISCONNECTED);
  }

  function onState(handler) {
    if (typeof handler === "function" && stateListeners.indexOf(handler) === -1) {
      stateListeners.push(handler);
    }
  }

  function onEvent(handler) {
    if (typeof handler === "function" && eventListeners.indexOf(handler) === -1) {
      eventListeners.push(handler);
    }
  }

  function offState(handler) {
    var index = stateListeners.indexOf(handler);
    if (index !== -1) stateListeners.splice(index, 1);
  }

  function offEvent(handler) {
    var index = eventListeners.indexOf(handler);
    if (index !== -1) eventListeners.splice(index, 1);
  }

  live.STATES = STATES;
  live.connect = connect;
  live.close = close;
  live.onState = onState;
  live.onEvent = onEvent;
  live.offState = offState;
  live.offEvent = offEvent;
  live.state = function () {
    return state;
  };

  QG.live = live;
})();
