# Product Guidelines: LEAFCLOUD System

## Prose Style
- **Technical & Precise:** All documentation, API responses, and developer-facing messages must focus on clarity, brevity, and objective technical details. Avoid conversational filler; prioritize accuracy in describing sensor data, NPK levels, and recommendation logic.

## API Design & Developer Experience
- **Predictable Design:** Maintain absolute consistency in API endpoint naming, request/response structures, and status codes. The API should feel intuitive and easy to navigate for both IoT devices and mobile applications.

## User Experience (UX) Principles
- **Data-First Layouts:** Design user interfaces specifically to present critical agricultural sensor data (pH, EC, NPK) clearly and prominently.
- **Mobile-First UX:** The primary user interface is for mobile-screen monitoring in a greenhouse or field environment. Prioritize accessibility and ease of interaction on small screens.
- **Glanceable Dashboard:** Users must be able to understand the system's current status and any critical alerts with a single glance. Use clear visual indicators and hierarchy.

## Notification & Alerting Strategy
- **Surgical Alerts:** The system must only notify users when a critical action is required (e.g., pH lockout, extreme nutrient burn). Minimize noise to ensure that every alert is actionable and high-priority.
