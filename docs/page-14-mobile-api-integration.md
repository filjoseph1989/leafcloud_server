[Prev](./page-13-tank-configuration.md) | [Next](./page-15-iot-pi-integration.md)

# API Integration: **Mobile App to Tank Config**

This guide explains how your mobile application (React Native, Flutter, etc.) can interact with the new Tank Configuration API.

## 1. API Endpoints Base URL
All requests should be made to: 
`http://<server-ip>:8000/api/v1/tank-configs/`

---

## 2. Common Operations (CRUD)

### A. Create a New Configuration (Save Button)
When the user fills out the settings form and clicks "Save":

**Request:**
- **Method**: `POST`
- **URL**: `/api/v1/tank-configs/`
- **Headers**: `Content-Type: application/json`
- **Body (JSON)**:
```json
{
  "tank_name": "Main Lettuce Bed",
  "water_volume_liters": 50.0,
  "macro_brand_name": "MasterBlend",
  "macro_n_pct": 8.0,
  "macro_p_pct": 15.0,
  "macro_k_pct": 36.0,
  "macro_density": 1.0,
  "micro_brand_name": "NutriHydro",
  "micro_n_pct": 5.0,
  "micro_p_pct": 10.0,
  "micro_k_pct": 15.0,
  "micro_density": 1.0,
  "target_macro_dosage_mll": 2.0,
  "target_micro_dosage_mll": 1.5,
  "is_active": true
}
```

---

### B. Fetch All Configurations (List Screen)
To show a list of all saved tanks/buckets:

**Request:**
- **Method**: `GET`
- **URL**: `/api/v1/tank-configs/`

---

### C. Update an Existing Configuration (Edit Screen)
To change only specific fields (e.g., updating the dosage):

**Request:**
- **Method**: `PATCH`
- **URL**: `/api/v1/tank-configs/{id}`
- **Body (JSON)**:
```json
{
  "target_macro_dosage_mll": 2.5
}
```

---

### D. Delete a Configuration
To remove a tank setup:

**Request:**
- **Method**: `DELETE`
- **URL**: `/api/v1/tank-configs/{id}`

---

## 3. Authentication & JWT Tokens

Due to route protection on all user-facing endpoints, the mobile app must authenticate requests:

1. **Get Token (Login):**
   Send a `POST` request to `/api/v1/auth/login` with email and password.
   **Response JSON:**
   ```json
   {
     "status": "success",
     "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
     "message": "Login successful"
   }
   ```
2. **Attach Token to Requests:**
   Include the token in the `Authorization` header as a Bearer token:
   `Authorization: Bearer <your-token-here>`

---

## 4. Mobile Implementation Example (JavaScript/Fetch)

```javascript
// Example login flow to retrieve token
const loginUser = async (email, password) => {
  const response = await fetch('http://192.168.1.20:8000/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  if (response.ok) {
    const data = await response.json();
    return data.token; // Save this token securely (e.g. AsyncStorage / SecureStore)
  }
  throw new Error('Authentication failed');
};

// Example authenticated API call
const saveSettings = async (formData, token) => {
  try {
    const response = await fetch('http://192.168.1.20:8000/api/v1/tank-configs/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}` // <-- REQUIRED
      },
      body: JSON.stringify(formData),
    });

    if (response.status === 401) {
      console.log('Session expired, redirecting to login...');
      // Handle logout/redirect
      return;
    }

    if (response.ok) {
      const data = await response.json();
      console.log('Successfully saved config with ID:', data.id);
    }
  } catch (error) {
    console.error('Failed to connect to LeafCloud Server:', error);
  }
};
```

## 4. Automatic Validation
FastAPI will automatically return a `422 Unprocessable Entity` error if the mobile app sends invalid data (e.g., sending a negative number for water volume or a string where a number is expected). This ensures your database always stays clean.

---

## 5. Related Mobile Endpoints
Beyond tank configuration, the mobile app also consumes these endpoints:

| Endpoint | Doc | Purpose |
| :--- | :--- | :--- |
| `GET /api/v1/iot/dashboard/{tank_id}` | page-16 | Real-time nutrient status and alerts |
| `GET /api/v1/iot/history/{tank_id}` | page-18 | Time-series readings for charts and trends |
| `GET /api/v1/iot/alert/{tank_id}` | page-19 | Lightweight poll for notification triggers |


