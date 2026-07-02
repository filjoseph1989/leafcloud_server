[Prev](./page-3-migrations-alembic.md) | [Next](./page-5-developer-guide.md)

# Network Discovery: **Zeroconf (mDNS)**

This document explains the implementation of the Zeroconf (mDNS) service discovery system.

## 1. Overview
To make the LeafCloud Server V2 easily discoverable on a local network without knowing its IP address, we have implemented a Zeroconf broadcaster. This allows clients (like mobile apps or other servers) to find the server using the service type `_leafcloud._tcp.local.`.

## 2. SOLID Implementation
Following the **Single Responsibility Principle (SRP)**, the discovery logic is decoupled from the main application logic:

*   **`app/discovery.py`**: Contains the `DiscoveryService` class which handles all `zeroconf` library interactions, IP resolution, and service registration.
*   **`app/main.py`**: Simply triggers the `start()` and `stop()` methods of the discovery service during the application's lifecycle hooks.

## 3. How it Works
1.  **Startup**: When the FastAPI server starts, it initializes the `DiscoveryService`.
2.  **IP Resolution**: It automatically detects the server's local IP address.
3.  **Registration**: It broadcasts a service named `LeafCloud-Server._leafcloud._tcp.local.` on the configured port (default: 8000).
4.  **Shutdown**: When the server stops, it gracefully unregisters the service from the network.

## 4. Configuration
The service name and port can be configured via environment variables in the `.env` file:
*   `PORT`: The port the server is running on (default: 8000).

## 5. Verification
You can verify that the server is broadcasting by running the following command (on macOS):
```bash
dns-sd -B _leafcloud._tcp
```

Or by using our provided verification script:
```bash
~/.env_leafcloud/bin/python scripts/verify-zeroconf.py
```

> [!TIP]
> To manually register a temporary `_leafcloud._tcp` service for testing without starting the FastAPI server, or to troubleshoot common `dns-sd` command mistakes, see the [Manual Zeroconf Service Registration Guide](file:///Users/fil/Fil/leafcloud/mimeng_leafcloud_server_v2/docs/page-49-manual-zeroconf-testing.md).


## 6. Dependencies
*   `zeroconf`: The Python library used for mDNS broadcasting.

---

[Prev](./page-3-migrations-alembic.md) | [Next](./page-5-developer-guide.md)
