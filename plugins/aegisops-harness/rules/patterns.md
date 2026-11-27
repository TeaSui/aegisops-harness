# Code patterns

- **Every HTTP endpoint uses the envelope.** Success `{ "data": {...}, "meta": {"timestamp": "..."} }`; error `{ "error": {"code": "...", "message": "...", "details": []} }`. Applies to backend (incl. model endpoints), platform (API Gateway + Lambda, scaffolded gateways) and any BFF. Migrate a diverging existing endpoint when you touch it; never add a new shape. A vendor-forced shape (e.g. signed webhook) is translated at ingress.
- try/catch only at boundaries; config from environment variables, nothing hardcoded; repository pattern for data access; single-responsibility services with dependency injection; DTOs validated at entry points.
- New code passes SonarQube "Sonar way": A ratings, all hotspots reviewed, ≥ 80% coverage and ≤ 3% duplication on new code.
