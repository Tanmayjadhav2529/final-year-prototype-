This folder is intended to contain third-party vendor assets used by the dashboard UI.

Chart.js (UMD build):
- Download the UMD build (minified) from the official release and place it here as `chart.umd.min.js`.

Recommended source:
- https://www.jsdelivr.com/package/npm/chart.js (choose the UMD build)
- Or build from source via Chart.js releases: https://github.com/chartjs/Chart.js/releases

Why local vendor copy?
- Factory laptops may not have reliable internet access or may be on restricted networks.
- Using a local copy ensures the dashboard's trend chart loads deterministically without external dependency.

After adding `chart.umd.min.js`, reload the dashboard page. The app will prefer the local copy and fall back to the CDN if the local file is missing or fails to define `Chart`.