[Prev](./page-17-static-image-serving.md) | [Next](./page-19-alert-polling.md)

# Tank Reading History: **Time-Series API**

This guide explains how the mobile app fetches historical sensor readings and AI predictions for a specific tank.

## 1. Endpoint
**URL**: `http://<server-ip>:8000/api/v1/iot/history/{tank_id}`
**Method**: `GET`

---

## 2. Query Parameters

| Parameter | Type | Default | Range | Description |
| :--- | :--- | :--- | :--- | :--- |
| `days` | Integer | `7` | 1 – 90 | How many past days of readings to fetch |
| `limit` | Integer | `200` | 1 – 200 | Maximum number of readings returned |

---

## 3. Full Sample Response

```
GET /api/v1/iot/history/1?days=7&limit=200
```

```json
{
  "tank_id": 1,
  "tank_name": "Reservoir",
  "days": 7,
  "total": 3,
  "readings": [
    {
      "reading_id": 52,
      "timestamp": "2026-05-18T14:30:22",
      "image_url": "http://192.168.1.20:8000/images/2026-05-18/Reservoir/reading_20260518_143022_a3f9c1.jpg",
      "ph": 6.2,
      "ec": 1.4,
      "water_temp": 26.5,
      "predicted_n": 0.7210,
      "predicted_p": 0.1830,
      "predicted_k": 0.0960,
      "macro_scale": 0.91,
      "micro_scale": 0.85
    },
    {
      "reading_id": 51,
      "timestamp": "2026-05-17T09:15:10",
      "image_url": "http://192.168.1.20:8000/images/2026-05-17/Reservoir/reading_20260517_091510_b2d4e8.jpg",
      "ph": 6.0,
      "ec": 1.2,
      "water_temp": 25.8,
      "predicted_n": 0.6540,
      "predicted_p": 0.2100,
      "predicted_k": 0.1360,
      "macro_scale": 0.78,
      "micro_scale": 0.72
    }
  ]
}
```

---

## 4. Response Fields

| Field | Description |
| :--- | :--- |
| `tank_id` | The tank queried |
| `tank_name` | Human-readable tank name |
| `days` | The `days` value used in the request |
| `total` | Actual number of readings returned |
| `readings` | List of readings, newest first |

### Per Reading

| Field | Description |
| :--- | :--- |
| `reading_id` | ID of the `daily_readings` row |
| `timestamp` | When the Pi uploaded this reading |
| `image_url` | Full HTTP URL — load directly as `<img>` src |
| `ph` / `ec` / `water_temp` | Raw sensor values |
| `predicted_n/p/k` | AI-estimated nutrient probabilities (`null` if AI hasn't run yet) |
| `macro_scale` / `micro_scale` | AI scaling index used in dashboard math (`null` if no prediction) |

---

## 5. Notes
- Readings are returned **newest first**.
- If a reading has no AI prediction yet (`is_new_data = True`, background task still pending), the `predicted_*` and `*_scale` fields will be `null`.
- The server caps results at **200 rows** regardless of the `limit` value sent.

---

## 6. Mobile Implementation Example

### Fetch and Display as a Chart
```javascript
const fetchHistory = async (tankId, days = 7) => {
  const response = await fetch(
    `http://192.168.1.20:8000/api/v1/iot/history/${tankId}?days=${days}`
  );
  const data = await response.json();

  // Map to chart-friendly format
  const chartData = data.readings.map(r => ({
    x: new Date(r.timestamp),
    ph: r.ph,
    ec: r.ec,
    n: r.predicted_n,
    p: r.predicted_p,
    k: r.predicted_k,
  }));

  renderChart(chartData);
};
```

### Common Use Cases

| Use Case | Query |
| :--- | :--- |
| Last 7 days (default) | `?days=7` |
| Last 30 days | `?days=30` |
| Today only, last 10 readings | `?days=1&limit=10` |
| Full quarter | `?days=90` |

---

## 7. Code Structure
This endpoint follows the SOLID principle — business logic is fully isolated in the service layer:

| Layer | File | Responsibility |
| :--- | :--- | :--- |
| Schema | `app/schemas/history.py` | `HistoryItem`, `HistoryResponse` data shapes |
| Service | `app/services/history_service.py` | DB query, row mapping, URL building |
| Endpoint | `app/api/v1/endpoints/iot.py` | Input validation, tank lookup, delegates to service |


