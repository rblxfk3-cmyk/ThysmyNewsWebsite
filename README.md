# THYSMY News Intelligence · V4

Ruang kerja fundamental XAUUSD dalam Bahasa Melayu. Redesign dark/gold responsif dengan tema cerah, dashboard sebenar (bukan mockup), serta pengekalan FastAPI, Supabase, ToyyibPay dan deployment Docker/Render sedia ada.

## Ciri dan akses

| Ciri | Akses | Sumber / syarat |
| --- | --- | --- |
| Kalendar MYT, actual/forecast/previous/revisi, countdown | Public | BiQuote, atau Trading Economics dengan kunci pilihan |
| XAUUSD, DXY, US10Y dan candlestick gold | Public | BiQuote; US10Y FRED **harian**, bukan live |
| Breaking-news timeline + konteks kategori BM | Public | GDELT; masa dikesan, bukan masa terbit |
| Kalkulator kos, komisen, slippage, FX dan break-even | Public | Input pengguna; spesifikasi broker boleh diubah |
| Jurnal peribadi, screenshot, corak event, CSV, arkib/pulih | Akaun | Supabase V4; SQLite untuk pembangunan |
| Peringatan event 15/5 minit dan actual | Akaun | Dashboard perlu **terbuka**; bukan push apabila pelayar ditutup |
| Bias sebelum/selepas, sebab dan data bercampur | Pro | Aturan telus; bukan arahan entry atau probability |
| Konteks makro 14 hari + topik global | Pro | Keluaran actual lalu dan tajuk GDELT |
| Skor volatiliti /100, berasingan daripada arah | Pro | Heuristik, bukan peratus kejayaan |
| Simulator actual pelbagai komponen/revisi | Pro | Angka andaian; tidak dimasukkan dalam track record |
| Track record append-only + reaksi 1/5/15 minit | Pro | Recorder aktif, Supabase V4, bar M1 tepat |
| Pembantu BM berpandukan snapshot dan sumber | Pro | OpenAI apabila key **dan** model ditetapkan; jika tidak, panduan aturan dilabel jelas |
| Muat turun kad analisis PNG berjenama | Pro | Dijanakan daripada analisis semasa, dengan waktu/phase/sumber |
| Pro automatik, tamat tempoh, resit + semak gateway | Akaun | ToyyibPay + fungsi transaksi Supabase V4 |

Harga asal dikekalkan: RM29 / 30 hari (boleh dikonfigurasi). Bayaran sekali, tiada auto-renew. Tiada demo credentials atau angka pasaran contoh dalam production.

## Upgrade production sedia ada

Jangan merge/deploy V4 sebelum langkah pangkalan data selesai: checkout baharu sengaja disekat jika penyimpanan V4 belum tersedia.

1. Simpan backup pangkalan data mengikut operasi biasa.
2. Jalankan `SUPABASE_V4_MIGRATION.sql` sekali dalam SQL Editor Supabase **projek yang sama**. Ia additive dan transactional: akaun/langganan/bayaran sedia ada tidak dipadam. Untuk pemasangan kosong, jalankan `SUPABASE_SETUP.sql` dahulu.
3. Kekalkan URL, Supabase keys, ADMIN_EMAIL dan ToyyibPay credentials pada hosting. Tetapkan SESSION_SECRET rawak yang stabil, DEMO_MODE=false dan APP_BASE_URL ke URL HTTPS sebenar.
4. Tetapkan LIVE_DATA_ENABLED=true dan ENABLE_RECORDER=true. Untuk AI penuh, tetapkan OPENAI_API_KEY dan OPENAI_MODEL ke model yang akaun API tersebut boleh akses. Key/model tidak disimpan di frontend atau GitHub.
5. Deploy branch/commit V4 melalui aliran Docker/Render sedia ada. Nama service dan pelan Render tidak diubah oleh upgrade ini. Tiada migrasi hosting ke Sites.
6. Log masuk admin, buka `/admin`, semak penyimpanan, recorder, sesi, AI dan mode bayaran. Uji sandbox dengan akaun admin sebelum memakai credentials production. DEMO_MODE mesti false untuk ujian gateway.
7. Buat ujian hujung-ke-hujung gateway, pengesahan email, browser/mobile dan sumber live pada deployment sebenar sebelum pelancaran umum. Ujian tempatan tidak menghantar wang atau menggunakan akaun production.

**Penting:** Render free boleh tidur ketika tiada trafik. Recorder/peringatan tidak dijamin ketika pelayan atau tab tidur. Gunakan perkhidmatan sentiasa aktif jika rekod setiap event diperlukan; jangan ubah pelan berbayar tanpa keputusan pemilik.

Tanpa akses hosting/Supabase, menyimpan kod ke GitHub tidak mengaktifkan SQL, secrets, atau deployment secara automatik. Migrasi juga boleh dimuat turun oleh admin di `/api/admin/migration`.

## Konfigurasi

Lihat `.env.example`; jangan commit `.env` sebenar.

