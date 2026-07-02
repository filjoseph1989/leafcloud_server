[Prev](./page-47-conceptual-framework-guide.md) | [Next](./page-49-nutrient-classifier-v11-code-walkthrough.md)

# Manual Zeroconf (mDNS) Service Registration Guide

This document provides a reference for manually registering, browsing, and resolving the Zeroconf (mDNS) services for LeafCloud Server V2 using the native `dns-sd` command-line tool.

## 1. Overview
During local development and network testing, you might want to simulate a running LeafCloud Server without launching the full Uvicorn/FastAPI application. You can do this by using the macOS/Linux system tool `dns-sd` to broadcast local service registrations.

## 2. Registering the Service
To register the LeafCloud Server manually, run the following command:

```bash
dns-sd -R "LeafCloud-Server" _leafcloud._tcp local 8000
```

### Parameter Breakdown
*   `-R`: The register command flag.
*   `"LeafCloud-Server"`: The service instance name.
*   `_leafcloud._tcp`: The service type (using TCP protocol).
*   `local`: The domain (multicast DNS local link).
*   `8000`: The port number where the service is (or will be) running.

---

### ⚠️ Common Pitfall: Missing Space
A common mistake when typing this command is omitting the space between the service name and service type:

```bash
# INCORRECT:
dns-sd -R "LeafCloud-Server"_leafcloud._tcp local 8000
```

#### Symptom:
If you omit the space, `dns-sd` parses `"LeafCloud-Server"_leafcloud._tcp` as a single parameter instead of two separate parameters. Because of this argument mismatch, the command will immediately exit and print its usage manual:

```text
dns-sd -R "LeafCloud-Server"_leafcloud._tcp local 8000
dns-sd -E                          (Enumerate recommended registration domains)
dns-sd -F                          (Enumerate recommended browsing     domains)
...
```

**Resolution:** Ensure there is a space separating the double-quoted name and the underscore of the type:
```bash
# CORRECT:
dns-sd -R "LeafCloud-Server" _leafcloud._tcp local 8000
```

---

## 3. Browsing and Resolving Service Advertisements
To verify that the service is successfully broadcasting on your local network, you can use the browsing and resolving features of `dns-sd` or python verification scripts.

### Browse for Services
To see all active services of type `_leafcloud._tcp` on the local network, run:
```bash
dns-sd -B _leafcloud._tcp local
```

### Resolve/Lookup a Service Instance
To resolve the IP and host information for the registered service, run:
```bash
dns-sd -L "LeafCloud-Server" _leafcloud._tcp local
```

---

## 4. Codebase Reference
In production and actual dev runs, manual registration is not required. The server handles this automatically:
*   [DiscoveryService](file:///Users/fil/Fil/leafcloud/mimeng_leafcloud_server_v2/app/services/discovery.py#L9) automatically starts broadcasting this service upon FastAPI startup.
*   [verify-zeroconf.py](file:///Users/fil/Fil/leafcloud/mimeng_leafcloud_server_v2/scripts/verify-zeroconf.py) handles automated scanning/browsing during local verification.
*   For more details, see [Network Discovery: Zeroconf (mDNS)](file:///Users/fil/Fil/leafcloud/mimeng_leafcloud_server_v2/docs/page-4-zeroconf-discovery.md).

[Prev](./page-47-conceptual-framework-guide.md) | [Next](./page-49-nutrient-classifier-v11-code-walkthrough.md)
