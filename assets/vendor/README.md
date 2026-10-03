# Vendored libraries

Kept in the repo, pinned, so the dashboard works offline and a new upstream release can't change it
without a commit.

| File | What | Version | License |
|---|---|---|---|
| `alpinejs-3.17.4.min.js` | [Alpine.js](https://alpinejs.dev), `dist/cdn.min.js` | 3.17.4 | MIT (`LICENSE-alpinejs.md`) |
| `qrcode-generator-2.0.4.js` | [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) by Kazuhiko Arase, `dist/qrcode.js`; draws the setup screen's QR code | 2.0.4 | MIT (notice in the file's header) |
| `inter-latin-variable.woff2` | [Inter](https://rsms.me/inter/) variable font, Latin subset, all weights, via [@fontsource-variable/inter](https://fontsource.org/fonts/inter) | 5.3.0 | SIL OFL 1.1 (`LICENSE-inter.txt`) |

To update one, download the new version from jsDelivr (`https://cdn.jsdelivr.net/npm/<package>@<version>/...`),
replace the file, and update the reference in `dashboard.html` and this table.