- `SUPABASE_PUBLISHABLE_KEY` / `SUPABASE_SECRET_KEY` menyokong format baharu. Alias lama `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` juga diterima.
- `TOYYIBPAY_MODE=sandbox` menggunakan dev.toyyibpay.com; `production` menggunakan toyyibpay.com. Sandbox checkout hanya admin.
- DuitNow QR dimatikan secara default; hidupkan `TOYYIBPAY_DUITNOW_ENABLED=true` hanya selepas merchant mengaktifkannya.
- `TRADING_ECONOMICS_KEY` pilihan menukar sumber kalendar; BiQuote tidak memerlukan key dalam adapter ini.
- `DATA_DIR` untuk SQLite tempatan. Production menggunakan Supabase jika lengkap dikonfigurasi; kegagalan schema **tidak** jatuh balik secara senyap ke SQLite.
- `OPENAI_API_KEY` dan `OPENAI_MODEL` pilihan. Ada kos API mengikut penggunaan. Soalan + snapshot pasaran sahaja dihantar, bukan jurnal/identiti akaun.
- `LIVE_DATA_ENABLED=false` mematikan fetch untuk ujian. UI menunjukkan unavailable, bukan data palsu.
- Gunakan satu worker recorder untuk deployment kecil. Beberapa worker berkongsi deduplikasi snapshot dan settlement atomic di Supabase, tetapi memanggil sumber lebih kerap. Had request frontend adalah per-process, bukan distributed rate limiter.

## Pembangunan tempatan

Python 3.12:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Windows: gunakan `.venv\\Scripts\\python` atau skrip start sedia ada. Salin nilai yang diperlukan daripada `.env.example` ke `.env`. DEMO_MODE=false secara default. Untuk ujian tempatan sahaja, DEMO_MODE=true membenarkan demo@thysmy.local / demo12345 dan admin@thysmy.local / demo12345; semua bayaran dilumpuhkan. Akaun demo ditakrifkan oleh pelayan, bukan pendaftaran sebenar.

## Pengesahan

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests/test_workspace.py
node --check static/workspace.js
node --check static/features.js
node --check static/admin.js
node --check static/standalone.js
node --check static/auth.js
node --check static/register.js
```

23 ujian deterministik meliputi nombor/unit/revisi, bias per phase, makro tanpa data masa hadapan, kos, bar hilang, immutable snapshots, pemilikan jurnal, freshness/backoff, routes/assets, CSRF, malformed JSON, simulasi/alerts/journal/guide, jumlah bayaran, idempotence Python, status bayaran milik sendiri dan kegagalan schema.

Ujian ini menggunakan fixtures berlabel dan tidak menguji transaksi PostgreSQL sebenar, endpoint provider live, screenshot pelayar, penghantaran email atau bayaran sebenar. Fungsi SQL settlement perlu diuji di Supabase sandbox sebelum pelancaran.

## Metodologi dan keselamatan

- Snapshot pertama BEFORE dalam 15 minit sebelum news disimpan append-only; AFTER disimpan apabila sekurang-kurangnya separuh komponen boleh dinilai. Tiada backfill “ramalan” dari data yang sudah diketahui.
- Bias BEFORE menggunakan forecast-vs-previous, ditambah separuh skor konteks makro 14 hari (maksimum ±1). AFTER/simulasi menggunakan actual-vs-forecast serta revisi; tajuk GDELT tidak menentukan bias numerik.
- Baseline ialah close M1 tepat sebelum news; reaksi +1/+5/+15 menggunakan closed M1 pada sempadan waktu sebenar. Hasil selepas event ialah konteks, bukan ramalan.
- Ketepatan arah +15 menggunakan BEFORE betul/salah sahaja. Neutral/flat/hilang dikecualikan daripada pembahagi tetapi dipaparkan. Halaman memuatkan 200 snapshot terkini, bukan seluruh sejarah. Ini bukan win rate trading.
- Cookie sesi signed, HttpOnly, SameSite=Lax dan Secure untuk APP_BASE_URL HTTPS. Tiada secret fallback tetap. API mutasi memerlukan custom header dan semakan same-origin.
- Gate Pro dan owner/admin diperiksa di server. Jadual V4 RLS-enabled; akses direct anon/authenticated direvoke, service key hanya di server.
- Settlement memeriksa hash callback, bill/order dan jumlah transaksi gateway; RPC mengunci order/subscriber dan melanjutkan langganan sekali sahaja. URL return bukan bukti bayaran.
- Gambar hanya JPEG/PNG kecil; CSV dilindungi daripada formula injection; teks luar di-escape; CSP tidak membenarkan inline scripts.
- Jadual, harga dan berita yang gagal di-refresh menunjukkan stale/unavailable dengan waktu sumber. Cache mengekalkan timestamp kejayaan asal dan menghormati Retry-After.

Butiran pengguna di `/methodology`.

## Sumber primer adapter

- https://biquote.io/docs/
- https://docs.tradingeconomics.com/economic_calendar/snapshot/
- https://fred.stlouisfed.org/series/DGS10
- https://www.gdeltproject.org/
- https://toyyibpay.com/apireference/
- https://developers.openai.com/api/docs/guides/text/
