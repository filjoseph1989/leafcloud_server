[Prev](./page-18-history-api.md) | [Next](./page-20-multi-task-ai-model.md)

# Alert Polling: **Mobile Notification System**

This guide explains how the mobile app polls for nutrient alerts and triggers local notifications without Firebase or WebSockets.

## 1. Endpoint
**URL**: `http://<server-ip>:8000/api/v1/iot/alert/{tank_id}`
**Method**: `GET`

Designed to be lightweight — no NPK math, no advisory text. Just enough for the mobile app to decide whether to show a notification.

---

## 2. Sample Responses

### No Alert
```json
{
  "tank_id": 1,
  "tank_name": "Reservoir",
  "has_alert": false,
  "level": null,
  "message": null,
  "topup_macro_ml": null,
  "topup_micro_ml": null,
  "last_reading_at": "2026-05-19T08:00:00"
}
```

### Warning (50–69%)
```json
{
  "tank_id": 1,
  "tank_name": "Reservoir",
  "has_alert": true,
  "level": "WARNING",
  "message": "Nutrient levels at 62% of target. Top-up required.",
  "topup_macro_ml": 3.2,
  "topup_micro_ml": 2.1,
  "last_reading_at": "2026-05-19T08:00:00"
}
```

### Critical (below 50%)
```json
{
  "tank_id": 1,
  "tank_name": "Reservoir",
  "has_alert": true,
  "level": "CRITICAL",
  "message": "Nutrient levels at 44% of target. Top-up required.",
  "topup_macro_ml": 6.4,
  "topup_micro_ml": 4.2,
  "last_reading_at": "2026-05-19T08:00:00"
}
```

---

## 3. Alert Levels

| Nutrient Scale | `has_alert` | `level` |
| :--- | :--- | :--- |
| ≥ 70% | `false` | `null` |
| 50% – 69% | `true` | `WARNING` |
| < 50% | `true` | `CRITICAL` |

Scale is the lower of `macro_scale` and `micro_scale` from the latest AI prediction.

---

## 4. Response Fields

| Field | Description |
| :--- | :--- |
| `has_alert` | `true` if nutrients are below 70% — the only field the mobile needs to check |
| `level` | `WARNING` or `CRITICAL`. `null` if no alert |
| `message` | Human-readable alert text ready to show in a notification |
| `topup_macro_ml` | mL of macro fertilizer to add. `null` if no alert |
| `topup_micro_ml` | mL of micro fertilizer to add. `null` if no alert |
| `last_reading_at` | Timestamp of the latest reading used for this check |

---

## 5. Mobile Implementation

### React Native (Expo)
```javascript
import * as Notifications from 'expo-notifications';

const POLL_INTERVAL_MS = 5 * 60 * 1000; // every 5 minutes

const pollForAlerts = async (tankId) => {
  const response = await fetch(`http://192.168.1.20:8000/api/v1/iot/alert/${tankId}`);
  const data = await response.json();

  if (data.has_alert) {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: `LeafCloud ${data.level}`,
        body: data.message,
      },
      trigger: null, // show immediately
    });
  }
};

// Start polling when app is open
setInterval(() => pollForAlerts(1), POLL_INTERVAL_MS);
```

### Flutter
```dart
Timer.periodic(const Duration(minutes: 5), (_) async {
  final response = await http.get(Uri.parse('http://192.168.1.20:8000/api/v1/iot/alert/1'));
  final data = jsonDecode(response.body);

  if (data['has_alert']) {
    flutterLocalNotificationsPlugin.show(
      0,
      'LeafCloud \${data['level']}',
      data['message'],
      notificationDetails,
    );
  }
});
```

---

## 6. Why Polling Instead of Push (FCM)

| | Polling (implemented) | FCM Push |
| :--- | :--- | :--- |
| Server changes | None — alert logic already in `/dashboard` | Requires device token table + Firebase SDK |
| Works when app closed | Only with background fetch | Yes, natively |
| Setup complexity | Low | High (Firebase project, credentials, mobile SDK) |
| Battery impact | Minimal at 5 min interval | Negligible |

Polling at a 5-minute interval is sufficient for nutrient alerts since readings from the Pi arrive at most every few minutes. If real-time alerting becomes a requirement, FCM can be added later without changing the alert endpoint.

---

## 7. Code Structure

| Layer | File | Responsibility |
| :--- | :--- | :--- |
| Schema | `app/schemas/alert.py` | `AlertStatusResponse` data shape |
| Service | `app/services/alert_service.py` | Scale check, level logic, top-up calculation |
| Endpoint | `app/api/v1/endpoints/iot.py` | Tank lookup, delegates to service |

---


