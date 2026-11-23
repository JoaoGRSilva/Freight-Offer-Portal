# CSS refactor - deployment notes

These files are extracted from the supplied global.css, keeping existing selectors and declaration values. Original files for carrier-portal, freight-board, freight-details remain unchanged.

1. Back up existing static/global.css.
2. Copy css/base and css/pages into static/css.
3. In base.html, replace the old global.css link with, in this order:
   <link rel="stylesheet" href="{{ url_for('static', filename='css/base/variables.css') }}">
   <link rel="stylesheet" href="{{ url_for('static', filename='css/base/global.css') }}">
   <link rel="stylesheet" href="{{ url_for('static', filename='css/base/components.css') }}">
4. In new-shipment.html add to block styles:
   <link rel="stylesheet" href="{{ url_for('static', filename='css/pages/new-shipment.css') }}">
5. In dashboard.html add to block styles:
   <link rel="stylesheet" href="{{ url_for('static', filename='css/pages/dashboard.css') }}">
6. If other pages used shared .frete-card / .route-badge / .kpis styles from global.css, they may need those rules explicitly imported or moved to components.css. Test all pages and their responsive layouts before removing old CSS.
7. Keep existing page-specific CSS links and verify their paths. No Python route or database change required.

IMPORTANT: This is a first-pass split based on CSS selectors; without every HTML template, exact page usage and visual equivalence cannot be guaranteed. Keep the original file for rollback.
